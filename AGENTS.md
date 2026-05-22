# AGENTS.md

This file provides project memory for Codex when working in this repository.

## Project Memory

- Multi-panel architecture PRD: `docs/prd_multi_panel_template_architecture.md`
- Migration branch plan: `docs/panel_platform_migration_branch_plan.md`
- Panel package specification: `docs/panel_package_spec.md`
- M6-M9 refactor implementation PRD: `docs/prd_refactor_implementation_m6_m9.md`
- Release checklist: `docs/release_checklist.md`

## Refactor Direction

The current branch tree should continue as an incremental migration, not a full rewrite. Keep the existing CRC 358/301 report behavior protected by golden cases, QA reports, field provenance, reference diff, and panel package validation.

The next major milestone is M6: staged generation pipeline. Start from `docs/prd_refactor_implementation_m6_m9.md`, then create follow-up branches in this order:

```text
codex/panel-platform-m6-pipeline
  -> codex/panel-platform-m7-rule-engine
  -> codex/panel-platform-m8-template-processors
  -> codex/panel-platform-m9-web-production
```

Every milestone must keep the Web app deployable, keep `ReportGenerator.generate()` externally compatible unless explicitly migrated, and avoid patient-specific hardcoding.
