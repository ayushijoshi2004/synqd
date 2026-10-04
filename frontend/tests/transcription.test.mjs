import assert from "node:assert/strict"
import test from "node:test"
import { createServer } from "vite"
import React from "react"
import { renderToStaticMarkup } from "react-dom/server"

await test("meeting-owned transcription flow", async (t) => {
  async function boot() {
    const server = await createServer({ configFile: false, optimizeDeps: { noDiscovery: true, include: [] },
      server: { middlewareMode: true, hmr: false, ws: false, watch: null }, appType: "custom" })
    t.after(() => server.close())
    return { server, meetings: await server.ssrLoadModule("/src/services/meetings.ts"), vexa: await server.ssrLoadModule("/src/services/vexa.ts") }
  }
  const { server, meetings, vexa } = await boot()
  const { default: Header } = await server.ssrLoadModule("/src/components/AppHeader.tsx")
  const { default: Controls } = await server.ssrLoadModule("/src/components/meeting-detail/TranscriptionControls.tsx")
  const { default: Content } = await server.ssrLoadModule("/src/components/meeting-detail/MeetingContent.tsx")
  let record = { id: "synq-1", title: "Transcription test", date: "2026-10-05", startTime: "12:00", endTime: "13:00",
    project: "Test", team: "Test", agenda: "Review", participants: [{ id: "p1", name: "Alex", color: "green" }],
    status: "scheduled", aiStatus: "unprocessed", preview: "", transcript: [], googleMeetUrl: "https://meet.google.com/abc-defg-hij" }
  const realFetch = globalThis.fetch
  t.after(() => { globalThis.fetch = realFetch })
  let joinCalls = 0, endCalls = 0, release, fail = false
  globalThis.fetch = async (input, init) => {
    const url = String(input)
    assert.ok(url.startsWith("http://localhost:7071/api/"), "Only Synq endpoints are used")
    if (url.endsWith("/meetings/join")) {
      assert.deepEqual(JSON.parse(init.body), { synqMeetingId: "synq-1" }); joinCalls++
      await new Promise((resolve) => { release = resolve })
      if (fail) return Response.json({ error: { message: "Vexa is unavailable. Saved transcript retained." } }, { status: 502 })
      record = { ...record, transcription: { id: "session-1", status: "transcribing", botId: 101, attempted: true, polling: true } }
    } else if (url.endsWith("/transcription/end")) {
      assert.equal(init.method, "POST"); endCalls++
      await new Promise((resolve) => { release = resolve })
      record = { ...record, transcription: { ...record.transcription, status: "stopping" } }
    } else if (init?.method === "PATCH") {
      assert.deepEqual(Object.keys(JSON.parse(init.body)), ["googleMeetUrl"])
      record = { ...record, ...JSON.parse(init.body) }
    } else if (url.endsWith("/meetings")) return Response.json([record])
    return Response.json(record)
  }
  const saved = () => meetings.getMeetingsSnapshot().meetings.find((m) => m.id === "synq-1")
  await meetings.getMeetings()
  await t.test("join removed from header and offered only in meeting detail", () => {
    assert.doesNotMatch(renderToStaticMarkup(React.createElement(Header, { activeTab: "meetings", onNavigate() {} })), /Join Meeting/)
    assert.match(renderToStaticMarkup(React.createElement(Controls, { meeting: saved() })), /Join Meeting/)
    assert.doesNotMatch(renderToStaticMarkup(React.createElement(Content, { meeting: saved(), tab: "transcript", onTabChange() {}, onTranscriptSelect() {} })), /Load live transcript|Meet ID/)
  })
  await t.test("duplicate joins send one request with Synq ID and hydrate shared snapshot", async () => {
    const first = vexa.joinMeeting("synq-1"), second = vexa.joinMeeting("synq-1")
    assert.equal(joinCalls, 1); release(); await Promise.all([first, second])
    assert.equal(saved().transcription.botId, 101)
    assert.match(renderToStaticMarkup(React.createElement(Controls, { meeting: saved() })), /End transcription/)
  })
  await t.test("backend refresh adds transcript; fresh browser store retains session and content", async () => {
    record.transcript = [{ timestamp: "00:04", speaker: record.participants[0], text: "A saved transcript sentence" }]
    await meetings.refreshMeeting("synq-1")
    assert.equal(saved().transcript.length, 1)
    assert.match(renderToStaticMarkup(React.createElement(Content, { meeting: saved(), tab: "transcript", onTabChange() {}, onTranscriptSelect() {} })), /A saved transcript sentence/)
    const fresh = await boot(); await fresh.meetings.getMeetings()
    const restored = fresh.meetings.getMeetingsSnapshot().meetings[0]
    assert.equal(restored.transcription.botId, 101); assert.equal(restored.transcript.length, 1)
  })
  await t.test("double stop sends one request; completed session has no start button", async () => {
    const first = vexa.endTranscription("synq-1"), second = vexa.endTranscription("synq-1")
    assert.equal(endCalls, 1); release(); await Promise.all([first, second])
    assert.match(renderToStaticMarkup(React.createElement(Controls, { meeting: saved() })), /Ending transcription/)
    record.transcription = { ...record.transcription, status: "completed", terminal: true, polling: false }
    await meetings.refreshMeeting("synq-1")
    const markup = renderToStaticMarkup(React.createElement(Controls, { meeting: saved() }))
    assert.match(markup, /Transcription completed/); assert.doesNotMatch(markup, /Join Meeting|End transcription/)
  })
  await t.test("safe saved Meet URLs and missing-link message", async () => {
    assert.equal(vexa.safeMeetUrl("javascript:alert(1)"), undefined)
    assert.equal(vexa.safeMeetUrl("https://meet.google.com.evil.test/abc-defg-hij"), undefined)
    assert.match(renderToStaticMarkup(React.createElement(Controls, { meeting: { ...saved(), googleMeetUrl: undefined, transcription: undefined } })), /no valid Google Meet link/)
    await assert.rejects(vexa.saveMeetUrl("synq-1", "https://evil.test/abc-defg-hij"), /valid HTTPS/)
    await vexa.saveMeetUrl("synq-1", record.googleMeetUrl)
    assert.equal(saved().googleMeetUrl, record.googleMeetUrl)
  })
  await t.test("failed request never invents session or discards transcript", async () => {
    fail = true
    const before = structuredClone(saved())
    const request = vexa.joinMeeting("synq-1"); release()
    await assert.rejects(request, /Vexa is unavailable/)
    assert.deepEqual(saved(), before)
  })
})
