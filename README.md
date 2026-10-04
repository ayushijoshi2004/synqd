# Recall

A practical refactor of the existing React + TypeScript + Vite demo. The Meetings → Meeting Detail and Calendar screens retain their original layout, styling, content, and interaction flow. Project information remains part of meetings, including the existing grouping toggle on the Meetings page.

The existing application lives in `frontend/`. `backend/` is empty and reserved for the future Python Azure Functions backend. The frontend will communicate with it over HTTP/JSON; Azure Cosmos DB is an external service, so there is no database source folder.

## Run

Use Node 22.12+ (or a newer supported Node release) and pnpm.

```sh
cd frontend
pnpm install --frozen-lockfile
pnpm dev
pnpm typecheck
pnpm build
pnpm preview
```

`build` runs TypeScript before Vite. No backend or environment variables are needed for the demo. Vite uses the React and Tailwind plugins, with the existing source alias and development port. Page metadata and crawler rules are plain `frontend/index.html` and `frontend/public/robots.txt` files.

## Important structure

```text
frontend/
  src/
    App.tsx                         Existing in-memory screen navigation
    pages/
      MeetingsPage.tsx
      MeetingDetailPage.tsx
      CalendarPage.tsx
    components/
      AppHeader.tsx
      ui.tsx                        Existing shared visual primitives
      meetings/                     Meeting card and section
      meeting-detail/               Context, overview, content, assistant, actions
      calendar/                     Sidebar, week grid, approvals
    types/
      meeting.ts                    Meeting, participant, transcript, decision, action
      calendar.ts                   Calendar events and follow-up meetings
      navigation.ts
    services/
      meetings.ts                   Meeting list, detail, project grouping metadata
      assistant.ts                  Existing canned Q&A behavior
      actionItems.ts                Existing demo ticket conversion
      calendar.ts                   Existing demo scheduling and approvals
    mocks/
      meetings.ts                   List plus shared detail fixture
      participants.ts
      assistant.ts
      actionItems.ts
      calendar.ts
    hooks/useAsyncData.ts           Loading, error, stale-response handling
    config/env.ts                   Future backend base URL
    utils/calendar.ts              Shared time formatting and filter toggling
  .env.example
  public/
  package.json
  pnpm-lock.yaml
  vite.config.ts
  tsconfig.json
  index.html
  .gitignore
backend/                          Empty
README.md
```

Pages load through services. Panels receive typed data as props. Only services import mock fixtures. State stays in React near the screen or panel that uses it; there is no store, event bus, router dependency, or dependency-injection framework.

Services return promises now so replacing a mock with an HTTP request does not require rewriting component data loading. Read services return independent copies of fixtures so local edits cannot change later loads. Navigating away still resets the local demo state, matching the source app.

## First Azure Functions connection

**Edit `frontend/src/services/meetings.ts` first.** Replace `getMeetings()` and `getMeeting(id)` with HTTP/JSON requests while keeping their public return types. The optional grouping metadata is loaded through `getMeetingProjects()` in the same file.

Copy `frontend/.env.example` to `frontend/.env.local` and set `VITE_API_BASE_URL` to your Python Azure Functions base URL, for example `http://localhost:7071/api`. `frontend/src/config/env.ts` exposes this value as `config.apiBaseUrl` and defaults to `/api`. Setting the variable alone does not activate HTTP calls; the current services intentionally remain mock-backed.

For example, the future body of `getMeetings()` can be:

```ts
// In frontend/src/services/meetings.ts, when the backend is ready:
import { config } from "../config/env";

export async function getMeetings(): Promise<Meeting[]> {
  const response = await fetch(`${config.apiBaseUrl}/meetings`);
  if (!response.ok) throw new Error("Unable to load meetings.");
  return response.json();
}
```

Use `/meetings/${encodeURIComponent(id)}` for detail, return `null` for a missing meeting, and map the backend JSON to the types in `frontend/src/types/meeting.ts` inside the service if needed. The frontend types describe only the existing UI; they are not a Cosmos DB schema. Python owns Cosmos persistence and service credentials. Vite's `VITE_*` variables are public browser configuration.

## Independent next steps, when needed

| Work | Existing boundary |
| --- | --- |
| Cosmos persistence | Python HTTP endpoints, consumed by `frontend/src/services/meetings.ts` |
| Post-meeting analysis | `getMeeting()` supplies typed summary, decisions, agenda, transcript, and action items |
| Dashboard AI questions | `frontend/src/services/assistant.ts` and `MeetingAssistant.tsx` |
| Vexa live transcript | `TranscriptEntry` and the transcript view in `MeetingContent.tsx` |
| Gemini and ElevenLabs live agent | Add a separate live-session service when this feature is built; existing pages do not depend on it |
| Calendar integration | `frontend/src/services/calendar.ts` and the three calendar panels |
| Jira integration | `frontend/src/services/actionItems.ts` and `ActionItemsPanel.tsx` |

No external integrations or authentication are implemented. The current canned AI replies, local ticket labels, calendar proposals, and approval messages are preserved, including the existing demo text about invitations. They do not send anything externally. Previously inert controls, including Join Meeting, New Meeting, Open project, and calendar arrows, remain as they were.

The original demo uses one Atlas dashboard fixture for all six meeting cards and one fixed calendar week. Those fixtures are preserved explicitly in `frontend/src/mocks/meetings.ts` and `frontend/src/mocks/calendar.ts`, rather than inventing new content. Unreferenced chart data, imported images, and platform-specific scaffolding have been removed. The existing app and service structure is unchanged.

A simple team split is pages/components for one teammate and services/types/backend contracts for the other. Add a new service only when a feature needs it.
