# Vexa integration

## Scope and files

Created:
- `backend/vexa_service.py`
- `backend/tests/test_vexa.py`
- `backend/local.settings.json`
- `frontend/src/services/vexa.ts`
- `VEXA_INTEGRATION.md`

Modified:
- `backend/function_app.py`: two routes using the existing `respond` helper.
- `backend/tests/test_meetings.py`: expected route names include the two new handlers.
- `frontend/src/components/AppHeader.tsx`: connect the existing Join Meeting button.
- `frontend/src/components/meeting-detail/MeetingContent.tsx`: load and poll live transcript in the existing transcript renderer.

Gemini, AI processing, Cosmos, Jira, Google Calendar, dependency manifests, and other meeting logic are unchanged. No new application dependencies.

## Configuration

The uploaded archive did not contain `backend/local.settings.json` or an example. The included file therefore contains only the Python worker settings and empty Vexa credentials. If you already have a working local settings file, keep it and add only these missing entries inside `Values`:

```json
"VEXA_BOT_KEY": "",
"VEXA_TRANSCRIPT_KEY": "",
"VEXA_API_BASE": "https://api.cloud.vexa.ai"
```

Fill the first two values with their separate keys. Keep them out of frontend files and source control. Your existing Cosmos settings (`COSMOS_ENDPOINT`, `COSMOS_KEY`, `COSMOS_DATABASE`, `COSMOS_CONTAINER`) remain required for backend startup. Retain all your existing Jira, Gemini, and Google Calendar settings too. For deployment, configure the same three Vexa settings as backend Azure app settings.

## Start locally

From the project root, using the project's existing Python 3.13 and Azure Functions Core Tools v4 setup:

```bash
cd backend
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
func start --cors http://localhost:5173
```

Use your existing virtual environment if already configured. Merge the configuration above before starting. The existing app connects to Cosmos at import time, independently of Vexa.

In a second terminal, from the project root:

```bash
cd frontend
npm ci
npm run dev -- --port 5173
```

The frontend defaults to `http://localhost:7071/api`; optionally set `VITE_API_BASE_URL` in `frontend/.env` to your backend URL. Never add Vexa keys there. If Vite uses another origin, add that origin to the Functions CORS setting.

## Test join

```bash
curl -i -X POST http://localhost:7071/api/meetings/join \
  -H 'Content-Type: application/json' \
  -d '{"meetingUrl":"https://meet.google.com/abc-defg-hij"}'
```

Use a real meeting code for live testing. Success returns HTTP 200 with `{ "id": 31549, "meetingId": "abc-defg-hij", "status": "requested" }` where `id` is the actual Vexa ID. `requested` acknowledges the bot request; it does not claim the bot has joined. Admit Synq AI in Google Meet if prompted. Raw IDs are also accepted. Joins are not automatically retried.

## Test transcript

```bash
curl -i http://localhost:7071/api/meetings/abc-defg-hij/transcript
```

The route uses the Google Meet code, not the Cosmos meeting ID or Vexa numeric bot ID. It returns an array of completed segments only, preserving order and duplicates. Each segment has `id`, `speaker`, `text`, `startTime`, `endTime`, and `completed: true`. Times remain upstream ISO strings. An existing empty transcript returns `[]`; upstream 404 returns a safe `transcript_not_found` error.

## UI

Click Join Meeting and enter the Meet URL or code. Open a Synq meeting, choose Transcript, and click Load live transcript. Enter the same Meet code. The existing transcript layout refreshes every five seconds while that tab is open. Show saved restores the persisted transcript. Polling stops when leaving the tab or closing the view.

There is no existing mapping between Synq records and Google Meet codes, so the transcript association is explicit and session-only. Live segments are display-only and are not saved to Cosmos, deduplicated, summarized, or passed to Gemini. The existing Process Meeting action still uses only the saved transcript. Joining does not create a Synq meeting record. There is no bot-stop endpoint in this change.

## Errors

Errors follow the existing `{ "error": { "code": "...", "message": "..." } }` shape:
- 400: invalid URL, ID, or JSON/body.
- 503: missing key or invalid Vexa base configuration.
- 404: transcript not found.
- 504: Vexa timeout.
- 502: Vexa authentication, permission/scope, other upstream errors, malformed payloads, or connectivity failure.

Upstream 401/403 have distinct error codes but map to 502 because they concern backend service credentials. Raw upstream bodies and exceptions are not returned or logged. HTTP requests use a timeout and disable redirects so keys are not forwarded to redirect destinations.

## Verification

- Python compile and application imports passed (Cosmos substituted only by the existing test harness).
- All 109 backend unit tests passed, including 14 Vexa tests.
- Exact example join URL and completed-only transcript contract verified through Azure HTTP handlers with mocked Vexa.
- Frontend `npm run typecheck` and `npm run build` passed.
- No Vexa key names or Vexa cloud URL under frontend, including generated build output.
- Original source comparison confirmed only the four existing files listed above were modified.

Re-run:

```bash
cd backend
python -m unittest discover -s tests
```

```bash
cd frontend
npm run typecheck
npm run build
```

Limitations: no real Vexa credentials or live meeting were available. Azure Functions Core Tools is unavailable in the verification environment, so an actual Functions host was not started. Tests ran on Python 3.12 with azure-functions 1.25.0, azure-cosmos 4.17.1, requests 2.34.2, and cryptography 46.0.0; the project's original Python 3.13/azure-functions 2.3.0 dependency requirements were not modified. Final live validation should use your existing project environment. Dependencies, build outputs, caches, and repository metadata are omitted from this source archive.
