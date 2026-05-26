# CRC301 Golden Templates

This directory contains CRC301 template artifacts that are derived from reviewed
final DOCX reports. Raw reviewed reports are not stored here and must remain in
ignored local paths.

## Template Build Notes

`crc_301_msi_golden_template_v0.docx` is a pilot golden-template candidate:

1. Select a reviewed CRC301+MSI final DOCX from the local historical corpus.
2. Build a scrubbed seed with `scripts/build_golden_template_seed.py`.
3. Replace the case-specific Part 3 narrative block with `__PART3_MARKER__`
   using `scripts/insert_docx_block_marker.py`.
4. Apply `golden_template_v0_variables.yaml` with
   `scripts/variableize_golden_template.py`.
5. Commit only the resulting template and variable map, not the raw source DOCX
   or local manifests.

The pilot template must not become the default template until at least two
distinct CRC301 cases pass generation, QA, privacy checks, and layout review.

