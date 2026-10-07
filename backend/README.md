# Synqd backend

Python Azure Functions with Cosmos DB persistence, Gemini analysis/Q&A, Vexa transcription, Jira action items and Google Calendar follow-ups. The production entry point is `function_app.py`; the in-memory repository is used by offline tests.

## Run locally

See the [root setup guide](../README.md) for prerequisites, credentials, Calendar OAuth and frontend startup.

```sh
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp local.settings.json.example local.settings.json
# Fill in Values; preserve your existing file if already configured.
# Start Azurite in a separate terminal for local Functions storage.
func start --cors http://localhost:8443
```

Cosmos endpoint, key, database and container are required at startup. Use a container partition key of `/id`. The example uses `UseDevelopmentStorage=true` for the ten-second transcript-polling timer. The app seeds sample meetings when its meeting repository is empty. Keep `local.settings.json` private; Azure Functions loads it automatically. No backend dotenv loader is present.

## API overview

All paths below start with `/api`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Basic liveness response |
| GET / POST | `/meetings` | List / create meetings |
| GET / PATCH / DELETE | `/meetings/{id}` | Read / update / delete a meeting |
| POST | `/meetings/{meeting_id}/process` | Analyze the stored transcript |
| POST | `/meetings/{meeting_id}/ask` | Meeting-scoped Gemini Q&A |
| POST | `/meetings/join` | Request a Vexa bot and attach transcription |
| GET | `/meetings/{meeting_id}/transcript` | Read synchronized transcript |
| POST | `/meetings/{meeting_id}/transcription/end` | End transcription |
| POST | `/meetings/{meeting_id}/action-items/{action_item_id}/jira` | Create/link a Jira issue |
| POST | `/meetings/{meeting_id}/follow-ups/{follow_up_id}/dismiss` | Dismiss a suggestion |
| POST | `/meetings/{meeting_id}/follow-ups/{follow_up_id}/approve` | Save a reviewed follow-up meeting |
| POST | `/meetings/{meeting_id}/follow-ups/{follow_up_id}/google-calendar` | Retry Calendar synchronization |
| GET | `/google-calendar/status` | Integration configuration/connection state |
| GET | `/google-calendar/authorize` | Begin OAuth |
| GET | `/google-calendar/callback` | Complete OAuth |
| GET | `/jira-test` | Check the configured Jira connection |

Meeting creation requires `title`, `date`, `startTime`, `endTime` and `participants`. Dates are `YYYY-MM-DD`, times `HH:mm`, and end time must follow start time on the same date. Unknown fields and invalid payloads are rejected. See `meeting_model.py` for the full contract. Errors generally use `{"error":{"code":"...","message":"..."}}`.

AI results are checked for shape, known participants and supporting transcript excerpts. Processing preserves existing task statuses and Jira metadata. Follow-ups are suggested until reviewed/approved; optional Calendar synchronization has its own result state, so an integration failure need not undo the saved meeting. Cosmos updates use optimistic concurrency checks.

Routes currently use anonymous Functions authentication. Application-level login and per-user meeting/Calendar isolation are not implemented. Deployment access controls must be considered separately.

## Verification

With the virtual environment active, run from this directory:

```sh
python -m unittest discover -s tests -v
```

Offline tests replace external services/storage with mocks or in-memory adapters. A passing offline run does not verify a live deployment. HTTP/frontend integration checks require a suitable local host and may modify local meeting fixtures; inspect their setup before running them.

Detailed integration notes: [transcription](TRANSCRIPTION.md), [AI processing](AI_PIPELINE.md), [Calendar](GOOGLE_CALENDAR.md), [Vexa](../VEXA_INTEGRATION.md), [Q&A](../ASK_SYNQD.md).
