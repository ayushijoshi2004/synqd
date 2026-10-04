# Synq frontend changes

All edits are inside `frontend/`. The original `backend/` and all other project files are preserved unchanged.

## Added behavior

- Synq document/product branding and removed Meetings subtitle.
- New Meeting modal with required title, date, start/end time and participants; optional agenda, project and team.
- Configurable eight-participant form limit in `src/config/demo.ts`. The data model and meeting service support larger participant lists.
- One subscribed local meeting store in `src/services/meetings.ts` for Meetings, Meeting Detail, Calendar and task updates.
- Calendar view, full edit and confirmed delete; working week navigation, minute-accurate event positions, overlap lanes and weekend/out-of-hours visibility when needed.
- Separate lifecycle (`scheduled`, `in_progress`, `ended`, `cancelled`) and AI (`unprocessed`, `processing`, `processed`, `failed`) statuses.
- Independent task statuses (`todo`, `in_progress`, `done`) and optional Jira metadata. Only `done` contributes to task completion.
- Open Jira is disabled unless the project's mock data supplies `jiraProjectUrl`.
- Follow-up suggestions have `suggested`, `approved` and `dismissed` states. Review/edit and approval create a scheduled meeting; dismissing or merely editing never does.

## Verification

- `npm run typecheck`: passed.
- `npm run build`: passed.
- `npm run dev`: started successfully on port 8443.
- `npm test`: 14 frontend flow checks plus the enclosing suite passed, covering validation, eight-person UI policy, shared create/edit/delete state, task completion, conditional Jira links, suggestions and duplicate approval prevention.
- Browser click-through and visual verification remain pending because access to the local preview was declined. The tests validate services and static component output, not actual browser interactions.

## Demo decisions

- State lasts for the current browser session and resets on a page reload. No backend, external integrations or persistent database are used.
- Participants are entered as comma-, semicolon- or newline-separated names, with existing demo participants reused by name.
- Date and start/end time use local calendar values. End time must be later on the same date.
- Existing layouts, navigation and visual theme are retained. No working drag behavior existed in the supplied Calendar.
- No new product approval is needed. Browser access is the remaining prerequisite for click-through QA.

## Files changed

- `index.html`
- `package.json`
- `src/App.tsx`
- `src/components/Modal.tsx`
- `src/components/calendar/CalendarApprovals.tsx`
- `src/components/calendar/CalendarMeetingModal.tsx`
- `src/components/calendar/CalendarSidebar.tsx`
- `src/components/calendar/CalendarWeekGrid.tsx`
- `src/components/meeting-detail/ActionItemsPanel.tsx`
- `src/components/meeting-detail/MeetingContent.tsx`
- `src/components/meeting-detail/MeetingContextPanel.tsx`
- `src/components/meeting-detail/ProjectOverviewPanel.tsx`
- `src/components/meetings/MeetingCard.tsx`
- `src/components/meetings/MeetingFormModal.tsx`
- `src/components/ui.tsx`
- `src/config/demo.ts`
- `src/hooks/useMeetings.ts`
- `src/mocks/calendar.ts`
- `src/mocks/meetings.ts`
- `src/pages/CalendarPage.tsx`
- `src/pages/MeetingDetailPage.tsx`
- `src/pages/MeetingsPage.tsx`
- `src/services/actionItems.ts`
- `src/services/calendar.ts`
- `src/services/meetings.ts`
- `src/types/calendar.ts`
- `src/types/meeting.ts`
- `src/utils/calendar.ts`
- `src/utils/meetingForm.ts`
- `src/utils/meetings.ts`
- `tests/meeting-flows.test.mjs`
- `FRONTEND_CHANGES.md` (this report)
