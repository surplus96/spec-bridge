"""W6-6 (NFR-01): the review application makes no outside connection.

1. The whole S1/S2 flow through the job API (upload, review, edit, register, link) runs
   under the socket guard; no attempt to reach a non-loopback host is allowed.
2. The built screen (web/dist) loads nothing from outside: no external script, stylesheet,
   font, image or fetch target. Strings that only name a URL (XML namespaces, React's error
   documentation link, licence comments) are listed and allowed explicitly.

The guard sees Python sockets only; native extensions and child processes are outside it
(CP-S3 R5), so the W6 report adds an OS-level observation of a local run.
"""

import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.api.test_jobs import add_values, jobs_for, send, upload, use, view
from tests.conftest import ROOT
from tests.eval.test_experiment import classify_reply
from tests.graph.test_registration import CLEAN, DUPLICATE

DIST = ROOT / "web/dist"
URL = re.compile(r"""https?://[^\s"'`)<>]+""")
NAME_ONLY = (  # URLs that appear as names in bundled libraries, never loaded
    "http://www.w3.org/",
    "https://react.dev/errors/",
    "https://tailwindcss.com",
    "http://www.mozilla.org/keymaster/",
    "https://github.com/wojtekmaj/react-pdf",
    "http://example.com",
    "https://foo.bar",
    "http://ns.adobe.com/",  # pdf.js: XML namespaces
    "http://www.xfa.org/schema/",
    "http://www.apache.org/licenses/",  # licence text
    "http://${",  # pdf.js: links inside a PDF; the viewer renders no annotation layer
)
LOAD = re.compile(
    r"""(?:src|href)\s*=\s*["']https?://|@import\s+url\(\s*["']?https?://|url\(\s*["']?https?://"""
)


def test_the_whole_review_flow_stays_on_this_machine(tmp_path: Path, outbound: list[Any]) -> None:
    replies = [classify_reply(CLEAN), {"facts": []}, classify_reply(DUPLICATE), {"facts": []}]
    use(jobs_for(tmp_path, replies))
    client = TestClient(__import__("spec_bridge.api.app", fromlist=["app"]).app)
    try:
        s1 = upload(client, CLEAN)["job_id"]
        add_values(client, s1, CLEAN)
        revision = view(client, s1)["prompt"]["revision"]
        send(client, s1, {"action": "register_new", "revision": revision})
        s2 = upload(client, DUPLICATE)["job_id"]
        add_values(client, s2, DUPLICATE)
        prompt = view(client, s2)["prompt"]
        target = prompt["link_targets"][0]
        send(client, s2, {"action": "link", "revision": prompt["revision"], "target_id": target})
        assert view(client, s1)["status"] == "registered"
        assert view(client, s2)["status"] == "linked"
        assert client.get("/api/display").status_code == 200
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]
    assert outbound == []


@pytest.mark.skipif(not DIST.is_dir(), reason="web/dist not built (npm --prefix web run build)")
def test_the_built_screen_loads_nothing_from_outside() -> None:
    files = [p for p in DIST.rglob("*") if p.suffix in (".html", ".js", ".mjs", ".css")]
    assert files
    loads, unknown = [], set()
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        loads += [f"{path.name}: {m.group(0)}" for m in LOAD.finditer(text)]
        unknown |= {u for u in URL.findall(text) if not u.startswith(NAME_ONLY)}
    assert loads == []
    assert unknown == set(), f"review these URLs in the bundle: {sorted(unknown)[:10]}"
