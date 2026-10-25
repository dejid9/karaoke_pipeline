# Legacy scripts after the final update

The original archive contained several independent generations of scripts with incompatible assumptions (`\\k` vs `\\kf` vs `\\K`, flattened ASS, regex colour detection, absolute paths, shared `work/`). They are intentionally not deleted by an update archive.

Canonical replacements are:

- ASS parsing/editing: `karaoke_core.ass` + `karaoke_core.editor`;
- SPS/bursts/graph: `karaoke_core.sps` and the SPS GUI;
- Audacity labels: `karaoke_core.audacity` (legacy compatibility only);
- TextGrid → ASS, автоязык, слоги и точное восстановление TXT:
  `karaoke_core.alignment`, `karaoke_core.language`, `karaoke_core.syllables`;
- MFA/Conda: `karaoke_core.mfa`;
- Japanese/Unicode transcript preprocessing: `karaoke_core.textprep`;
- render/layout: `karaoke_core.render`;
- environment verification: `python scripts/doctor.py <project>`.

The maintained wrappers `auto_language.py`, `textgrid_to_ass.py`,
`hyphen_lang_as_arg.py`, `fix_subs.py`, and `fix_reg_punct_int.py` resolve defaults
relative to the project root and delegate to the same core as the GUI. Other
legacy rewrite scripts should not be run on an ASS that already contains manual
burst colours or handcrafted override tags unless the old behaviour is intended.
