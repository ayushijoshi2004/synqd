# Synq Google Calendar integration

## 1. Files changed

- `backend/GOOGLE_CALENDAR.md`
- `backend/cosmos_meeting_repository.py`
- `backend/function_app.py`
- `backend/google_calendar.py`
- `backend/google_calendar_store.py`
- `backend/meeting_model.py`
- `backend/meeting_service.py`
- `backend/requirements.txt`
- `backend/tests/local_http_host.py`
- `backend/tests/test_google_calendar.py`
- `backend/tests/test_meetings.py`
- `frontend/package.json`
- `frontend/src/components/calendar/CalendarMeetingModal.tsx`
- `frontend/src/components/calendar/GoogleCalendarConnection.tsx`
- `frontend/src/components/calendar/GoogleCalendarEvent.tsx`
- `frontend/src/components/meetings/MeetingFormModal.tsx`
- `frontend/src/pages/CalendarPage.tsx`
- `frontend/src/services/googleCalendar.ts`
- `frontend/src/services/meetings.ts`
- `frontend/src/types/meeting.ts`
- `frontend/src/utils/calendarParticipants.ts`
- `frontend/tests/google-calendar.test.mjs`

The Gemini provider, AI processing method, Jira integration, existing frontend follow-up store/service, meeting CRUD methods, fixture data, host.json, and local.settings.json are unchanged. The production repository is still CosmosMeetingRepository. No Azure resource or container was created or reconfigured.

## 2. Routes and behavior

New routes:

| Method | Route | Purpose |
| --- | --- | --- |
| GET | /api/google-calendar/status | Public connection/configuration status and configured timezone; no tokens |
| GET | /api/google-calendar/authorize | Redirect to Google consent; bind state to an HttpOnly cookie |
| GET | /api/google-calendar/callback | Validate/consume state, exchange code, store encrypted refresh token; simple completion tab |
| POST | /api/meetings/{meeting_id}/follow-ups/{follow_up_id}/google-calendar | Retry/create only for an already-approved follow-up's scheduled meeting |

Extended existing route:

`POST /api/meetings/{meeting_id}/follow-ups/{follow_up_id}/approve`

The existing Synq approval completes first. Its source follow-up remains approved, linked by scheduledMeetingId to the scheduled meeting. Only then does MeetingService attempt Google Calendar creation. Duplicate approval still returns the existing 409 conflict. The separate retry route never creates another Synq meeting and rejects suggested/dismissed follow-ups.

Approval still returns `{sourceMeeting, meeting}`. Inspect `meeting.googleCalendar.status` for the Calendar outcome. A successful Synq approval with a failed Calendar operation remains HTTP 200 with an explicit failed/not_connected Calendar state and a safe error message. Retry returns the scheduled meeting, including the same explicit Calendar state; frontend handles failed outcomes as errors. Unknown records retain 404 behavior.

GoogleCalendar isolates backend OAuth and REST transport. MeetingService owns orchestration and meeting metadata writes through the existing repository. GoogleCalendarStore holds encrypted integration records in the same existing Cosmos container. The Calendar page gains a connection/status line; the existing meeting modal gains a real-event link or retry action. No new navigation or page is added to Synq.

No event is created by AI processing, draft editing, merely viewing a suggestion, or dismissal. Connecting Google also does not retroactively schedule anything. Initial creation happens after explicit approval, or an explicit retry/create click for an already-approved follow-up.

## 3. Required environment variables

All five names below are backend-only. Do not put them in VITE variables, frontend files, source control, or shared screenshots.

| Name | Purpose |
| --- | --- |
| GOOGLE_CLIENT_ID | OAuth Web application client ID |
| GOOGLE_CLIENT_SECRET | OAuth client secret |
| GOOGLE_REDIRECT_URI | Exact registered backend callback URL |
| GOOGLE_TOKEN_ENCRYPTION_KEY | Stable Fernet key for server-side refresh-token/state encryption |
| GOOGLE_CALENDAR_TIME_ZONE | Explicit IANA timezone for the existing local date/time fields |

For local setup, use `http://localhost:7071/api/google-calendar/callback` as GOOGLE_REDIRECT_URI. Choose the workspace timezone deliberately; `America/New_York` is an example. It is shown in the Calendar UI and approval notice. No timezone is guessed from the server or browser. Ambiguous/nonexistent daylight-saving times fail clearly so the user can edit them.

Install the updated backend requirements in your existing Python environment:

```sh
cd backend
python -m pip install -r requirements.txt
```

The only added dependency is cryptography, used for authenticated token encryption. Generate a key once:

```sh
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Keep that value in your private backend environment, stable across restarts and workers. Losing/changing it makes the saved connection unreadable. Do not generate a new key each time you start the server. Existing Cosmos/Jira/AI variables and local.settings.json were not edited by this task.

## 4. Minimal, backward-compatible schema changes

Optional `Participant.email: string`. Existing name-only participants are valid and remain supported. For invitations, the existing participant text area accepts `Name <email@example.com>` or an email alone. Addresses must be entered explicitly; no demo address or name-to-email inference is performed. Google creation requires an email for every participant and deduplicates identical emails. Missing emails leave the Synq meeting approved, with a message to use Edit Meeting and retry.

Optional, server-owned `Meeting.googleCalendar`:

```ts
{
  status: "not_connected" | "pending" | "failed" | "created";
  accountId?: string;
  timeZone?: string;
  eventId?: string;
  eventUrl?: string;
  error?: string;
}
```

- status/error preserve a visible retry outcome across reloads.
- accountId is a one-way hash of Google's stable subject identifier, not a token. It binds retries to the original organizer account and prevents an accidental second event after connecting a different account.
- timeZone pins the timezone used for that event attempt.
- eventId/eventUrl are copied only from a validated Google event response. Public meeting POST/PATCH cannot set or overwrite googleCalendar.
- Follow-up statuses and scheduledMeetingId are unchanged. Metadata lives once on the scheduled meeting, reached through the existing link.

Private Cosmos documents use IDs `__synq_google_connection` and `__synq_google_oauth_state`, with only an id and encrypted payload. They are filtered out of meeting lists and blocked from direct meeting GET/PATCH/DELETE and creation at those IDs. No token field is added to a meeting, follow-up, API response, or frontend store. Access tokens live only within the backend request; refresh tokens are encrypted and persist across restarts. Pending OAuth state is short-lived, browser-bound, single-use, and bounded to one outstanding authorization per workspace.

No data migration is needed for existing meetings.

## 5. OAuth redirect URI

Enter this exact local URI under Authorized redirect URIs:

```text
http://localhost:7071/api/google-calendar/callback
```

Set GOOGLE_REDIRECT_URI to the identical value. Do not enter the frontend port, an /authorize URL, or add a trailing slash. Use localhost consistently in the backend API URL and callback; using 127.0.0.1 for one and localhost for the other prevents the browser-bound cookie from matching.

For an existing deployed Functions host, separately register:

```text
https://<your-existing-functions-host>/api/google-calendar/callback
```

Use the actual hostname, not the placeholder. The deployed backend must use that same HTTPS URL. No Azure deployment/configuration change was performed here.

## 6. Verification

- Complete backend suite: **95 tests passed**, including all existing CRUD, follow-up, Jira, and AI tests.
- New Calendar backend coverage: configuration, consent/state/cookies, denied/expired/replayed OAuth, refresh expiry, encrypted storage, private-record isolation, reviewed event fields, attendee mapping, missing emails, missing connection, Google failures, duplicate approval/retry, parallel retries, a lost response after Google creation, Cosmos save failure recovery, cross-account retry protection, DST ambiguity, and retry routing.
- Frontend `npm test`: **19 passing tests**, using a loopback HTTP harness over the registered Azure Functions handlers and test-only in-memory storage. The original test file is unchanged.
- Frontend `npm run test:jira`: **6 passing tests**.
- Frontend `npm run test:ai`: **9 passing tests**.
- Frontend `npm run test:google`: **8 passing tests**.
- Frontend `npm run typecheck`: passed.
- Frontend `npm run build`: passed.

Frontend counts include the parent test. Component checks use static rendering; service flows use real frontend stores with stubbed responses or the offline HTTP harness. These are not interactive browser or live-cloud acceptance tests. Google HTTP calls are mocked, with real network requests prohibited in the Calendar service tests. No Google credentials are required by any automated test. No real Calendar event, invitation, Jira issue, or cloud meeting was created during verification.

Reproduce backend and self-contained frontend checks:

```sh
cd backend
python -m unittest discover -s tests -v
```

```sh
cd frontend
npm run test:google
npm run test:ai
npm run test:jira
npm run typecheck
npm run build
```

To run the existing frontend/API suite without touching live Cosmos, start the included test-only harness in one terminal:

```sh
cd backend
python tests/local_http_host.py
```

Then, in another terminal:

```sh
cd frontend
VITE_API_BASE_URL=http://127.0.0.1:7079/api npm test
```

Restart the harness before rerunning that suite because it resolves seeded follow-ups. The harness is not an Azure Functions host or production adapter; production still uses Cosmos. Azure Functions Core Tools was unavailable in this execution environment, so `func start` was not verified here.

## 7. Exact Google Cloud Console and manual acceptance steps

1. Open Google Cloud Console and select your intended Google project.
2. Go to **APIs & Services > Library**, search for **Google Calendar API**, and enable it for that project.
3. Go to **Google Auth platform > Branding**. If prompted, click Get Started. Enter Synq as the app name, your support email, and developer contact email. Complete the setup.
4. In **Audience**, use External for a personal Gmail/demo account. Keep the app in Testing for the demo and add the Google account you will connect under Test users. If your organization requires Internal, use its permitted Workspace account instead.
5. In **Data Access**, add only `https://www.googleapis.com/auth/calendar.events.owned` and `openid`. Calendar events.owned supports events on the organizer's existing primary calendar; no full-calendar/calendar-list permissions are requested. OpenID provides only a stable organizer identity for retry protection, not a new Synq login flow. Do not add profile/email scopes for this implementation.
6. Go to **Google Auth platform > Clients > Create client**. Select **Web application**, name it Synq backend, and add the exact local callback URL from section 5 under **Authorized redirect URIs**. JavaScript origins are not needed for this backend authorization-code flow. Create the client and keep its ID/secret private.
7. Set the five backend environment variables from section 3. Keep existing Cosmos settings. Start the backend normally with `func start` and the frontend with `npm run dev`. The frontend API base must point to the backend host used by the callback.
8. Open Synq's Calendar and click **Connect Google Calendar**. Select the intended organizer account, review and grant the requested Calendar access. If Google restricts the test app, confirm that the account is in Test users or permitted by your Workspace administrator.
9. After the callback says connected, close that tab and return to Synq. The connection status refreshes on window focus. Refresh manually if necessary. Confirm the displayed workspace timezone.
10. Review a suggested follow-up. Enter the actual title/date/start/end and each real attendee as `Name <email>`. Only use consenting test recipients for acceptance, because approving sends real Google invitations. Click **Approve & Schedule**.
11. Verify the source remains approved and has scheduledMeetingId. The scheduled Synq meeting opens in the existing modal. If Calendar succeeded, **Open Google Calendar event** must open the real event on the organizer's primary calendar. Check title, time/timezone, attendee addresses, source-meeting reference, and invitation delivery. Google controls delivery and guest acceptance; Synq does not mark guests as accepted.
12. Refresh the browser and restart the backend. The approved follow-up, scheduled meeting, event link, and connection should remain because they are saved in Cosmos. Never change the encryption key during this test.
13. Verify failure/retry safely: approve another suggestion with a name-only participant. Synq approval must succeed, Calendar must show the missing-email error, and no invitation should be sent. Edit the scheduled meeting to add the correct email, then click **Retry Google Calendar**. Confirm one event and its real link.
14. Repeating the approval request must remain a 409 conflict. Repeating the retry request for a created event returns the saved metadata, without sending another invitation. Automated tests additionally cover the harder case where Google created an event but its response or the Cosmos write was lost.
15. If permission expires/revokes, reconnect the same Google account and retry. A different account cannot create a second event for an existing bound attempt. Google test-app/organization policies can require renewed consent; authorization or invitation delivery issues must be validated with your actual account.

### Retry and scope decisions

Google supports a caller-supplied event ID. The integration derives one UUIDv5 request ID from the scheduled Synq meeting ID, calls GET first, and handles insert conflict by GET. It requests `sendUpdates=all` only on the creation POST. An API-supported idempotency key is not treated as proof that an event exists: eventId/eventUrl are not persisted until Google confirms a non-cancelled event with the matching private Synq marker and a valid Google HTTPS link.

Calendar errors never undo Synq approval. Even if Google succeeds but the metadata save fails, the next retry retrieves the same event. A concurrent successful result wins over a failure update. If storage is completely unavailable after approval, the response still distinguishes Calendar failure; its error state itself may not be persisted, but the existing approved source link permits retry after recovery.

This is one shared workspace connection because the existing application has anonymous routes and no users/tenant ownership. Connecting changes the workspace organizer for future events. It is intended for the existing trusted demo environment, not a new authenticated multi-user service. Authentication/tenant isolation remains outside this task.

This scope creates events only for approved follow-ups. It does not add two-way synchronization: later Synq edits/deletion do not modify/delete the Google event. The modal says to manage an existing Google event through its link. No automatic backlog creation, Google Meet conference generation, recurring events, new calendar creation, live meeting integration, AI changes, or Jira changes were implemented.

Live OAuth consent, actual Google event creation, invitation delivery, and live Cosmos restart acceptance remain for your configured environment. All original archive entries outside the file list are preserved.

Official references checked:

- https://developers.google.com/workspace/calendar/api/v3/reference/events/insert
- https://developers.google.com/workspace/calendar/api/auth
- https://developers.google.com/identity/protocols/oauth2/web-server
- https://developers.google.com/identity/openid-connect/reference
- https://developers.google.com/workspace/guides/configure-oauth-consent
- https://developers.google.com/workspace/guides/create-credentials
