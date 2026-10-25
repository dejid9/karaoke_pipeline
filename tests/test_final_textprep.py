from __future__ import annotations

from pathlib import Path
import json
import shutil
import sys
import tempfile
import unittest
import wave

from karaoke_core.mfa import build_conda_run_prefix, prepare_mfa_workspace
from karaoke_core.textprep import (
    TextPreprocessSettings,
    normalize_text,
    prepare_text_local,
    probe_python_packages,
    strip_punctuation_tokens,
    tokenize_japanese_sudachi,
)
from karaoke_core.doctor import HealthCheck, HealthReport


FAKE_CONDA = r'''
import json, subprocess, sys
args=sys.argv[1:]
if args and args[0]=='run':
    i=1
    while i < len(args):
        if args[i] in {'--no-capture-output','--live-stream'}: i+=1; continue
        if args[i] in {'-n','--name'}: i+=2; continue
        break
    tail=args[i:]
    # Package probe script: return deterministic package availability.
    if tail[:2] == ['python','-c'] and 'find_spec' in tail[2]:
        names=tail[3:]
        print(json.dumps({n:(n != 'missing_pkg') for n in names}))
        raise SystemExit(0)
    # Sudachi inline script: emulate tokenized JSON without requiring Sudachi.
    if tail[:2] == ['python','-c'] and 'sudachipy' in tail[2]:
        _=sys.stdin.read()
        print(json.dumps(['私','は','猫','です','。'], ensure_ascii=False))
        raise SystemExit(0)
    result=subprocess.run(tail)
    raise SystemExit(result.returncode)
raise SystemExit(2)
'''


class TextPreparationTests(unittest.TestCase):
    def test_normalize_unicode_and_whitespace(self):
        self.assertEqual(normalize_text('  Ａ\u3000Ｂ\n C  '), 'A B C')

    def test_local_preprocess_and_punctuation(self):
        settings=TextPreprocessSettings(mode='normalize', strip_punctuation=True)
        report=prepare_text_local('Hello ,   world !', settings)
        self.assertEqual(report.text, 'Hello world')
        self.assertEqual(report.token_count, 2)
        self.assertEqual(strip_punctuation_tokens('a 。 b !!!'), 'a b')

    def test_conda_prefix_is_program_agnostic(self):
        self.assertEqual(build_conda_run_prefix('conda','aligner'), ('conda','run','-n','aligner'))

    def test_package_probe_through_fake_conda(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); fake=root/'conda.py'; fake.write_text(FAKE_CONDA, encoding='utf-8')
            prefix=(sys.executable, str(fake), 'run', '-n', 'aligner')
            result=probe_python_packages(prefix, ('sudachipy','missing_pkg'))
            self.assertTrue(result['sudachipy'])
            self.assertFalse(result['missing_pkg'])

    def test_sudachi_tokenizer_uses_selected_conda_python(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); fake=root/'conda.py'; fake.write_text(FAKE_CONDA, encoding='utf-8')
            prefix=(sys.executable, str(fake), 'run', '-n', 'aligner')
            report=tokenize_japanese_sudachi('私は猫です。', prefix, split_mode='C', strip_punctuation=True)
            self.assertEqual(report.text, '私 は 猫 です')
            self.assertEqual(report.token_count, 4)

    def test_prepare_workspace_can_use_prepared_text_without_touching_source(self):
        ffmpeg=shutil.which('ffmpeg')
        if not ffmpeg:
            self.skipTest('ffmpeg unavailable')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            source=root/'song.wav'
            with wave.open(str(source),'wb') as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b'\0\0'*1600)
            transcript=root/'lyrics.txt'; transcript.write_text('ORIGINAL', encoding='utf-8')
            ws=prepare_mfa_workspace(source, transcript, root/'mfa', ffmpeg=ffmpeg, transcript_text='PREPARED TEXT')
            self.assertEqual(ws.transcript_path.read_text(encoding='utf-8'), 'PREPARED TEXT\n')
            self.assertEqual(transcript.read_text(encoding='utf-8'), 'ORIGINAL')


class HealthReportTests(unittest.TestCase):
    def test_health_report_format_and_warning_semantics(self):
        report=HealthReport((HealthCheck('A', True, 'ok'), HealthCheck('B', False, 'optional', warning=True)))
        self.assertTrue(report.ok)
        text=report.format_text()
        self.assertIn('[OK] A', text)
        self.assertIn('[WARN] B', text)


if __name__ == '__main__':
    unittest.main()
