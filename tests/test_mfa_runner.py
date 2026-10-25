from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import wave

from karaoke_core.alignment import MFACommandSettings
from karaoke_core.mfa import (
    MFAInstallation,
    MFAProcess,
    adopt_textgrid,
    build_runtime_align_command,
    detect_mfa_installation,
    find_textgrid,
    prepare_mfa_workspace,
)


FAKE_MFA = r'''
import sys
args = sys.argv[1:]
if args == ["version"]:
    print("Montreal Forced Aligner 3.4.2")
    raise SystemExit(0)
if args == ["--help"]:
    print("Commands:\n  align\n  align_hf\n  align_one\n  align_one_hf\n  model\n  validate\n  version")
    raise SystemExit(0)
if args[:3] == ["model", "list", "acoustic"]:
    print("japanese_mfa")
    raise SystemExit(0)
print("unknown", args)
raise SystemExit(2)
'''


class MFADetectionTests(unittest.TestCase):
    def test_detects_version_and_hf_subcommand(self):
        with tempfile.TemporaryDirectory() as td:
            script = Path(td) / "fake_mfa.py"
            script.write_text(FAKE_MFA, encoding="utf-8")
            inst = detect_mfa_installation([sys.executable, str(script)])
            self.assertEqual(inst.version_tuple, (3, 4, 2))
            self.assertIn("align_hf", inst.commands)
            self.assertEqual(inst.alignment_subcommand("auto"), "align_hf")
            self.assertEqual(inst.alignment_subcommand("legacy"), "align")

    def test_future_mfa4_prefers_plain_align_for_hf_and_align_legacy_for_legacy(self):
        inst = MFAInstallation(("mfa",), "4.0.0", (4, 0, 0), frozenset({"align", "align_legacy"}))
        self.assertEqual(inst.alignment_subcommand("auto"), "align")
        self.assertEqual(inst.alignment_subcommand("hf"), "align")
        self.assertEqual(inst.alignment_subcommand("legacy"), "align_legacy")


class MFACommandRuntimeTests(unittest.TestCase):
    def _workspace(self, root: Path):
        from karaoke_core.mfa import MFAWorkspace
        corpus = root / "corpus"; corpus.mkdir()
        output = root / "output"; output.mkdir()
        return MFAWorkspace(root, corpus, output, corpus / "song.wav", corpus / "song.lab", "song")

    def test_hf_command_uses_detected_command(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ws = self._workspace(root)
            inst = MFAInstallation(("conda", "run", "-n", "aligner", "mfa"), "3.4.1", (3, 4, 1), frozenset({"align", "align_hf"}))
            cmd = build_runtime_align_command(ws, MFACommandSettings(mode="auto", model="japanese_mfa", use_g2p=True, num_jobs=2), inst)
            self.assertEqual(cmd[:6], ["conda", "run", "-n", "aligner", "mfa", "align_hf"])
            self.assertIn("japanese_mfa", cmd)
            self.assertIn("--use_g2p", cmd)
            self.assertIn("long_textgrid", cmd)

    def test_legacy_command_keeps_dictionary_explicit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ws = self._workspace(root)
            inst = MFAInstallation(("mfa",), "3.3.9", (3, 3, 9), frozenset({"align"}))
            cmd = build_runtime_align_command(ws, MFACommandSettings(mode="legacy", model="japanese_mfa", dictionary="japanese_mfa"), inst)
            self.assertEqual(cmd[:3], ["mfa", "align", str(ws.corpus_directory)])
            self.assertEqual(cmd[3:6], ["japanese_mfa", "japanese_mfa", str(ws.output_directory)])
            self.assertEqual(cmd[cmd.index("--beam") + 1], "10")
            self.assertEqual(cmd[cmd.index("--retry_beam") + 1], "40")

    def test_custom_beam_values_are_forwarded(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ws = self._workspace(root)
            inst = MFAInstallation(("mfa",), "3.3.9", (3, 3, 9), frozenset({"align"}))
            settings = MFACommandSettings(
                mode="legacy",
                model="portuguese_mfa",
                dictionary="portuguese_mfa",
                beam=100,
                retry_beam=400,
            )
            cmd = build_runtime_align_command(ws, settings, inst)
            self.assertEqual(cmd[cmd.index("--beam") + 1], "100")
            self.assertEqual(cmd[cmd.index("--retry_beam") + 1], "400")


class MFACorpusTests(unittest.TestCase):
    def test_prepare_workspace_creates_matching_wav_and_lab(self):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.skipTest("ffmpeg unavailable")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "song.wav"
            with wave.open(str(source), "wb") as w:
                w.setnchannels(2)
                w.setsampwidth(2)
                w.setframerate(8000)
                w.writeframes(b"\0\0\0\0" * 800)
            transcript = root / "lyrics.txt"
            transcript.write_text("hello world\n", encoding="utf-8")
            ws = prepare_mfa_workspace(source, transcript, root / "mfa", ffmpeg=ffmpeg)
            self.assertTrue(ws.audio_path.exists())
            self.assertTrue(ws.transcript_path.exists())
            self.assertEqual(ws.audio_path.stem, ws.transcript_path.stem)
            self.assertEqual(ws.transcript_path.read_text(encoding="utf-8"), "hello world\n")
            with wave.open(str(ws.audio_path), "rb") as w:
                self.assertEqual(w.getnchannels(), 1)
                self.assertEqual(w.getframerate(), 16000)

    def test_find_and_adopt_textgrid_with_backup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output = root / "output" / "speaker"
            output.mkdir(parents=True)
            source = output / "song.TextGrid"
            source.write_text("new", encoding="utf-8")
            self.assertEqual(find_textgrid(root / "output", "song"), source)
            final = root / "alignment" / "song.TextGrid"
            final.parent.mkdir()
            final.write_text("old", encoding="utf-8")
            adopt_textgrid(source, final)
            self.assertEqual(final.read_text(encoding="utf-8"), "new")
            self.assertEqual(final.with_suffix(".TextGrid.bak").read_text(encoding="utf-8"), "old")


class MFAProcessTests(unittest.TestCase):
    def test_process_streams_stdout(self):
        lines = []
        proc = MFAProcess([sys.executable, "-c", "print('one'); print('two')"], on_line=lines.append)
        self.assertEqual(proc.run(), 0)
        self.assertEqual(lines, ["one", "two"])


class MFAEndToEndTests(unittest.TestCase):
    def test_end_to_end_fake_alignment_process(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake = root / "aligner.py"
            fake.write_text(
                "import pathlib, sys\n"
                "args=sys.argv[1:]\n"
                "if args==['version']:\n    print('3.4.2'); raise SystemExit(0)\n"
                "if args==['--help']:\n    print('Commands: align align_hf model version'); raise SystemExit(0)\n"
                "if args and args[0]=='align_hf':\n"
                "    out=pathlib.Path(args[3]); out.mkdir(parents=True, exist_ok=True)\n"
                "    corpus=pathlib.Path(args[1]); stem=next(corpus.glob('*.wav')).stem\n"
                "    (out/(stem+'.TextGrid')).write_text('fake-grid', encoding='utf-8')\n"
                "    print('alignment complete'); raise SystemExit(0)\n"
                "raise SystemExit(3)\n",
                encoding="utf-8",
            )
            from karaoke_core.mfa import MFAWorkspace
            corpus = root / "corpus"
            corpus.mkdir()
            (corpus / "song.wav").write_bytes(b"RIFF")
            (corpus / "song.lab").write_text("hello", encoding="utf-8")
            output = root / "output"
            output.mkdir()
            ws = MFAWorkspace(root, corpus, output, corpus / "song.wav", corpus / "song.lab", "song")
            inst = detect_mfa_installation([sys.executable, str(fake)])
            cmd = build_runtime_align_command(ws, MFACommandSettings(mode="auto", model="demo"), inst)
            lines = []
            process = MFAProcess(cmd, on_line=lines.append)
            self.assertEqual(process.run(), 0)
            result = find_textgrid(output, "song")
            self.assertIsNotNone(result)
            self.assertIn("alignment complete", lines)


if __name__ == "__main__":
    unittest.main()
