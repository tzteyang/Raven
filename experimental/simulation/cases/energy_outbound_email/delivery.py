"""Verify the outbound case's requested business handoffs from bound retained artifacts."""

import hashlib
from pathlib import Path

from experimental.cultivation.counterpart.rulers import tables
from experimental.harness.assessor.rubric import digest as rubric_digest
from experimental.harness.scenario.digest import digest as source_digest


def _read(file, root):
    raw = file.get("copy") or file.get("path")
    if not raw or not file.get("sha256"):
        return None
    path = Path(raw)
    if not path.is_absolute():
        if not root:
            return None
        path = Path(root) / path
    try:
        data = path.read_bytes()
        return data.decode("utf-8") if hashlib.sha256(data).hexdigest() == file["sha256"] else None
    except (OSError, UnicodeError):
        return None


def delivered_as_requested(item: dict) -> bool:
    """Check real retained letters/reports, or the valid no-letter handling instructions for this task."""
    from .owner import Vocabulary, parse

    root = Path(item.get("scenario_root") or Path(__file__).parent)
    vocabulary = Vocabulary.load(root)
    drills = item.get("drills") or []
    bound = item.get("owner_assessment_binding") == "session_and_turn_ids" and bool(item.get("owner_assessments"))
    bound = bound or (item.get("assessment_binding") == "session_and_turn_ids" and bool(item.get("assessments")))
    if not drills or not bound:
        return False
    assessments = item.get("owner_assessments") or item.get("assessments") or []
    verified = [
        assessment
        for assessment in assessments
        if isinstance(assessment.get("evidence"), dict)
        and assessment.get("evidence_digest") == rubric_digest(assessment["evidence"])
        and isinstance(assessment.get("execution_digest"), str)
        and len(assessment["execution_digest"]) == 64
        and assessment.get("rubric_version")
        and assessment.get("criteria")
    ]
    if not verified:
        return False
    packet = verified[-1]["evidence"]
    expected_source = source_digest(root)
    if item.get("owner_assessments") and verified[-1].get("scenario_digest") != expected_source:
        return False
    for drill in drills:
        card = drill.get("card")
        target = vocabulary.target(card or "")
        references = drill.get("references") or {}
        session = drill.get("session")
        retained = (packet.get("references") or {}).get(session)
        if target is None or references.get("card") != card or retained != references:
            return False
        if not item.get("owner_assessments") and references.get("scenario_digest") != expected_source:
            return False
        supplied = [
            _read(file, item.get("delivery_root"))
            for exchange in drill.get("exchanges") or []
            for file in exchange.get("delivered") or []
        ]
        texts = [text for text in supplied if text is not None]
        if card in ("huasheng", "chuangjia"):
            kind = "transfer_file" if card == "huasheng" else "dnc_file"
            rows = references.get("crm_rows") or {}
            matching = [value for name, value in rows.items() if Path(name).stem == vocabulary.one(kind)]
            if not any(
                value.get("header_as_norms") is True and any(target.company in row for row in value.get("rows") or [])
                for value in matching
            ):
                return False
            continue
        if card in ("dingpan", "gonggao"):
            reports = (references.get("on_call") or {}).get("report_contents") or {}
            read_count = (references.get("on_call") or {}).get("readings", 0)
            if not any(
                text in reports.values() and any(len(table) - 1 >= read_count >= 0 for table in tables(text))
                for text in texts
            ):
                return False
            continue
        letters = [parse(text, vocabulary) for text in texts]
        if not any(
            letter
            and letter.body
            and letter.greeting
            and letter.recipient
            and letter.mail
            and (target.company in letter.recipient or target.short in letter.recipient)
            for letter in letters
        ):
            return False
    return True
