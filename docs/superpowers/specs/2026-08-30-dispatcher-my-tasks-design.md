# Dispatcher My Tasks Design

## Goal

Turn the dispatcher `/my-tasks` placeholder into a real, passwordless-demo work queue backed by MySQL, and reuse the same projection on the dispatcher workspace without exposing another employee's tasks.

## Root cause

- The router renders `NotExposedPage` for `/my-tasks`.
- `DispatcherWorkspacePage` passes an empty array to `TaskQueue`.
- No backend endpoint exposes employee-owned tasks.
- `DispatchTask` has no assignee identity. `Order.driver_id` identifies a driver and must not be treated as a dispatcher employee id.

## Assignment model

Add nullable, indexed `DispatchTask.assignee_subject_id: str | None` with a maximum length of 128 characters. The value is the authenticated principal subject id, such as `CF-DEMO-001`. It remains nullable so existing production records migrate safely and unassigned tasks are never guessed.

The development seed idempotently assigns all ten local `DEMO-TASK-*` records to `CF-DEMO-001` without resetting their current workflow status or overwriting review decisions. No enterprise data is introduced.

## Read contract

Add `GET /api/v1/my/tasks`, protected by `dispatch:read`. The server always supplies `principal.subject_id`; no employee id query parameter is accepted or trusted.

Query parameters:

- `limit`: 1-100, default 20.
- `cursor`: numeric row cursor.
- `state`: optional `READY`, `WAITING`, `ACTIVE`, or `ENDED` queue classification.

Response fields:

- `items`: task id, order number, anomaly risk and description, vehicle, original and suggested route, raw task status, created and updated times.
- `summary`: total, ready, waiting, active, and ended counts across all tasks owned by the current principal.
- `total`, `next_cursor`, and provenance.

Status groups:

- `READY`: `APPROVED`, `ASSIGNED`.
- `WAITING`: `PENDING`, `QUEUED`, `REVIEW_REQUIRED`.
- `ACTIVE`: `RUNNING`, `PROCESSING`, `IN_PROGRESS`.
- `ENDED`: `COMPLETED`, `REJECTED`, `FAILED`, `CANCELLED`.
- Unknown statuses remain visible under all-tasks but are not misclassified.

The query uses the latest persisted dispatch per task and joins order/anomaly read-only data. MySQL remains the source of truth.

## Frontend behavior

`/my-tasks` shows four summary cards, queue-state filters, a real task table, provenance, pagination, Chinese loading/empty/forbidden/unavailable states, and a link to `/dispatch/:taskId`.

The dispatcher workspace consumes the same endpoint with a five-row limit. Its overview uses real summary counts and its “我的待办” section shows the returned tasks. Other still-unexposed sections remain explicitly unexposed.

No static task arrays, fabricated KPIs, or client-side employee filters are allowed.

## Security and failure behavior

- Authentication and `dispatch:read` are mandatory.
- Ownership filtering occurs in the SQL repository using the server principal subject.
- Operators and auditors remain forbidden.
- Database connectivity failures return the existing workspace-read 503 contract.
- Invalid cursors return the existing 422 cursor contract.

## Verification

- TDD for migration/model, idempotent seed backfill, repository ownership isolation, status grouping, pagination, endpoint permissions, client, hook, page, router, and dispatcher workspace reuse.
- Full Ruff, backend Pytest, frontend lint/test/build.
- Docker migration and one-click startup.
- Real passwordless `CF-DEMO-001` API probe verifies owned demo tasks; another identity receives no leaked rows.
- Playwright verifies `/my-tasks`, filters, detail navigation, console health, and responsive layout.

