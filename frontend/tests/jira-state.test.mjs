import assert from "node:assert/strict"
import test from "node:test"
import { createServer } from "vite"
import React from "react"
import { renderToStaticMarkup } from "react-dom/server"

// Self-contained: fetch is fully stubbed, so no backend and no real Jira.
const task = (id, text, status = "todo", extra = {}) => ({
  id, text, status, due: "Oct 1", assignee: { id: "a", name: "Alex", color: "#000" }, ...extra,
})
const meeting = (actionItems, projectOverview) => ({
  id: "m1", title: "Atlas", date: "2026-10-01", startTime: "10:00", endTime: "11:00",
  project: "Atlas Launch", team: "", agenda: "", status: "ended", aiStatus: "processed",
  preview: "", participants: [{ id: "a", name: "Alex", color: "#000" }],
  actionItems, ...(projectOverview ? { projectOverview } : {}),
})

await test("Jira state in the shared meeting snapshot", async (t) => {
  const server = await createServer({
    configFile: false,
    optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, hmr: false, ws: false, watch: null },
    appType: "custom",
  })
  t.after(() => server.close())
  const meetings = await server.ssrLoadModule("/src/services/meetings.ts")
  const { default: Actions } = await server.ssrLoadModule("/src/components/meeting-detail/ActionItemsPanel.tsx")
  const { default: Overview } = await server.ssrLoadModule("/src/components/meeting-detail/ProjectOverviewPanel.tsx")

  const realFetch = globalThis.fetch
  t.after(() => { globalThis.fetch = realFetch })
  let backend = [meeting([task("t1", "Fix bug"), task("t2", "Patch rounding", "in_progress")])]
  const posts = []
  globalThis.fetch = async (input, init) => {
    const url = String(input)
    const post = url.match(/\/meetings\/([^/]+)\/action-items\/([^/]+)\/jira$/)
    if (post && init?.method === "POST") {
      posts.push(post[2])
      const item = backend[0].actionItems.find((x) => x.id === post[2])
      if (post[2] === "bad") return new Response("{}", { status: 502 })
      if (!item.jiraIssueKey) {
        item.jiraIssueKey = "KAN-8"
        item.jiraIssueUrl = "https://synq.example.invalid/browse/KAN-8"
        return new Response(JSON.stringify(item), { status: 201 })
      }
      return new Response(JSON.stringify(item), { status: 200 })
    }
    if (url.endsWith("/meetings")) return new Response(JSON.stringify(backend), { status: 200 })
    throw new Error(`Unexpected fetch ${url}`)
  }
  const local = () => meetings.getMeetingsSnapshot().meetings.find((m) => m.id === "m1")

  await t.test("backend action items and Jira metadata survive a reload", async () => {
    await meetings.getMeetings()
    assert.deepEqual(local().actionItems.map((x) => x.id), ["t1", "t2"])
    await meetings.createJiraTickets("m1", ["t1", "t1"])
    assert.equal(posts.length, 1, "duplicate ids in one call send one request")
    assert.equal(local().actionItems[0].jiraIssueKey, "KAN-8")
    assert.equal(local().actionItems[0].status, "todo", "creating a ticket never completes a task")
    await meetings.getMeetings() // refresh from the backend
    assert.equal(local().actionItems[0].jiraIssueKey, "KAN-8")
    assert.equal(local().actionItems[0].jiraIssueUrl, "https://synq.example.invalid/browse/KAN-8")
    assert.equal(local().actionItems[1].status, "in_progress")
  })

  await t.test("an item that already has a key sends no request", async () => {
    const before = posts.length
    await meetings.createJiraTickets("m1", ["t1"])
    assert.equal(posts.length, before)
  })

  await t.test("the key renders as a safe new-tab link, not the create button", () => {
    const html = renderToStaticMarkup(React.createElement(Actions, { meetingId: "m1", actionItems: local().actionItems }))
    assert.match(html, /href="https:\/\/synq\.example\.invalid\/browse\/KAN-8"/)
    assert.match(html, /target="_blank"/)
    assert.match(html, /rel="noopener noreferrer"/)
    assert.match(html, />KAN-8</)
    assert.equal((html.match(/Create Jira Ticket/g) ?? []).length, 1) // only t2 still offers it
  })

  await t.test("a failed ticket does not discard one that was created", async () => {
    backend[0].actionItems.push(task("bad", "Will fail"))
    await meetings.getMeetings()
    await assert.rejects(meetings.createJiraTickets("m1", ["t2", "bad"]), /502/)
    assert.equal(local().actionItems.find((x) => x.id === "t2").jiraIssueKey, "KAN-8")
    assert.equal(local().actionItems.find((x) => x.id === "bad").jiraIssueKey, undefined)
  })

  await t.test("Open Jira uses the stored project URL and ignores unsafe ones", async () => {
    backend = [meeting([], { name: "Atlas Launch", description: "", previousLaunchDate: "", launchDate: "",
      resources: [], additionalResourceCount: 0, previousMeetingCount: 0, relatedResources: [],
      jiraProjectUrl: "https://synq.example.invalid/jira/software/projects/KAN/boards/1" })]
    await meetings.getMeetings()
    const stored = local().projectOverview.jiraProjectUrl
    assert.equal(stored, "https://synq.example.invalid/jira/software/projects/KAN/boards/1")
    const render = (url) => renderToStaticMarkup(React.createElement(Overview, {
      project: { ...local().projectOverview, jiraProjectUrl: url }, actionItems: [],
    }))
    assert.match(render(stored), /href="https:\/\/synq\.example\.invalid\/jira\/software\/projects\/KAN\/boards\/1"/)
    assert.match(render(stored), /rel="noopener noreferrer"/)
    assert.doesNotMatch(render(stored), /\/browse\//)
    for (const bad of [undefined, "", "javascript:alert(1)"]) {
      const html = render(bad)
      assert.match(html, /<button disabled=""/)
      assert.doesNotMatch(html, /href=/)
    }
  })
})
