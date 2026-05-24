# CRC358+MSI Golden Template Workspace

This directory is reserved for CRC358+MSI golden-template pilot files.

Rules:

- Do not commit raw customer reports or patient files.
- Any `.docx` committed here must be scrubbed of patient names, sample IDs, report numbers, comments, and tracked-change metadata.
- `crc_358_msi_golden_template_v0.docx` is the current scrubbed golden-template
  pilot generated from the reviewed CRC358+MSI report. It is not the default
  production template until the acceptance gates pass.
- `golden_template_v0_variables.yaml` declares the first-pass structural
  variables for a local scrubbed seed. It contains variable names and table/
  paragraph positions only, not patient values. M4.2 also declares docxtpl
  row loops for `targeted_drug_tips`, `variants_2_1`, and `chemotherapy`.
  M4.3 extends the same mechanism to `nccn_results`,
  `immune_positive_results`, `immune_negative_results`, and
  `immune_hyperprogression_results`.
- Production promotion requires the acceptance gates in `docs/prd_golden_template_migration.md`.
