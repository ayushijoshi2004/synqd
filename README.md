# Synqd

Synqd is a GirlHacks meeting-assistant project built with React, TypeScript, and a Python Azure Functions backend. It brings meeting transcripts, AI-generated summaries, decisions, action items, and follow-up scheduling into one dashboard.

## Implemented features

- Meeting creation, editing, deletion, and project grouping with Azure Cosmos DB persistence.
- Google Meet bot integration through Vexa, transcript synchronization, and explicit transcription controls.
- Gemini-based post-meeting analysis with structured output validation and transcript-evidence checks.
- Meeting-scoped “Ask Synqd” questions, using the selected meeting as context.
- Action-item tracking and conversion into Jira issues.
- Follow-up review, approval, and dismissal, with optional Google Calendar event creation and invitations.
- Loading/error states, stale-response protection, and retry/concurrency handling across several workflows.

External features require your own configured service accounts and credentials. The repository includes fixtures and some demo project metadata; it is a hackathon prototype. Authentication and user-specific access isolation are not implemented in the application routes.

## Stack

| Layer | Technologies |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS |
| Backend | Python, Azure Functions v2 programming model |
| Persistence | Azure Cosmos DB |
| AI | Gemini REST API for processing; Google Gen AI SDK for Q&A |
| Integrations | Vexa, Jira, Google Calendar OAuth |

## Local setup

Prerequisites: Node 22.12+ and pnpm; Python 3.13; Azure Functions Core Tools v4; Azurite for local Functions storage; an existing Cosmos DB database/container. The Cosmos adapter expects a container partition key of `/id`.

### 1. Backend configuration

```sh
cd backend
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp local.settings.json.example local.settings.json
```

If you already have working `local.settings.json`, keep it and add only missing settings from the example. Fill in your real values under `Values`. Azure Functions loads this file; the backend does not automatically load a `.env` file.

| Settings | Purpose |
| --- | --- |
| `COSMOS_ENDPOINT`, `COSMOS_KEY`, `COSMOS_DATABASE`, `COSMOS_CONTAINER` | Required at backend startup |
| `AzureWebJobsStorage` | Functions storage for the transcription timer; example uses local Azurite |
| `FUNCTIONS_WORKER_RUNTIME` | Set to `python` |
| `AI_PROVIDER`, `AI_MODEL`, `GEMINI_API_KEY` | Post-meeting processing; Q&A shares the model and key |
| `VEXA_BOT_KEY`, `VEXA_TRANSCRIPT_KEY`, `VEXA_API_BASE` | Bot and transcript access; use keys from the same Vexa account |
| `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY` | Jira integration |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` | Google Calendar OAuth |
| `GOOGLE_TOKEN_ENCRYPTION_KEY`, `GOOGLE_CALENDAR_TIME_ZONE` | Persistent token encryption and explicit IANA timezone |

Optional integration credentials are blank in the example. Configure the integrations you want to use. Set `AI_MODEL` to a Gemini model available to your account. For Jira assignee mapping, review the existing account mappings in `backend/jira_service.py`.

For Calendar, register `http://localhost:7071/api/google-calendar/callback` as the OAuth redirect URI and use that same value in settings. Generate a Fernet key once after installing dependencies:

```sh
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Save it privately as `GOOGLE_TOKEN_ENCRYPTION_KEY` and retain it across restarts. Choose your workspace timezone; `America/New_York` is the example value. See [Calendar setup](backend/GOOGLE_CALENDAR.md) for consent, scopes and troubleshooting.

### 2. Start the backend

Start Azurite in a separate terminal, then run from `backend/` with the virtual environment active:

```sh
func start --cors http://localhost:8443
```

The API defaults to `http://localhost:7071/api`. A timer synchronizes active transcripts every ten seconds. On startup, the backend seeds sample meetings when the meeting repository is empty.

### 3. Start the frontend

In another terminal, from the repository root:

```sh
cd frontend
cp .env.example .env.local
pnpm install --frozen-lockfile
pnpm dev
```

Open `http://localhost:8443`. `VITE_API_BASE_URL` points to the backend; its default is `http://localhost:7071/api`. Restart Vite after changing frontend environment values. Use `localhost` consistently for the API and Google callback.

Frontend `VITE_*` variables are public browser configuration. Keep all service keys and OAuth secrets in backend settings. Private `.env` files and `local.settings.json` are ignored by Git; only blank/safe example files should be committed.

## Checks

From `backend/`, with dependencies installed:

```sh
python -m unittest discover -s tests -v
```

The backend tests use mocks/in-memory adapters for service boundaries. They do not establish that live service credentials or deployment work.

From `frontend/`:

```sh
pnpm typecheck
pnpm build
```

The frontend has separate integration scripts: `pnpm test`, `pnpm test:ai`, `pnpm test:jira`, `pnpm test:google`, `pnpm test:transcription`, and `pnpm test:assistant`. Read each script's host/mocking requirements before running it; some expect a fresh local backend and modify its meeting fixtures. The root package does not provide the application test runner.

## Repository structure

```text
frontend/src/
  pages/              Meetings, meeting detail, calendar
  components/         Meeting, assistant, task and calendar UI
  services/           API calls and shared meeting state
  types/              Typed frontend contracts
  mocks/              Demo fixtures and project metadata
backend/
  function_app.py     HTTP routes and transcript polling timer
  meeting_service.py  Meeting and integration workflows
  cosmos_meeting_repository.py  Persistent storage adapter
  meeting_intelligence.py      AI validation and normalization
  gemini_provider.py / meeting_assistant.py  Analysis and Q&A
  transcription_service.py / vexa_service.py  Transcript ingestion
  jira_service.py / google_calendar.py        External integrations
  tests/              Offline backend checks
```

## Further documentation

- [Backend API and local configuration](backend/README.md)
- [Transcription](backend/TRANSCRIPTION.md)
- [Vexa integration](VEXA_INTEGRATION.md)
- [AI processing pipeline](backend/AI_PIPELINE.md)
- [Ask Synqd](ASK_SYNQD.md)
- [Google Calendar](backend/GOOGLE_CALENDAR.md)

Some integration documents describe earlier implementation stages. The current source and this README describe the present application setup.

For deployment, configure backend variables as Azure application settings and frontend configuration at build time; private local settings are not deployed automatically. Configure the deployed frontend's allowed origin and access controls before using real meeting data.
