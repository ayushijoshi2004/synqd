import assert from "node:assert/strict"
import test from "node:test"
import { createServer } from "vite"
import React from "react"
import { renderToStaticMarkup } from "react-dom/server"

await test("Google Calendar frontend flow with mocked backend responses", async (t) => {
  async function boot() {
    const server = await createServer({ configFile: false, optimizeDeps: { noDiscovery: true, include: [] },
      server: { middlewareMode: true, hmr: false, ws: false, watch: null }, appType: "custom" })
    t.after(() => server.close())
    return { server, meetings: await server.ssrLoadModule("/src/services/meetings.ts"),
      calendar: await server.ssrLoadModule("/src/services/calendar.ts"),
      google: await server.ssrLoadModule("/src/services/googleCalendar.ts") }
  }
  const { server, meetings, calendar, google } = await boot()
  const { parseParticipants } = await server.ssrLoadModule("/src/utils/calendarParticipants.ts")
  const { default: Event } = await server.ssrLoadModule("/src/components/calendar/GoogleCalendarEvent.tsx")
  const { default: Form } = await server.ssrLoadModule("/src/components/meetings/MeetingFormModal.tsx")
  const fields = { title: "Reviewed title", date: "2026-10-12", startTime: "14:00", endTime: "15:00", project: "Test", team: "QA", agenda: "Review work",
    participants: [{ id: "p1", name: "Reviewer", color: "#2f6f5e", email: "reviewer@example.invalid" }] }
  const source = { ...fields, id: "source", status: "ended", aiStatus: "processed", preview: "",
    followUps: [{ ...fields, id: "followup", sourceMeetingId: "source", status: "suggested" }] }
  let scheduled, fail = true, requestCount = 0, release
  const realFetch = globalThis.fetch
  t.after(() => { globalThis.fetch = realFetch })
  globalThis.fetch = async (input, init) => {
    const url = String(input)
    assert.ok(url.startsWith("http://localhost:7071/api/"), "No real Google HTTP")
    if (url.endsWith("/google-calendar/status")) return Response.json({ configured: true, connected: true, timeZone: "America/New_York" })
    if (url.endsWith("/approve")) {
      assert.equal(init.method, "POST")
      const edited = JSON.parse(init.body)
      assert.equal(edited.participants[0].email, "reviewer@example.invalid")
      source.followUps[0] = { ...source.followUps[0], ...edited, status: "approved", scheduledMeetingId: "scheduled" }
      scheduled = { ...edited, id: "scheduled", status: "scheduled", aiStatus: "unprocessed", preview: "", googleCalendar: { status: "failed", error: "Google Calendar unavailable. Synq meeting saved." } }
      return Response.json({ sourceMeeting: source, meeting: scheduled })
    }
    if (url.endsWith("/follow-ups/followup/google-calendar")) {
      assert.equal(init.method, "POST"); requestCount++
      await new Promise((resolve) => { release = resolve })
      scheduled.googleCalendar = fail ? { status: "failed", error: "Reconnect Google Calendar." } : { status: "created", eventId: "google-confirmed", eventUrl: "https://calendar.google.com/calendar/event?eid=confirmed" }
      return Response.json(scheduled)
    }
    if (url.endsWith("/meetings")) return Response.json(scheduled ? [source, scheduled] : [source])
    throw new Error(`Unexpected request ${url}`)
  }
  await t.test("names work unchanged and invitation email is explicitly entered", () => {
    const known = [{ id: "a", name: "Alex", color: "red" }]
    assert.deepEqual(parseParticipants("Alex", known), known)
    assert.deepEqual(parseParticipants("Alex <alex@example.invalid>", known), [{ ...known[0], email: "alex@example.invalid" }])
    assert.equal(parseParticipants("guest@example.invalid", [])[0].email, "guest@example.invalid")
    assert.throws(() => parseParticipants("Alex <invalid>", known), /valid participant email/)
    assert.equal(parseParticipants("Unknown", [])[0].email, undefined)
  })
  await t.test("status and connect use only backend endpoints", async () => {
    assert.equal((await google.getGoogleCalendarStatus()).connected, true)
    assert.equal(google.googleAuthorizationUrl, "http://localhost:7071/api/google-calendar/authorize")
  })
  await t.test("approval stays approved when Google fails and retains edited attendees", async () => {
    await meetings.getMeetings()
    assert.equal(await calendar.approveFollowUp("followup", fields), "scheduled")
    assert.equal(calendar.getFollowUpsSnapshot()[0].status, "approved")
    const meeting = meetings.getMeetingsSnapshot().meetings.find((m) => m.id === "scheduled")
    assert.equal(meeting.googleCalendar.status, "failed")
    const markup = renderToStaticMarkup(React.createElement(Event, { meeting, sourceId: "source", followUpId: "followup" }))
    assert.match(markup, /Synq meeting saved/); assert.match(markup, /Retry Google Calendar/)
    assert.doesNotMatch(markup, /href=/)
  })
  await t.test("failed retry hydrates saved failure and does not claim success", async () => {
    const request = google.retryGoogleCalendar("source", "followup")
    release()
    await assert.rejects(request, /Reconnect Google Calendar/)
    assert.equal(meetings.getMeetingsSnapshot().meetings.find((m) => m.id === "scheduled").googleCalendar.status, "failed")
  })
  await t.test("repeated clicks send one request; confirmed event link is rendered", async () => {
    fail = false
    const before = requestCount
    const first = google.retryGoogleCalendar("source", "followup")
    await google.retryGoogleCalendar("source", "followup")
    assert.equal(requestCount, before + 1)
    release(); await first
    const meeting = meetings.getMeetingsSnapshot().meetings.find((m) => m.id === "scheduled")
    assert.equal(google.googleEventUrl(meeting), scheduled.googleCalendar.eventUrl)
    assert.match(renderToStaticMarkup(React.createElement(Event, { meeting })), /Open Google Calendar event/)
    assert.equal(google.googleEventUrl({ ...meeting, googleCalendar: { ...meeting.googleCalendar, eventUrl: "javascript:alert(1)" } }), undefined)
  })
  await t.test("fresh frontend reload retains approved state and Google event metadata", async () => {
    const reloaded = await boot(); await reloaded.meetings.getMeetings()
    assert.equal(reloaded.calendar.getFollowUpsSnapshot()[0].status, "approved")
    const meeting = reloaded.meetings.getMeetingsSnapshot().meetings.find((m) => m.id === "scheduled")
    assert.equal(reloaded.google.googleEventUrl(meeting), scheduled.googleCalendar.eventUrl)
  })
  await t.test("review form preserves saved emails and explains invitations", () => {
    const markup = renderToStaticMarkup(React.createElement(Form, { title: "Review follow-up", submitLabel: "Approve & Schedule", initial: fields,
      calendarNotice: "Approval sends Google invitations. Times use America/New_York.", onSubmit: async () => {}, onClose() {} }))
    assert.match(markup, /reviewer@example.invalid/)
    assert.match(markup, /Approval sends Google invitations/)
    assert.equal((markup.match(/required=""/g) || []).length, 5)
  })
})
