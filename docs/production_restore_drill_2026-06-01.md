# Production Restore Drill - 2026-06-01

Target: `panel.mailuo-report.com.cn` on `iyun-server`.

## Result

- Status: PASS
- Drill time: 2026-06-01 09:32:55 CST
- Backup archive: `reportgen-web-backup-20260601_021701.tar.gz`
- Archive size: 1,372,830,748 bytes
- Source revision: `e799bfd3b35483932c83df4b25238c51ea43c1b8`
- Server report:
  `/media/desk16/iyun6208/apps/reportgen-web-runtime/logs/restore-drill-20260601_093255.json`

## Checks

- SHA-256 sidecar matched the archive.
- Full `tar -tzf` archive stream was readable.
- Required restore entries existed:
  - `meta/manifest.pre.json`
  - `db/reportgen_web.sqlite`
- SQLite backup copy extracted successfully.
- SQLite `PRAGMA integrity_check` returned `ok`.
- SQLite table count: 6.
- Audit log rows in extracted backup: 0.
- Temporary extracted metadata/DB directory was removed after the drill.

## Archive Entry Counts

These are entry counts from the archive listing, not retained filenames.

| Root | Entries |
| --- | ---: |
| `meta` | 6 |
| `db` | 1 |
| `uploads` | 424 |
| `reports` | 829 |
| `signatures` | 11 |
| `reference_reports` | 1 |

## Scope

This was the default non-destructive drill. It did not modify production
storage and did not duplicate all generated reports onto disk. Full extraction
is reserved for an isolated host or an explicit `RESTORE_DRILL_FULL=1` run with
confirmed free disk.
