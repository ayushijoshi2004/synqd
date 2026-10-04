"""Live loopback-only API smoke test. Start `func start` before running.

Run from backend/: python tests/verify_http.py [--port 7071]
Only temporary meetings created by this script are modified or deleted.
"""

import argparse
import json
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler
from uuid import uuid4


def verify(port=7071):
    base = f"http://127.0.0.1:{port}/api"
    opener = build_opener(ProxyHandler({}))
    checks = []
    temporary_ids = set()

    def request(method, route, body=None, *, raw=None):
        data = raw if raw is not None else json.dumps(body).encode() if body is not None else None
        req = Request(base + route, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            response = opener.open(req, timeout=15)
        except HTTPError as exc:
            response = exc
        with response:
            assert response.headers.get_content_type() == "application/json"
            return response.status, json.loads(response.read()), response.headers

    def passed(name):
        checks.append(name)
        print(f"PASS {name}", flush=True)

    try:
        status, body, _ = request("GET", "/health")
        assert (status, body) == (200, {"status": "working"})
        passed("GET /api/health preserved")

        status, original, _ = request("GET", "/meetings")
        assert status == 200 and isinstance(original, list) and len(original) >= 3
        passed("GET /api/meetings returns demo data")

        payload = {
            "title": "Synq HTTP verification", "date": "2026-10-12",
            "startTime": "10:15", "endTime": "11:00",
            "participants": [{"id": "test-person", "name": "Test Person", "color": "#2f6f5e"}],
            "agenda": "Verify local CRUD", "project": "API demo", "team": "QA",
        }
        status, created, headers = request("POST", "/meetings", payload)
        assert status == 201
        meeting_id = created["id"]
        temporary_ids.add(meeting_id)
        assert headers["Location"] == f"/api/meetings/{meeting_id}"
        assert created["status"] == "scheduled" and created["aiStatus"] == "unprocessed"
        passed("POST creates a meeting with generated id and defaults")

        status, body, _ = request("GET", f"/meetings/{meeting_id}")
        assert status == 200 and body == created
        passed("GET created meeting")

        patch = {"title": "Synq patched meeting", "startTime": "14:10", "endTime": "15:20", "status": "in_progress", "aiStatus": "processing"}
        status, updated, _ = request("PATCH", f"/meetings/{meeting_id}", patch)
        assert status == 200 and updated == {**created, **patch}
        status, reread, _ = request("GET", f"/meetings/{meeting_id}")
        assert status == 200 and reread == updated
        passed("PATCH updates supplied fields and preserves other fields")

        for field in ("status", "aiStatus"):
            status, body, _ = request("POST", "/meetings", {**payload, field: "invalid"})
            assert status == 400 and "error" in body
            status, body, _ = request("PATCH", f"/meetings/{meeting_id}", {field: "invalid"})
            assert status == 400 and "error" in body
        status, reread, _ = request("GET", f"/meetings/{meeting_id}")
        assert status == 200 and reread == updated
        passed("Invalid status and aiStatus rejected on POST and PATCH")

        for invalid in ({}, [], {**payload, "participants": []}, {**payload, "extra": "not allowed"}):
            assert request("POST", "/meetings", invalid)[0] == 400
        assert request("POST", "/meetings", raw=b"{invalid")[0] == 400
        assert request("PATCH", f"/meetings/{meeting_id}", {"id": "replacement"})[0] == 400
        assert request("PATCH", f"/meetings/{meeting_id}", {"unsupported": True})[0] == 400
        passed("Required fields, JSON shape, and PATCH allowlist validated")

        custom_id = f"http-test-{uuid4()}"
        status, custom, _ = request("POST", "/meetings", {**payload, "id": custom_id})
        assert status == 201 and custom["id"] == custom_id
        temporary_ids.add(custom_id)
        assert request("POST", "/meetings", {**payload, "id": custom_id})[0] == 409
        passed("Supplied id supported; duplicates return 409")

        status, body, _ = request("DELETE", f"/meetings/{meeting_id}")
        assert status == 200 and body == {"id": meeting_id, "deleted": True}
        temporary_ids.remove(meeting_id)
        passed("DELETE created meeting")

        for method, data in (("GET", None), ("PATCH", {"title": "Missing"}), ("DELETE", None)):
            status, body, _ = request(method, f"/meetings/{meeting_id}", data)
            assert status == 404 and body["error"]["code"] == "meeting_not_found"
        passed("Deleted/unknown meeting returns 404 for GET, PATCH, DELETE")

        assert request("DELETE", f"/meetings/{custom_id}")[0] == 200
        temporary_ids.remove(custom_id)
        status, final, _ = request("GET", "/meetings")
        assert status == 200 and final == original
        passed("List reflects deletes; original seed meetings unchanged")
        print(f"{len(checks)} live HTTP checks passed.", flush=True)
    finally:
        for meeting_id in temporary_ids:
            request("DELETE", f"/meetings/{meeting_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7071)
    verify(parser.parse_args().port)
