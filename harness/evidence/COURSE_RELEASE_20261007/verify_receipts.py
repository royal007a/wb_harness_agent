"""Read-only verification of fixed release receipts; never creates a Run."""
import collections
import hashlib
import json
from pathlib import Path
import urllib.request

BASE = "http://127.0.0.1:8876"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def raw(path):
    with OPENER.open(BASE + path, timeout=10) as response:
        return response.read()


def get(path):
    return json.loads(raw(path))


def main():
    receipt = json.loads(Path(__file__).with_name("course-browser.json").read_text())
    assert get("/api/local/dsh/runtime")["release"] == receipt["release"]
    for expected in receipt["runs"]:
        ident = expected["id"]
        detail = get("/api/local/dsh/runs/" + ident)
        assert detail["run"]["status"] == expected["status"] == "succeeded"
        for key in ("spent", "reserved", "calls"):
            assert detail["budget"][key] == expected["budget"][key]
        events, after = [], 0
        while True:
            page = get(f"/api/local/dsh/runs/{ident}/events?after={after}")
            if not page["items"]:
                break
            assert page["next_cursor"] > after
            events.extend(page["items"])
            after = page["next_cursor"]
        assert len({e["sequence"] for e in events}) == len(events)
        assert events[-1]["event_type"] == "run.succeeded"
        changes = [e["data"] for e in events if e["event_type"] == "dsh.crossing"]
        latest = {e["crossing_id"]: e for e in changes}
        assert dict(collections.Counter(e["status"] for e in latest.values())) == expected["final_receipt_status_counts"]
        assert dict(collections.Counter(e["status"] for e in changes)) == expected["crossing_event_status_counts"]
        for kind in ("model", "tool"):
            assert sum(e["kind"] == kind and e["status"] == "completed" for e in latest.values()) == expected[kind + "_completed"]
        assert sorted({e["model_round"] for e in changes if e["kind"] == "tool" and e["status"] == "completed"}) == expected["tool_rounds"]
        for artifact in expected["artifacts"]:
            body = raw("/api/v1/artifacts/" + artifact["id"] + "/content")
            assert len(body) == artifact["size_bytes"]
            assert hashlib.sha256(body).hexdigest() == artifact["sha256"]
            if artifact["name"] == "dsh-findings.json":
                findings = json.loads(body)
                assert findings["business_status"] == expected["business_status"]
                assert findings["findings"]["term"]["claim"] == expected["term_claim"]
                assert [q["clause_id"] for q in findings["findings"]["exception"]["quotes"]] == expected["exception_citations"]
        print(json.dumps({"run_id": ident, "read_only_receipt_check": "passed"}))
    assert get("/api/local/dsh/runtime")["release"] == receipt["release"]


if __name__ == "__main__":
    main()
