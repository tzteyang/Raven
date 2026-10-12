"""Verify a studio request ends with one actual retained HTML page, preserving correction history."""

import hashlib
from pathlib import Path

from experimental.harness.assessor.rubric import digest as evidence_digest
from experimental.harness.scenario.digest import digest as source_digest


def delivered_as_requested(item):
    """Read the final native delivery batch and archived bytes instead of counting historical filenames."""
    root = Path(item.get("scenario_root") or Path(__file__).parent)
    owner = bool(item.get("owner_assessments"))
    assessments = item.get("owner_assessments") if owner else item.get("assessments")
    binding = item.get("owner_assessment_binding") if owner else item.get("assessment_binding")
    if binding != "session_and_turn_ids" or not assessments or not item.get("delivery_root"):
        raise ValueError("The actual assessment or delivery root is unavailable.")
    assessment = assessments[-1]
    packet = assessment.get("evidence") or {}
    if assessment.get("evidence_digest") != evidence_digest(packet) or not assessment.get("execution_digest"):
        raise ValueError("The assessment evidence is missing or changed.")
    if owner and assessment.get("scenario_digest") != source_digest(root):
        raise ValueError("The assessment describes another scenario source.")
    archive = Path(item["delivery_root"]).resolve()
    drills = item.get("drills") or []
    if not drills:
        return False
    for drill in drills:
        refs = drill.get("references") or {}
        if refs.get("card") != drill.get("card") or refs != (packet.get("references") or {}).get(drill.get("session")):
            raise ValueError("The task's retained references do not match the assessment.")
        if not owner and refs.get("scenario_digest") != source_digest(root):
            raise ValueError("The held-out source identity differs.")
        group = refs.get("final_delivery_group") or {}
        files = group.get("files") or []
        if not group:
            return False
        if not group.get("verified"):
            raise ValueError("The final delivery batch is not bound to native retained bytes.")
        if len(files) != 1 or Path(files[0]["name"]).suffix.lower() not in (".html", ".htm"):
            return False
        expected = files[0]
        if expected.get("status") != "read":
            raise ValueError("The final HTML page is unreadable.")
        actual = [
            file
            for exchange in drill.get("exchanges") or []
            for file in exchange.get("delivered") or []
            if Path(file.get("path") or "").name == expected["name"] and file.get("sha256") == expected.get("sha256")
        ]
        if not actual:
            raise ValueError("The final page has no matching archived snapshot.")
        path = (archive / actual[-1]["path"]).resolve()
        if not path.is_relative_to(archive):
            raise ValueError("The final page escaped the archive.")
        try:
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected["sha256"] or raw.decode("utf-8") != expected["content"]:
                raise ValueError("The final page bytes changed after delivery.")
        except (OSError, UnicodeError) as exc:
            raise ValueError("The final page is unavailable.") from exc
        if not expected["content"].strip() or "<" not in expected["content"]:
            return False
    return True
