from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karaoke_core.alignment import MFACommandSettings
from karaoke_core.mfa import (
    MFAInstalledModelCatalog,
    MFAInstallation,
    MFAProcess,
    MFAWorkspace,
    build_conda_mfa_prefix,
    build_find_oovs_command,
    build_model_command,
    build_validate_command,
    detect_mfa_installation,
    find_oov_artifacts,
    list_conda_environments,
    list_installed_mfa_models,
    matching_model_variant,
    model_language_key,
    parse_mfa_model_list_output,
    parse_conda_mfa_launcher,
    read_oov_summary,
)
from karaoke_core.project import ProjectConfig, load_project, save_project


FAKE_CONDA = r'''
import json, pathlib, subprocess, sys
args=sys.argv[1:]
if args == ['env','list','--json']:
    root=pathlib.Path(__file__).parent
    print(json.dumps({'envs':[str(root/'base'), str(root/'aligner')], 'default_prefix':str(root/'base')}))
    raise SystemExit(0)
if args and args[0]=='run':
    i=1
    while i < len(args):
        if args[i] in {'--no-capture-output','--live-stream'}:
            i += 1; continue
        if args[i] in {'-n','--name'}:
            i += 2; continue
        break
    result=subprocess.run(args[i:])
    raise SystemExit(result.returncode)
print('bad conda args', args)
raise SystemExit(2)
'''

FAKE_MFA = r'''
import pathlib, sys
args=sys.argv[1:]
if args in (['version'], ['--version']):
    print('Montreal Forced Aligner 3.4.2'); raise SystemExit(0)
if args == ['--help']:
    print('Commands: align align_hf model validate find_oovs version'); raise SystemExit(0)
if args and args[0]=='validate':
    out=pathlib.Path(args[args.index('--output_directory')+1]); out.mkdir(parents=True, exist_ok=True)
    (out/'oovs_found.txt').write_text('missing_word 2\n', encoding='utf-8')
    print('Validation complete'); raise SystemExit(0)
if args and args[0]=='find_oovs':
    out=pathlib.Path(args[3]); out.mkdir(parents=True, exist_ok=True)
    (out/'oovs_found.txt').write_text('other_word 1\n', encoding='utf-8')
    print('OOV complete'); raise SystemExit(0)
if args[:3]==['model','list','acoustic']:
    print("['english_mfa', 'english_us_arpa', 'japanese_mfa', 'portuguese_mfa']"); raise SystemExit(0)
if args[:3]==['model','list','dictionary']:
    print("['english_mfa', 'english_us_arpa', 'english_us_mfa', 'japanese_mfa', 'portuguese_mfa']"); raise SystemExit(0)
if args[:3]==['model','inspect','acoustic']:
    print('model metadata'); raise SystemExit(0)
if args[:3]==['model','download','acoustic']:
    print('downloaded'); raise SystemExit(0)
print('bad mfa args', args)
raise SystemExit(3)
'''


class CondaLauncherTests(unittest.TestCase):
    def _scripts(self, root: Path):
        conda = root / 'fake_conda.py'
        mfa = root / 'fake_mfa.py'
        conda.write_text(FAKE_CONDA, encoding='utf-8')
        mfa.write_text(FAKE_MFA, encoding='utf-8')
        return conda, mfa

    def test_build_prefix_and_migrate_old_launcher(self):
        prefix = build_conda_mfa_prefix('conda', 'aligner', 'mfa')
        self.assertEqual(prefix, ('conda', 'run', '--no-capture-output', '-n', 'aligner', 'mfa'))
        self.assertEqual(parse_conda_mfa_launcher('conda run -n aligner mfa'), ('conda', 'aligner', 'mfa'))

    def test_lists_conda_environments(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); conda, _ = self._scripts(root)
            envs = list_conda_environments([sys.executable, str(conda)])
            self.assertEqual([e.name for e in envs], ['base', 'aligner'])

    def test_detects_mfa_through_conda_run(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); conda, mfa = self._scripts(root)
            prefix = build_conda_mfa_prefix([sys.executable, str(conda)], 'aligner', [sys.executable, str(mfa)])
            inst = detect_mfa_installation(prefix)
            self.assertEqual(inst.version_tuple, (3, 4, 2))
            self.assertIn('find_oovs', inst.commands)
            self.assertIn('validate', inst.commands)


class PreflightCommandTests(unittest.TestCase):
    def _workspace(self, root: Path):
        corpus=root/'corpus'; corpus.mkdir()
        output=root/'output'; output.mkdir()
        return MFAWorkspace(root, corpus, output, corpus/'song.wav', corpus/'song.lab', 'song')

    def test_validate_and_oov_commands_are_explicit(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); ws=self._workspace(root)
            inst=MFAInstallation(('mfa',), '3.4.2', (3,4,2), frozenset({'validate','find_oovs','model','align_hf'}))
            settings=MFACommandSettings(mode='hf', model='japanese_mfa', dictionary='japanese_mfa', num_jobs=2)
            validate=build_validate_command(ws, settings, inst, root/'validation', ignore_acoustics=True)
            self.assertEqual(validate[:4], ['mfa','validate',str(ws.corpus_directory),'japanese_mfa'])
            self.assertIn('--ignore_acoustics', validate)
            self.assertNotIn('--acoustic_model_path', validate)
            oov=build_find_oovs_command(ws, settings, inst, root/'oov')
            self.assertEqual(oov[:4], ['mfa','find_oovs',str(ws.corpus_directory),'japanese_mfa'])

            legacy_inst=MFAInstallation(('mfa',), '3.3.9', (3,3,9), frozenset({'validate','align'}))
            legacy_settings=MFACommandSettings(
                mode='legacy', model='portuguese_mfa', dictionary='portuguese_mfa',
                beam=100, retry_beam=400,
            )
            validate=build_validate_command(ws, legacy_settings, legacy_inst, root/'validation_beam')
            self.assertEqual(validate[validate.index('--beam') + 1], '100')
            self.assertEqual(validate[validate.index('--retry_beam') + 1], '400')

    def test_model_commands(self):
        inst=MFAInstallation(('mfa',), '3.4.2', (3,4,2), frozenset({'model'}))
        self.assertEqual(build_model_command(inst,'list','acoustic'), ['mfa','model','list','acoustic'])
        self.assertEqual(build_model_command(('mfa',),'list','dictionary'), ['mfa','model','list','dictionary'])
        self.assertEqual(build_model_command(inst,'inspect','acoustic','japanese_mfa'), ['mfa','model','inspect','acoustic','japanese_mfa'])
        self.assertEqual(build_model_command(inst,'download','g2p','japanese_mfa',force=True)[-1], '--force')

    def test_model_catalog_parser_and_variant_matching(self):
        rich = """[
│   'english_mfa',
│   'english_us_arpa',
│   'hungarian_cv',
│   'portuguese_mfa'
]"""
        names = parse_mfa_model_list_output(rich)
        self.assertEqual(
            names,
            ('english_mfa', 'english_us_arpa', 'hungarian_cv', 'portuguese_mfa'),
        )
        catalog = MFAInstalledModelCatalog(
            acoustic=names,
            dictionary=('english_mfa', 'english_us_arpa', 'english_us_mfa', 'portuguese_mfa'),
        )
        self.assertEqual(catalog.language_keys(), ('english', 'hungarian', 'portuguese'))
        self.assertEqual(
            catalog.for_language('acoustic', 'english'),
            ('english_mfa', 'english_us_arpa'),
        )
        self.assertEqual(model_language_key('english_us_arpa'), 'english')
        self.assertEqual(
            matching_model_variant(catalog.dictionary, 'english_us_arpa', preferred='english_us_mfa'),
            'english_us_arpa',
        )

    def test_reads_installed_acoustic_and_dictionary_catalog(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); conda,mfa=self._scripts(root)
            prefix=build_conda_mfa_prefix([sys.executable,str(conda)], 'aligner', [sys.executable,str(mfa)])
            inst=detect_mfa_installation(prefix)
            catalog=list_installed_mfa_models(inst)
            self.assertIn('portuguese_mfa', catalog.acoustic)
            self.assertIn('portuguese_mfa', catalog.dictionary)
            self.assertIn('english_us_arpa', catalog.for_language('dictionary', 'english'))

    def _scripts(self, root: Path):
        conda = root / 'fake_conda.py'; mfa=root/'fake_mfa.py'
        conda.write_text(FAKE_CONDA, encoding='utf-8'); mfa.write_text(FAKE_MFA, encoding='utf-8')
        return conda,mfa

    def test_preflight_process_and_oov_summary(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); conda,mfa=self._scripts(root)
            ws=self._workspace(root)
            prefix=build_conda_mfa_prefix([sys.executable,str(conda)], 'aligner', [sys.executable,str(mfa)])
            inst=detect_mfa_installation(prefix)
            settings=MFACommandSettings(mode='hf', model='japanese_mfa', dictionary='japanese_mfa')
            cmd=build_validate_command(ws, settings, inst, root/'validation')
            lines=[]; proc=MFAProcess(cmd,on_line=lines.append)
            self.assertEqual(proc.run(),0)
            self.assertIn('Validation complete',lines)
            self.assertTrue(find_oov_artifacts(root/'validation'))
            self.assertIn('missing_word 2',read_oov_summary(root/'validation'))


class ProjectCondaSettingsTests(unittest.TestCase):
    def test_roundtrip_conda_settings(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); root.mkdir(exist_ok=True)
            cfg=ProjectConfig(name='x', conda_executable='C:/Miniforge/conda.exe', mfa_conda_env='aligner', mfa_use_conda=True, mfa='mfa')
            save_project(root,cfg)
            loaded=load_project(root)
            self.assertEqual(loaded.mfa_conda_env,'aligner')
            self.assertTrue(loaded.mfa_use_conda)
            self.assertEqual(loaded.conda_executable,'C:/Miniforge/conda.exe')


if __name__ == '__main__':
    unittest.main()
