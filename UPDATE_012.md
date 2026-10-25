# Update 012 — 7C-1 Conda-aware MFA preflight

Apply this archive over a project that already has Updates 001–011.

## Added

- Conda is now the primary MFA runtime rather than a manually typed launcher.
- Separate project settings for Conda executable, environment name, whether to
  use Conda, and the MFA executable inside the environment.
- Migration of old `conda run -n <env> mfa` values saved by Update 011.
- `conda env list --json` discovery and an environment picker in Alignment.
- All MFA probes/runs/model actions use the selected environment.
- `mfa validate` preflight with live output and optional `--ignore_acoustics`.
- `mfa find_oovs` with collection/preview of generated OOV files.
- Model manager: list/download/inspect for acoustic, dictionary, g2p and
  tokenizer models, including forced re-download.
- Validation, OOV and model processes are cancellable through the same process
  tree cancellation used by alignment.

## Important MFA behavior

MFA 3.x `validate` and `find_oovs` require an explicit pronunciation dictionary.
Even if alignment uses an HF model, this application does not guess a dictionary
from the HF model ID. Fill the Dictionary field before Validate/OOV.

## Tests

- 66/66 unit/integration tests pass in the development environment.
- GUI smoke test verifies the generated launcher:
  `conda run --no-capture-output -n aligner mfa`.
- Fake-Conda + fake-MFA end-to-end tests cover environment discovery, MFA
  detection through Conda, validate output and OOV artifact reading.
