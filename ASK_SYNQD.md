# Ask Synqd

The existing **AI Assistant** tab on each meeting detail page now contains **Ask Synqd**. It uses Google Gemini through the backend. The previous canned-answer service is no longer imported by the assistant.

## Setup

Prerequisites: the project's Python environment (the existing README recommends Python 3.13), Node 22.12+ or Node 24, Azure Functions Core Tools v4, and your existing Cosmos configuration. This feature adds only `google-genai>=1.30.0,<2.0.0` to backend requirements. The official SDK interface was checked against Google's Python documentation and tested with SDK 1.75.0. Existing AI processing continues using its existing REST adapter.

Add these entries inside `Values` in `backend/local.settings.json`:

```json
"GEMINI_API_KEY": "YOUR_GEMINI_API_KEY",
"AI_MODEL": "gemini-2.5-flash"
```

Reuse your existing `GEMINI_API_KEY` and `AI_MODEL` if they are already configured. `AI_MODEL` is shared with the existing processing pipeline. No VITE variable should contain credentials. Missing or invalid Gemini configuration returns a safe 503 only when Ask Synqd is called.

**The uploaded `backend/local.settings.json` was empty.** Restore your working settings, including `COSMOS_ENDPOINT`, `COSMOS_KEY`, `COSMOS_DATABASE`, `COSMOS_CONTAINER`, and your Vexa/Jira/Google Calendar values, before starting the app. No credentials were inserted or changed. For a new settings file, the surrounding structure is:

```json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsStorage": "",
    "COSMOS_ENDPOINT": "YOUR_EXISTING_COSMOS_ENDPOINT",
    "COSMOS_KEY": "YOUR_EXISTING_COSMOS_KEY",
    "COSMOS_DATABASE": "YOUR_EXISTING_DATABASE",
    "COSMOS_CONTAINER": "YOUR_EXISTING_CONTAINER",
    "GEMINI_API_KEY": "YOUR_GEMINI_API_KEY",
    "AI_MODEL": "gemini-2.5-flash"
  }
}
```

This is a structure example, not a replacement for configured integration settings. Keep any existing working Azure Storage value, especially for the Vexa polling timer.

From the extracted project root, start the backend:

```bash
cd backend
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
func start --cors http://localhost:5173 --port 7071
```

If `.venv` already exists, skip its creation and activate it. Keep your existing Storage/Azurite configuration for timer-triggered Vexa polling.

In a second terminal, from the project root:

```bash
cd frontend
npm ci
VITE_API_BASE_URL=http://localhost:7071/api npm run dev -- --port 5173
```

Open http://localhost:5173, select a meeting, then its AI Assistant tab.

## Endpoint and scope

`POST http://localhost:7071/api/meetings/{meeting_id}/ask`

```json
{"question":"What is Alex responsible for?"}
```

Success: `{"answer":"..."}`. Optional `history` contains at most six `{ "question": "...", "answer": "..." }` exchanges. The frontend sends only completed exchanges from this meeting's current session. All previous messages stay visible until navigation away or refresh. Switching Summary/Transcript/Assistant tabs preserves messages; switching meetings resets them.

The route uses `MeetingService.get()` and the existing Cosmos repository. It performs no writes. It sends allowlisted title/date/times, participants' IDs/names, transcript entries with speaker names and timestamps, summary, decisions, action items with assignees/due/status, follow-ups with their actual status, unresolved items, and agenda. It excludes Cosmos internals, integration state, participant emails, Jira links, and project-wide/demo memory. No cross-meeting query is performed. Reserved private record IDs are rejected with the existing 404 envelope.

The existing app uses anonymous Azure Function routes with no per-user meeting authorization. Ask Synqd inherits that access model; it does not add multi-user authorization. It is restricted to the one requested meeting and does not read linked meetings or private integration records.

The grounding prompt treats meeting text and history as untrusted data, forbids outside knowledge and invented facts, and asks for an explicit insufficient-information answer where appropriate. Prior assistant messages are never factual evidence. Meetings without transcripts/intelligence still provide available metadata, and Gemini is instructed not to infer absent decisions or commitments.

Input questions are capped at 2,000 characters. Context plus history and question is capped at 200,000 UTF-8 bytes. Oversized meetings receive a clear 413 error; no transcript is silently truncated and no data is deleted. Gemini has a 45-second request timeout, one attempt, and a bounded output; the browser has a 60-second timeout. Missing settings, rate limits, timeouts, blocked/empty/incomplete responses and other provider failures return a safe 503. No provider exception text is logged or returned by this feature, and no fake answer is substituted.

## Files changed

| File | Change |
| --- | --- |
| `backend/meeting_assistant.py` | New allowlisted context builder, input/history validation, grounding prompt, SDK call, size/timeout limits, safe errors. |
| `backend/meeting_service.py` | Read-only `ask()` operation through the existing repository. |
| `backend/function_app.py` | Registers POST meeting ask route using existing JSON/error helpers. |
| `backend/requirements.txt` | Adds the official `google-genai` SDK. |
| `backend/tests/test_meeting_assistant.py` | New offline SDK/HTTP boundary and isolation tests. |
| `backend/tests/test_meetings.py` | Adds the new handler to the expected route list. |
| `frontend/src/services/assistant.ts` | Replaces canned answers with backend fetch, bounded history, timeout and friendly errors. |
| `frontend/src/components/meeting-detail/MeetingAssistant.tsx` | Ask Synqd UI, immediate user messages, loading/errors, Enter and Shift+Enter, disabled empty/pending send, scroll and retry input. |
| `frontend/src/components/meeting-detail/MeetingContent.tsx` | Keys assistant state by meeting; removes demo scope/suggestions prop. |
| `frontend/src/types/meeting.ts` | Allows pending/failed user messages without an answer. |
| `frontend/src/pages/MeetingDetailPage.tsx` | Explicit loading/error state while checking the selected meeting. |
| `frontend/tests/assistant.test.mjs` | New API service and initial-render tests. |
| `frontend/package.json` | Adds `npm run test:assistant`. |
| `ASK_SYNQD.md` | Setup, architecture, changed-file list, tests, and limitations. |

## Verification

Run new backend tests from `backend/` with the environment active:

```bash
python -m unittest discover -s tests -p 'test_meeting_assistant.py' -v
```

Run frontend tests/build from `frontend/`:

```bash
npm run test:assistant
npm run build
```

Frontend verification passed: production build, the new assistant suite, and all existing meeting-flow, Jira, AI-processing, Google Calendar, and transcription frontend suites. The meeting-flow suite used the existing offline HTTP harness; suites with their own mocked fetch ran with the default API base URL. Interactive DOM checks also passed for empty/pending Send, immediate messages, response rendering, tab history, follow-up history, friendly errors, restored retry text, Enter/Shift+Enter, and discarding late replies after switching meetings. A visual browser review was unavailable because the browser download failed.

The new backend tests use the real SDK with mocked HTTP transport. They check context construction for decisions and Alex's ownership, unsupported-answer passthrough, missing intelligence, conversation history, 400/404/413/503 behavior, missing keys, timeout/provider failure, non-complete output, no storage mutation, and exclusion of unrelated/private fields. Controlled provider replies test application behavior; they do **not** prove live model grounding.

The complete backend suite was compared against the original ZIP: 135 tests after changes, with the same four pre-existing failures as the original's 130 tests. Those failures are:

- `test_ai_tasks_use_existing_jira_flow_and_reprocessing_preserves_it`
- `test_creation_stores_key_and_url_on_the_correct_item`
- `test_join_endpoint_and_bot_key`
- `test_upstream_errors_are_safe`

Jira, Vexa, Calendar, Cosmos, and existing AI provider implementations were not changed. The existing Jira test failures mean live Jira behavior cannot be certified from this environment. No external issues, meetings, or invitations were created during testing.

After restoring your backend configuration, check a real meeting whose transcript/intelligence you know:

1. Ask “What were the main decisions?” and compare with stored decisions/transcript.
2. Ask “What is Alex responsible for?” and verify assignee names and exact deadline wording.
3. Ask about a budget or commitment absent from the meeting. Expect an explicit insufficient-information answer.
4. Ask “When is it due?” after an ownership question to verify conversational reference resolution.
5. Test blank input, a missing meeting ID, unavailable Gemini, and a meeting without intelligence.
6. Reload the app, reopen the meeting, and check that stored meeting data still loads.
7. Use your normal Jira creation flow and verify its saved metadata.

Live Gemini grounding, live Cosmos persistence, live Jira creation, and live Vexa/Calendar calls were not run because working credentials were not supplied. Gemini answers remain generative; the prompt enforces the requested behavior but is not a formal guarantee of factual correctness.

Official SDK documentation: https://googleapis.github.io/python-genai/
