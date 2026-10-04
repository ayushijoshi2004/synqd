import assert from "node:assert/strict"
import test from "node:test"
import { createServer } from "vite"
import React from "react"
import { renderToStaticMarkup } from "react-dom/server"

// All HTTP is stubbed. No cloud calls or credentials are used.
await test("Persisted AI intelligence in the existing Synq frontend", async (t) => {
  async function boot() {
    const server = await createServer({ configFile: false, optimizeDeps: { noDiscovery: true, include: [] },
      // The app is client-only. Give static-render checks a snapshot hook;
      // subscriptions and API mutations are exercised through the real store.
      plugins: [{ name: "test-meeting-snapshot", enforce: "pre", transform(code, id) {
        if (id.endsWith("/src/hooks/useMeetings.ts"))
          return code.replace("useSyncExternalStore(subscribeMeetings, getMeetingsSnapshot)", "useSyncExternalStore(subscribeMeetings, getMeetingsSnapshot, getMeetingsSnapshot)")
      } }],
      server: { middlewareMode: true, hmr: false, ws: false, watch: null }, appType: "custom" })
    t.after(() => server.close())
    return { server, meetings: await server.ssrLoadModule("/src/services/meetings.ts"), calendar: await server.ssrLoadModule("/src/services/calendar.ts") }
  }
  const { server, meetings, calendar } = await boot()
  const { default: Content } = await server.ssrLoadModule("/src/components/meeting-detail/MeetingContent.tsx")
  const { default: Context } = await server.ssrLoadModule("/src/components/meeting-detail/MeetingContextPanel.tsx")
  const { default: Actions } = await server.ssrLoadModule("/src/components/meeting-detail/ActionItemsPanel.tsx")
  const { default: Approvals } = await server.ssrLoadModule("/src/components/calendar/CalendarApprovals.tsx")
  const { default: Form } = await server.ssrLoadModule("/src/components/meetings/MeetingFormModal.tsx")
  const { default: Detail } = await server.ssrLoadModule("/src/pages/MeetingDetailPage.tsx")
  const person = { id: "p", name: "Reviewer", color: "#2f6f5e" }
  let backend = {
    id: "m1", title: "Real backend meeting", date: "2026-10-07", startTime: "10:00", endTime: "11:00",
    project: "Atlas Launch", team: "QA", agenda: "QA\nBudget", participants: [person],
    status: "ended", aiStatus: "unprocessed", preview: "", transcript: [{ speaker: person, timestamp: "00:10", text: "QA tests passed. We should meet again." }],
    agendaEntries: [{ title: "QA", timestamp: "", completed: false }, { title: "Budget", timestamp: "", completed: false }],
    actionItems: [], decisions: [], followUps: [],
  }
  let fail = false
  let release
  let requestCount = 0
  const originalFetch = globalThis.fetch
  t.after(() => { globalThis.fetch = originalFetch })
  globalThis.fetch = async (input, options) => {
    const url = String(input)
    if (url.endsWith("/process")) {
      assert.equal(options.method, "POST")
      requestCount++
      backend.aiStatus = "processing"
      await new Promise((resolve) => { release = resolve })
      if (fail) {
        backend.aiStatus = "failed"
        return new Response(JSON.stringify({ error: { code: "ai_processing_failed" } }), { status: 503 })
      }
      backend = {
        ...backend, aiStatus: "processed",
        summary: { beforeHighlight: "QA tests passed.", highlight: "", afterHighlight: "", points: ["A review was suggested."] },
        decisions: [{ id: "decision-ai", text: "QA passed", participant: null, timestamp: "", note: "" }],
        actionItems: [{ id: "task-ai", text: "Review support coverage", assignee: null, due: "", status: "todo" }],
        unresolvedItems: ["Who owns support?"],
        followUps: [{ id: "follow-ai", title: "Support review", date: "", startTime: "", endTime: "", agenda: "Review coverage", participants: [], project: "Atlas Launch", team: "QA", sourceMeetingId: "m1", status: "suggested" }],
        agendaEntries: [{ title: "QA", timestamp: "00:10", completed: true }, { title: "Budget", timestamp: "", completed: false }],
      }
      return new Response(JSON.stringify(backend))
    }
    if (url.endsWith("/action-items/task-ai/jira")) {
      backend.actionItems[0].jiraIssueKey = "KAN-99"
      backend.actionItems[0].jiraIssueUrl = "https://jira.example.invalid/browse/KAN-99"
      return new Response(JSON.stringify(backend.actionItems[0]), { status: 201 })
    }
    if (url.endsWith("/meetings")) return new Response(JSON.stringify([backend]))
    if (url.endsWith("/meetings/m1")) {
      if (options?.method === "PATCH") backend = { ...backend, ...JSON.parse(options.body) }
      return new Response(JSON.stringify(backend))
    }
    throw new Error(`Unexpected request ${url}`)
  }
  const current = () => meetings.getMeetingsSnapshot().meetings[0]

  await t.test("missing backend intelligence never falls back to m1 demo results", async () => {
    await meetings.getMeetings()
    assert.equal(current().summary.beforeHighlight, "")
    assert.deepEqual(current().decisions, [])
    assert.deepEqual(current().transcript, backend.transcript)
    assert.deepEqual(current().agendaEntries, backend.agendaEntries)
  })

  await t.test("processing is visible, repeated clicks send one request, and results hydrate", async () => {
    const pending = meetings.processMeeting("m1")
    assert.equal(current().aiStatus, "processing")
    const html = renderToStaticMarkup(React.createElement(Detail, { meetingId: "m1", onBack() {} }))
    assert.match(html, /Processing…/)
    await assert.rejects(meetings.processMeeting("m1"), /already/)
    assert.equal(requestCount, 1)
    release()
    await pending
    assert.equal(current().aiStatus, "processed")
    assert.deepEqual(current().summary, backend.summary)
    assert.deepEqual(current().agendaEntries, backend.agendaEntries)
    assert.deepEqual(current().unresolvedItems, backend.unresolvedItems)
    assert.equal(calendar.getFollowUpsSnapshot()[0].sourceMeetingId, "m1")
  })

  await t.test("existing panels display stored intelligence and unknown ownership safely", () => {
    const summary = renderToStaticMarkup(React.createElement(Content, { meeting: current(), tab: "summary", onTabChange() {}, highlightedTimestamp: null, onTranscriptSelect() {} }))
    assert.match(summary, /QA tests passed/)
    assert.match(summary, /Who owns support/)
    const context = renderToStaticMarkup(React.createElement(Context, { meeting: current(), onJump() {} }))
    assert.match(context, /Unattributed/)
    assert.match(context, /00:10/)
    const actions = renderToStaticMarkup(React.createElement(Actions, { meetingId: "m1", actionItems: current().actionItems }))
    assert.match(actions, /Unassigned/)
    assert.match(actions, /Create Jira Ticket/)
  })

  await t.test("undated follow-ups stay in approvals and out of the calendar grid", async () => {
    const proposals = calendar.getFollowUpsSnapshot()
    assert.equal(proposals[0].date, "")
    assert.ok(!calendar.getCalendarView("2026-10-05").events.some((event) => event.id === "follow-ai"))
    const html = renderToStaticMarkup(React.createElement(Approvals, { proposals, pending: false, onApprove() {}, onEdit() {}, onDismiss() {} }))
    assert.match(html, /Date to be chosen/)
    assert.match(html, /Time to be chosen/)
    assert.doesNotMatch(html, /Invalid Date|NaN/)
    await calendar.editFollowUp("follow-ai", { ...proposals[0], title: "Reviewed support suggestion" })
    assert.equal(calendar.getFollowUpsSnapshot()[0].title, "Reviewed support suggestion")
    await assert.rejects(calendar.approveFollowUp("follow-ai", proposals[0]), /valid meeting date/)
    const review = renderToStaticMarkup(React.createElement(Form, { title: "Review", submitLabel: "Approve", initial: proposals[0], onClose() {}, onSubmit() {} }))
    assert.equal((review.match(/required=""/g) ?? []).length, 5)
    const draft = renderToStaticMarkup(React.createElement(Form, { title: "Edit suggestion", submitLabel: "Save", initial: proposals[0], allowIncomplete: true, onClose() {}, onSubmit() {} }))
    assert.equal((draft.match(/required=""/g) ?? []).length, 1)
  })

  await t.test("AI tasks use the existing Jira endpoint without completing tasks", async () => {
    await meetings.createJiraTickets("m1", ["task-ai"])
    assert.equal(current().actionItems[0].jiraIssueKey, "KAN-99")
    assert.equal(current().actionItems[0].status, "todo")
  })

  await t.test("a fresh frontend hydrates saved summary, agenda ticks, follow-ups and Jira", async () => {
    const fresh = await boot()
    await fresh.meetings.getMeetings()
    const restored = fresh.meetings.getMeetingsSnapshot().meetings[0]
    assert.deepEqual(restored.summary, backend.summary)
    assert.deepEqual(restored.agendaEntries, backend.agendaEntries)
    assert.deepEqual(restored.decisions, backend.decisions)
    assert.deepEqual(restored.unresolvedItems, backend.unresolvedItems)
    assert.equal(restored.actionItems[0].jiraIssueKey, "KAN-99")
    assert.deepEqual(fresh.calendar.getFollowUpsSnapshot(), backend.followUps)
  })

  await t.test("failure preserves intelligence, shows the saved-data message, and offers retry", async () => {
    fail = true
    const before = structuredClone(current())
    const pending = meetings.processMeeting("m1")
    release()
    await assert.rejects(pending, /Your meeting and transcript are still saved/)
    assert.deepEqual(current(), { ...before, aiStatus: "failed" })
    const html = renderToStaticMarkup(React.createElement(Detail, { meetingId: "m1", onBack() {} }))
    assert.match(html, /Retry processing/)
    assert.match(html, /Your meeting and transcript are still saved/)
    fail = false
    const retry = meetings.processMeeting("m1")
    release()
    await retry
    assert.equal(current().aiStatus, "processed")
    // The newer local Jira response is not lost to a late processing payload.
    assert.equal(current().actionItems[0].jiraIssueKey, "KAN-99")
  })

  await t.test("editing meeting metadata preserves saved agenda titles and completion", async () => {
    backend.agendaEntries[0].title = "QA status as saved"
    await meetings.getMeetings()
    const expected = structuredClone(current().agendaEntries)
    await meetings.updateMeeting("m1", { ...current(), title: "Renamed meeting" })
    assert.equal(current().title, "Renamed meeting")
    assert.deepEqual(current().agendaEntries, expected)
    assert.deepEqual(backend.agendaEntries, expected)
  })
})
