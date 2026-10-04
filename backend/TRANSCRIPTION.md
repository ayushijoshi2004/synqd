# Synq meeting transcription

Open a Synq meeting detail page. If it has no Google Meet link, choose **Add Meet link**, enter its existing Google Meet URL once, and save it. **Join Meeting** sends only the Synq meeting ID to the backend. The backend reads the saved URL, requests Synq AI, and returns the saved session. The browser opens Google Meet. Join normally and admit Synq AI when prompted.

The header no longer has a global Join Meeting button. The Transcript tab displays persisted meeting content, without a separate Vexa/manual-code mode. The detail page refreshes Synq data every four seconds while starting, active or stopping. Closing the browser does not stop collection. Reopening the meeting restores its session.

Choose **End transcription** to stop the bot and collect remaining completed segments. Finalization waits for Vexa's terminal status and at least 30 seconds without new completed segments. The completed session cannot start another bot. Opening the Google Meet link itself never creates a bot.

## Local setup

Keep your existing private settings files; they are intentionally excluded from the delivered archive. Do not replace them with credentials from another environment.

1. Install the existing backend dependencies in your Python environment: `python -m pip install -r requirements.txt` from `backend/`.
2. Keep your existing Cosmos settings and `VEXA_BOT_KEY`, `VEXA_TRANSCRIPT_KEY`, and optional `VEXA_API_BASE`. No new application secrets are needed. Both Vexa keys must refer to the same account and allow their respective bot/transcript operations.
3. The timer requires the existing `AzureWebJobsStorage` host setting. Your supplied settings select `UseDevelopmentStorage=true`; start Azurite locally (for example, the VS Code Azurite extension). No Azure resources are created. The timer binding uses Microsoft's Functions extension bundle in `host.json`.
4. Start the backend once with `func start` (Azure Functions Core Tools v4). Keep it running. The timer executes automatically; no repeated terminal/polling commands are needed.
5. From `frontend/`, install dependencies using your existing package manager and start `npm run dev`. Keep the existing frontend API-base setting.
6. Open the desired Synq meeting, save its existing Meet link if absent, join, admit Synq AI, speak, and watch the Transcript tab. Reload the page and verify the same session remains. End transcription and wait for the completed state. Then use **Process Meeting** to exercise your existing Gemini flow against the saved transcript.

Your provided Meet URL was not hardcoded or assigned to an arbitrary Synq meeting. Select its actual meeting and save it through the detail-page control.

## API

- Modified `POST /api/meetings/join`: body `{ "synqMeetingId": "..." }`; returns the updated Synq meeting, including its saved URL and transcription state. Repeated starts return an existing active/completed session.
- Added `POST /api/meetings/{meeting_id}/transcription/end`: requests stop and performs one bounded polling step. Returns the updated meeting. Delayed final segments are drained by the timer.
- Modified `GET /api/meetings/{meeting_id}/transcript`: now accepts a Synq meeting ID and returns the persisted meeting including transcript/session, with `Cache-Control: no-store`. It never accepts a raw Meet code or fetches arbitrary Vexa transcripts.
- Existing `GET /api/meetings/{id}` remains the frontend refresh endpoint.
- Existing `PATCH /api/meetings/{id}` accepts optional `googleMeetUrl`. Session fields are backend-owned and rejected on public create/patch. Replacing the link/transcript or deleting a meeting is blocked while its attempted session is unresolved; ordinary metadata edits still work.
- `poll_transcriptions` is an Azure Functions timer, not a public HTTP route.

## Storage and isolation

No Cosmos container, database, partition key or infrastructure changes. Existing meeting documents gain optional `googleMeetUrl` and `transcription`; old meetings remain valid without either. Existing `transcript` entries retain `{ timestamp, speaker, text }`, preserving Gemini's input format.

Transcription metadata includes a Synq session UUID, the returned Vexa record ID, normalized Meet ID, lifecycle state, timestamps, stop intent, polling lease/backoff and committed segment IDs. Transcript appends and the dedupe cursor are committed together in the meeting's Cosmos ETag update. Existing intelligence and other concurrent edits are preserved.

Private `__synq_vexa_*` coordination records live in the existing Cosmos container and are excluded from meeting lists and CRUD access. A link reservation prevents simultaneous Synq sessions on the same Meet link. A permanent record reservation prevents a Vexa record from being attached to a different Synq session. Completed link reservations are released after final transcript draining. A later meeting can reuse the link only with a different Vexa record.

Polling reads `/transcripts/by-id/{VexaRecordId}` and verifies the returned ID, platform and native Meet ID before accepting completed segments. It never falls back to reading the newest transcript by Meet link. The Vexa deployment must support this record-specific API. Because Vexa's stop endpoint uses a native Meet ID, Synq checks that its latest record still matches the saved ID immediately before stopping it, while holding the Synq link reservation. A different record fails closed. Coordination covers Synq workers; unrelated external Vexa clients should not manipulate the same active Meet link.

## Bounded work and failures

- Timer interval: 10 seconds; maximum three eligible sessions per invocation, oldest first, with a 100-second dispatch budget. External requests have 20-second timeouts. A request in progress may finish after the dispatch budget.
- Per-session persisted leases last 120 seconds, preventing overlapping poll/stop work across workers. A crashed worker's lease expires.
- Completed segments are deduplicated by their Vexa segment ID within the bound session. Pending segments are ignored.
- Transient polling/storage errors retain saved content, back off up to five minutes and pause after six failures. The detail page shows the error and allows a safe End transcription retry for a known bot. No new bot is created by retrying stop.
- Sessions request stop after eight hours. A stop not confirmed within five minutes becomes a visible error after bounded retries.
- A confirmed spawn whose Cosmos commit fails gets a best-effort stop; saved recovery state is retried when storage is available.
- Vexa does not provide a client idempotency key for this spawn API. If the connection is lost after POST but before a usable bot ID returns, Synq cannot prove which bot was created. It records an error and retains the reservation rather than issuing another POST or guessing a bot ID. This exceptional ambiguous state requires operator reconciliation with Vexa. Definite preflight/refusal errors can be retried through Join Meeting. A normal join/transcribe/end flow needs no manual commands.
- An expired, mismatched or unsupported record-specific API fails safely; no other meeting's transcript is substituted. Raw upstream bodies, tokens and stack traces are not returned by transcription endpoints.

## Checks

From `backend/`: `python -m unittest discover -s tests -q`.

From `frontend/`: `npm run typecheck`, `npm run build`, `npm run test:jira`, `npm run test:ai`, `npm run test:google`, and `npm run test:transcription`.

For the existing offline cross-stack CRUD/follow-up suite, start `python tests/local_http_host.py` from `backend/` and run `VITE_API_BASE_URL=http://127.0.0.1:7079/api npm test` from `frontend/`. This harness uses registered Functions HTTP handlers and test-only local storage. It does not start a real Functions host, timer, Vexa bot or cloud service.

Gemini's provider, schema, normalization/merge code, assistant component, and MeetingService.process behavior are preserved. The new suite also passes a newly collected transcript through the existing intelligence pipeline using a mocked provider.

References: [Vexa Meetings API](https://docs.vexa.ai/api/meetings), [Azure Functions timer trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-timer).
