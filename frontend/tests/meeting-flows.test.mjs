import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { createServer } from "vite"
import React from "react"
import { renderToStaticMarkup } from "react-dom/server"

// Run against a freshly started, single-worker local Functions host.
// VITE_API_BASE_URL may override http://localhost:7071/api for an isolated host.
// These integration checks intentionally resolve demo follow-ups in that host.
await test("Synq frontend/API flows", async (t) => {
  async function bootFrontend() {
    const server = await createServer({
      configFile: false,
      optimizeDeps: { noDiscovery: true, include: [] },
      server: { middlewareMode: true, hmr: false, ws: false, watch: null },
      appType: "custom",
    })
    t.after(() => server.close())
    return {
      server,
      meetings: await server.ssrLoadModule("/src/services/meetings.ts"),
      calendar: await server.ssrLoadModule("/src/services/calendar.ts"),
    }
  }
  const { server, meetings, calendar } = await bootFrontend()
  // Never create real Jira issues from tests: stub only the Jira route and
  // behave like the backend (first call creates, repeats return the same item).
  const realFetch = globalThis.fetch
  const stubbedIssues = new Map()
  globalThis.fetch = async (input, init) => {
    const match = String(input).match(/\/meetings\/([^/]+)\/action-items\/([^/]+)\/jira$/)
    if (!match || init?.method !== "POST") return realFetch(input, init)
    const [, meetingId, id] = match
    const existing = stubbedIssues.get(`${meetingId}:${id}`)
    const item = existing ?? {
      id,
      jiraIssueKey: `KAN-${stubbedIssues.size + 1}`,
      jiraIssueUrl: `https://jira.example.invalid/browse/KAN-${stubbedIssues.size + 1}`,
    }
    stubbedIssues.set(`${meetingId}:${id}`, item)
    return new Response(JSON.stringify(item), { status: existing ? 200 : 201 })
  }
  t.after(() => {
    globalThis.fetch = realFetch
  })
  const { config } = await server.ssrLoadModule("/src/config/env.ts")
  const apiUrl = new URL(config.apiBaseUrl)
  assert.ok(["localhost", "127.0.0.1", "[::1]"].includes(apiUrl.hostname))
  assert.equal(apiUrl.protocol, "http:")
  const seed = JSON.parse(await readFile(new URL("../../backend/fixtures/meetings.json", import.meta.url), "utf8"))
  const localMeeting = (id) => structuredClone(meetings.getMeetingsSnapshot().meetings.find((item) => item.id === id))
  const tasks = await server.ssrLoadModule("/src/services/actionItems.ts")
  const { validateMeetingForm } = await server.ssrLoadModule(
    "/src/utils/meetingForm.ts",
  )
  const { validateMeeting, formatDate, formatTimeRange } =
    await server.ssrLoadModule("/src/utils/meetings.ts")
  const { default: Form } = await server.ssrLoadModule(
    "/src/components/meetings/MeetingFormModal.tsx",
  )
  const { default: Overview } = await server.ssrLoadModule(
    "/src/components/meeting-detail/ProjectOverviewPanel.tsx",
  )
  const { default: MeetingModal } = await server.ssrLoadModule(
    "/src/components/calendar/CalendarMeetingModal.tsx",
  )
  const people = Array.from({ length: 9 }, (_, index) => ({
    id: `test-${index}`,
    name: `Participant ${index + 1}`,
    color: "#2f6f5e",
  }))
  const fields = {
    title: "Frontend QA",
    date: "2026-10-10",
    startTime: "17:15",
    endTime: "18:35",
    participants: people.slice(0, 8),
    agenda: "Review notes\nAssign owners",
    project: "QA project",
    team: "QA team",
  }
  let createdId
  let approvedId
  let approvedFields

  await t.test("follow-ups hydrate exclusively from backend source meetings", async () => {
    assert.deepEqual(calendar.getFollowUpsSnapshot(), [])
    const all = await meetings.getMeetings()
    const expected = all.flatMap((meeting) => meeting.followUps ?? [])
    assert.deepEqual(calendar.getFollowUpsSnapshot(), expected)
    assert.deepEqual(expected.map((item) => item.id).sort(), ["f1", "f2", "f3"])
    for (const proposal of expected) {
      assert.equal(proposal.status, "suggested")
      assert.ok(all.find((meeting) => meeting.id === proposal.sourceMeetingId).followUps.some((item) => item.id === proposal.id))
    }
  })

  await t.test("Synq document branding and required form fields", async () => {
    const html = await readFile(
      new URL("../index.html", import.meta.url),
      "utf8",
    )
    assert.match(html, /<title>Synq<\/title>/)
    assert.match(html, /property="og:title" content="Synq"/)
    const markup = renderToStaticMarkup(
      React.createElement(Form, {
        title: "New Meeting",
        submitLabel: "Create Meeting",
        onSubmit: async () => {},
        onClose: () => {},
      }),
    )
    assert.equal((markup.match(/required=""/g) ?? []).length, 5)
    assert.match(markup, /Cancel/)
    assert.match(markup, /Create Meeting/)
    assert.match(markup, /0\/8 participants/)
    const page = await readFile(
      new URL("../src/pages/MeetingsPage.tsx", import.meta.url),
      "utf8",
    )
    assert.doesNotMatch(
      page,
      /Every conversation, turned into decisions, tasks and memory/,
    )
  })

  await t.test("lifecycle and AI statuses are independent", async () => {
    const all = await meetings.getMeetings()
    assert.equal(all.length, seed.length)
    assert.ok(
      all.every((meeting) =>
        ["scheduled", "in_progress", "ended", "cancelled"].includes(
          meeting.status,
        ),
      ),
    )
    assert.ok(
      all.every((meeting) =>
        ["unprocessed", "processing", "processed", "failed"].includes(
          meeting.aiStatus,
        ),
      ),
    )
    assert.equal(all.find((meeting) => meeting.id === "m3").status, "ended")
    assert.equal(
      all.find((meeting) => meeting.id === "m3").aiStatus,
      "processing",
    )
  })

  await t.test(
    "required fields, dates, times, and duplicate participants reject invalid input",
    async () => {
      for (const overrides of [
        { title: "   " },
        { date: "" },
        { date: "2026-02-30" },
        { startTime: "" },
        { endTime: "" },
        { endTime: "17:14" },
        { endTime: "17:15" },
        { startTime: "24:00" },
        { participants: [] },
        { participants: [people[0], { ...people[0], id: "duplicate" }] },
      ]) {
        assert.throws(() => validateMeetingForm({ ...fields, ...overrides }))
        await assert.rejects(
          meetings.createMeeting({ ...fields, ...overrides }),
        )
      }
      assert.equal((await meetings.getMeetings()).length, seed.length)
    },
  )

  await t.test(
    "eight participants accepted; demo limit does not constrain the model",
    async () => {
      assert.doesNotThrow(() => validateMeetingForm(fields))
      assert.throws(
        () => validateMeetingForm({ ...fields, participants: people }),
        /up to 8 participants/,
      )
      assert.doesNotThrow(() =>
        validateMeeting({ ...fields, participants: people }),
      )
      const larger = await meetings.createMeeting({
        ...fields,
        participants: people,
      })
      assert.equal(larger.participants.length, 9)
      await meetings.deleteMeeting(larger.id)
    },
  )

  await t.test(
    "creation synchronizes Meetings, Detail, Calendar, and subscriptions",
    async () => {
      let notifications = 0
      const unsubscribe = meetings.subscribeMeetings(() => {
        notifications++
      })
      const created = await meetings.createMeeting(fields)
      createdId = created.id
      unsubscribe()
      assert.equal(notifications, 1)
      assert.equal(
        (await meetings.getMeetings()).find(
          (meeting) => meeting.id === createdId,
        ).title,
        fields.title,
      )
      const detail = await meetings.getMeeting(createdId)
      assert.equal(detail.status, "scheduled")
      assert.equal(detail.aiStatus, "unprocessed")
      assert.deepEqual(detail.actionItems, [])
      assert.deepEqual(detail.transcript, [])
      assert.equal(detail.projectOverview.name, fields.project)
      assert.equal(detail.agendaEntries.length, 2)
      const view = calendar.getCalendarView(fields.date)
      const event = view.events.find((event) => event.id === createdId)
      assert.equal(event.title, fields.title)
      assert.equal(event.day, 5)
      assert.equal(event.startHour, 17.25)
      assert.equal(event.durationHours, 80 / 60)
      assert.equal(view.days.length, 7)
      assert.ok(view.hours.includes(18))
    },
  )

  await t.test(
    "optional fields can be empty and service reads are isolated snapshots",
    async () => {
      const minimal = await meetings.createMeeting({
        ...fields,
        agenda: "",
        project: "",
        team: "",
        participants: [people[0]],
      })
      assert.equal(minimal.projectOverview.name, "No project")
      assert.deepEqual(minimal.agendaEntries, [])
      const detail = await meetings.getMeeting(minimal.id)
      detail.title = "Changed outside service"
      assert.equal((await meetings.getMeeting(minimal.id)).title, fields.title)
      await meetings.deleteMeeting(minimal.id)
    },
  )

  await t.test(
    "editing every field updates all views and moves weeks",
    async () => {
      const edited = {
        ...fields,
        title: "Edited QA",
        date: "2026-11-01",
        startTime: "22:10",
        endTime: "23:55",
        participants: [people[1]],
        agenda: "Updated agenda",
        project: "Roadmap",
        team: "Leadership",
      }
      await meetings.updateMeeting(createdId, edited)
      const detail = await meetings.getMeeting(createdId)
      for (const key of Object.keys(edited))
        assert.deepEqual(detail[key], edited[key])
      assert.deepEqual(
        detail.agendaEntries.map((entry) => entry.title),
        ["Updated agenda"],
      )
      assert.equal(detail.projectOverview.name, "Roadmap")
      assert.equal(meetings.getMeetingsSnapshot().focusDate, edited.date)
      assert.ok(
        !(await calendar.getCalendarView(fields.date)).events.some(
          (event) => event.id === createdId,
        ),
      )
      const event = calendar
        .getCalendarView(edited.date)
        .events.find((event) => event.id === createdId)
      assert.equal(event.title, edited.title)
      assert.equal(event.day, 6)
      assert.equal(event.startHour, 22 + 10 / 60)
      assert.equal(formatDate(edited.date), "Nov 1, 2026")
      assert.equal(formatTimeRange(edited), "10:10 PM – 11:55 PM")
      assert.match(
        renderToStaticMarkup(
          React.createElement(MeetingModal, {
            meeting: detail,
            onEdit() {},
            onView() {},
            onClose() {},
          }),
        ),
        /Edit Meeting/,
      )
    },
  )

  await t.test(
    "delete removes the record from Meetings, Detail, and Calendar",
    async () => {
      const date = (await meetings.getMeeting(createdId)).date
      await meetings.deleteMeeting(createdId)
      assert.equal(await meetings.getMeeting(createdId), null)
      assert.ok(
        !(await meetings.getMeetings()).some(
          (meeting) => meeting.id === createdId,
        ),
      )
      assert.ok(
        !calendar
          .getCalendarView(date)
          .events.some((event) => event.id === createdId),
      )
    },
  )

  await t.test(
    "Jira ticket creation is idempotent and never completes tasks",
    async () => {
      const before = localMeeting("m1")
      const doneBefore = before.actionItems.filter(
        (task) => task.status === "done",
      ).length
      await tasks.createActionItemTickets("m1", ["t1", "t1"])
      const after = localMeeting("m1")
      assert.equal(
        after.actionItems.find((task) => task.id === "t1").status,
        "todo",
      )
      assert.equal(
        after.actionItems.find((task) => task.id === "t1").jiraIssueKey,
        "KAN-1",
      )
      assert.equal(
        after.actionItems.filter((task) => task.status === "done").length,
        doneBefore,
      )
      await tasks.createActionItemTickets("m1", ["t1", "t2"])
      const latest = localMeeting("m1")
      assert.equal(
        latest.actionItems.find((task) => task.id === "t1").jiraIssueKey,
        "KAN-1",
      )
      assert.equal(
        latest.actionItems.find((task) => task.id === "t2").jiraIssueKey,
        "KAN-2",
      )
      assert.equal(
        latest.actionItems.find((task) => task.id === "t2").status,
        "in_progress",
      )
    },
  )

  await t.test(
    "only done affects the rendered completion count in local task snapshots",
    async () => {
      async function markup() {
        const detail = localMeeting("m1")
        return renderToStaticMarkup(
          React.createElement(Overview, {
            project: detail.projectOverview,
            actionItems: detail.actionItems,
          }),
        )
      }
      assert.match(await markup(), /1 of 5 tasks completed/)
      await tasks.updateActionItemStatus("m1", "t1", "in_progress")
      assert.match(await markup(), /1 of 5 tasks completed/)
      await tasks.updateActionItemStatus("m1", "t1", "done")
      assert.match(await markup(), /2 of 5 tasks completed/)
      assert.equal(
        localMeeting("m1").actionItems.find(
          (task) => task.id === "t1",
        ).jiraIssueKey,
        "KAN-1",
      )
      await tasks.updateActionItemStatus("m1", "t1", "todo")
      assert.match(await markup(), /1 of 5 tasks completed/)
      assert.equal(
        meetings
          .getProjectGroups()
          .find((project) => project.name === "Atlas Launch").openActionItems,
        4,
      )
    },
  )

  await t.test(
    "Open Jira is disabled without a URL and uses only supplied project data",
    async () => {
      const detail = await meetings.getMeeting("m1")
      const disabled = renderToStaticMarkup(
        React.createElement(Overview, {
          project: detail.projectOverview,
          actionItems: [],
        }),
      )
      assert.match(disabled, /<button disabled=""/)
      assert.doesNotMatch(disabled, /href=/)
      assert.match(disabled, /width:0%/)
      const enabled = renderToStaticMarkup(
        React.createElement(Overview, {
          project: {
            ...detail.projectOverview,
            jiraProjectUrl: "https://jira.example.invalid/project",
          },
          actionItems: [],
        }),
      )
      assert.match(enabled, /href="https:\/\/jira.example.invalid\/project"/)
      assert.match(enabled, /Open Jira/)
    },
  )

  await t.test(
    "suggestions stay separate until explicitly approved",
    async () => {
      const all = await meetings.getMeetings()
      for (const proposal of calendar.getFollowUpsSnapshot()) {
        assert.equal(proposal.status, "suggested")
        assert.ok(!all.some((meeting) => meeting.id === proposal.id))
      }
      const before = all.length
      const proposal = await calendar.proposeFollowUp(
        "Review test agenda",
        "2026-10-05",
      )
      assert.equal((await meetings.getMeetings()).length, before)
      await calendar.editFollowUp(proposal.id, {
        ...fields,
        title: "Reviewed follow-up",
        participants: [people[0]],
      })
      assert.equal((await meetings.getMeetings()).length, before)
      const edited = calendar
        .getFollowUpsSnapshot()
        .find((item) => item.id === proposal.id)
      assert.equal(edited.status, "suggested")
      assert.equal(edited.title, "Reviewed follow-up")
      const id = await calendar.approveFollowUp(edited.id, edited)
      approvedId = id
      approvedFields = edited
      assert.equal((await meetings.getMeetings()).length, before + 1)
      const meeting = await meetings.getMeeting(id)
      assert.equal(meeting.title, edited.title)
      assert.equal(meeting.status, "scheduled")
      assert.equal(meeting.aiStatus, "unprocessed")
      const savedProposal = calendar
        .getFollowUpsSnapshot()
        .find((item) => item.id === edited.id)
      assert.equal(savedProposal.status, "approved")
      assert.equal(savedProposal.scheduledMeetingId, id)
      const events = calendar.getCalendarView(edited.date).events
      assert.ok(
        events.some((event) => event.id === id && event.kind === "event"),
      )
      assert.ok(!events.some((event) => event.id === edited.id))
      await assert.rejects(calendar.approveFollowUp(edited.id, edited))
    },
  )

  await t.test("dismissed follow-ups never become meetings", async () => {
    const before = (await meetings.getMeetings()).length
    await calendar.dismissFollowUp("f1")
    assert.equal(
      calendar.getFollowUpsSnapshot().find((item) => item.id === "f1").status,
      "dismissed",
    )
    assert.equal((await meetings.getMeetings()).length, before)
    assert.ok(
      !calendar
        .getCalendarView("2026-10-05")
        .events.some((event) => event.id === "f1"),
    )
  })

  await t.test("failed requests leave suggestion and meeting state unchanged", async () => {
    const proposal = calendar.getFollowUpsSnapshot().find((item) => item.id === "f3")
    const originalFetch = globalThis.fetch
    const before = structuredClone(meetings.getMeetingsSnapshot())
    const beforeProposals = structuredClone(calendar.getFollowUpsSnapshot())
    globalThis.fetch = async () => new Response(JSON.stringify({ error: "Test failure" }), { status: 500 })
    try {
      await assert.rejects(calendar.dismissFollowUp(proposal.id), /500/)
      await assert.rejects(calendar.approveFollowUp(proposal.id, proposal), /500/)
      assert.deepEqual(meetings.getMeetingsSnapshot(), before)
      assert.deepEqual(calendar.getFollowUpsSnapshot(), beforeProposals)
    } finally {
      globalThis.fetch = originalFetch
    }
  })

  await t.test(
    "simultaneous approval cannot create duplicate scheduled meetings",
    async () => {
      const proposal = calendar
        .getFollowUpsSnapshot()
        .find((item) => item.id === "f2")
      const before = (await meetings.getMeetings()).length
      const results = await Promise.allSettled([
        calendar.approveFollowUp(proposal.id, proposal),
        calendar.approveFollowUp(proposal.id, proposal),
      ])
      assert.equal(
        results.filter((result) => result.status === "fulfilled").length,
        1,
      )
      assert.equal((await meetings.getMeetings()).length, before + 1)
      const duplicate = await fetch(`${config.apiBaseUrl}/meetings/${proposal.sourceMeetingId}/follow-ups/${proposal.id}/approve`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
      })
      assert.equal(duplicate.status, 409)
      assert.equal((await meetings.getMeetings()).length, before + 1)
    },
  )

  await t.test("fresh frontend state reloads dismissed, approved, and suggested statuses", async () => {
    const fresh = await bootFrontend()
    assert.deepEqual(fresh.calendar.getFollowUpsSnapshot(), [])
    const all = await fresh.meetings.getMeetings()
    const proposals = fresh.calendar.getFollowUpsSnapshot()
    assert.equal(proposals.find((item) => item.id === "f1").status, "dismissed")
    const approved = proposals.find((item) => item.id === "f2")
    assert.equal(approved.status, "approved")
    assert.ok(all.some((meeting) => meeting.id === approved.scheduledMeetingId))
    assert.equal(proposals.find((item) => item.id === "f3").status, "suggested")
    const reviewed = all.find((item) => item.id === approvedId)
    for (const field of ["title", "date", "startTime", "endTime", "participants", "agenda", "project", "team"])
      assert.deepEqual(reviewed[field], approvedFields[field])
    const savedProposal = proposals.find((item) => item.id === approvedFields.id)
    assert.equal(savedProposal.status, "approved")
    assert.equal(savedProposal.scheduledMeetingId, approvedId)
    const events = fresh.calendar.getCalendarView("2026-10-05").events
    assert.ok(!events.some((event) => ["f1", "f2", approvedFields.id].includes(event.id)))
    assert.ok(events.some((event) => event.id === approved.scheduledMeetingId && event.kind === "event"))
    assert.ok(events.some((event) => event.id === "f3" && event.kind === "proposed"))
    assert.equal((await fresh.meetings.getMeeting(approvedId)).title, approvedFields.title)
  })

  await t.test("a late list response cannot resurrect a dismissed follow-up", async () => {
    const stale = await meetings.getMeetings()
    const originalFetch = globalThis.fetch
    let release
    const delayed = new Promise((resolve) => { release = resolve })
    globalThis.fetch = (url, options) =>
      String(url) === `${config.apiBaseUrl}/meetings` && !options?.method
        ? delayed
        : originalFetch(url, options)
    try {
      const pending = meetings.getMeetings()
      await calendar.dismissFollowUp("f3")
      release(new Response(JSON.stringify(stale)))
      await pending
      assert.equal(calendar.getFollowUpsSnapshot().find((item) => item.id === "f3").status, "dismissed")
    } finally {
      globalThis.fetch = originalFetch
      release(new Response("[]"))
    }
  })
})
