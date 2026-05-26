# CRC35+MSI Template Workspace

This directory tracks the CRC35+MSI template-authoring recipe only.

Rules:

- Do not commit raw reviewed reports, local manifests, or generated seed files.
- The local seed is built under `tmp/golden_template_seed/` with
  `scripts/build_crc35_msi_seed.py`.
- `golden_template_v0_variables.yaml` declares the first reusable structural
  variable map for the CRC35 reviewed-report layout.
- `crc_35_msi_golden_template_v0.docx` is a pilot template. Before committing,
  the local candidate was scrubbed with `scripts/scrub_docx_signature_images.py`
  to blank reviewed-report signature images and normalize Office metadata.
- Promotion beyond pilot still requires fuller layout review and a golden QA
  gate using real CRC35 fixtures.
