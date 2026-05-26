# CRC35+MSI Template Workspace

This directory tracks the CRC35+MSI template-authoring recipe only.

Rules:

- Do not commit raw reviewed reports, local manifests, or generated seed files.
- The local seed is built under `tmp/golden_template_seed/` with
  `scripts/build_crc35_msi_seed.py`.
- `golden_template_v0_variables.yaml` declares the first reusable structural
  variable map for the CRC35 reviewed-report layout.
- A CRC35 DOCX template should not be committed or promoted until the tentative
  dose-safety table loop is checked against a second CRC35 Excel and at least
  two rendered reports pass privacy, structure, and layout checks.
