# Synqd local meeting API

Python Azure Functions v2 programming model. The existing anonymous health endpoint is unchanged. Meetings and follow-ups use the process-local repository; the frontend calls this local API. No external integration is connected.

## Run locally

Use Python 3.13, matching the existing `azure-functions==2.3.0` dependency, and Azure Functions Core Tools v4. The original requirements and `local.settings.json` are unchanged.

From `backend/`:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
AzureWebJobsStorage="" AzureWebJobsSecretStorageType=files FUNCTIONS_WORKER_PROCESS_COUNT=1 FUNCTIONS_CORE_TOOLS_TELEMETRY_OPTOUT=1 func start
```

The process-only empty storage setting allows this HTTP-only app to run without Azure Storage or Azurite. It does not edit `local.settings.json`. No cloud resources are created or changed.

In another terminal, from `backend/` with the same environment activated:

```bash
python -m unittest discover -s tests -v
python tests/verify_http.py
```

The smoke test connects only to loopback, creates its own temporary meetings, and cleans them up. Optional: `python tests/verify_http.py --port 7072` when the host uses a different local port.

## Endpoints

| Method | Path | Success response |
| --- | --- | --- |
| GET | `/api/health` | 200, `{"status":"working"}` |
| GET | `/api/meetings` | 200, JSON array of meeting records |
| POST | `/api/meetings` | 201, created meeting; `Location` header |
| GET | `/api/meetings/{id}` | 200, meeting record |
| PATCH | `/api/meetings/{id}` | 200, updated meeting record |
| DELETE | `/api/meetings/{id}` | 200, `{"id":"...","deleted":true}` |
| POST | `/api/meetings/{meeting_id}/follow-ups/{follow_up_id}/dismiss` | 200, updated source meeting |
| POST | `/api/meetings/{meeting_id}/follow-ups/{follow_up_id}/approve` | 200, `{ "sourceMeeting": {...}, "meeting": {...} }` |

All responses from these handlers are JSON. Invalid payloads return 400, missing meetings return 404, and duplicate supplied IDs return 409. Errors use `{"error":{"code":"...","message":"..."}}`.

## Meeting contract

Required POST fields: `title`, `date`, `startTime`, `endTime`, `participants`.

- `date` is a valid `YYYY-MM-DD` local date.
- Times use `HH:mm`. End time must be later on the same date, matching the frontend form.
- Participants are objects with non-empty string `id`, `name`, and `color` values. At least one participant is required, with unique IDs and names. The backend has no eight-participant limit.
- `id` is generated as a UUID when omitted. Supplied IDs accept letters, numbers, underscores and hyphens; IDs cannot be patched.
- `project`, `team`, `agenda`, and `preview` default to empty strings.
- `status` defaults to `scheduled`; allowed values are `scheduled`, `in_progress`, `ended`, and `cancelled`.
- `aiStatus` defaults to `unprocessed`; allowed values are `unprocessed`, `processing`, `processed`, and `failed`.
- Optional detail fields are `agendaEntries`, `summary`, `transcript`, `decisions`, `actionItems`, `projectOverview`, `assistant`, and `followUps`. Their supplied shapes are validated against the current frontend types. No generated AI results are fabricated.
- Action-item status is independent of Jira metadata and accepts only `todo`, `in_progress`, and `done`.

PATCH permits only known fields other than `id`. It validates the merged record and updates only supplied fields. Arrays and nested objects are replaced as whole fields; omitted fields remain unchanged. An empty patch, unknown field, null for a string field, or invalid merged time range is rejected without writing anything. Related detail fields are not automatically regenerated when core fields change.

For `followUps`, PATCH must retain existing follow-up IDs, statuses, and `scheduledMeetingId` links. This prevents a stale demo append from undoing a dismissal/approval or enabling a second approval; stale updates return 409. Resolve statuses through the follow-up routes.

## Follow-up flow

Each source meeting owns its optional `followUps` array. A follow-up has the editable meeting fields, `id`, `sourceMeetingId` (matching its parent), and `status`: `suggested`, `approved`, or `dismissed`. An approved follow-up also has `scheduledMeetingId`.

- Dismiss accepts no body, checks that the follow-up is suggested, saves `dismissed`, and returns the updated source meeting.
- Approve accepts a JSON object with any edited `title`, `date`, `startTime`, `endTime`, `participants`, `agenda`, `project`, and `team`. `{}` uses the current suggestion unchanged. Other fields are rejected.
- `MeetingService` validates the edited values and both records before writing, creates a `scheduled`/`unprocessed` meeting, and records `approved` plus the created ID on the source follow-up. It returns both records.
- A missing source or follow-up returns 404; approving or dismissing a resolved follow-up returns 409. Repeated/concurrent approval creates only one meeting.
- Approval uses the existing repository `update` and `create` methods. The in-memory adapter's reentrant lock holds across both writes. A future shared-storage adapter must preserve that two-record atomicity and the suggested-state check; a simple independent pair of Cosmos writes would not be sufficient.

The frontend calendar subscribes to the meeting snapshot and flattens each meeting's `followUps`. It starts with no mock proposals and hydrates the backend statuses on `GET /api/meetings`. Successful dismiss/approve responses update that same snapshot; failed responses do not change it. A stale list response started before a mutation is ignored.

The existing review form keeps unsaved edits in memory and sends them with approval. These draft edits may be lost on reload. The canned proposal generator still generates locally, but attaches each new suggestion to a real source meeting through existing GET/PATCH operations before displaying it. Calendar project colors remain frontend mocks.

Browser reloads preserve suggested, dismissed, and approved states, plus scheduled meetings, while the same backend worker runs. Restarting the backend reloads fixtures. There is no localStorage, Cosmos connection, new infrastructure, or new draft-edit endpoint.

Example POST body:

```json
{
  "title": "Design review",
  "date": "2026-10-12",
  "startTime": "14:00",
  "endTime": "14:45",
  "participants": [
    {"id": "maya", "name": "Maya Chen", "color": "#c96f4a"}
  ],
  "agenda": "Review checkout changes",
  "project": "Atlas Launch",
  "team": "Design"
}
```

## Repository structure

- `function_app.py`: route registration and dependency composition; retains health.
- `api_http.py`: JSON responses, request parsing, and domain-error-to-HTTP mapping.
- `meeting_model.py`: field allowlists and frontend-compatible validation.
- `meeting_errors.py`: validation, missing-record, duplicate-ID, and follow-up conflict errors.
- `meeting_service.py`: create defaults/IDs, validated partial updates, and follow-up resolution.
- `meeting_repository.py`: `MeetingRepository` protocol and `InMemoryMeetingRepository` adapter. Returns isolated copies and serializes mutations within the local worker.
- `seed_data.py`: loads validated fixtures once during startup.
- `fixtures/meetings.json`: four demo meetings, including one rich detail; `m1` owns `f1`/`f3` and `m3` owns `f2`. This folder is not excluded by the existing Git ignore rules.
- `tests/test_meetings.py`: 21 unit tests covering validation, service/storage behavior, concurrency, and HTTP boundaries.
- `tests/test_follow_ups.py`: 14 focused service/HTTP tests covering state, edited approval, failures, validation, and concurrent resolution.
- `tests/verify_http.py`: 11 live HTTP checks covering the requested CRUD sequence and errors.

The repository survives successive requests within the same worker. Restarting the host resets it to the seed data. Separate workers do not share this memory, so run a single worker for this local step. No persistence or cloud connection is implied.

A future Cosmos adapter can implement `MeetingRepository` and be injected at the composition point. Routes do not need to be rewritten. Its update operation should preserve atomic read/validate/write behavior using appropriate concurrency controls.

## Verification performed

- Python 3.13.15 with the existing pinned requirements.
- Azure Functions Core Tools 4.15.2 successfully started the Python worker and registered all eight HTTP handlers.
- 35 backend unit tests passed.
- 11 live loopback HTTP checks passed, including the original health response, create/get/patch/delete, deleted-record 404s, invalid statuses, allowlist validation, supplied IDs and duplicate rejection.
- The CRUD smoke test removes its temporary meetings and leaves demo data unchanged.
- Frontend TypeScript typecheck and production build passed.
- 18 frontend/API integration checks passed, including fresh module/store reloads (no browser automation), edited approval, failure handling, duplicate rejection, CRUD, and local task completion counts.
- `local.settings.json`, `host.json`, `requirements.txt`, authentication, and the repository implementation were preserved.

To run the frontend integration suite, start a **fresh dedicated local backend host** in single-worker mode using the command above. The suite intentionally resolves fixture suggestions and creates meetings in that disposable process. From `frontend/`:

```bash
npm run typecheck
npm run build
VITE_API_BASE_URL=http://127.0.0.1:7071/api npm test
```

Restart that test host before rerunning the integration suite. The suite uses only loopback HTTP, requires no browser, and uses fresh frontend module instances to simulate browser reloads while retaining the backend process.

## Before the Cosmos step

No decision blocks this local implementation. Before connecting Cosmos, confirm the existing database/container to use and the partition key/access scope. Project/team values are optional and editable, so they have not been silently selected as partition keys. No Cosmos resources, credentials, SDK, or connection are included here.
