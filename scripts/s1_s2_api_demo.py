"""S1/S2 through the job API without a UI (W5-4 DoD). Run by scripts/s1_s2_api_demo.sh.

    S1   upload a dev document, confirm one value (a human edit with a reason), register
         if the reviewer screen allows it; otherwise print the blockers and the
         supplement request (D-066): the script never invents a value.
    S2a  upload a document whose product is already registered: link, facts unchanged.
    S2b  upload the S1 document again: it is now a duplicate of the S1 product: link.

Every choice a person would make is printed. Nothing is decided that the prompt does not
offer.
"""

import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
S1_DOC = Path(sys.argv[2] if len(sys.argv) > 2 else "data/synth/inputs/SYN-011.docx")
S2_DOC = Path(sys.argv[3] if len(sys.argv) > 3 else "data/synth/inputs/SYN-004.docx")
WAIT_S = 900
client = httpx.Client(base_url=URL, timeout=60)


def upload(path: Path) -> str:
    response = client.post("/api/jobs", files={"file": (path.name, path.read_bytes())})
    response.raise_for_status()
    job_id: str = response.json()["job_id"]
    print(f"\nupload {path.name} -> {job_id}")
    return job_id


def settled(job_id: str) -> dict[str, Any]:
    start = time.time()
    while True:
        view: dict[str, Any] = client.get(f"/api/jobs/{job_id}").json()
        if view["status"] != "running":
            print(f"  {view['status']} after {time.time() - start:.0f} s")
            return view
        if time.time() - start > WAIT_S:
            sys.exit(f"  still running after {WAIT_S} s")
        time.sleep(2)


def send(job_id: str, command: dict[str, Any]) -> dict[str, Any]:
    body = {"request_id": uuid.uuid4().hex, "command": command}
    response = client.post(f"/api/jobs/{job_id}/resume", json=body)
    if response.status_code == 409:
        print(f"  refused: {response.json()['detail']}")
    response.raise_for_status()
    return settled(job_id)


def show(view: dict[str, Any]) -> dict[str, Any] | None:
    prompt: dict[str, Any] | None = view["prompt"]
    if prompt is None:
        print(f"  outcome: {view['status']}, product {view['product_id']}")
        if view.get("error"):
            print(f"  error: {view['error']}")
        return None
    if prompt["kind"] == "choose_class":
        print(f"  waiting for a class choice: candidates {prompt['candidates']}")
        return prompt
    result = prompt["result"]
    print(
        f"  class {result['class_id']}, facts {len(result['facts'])}, "
        f"unresolved {len(result['unresolved'])}"
    )
    print(
        f"  findings {[(f['code'], f['attribute_ids']) for f in result['validation']['findings']]}"
    )
    duplicates = [m["registry_id"] for m in result["matches"] if m["relation"] == "duplicate"]
    similar = sum(m["relation"] == "similar" for m in result["matches"])
    print(f"  matches  duplicate {duplicates}, similar {similar}")
    print(f"  allowed  {prompt['allowed']}")
    for blocker in prompt["blockers"]:
        print(f"  blocked: {blocker}")
    if prompt["notice"]:
        print(f"  notice: {prompt['notice']}")
    return prompt


def product(product_id: str) -> None:
    p = client.get(f"/api/products/{product_id}").json()
    kinds: dict[str, int] = {}
    for fact in p["facts"]:
        kinds[fact["evidence_kind"]] = kinds.get(fact["evidence_kind"], 0) + 1
    print(f"  product {product_id}: {len(p['facts'])} facts {kinds}")
    for e in p["edits"]:
        print(f"    edit {e['edit_id']}: {e['op']} {e['attribute']} — {e['reason']}")
    print(f"    events {[e['event_type'] for e in p['events']]}")


def confirm_one_value(job_id: str, prompt: dict[str, Any]) -> dict[str, Any]:
    """The reviewer checks one value against the document and confirms it (S1 edit)."""
    facts = prompt["result"]["facts"]
    index, fact = next(
        ((i, f) for i, f in enumerate(facts) if isinstance(f["value"], (int, float))),
        (None, None),
    )
    if fact is None:
        print("  no plain number to confirm; skipping the edit")
        return settled(job_id)
    edit = {
        "op": "set",
        "target": "fact",
        "index": index,
        "value_text": str(fact["value"]),
        "unit_text": fact["unit"],
        "reason": "checked against the document (demo)",
    }
    print(f"  edit: confirm {fact['attribute']} = {fact['value']} {fact['unit'] or ''}")
    return send(job_id, {"action": "edit", "revision": prompt["revision"], "edit": edit})


def link_duplicate(job_id: str, prompt: dict[str, Any]) -> str | None:
    duplicates = [
        m["registry_id"] for m in prompt["result"]["matches"] if m["relation"] == "duplicate"
    ]
    if not duplicates or "link" not in prompt["allowed"]:
        print("  no duplicate to link to")
        return None
    target = duplicates[0]
    before = client.get(f"/api/products/{target}").json()["facts"]
    print(f"  choice: link to {target}")
    show(send(job_id, {"action": "link", "revision": prompt["revision"], "target_id": target}))
    after = client.get(f"/api/products/{target}").json()["facts"]
    print(f"  facts of {target} unchanged: {after == before}")
    product(target)
    return target


def main() -> None:
    print("== S1: new product ==")
    s1 = upload(S1_DOC)
    prompt = show(settled(s1))
    registered = None
    if prompt is not None and prompt["kind"] == "review" and "edit" in prompt["allowed"]:
        prompt = show(confirm_one_value(s1, prompt))
    if prompt is not None and prompt["kind"] == "review":
        if "register_new" in prompt["allowed"]:
            print("  choice: register")
            done = send(s1, {"action": "register_new", "revision": prompt["revision"]})
            show(done)
            registered = done["product_id"]
            product(registered)
        else:
            print("  cannot register yet; supplement request for the sender:")
            text = client.get(f"/api/jobs/{s1}/supplement").json()["text"]
            print("    " + text.rstrip().replace("\n", "\n    "))

    print("\n== S2a: already registered product ==")
    s2 = upload(S2_DOC)
    prompt = show(settled(s2))
    if prompt is not None and prompt["kind"] == "review":
        link_duplicate(s2, prompt)

    if registered:
        print("\n== S2b: the S1 document again ==")
        again = upload(S1_DOC)
        prompt = show(settled(again))
        if prompt is not None and prompt["kind"] == "review":
            link_duplicate(again, prompt)


if __name__ == "__main__":
    main()
