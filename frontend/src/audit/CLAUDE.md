# frontend audit/

Backend: `modules/audit`.

- `api.ts` — `AuditAction`/`AuditEvent`/`AuditEventPage` types and `listAuditEvents(params)`
  (`GET /admin/audit-events`; `action`/`entity_type`/`actor_id`/`occurred_from`/`occurred_to`, all
  optional, plus `limit`/`offset`).
- `hooks.ts` — `auditKeys` + `useAuditEvents`, a plain query (no mutations — this module only ever
  reads).
- `entity_type` is a plain string on the backend (see `audit/CLAUDE.md` there for why), so
  `pages/admin/AdminAuditPage.tsx` hardcodes its own `ENTITY_TYPE_LABELS`/`ACTION_LABELS` maps
  rather than deriving them from the schema; keep both in sync with
  `time_reporting.modules.audit.contracts.AuditAction` and the `entity_type` strings each
  instrumented module passes to `RecordAuditEvent`.
