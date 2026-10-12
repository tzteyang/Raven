"""Verify retained regional HTML pages and their source-bound reconciliation sheets."""

import hashlib
from pathlib import Path

from experimental.harness.assessor.rubric import digest as evidence_digest
from experimental.harness.scenario.digest import digest as source_digest


def delivered_as_requested(item):
    """Require the actual single-file page and actual named sheet, independently of semantic scores."""
    from .owner import Vocabulary, cards, meeting, visible

    root = Path(item.get("scenario_root") or Path(__file__).parent)
    vocabulary = Vocabulary.load(root)
    rulers = cards(root)
    owner = bool(item.get("owner_assessments"))
    assessments = item.get("owner_assessments") if owner else item.get("assessments")
    binding = item.get("owner_assessment_binding") if owner else item.get("assessment_binding")
    if binding != "session_and_turn_ids" or not assessments:
        raise ValueError("Actual assessment binding is unavailable for reconciliation evidence.")
    assessment = assessments[-1]
    packet = assessment.get("evidence") or {}
    if assessment.get("evidence_digest") != evidence_digest(packet) or not assessment.get("execution_digest"):
        raise ValueError("The retained assessment evidence changed or lacks execution identity.")
    if owner and assessment.get("scenario_digest") != source_digest(root):
        raise ValueError("The assessment describes a different case source.")
    if not item.get("delivery_root"):
        raise ValueError("No retained artifact root is available.")
    delivery = Path(item["delivery_root"]).resolve()
    drills = item.get("drills") or []
    if not drills:
        return False
    for drill in drills:
        card = rulers.get(drill.get("card"))
        refs = drill.get("references") or {}
        if card is None or refs != (packet.get("references") or {}).get(drill.get("session")):
            raise ValueError("The task's source and reference packet are not bound.")
        if not owner and refs.get("scenario_digest") != source_digest(root):
            raise ValueError("The held-out source identity differs.")
        filename = meeting(card, vocabulary)[1]
        files = []
        for exchange in drill.get("exchanges") or []:
            for file in exchange.get("delivered") or []:
                if not file.get("path") or not file.get("sha256"):
                    raise ValueError("A delivered artifact has no retained path or hash.")
                path = (delivery / file["path"]).resolve()
                if not path.is_relative_to(delivery):
                    raise ValueError("The artifact escaped the retained root.")
                try:
                    raw = path.read_bytes()
                    if hashlib.sha256(raw).hexdigest() != file["sha256"]:
                        raise ValueError("The retained artifact bytes changed.")
                    text = raw.decode("utf-8")
                except (OSError, UnicodeError) as exc:
                    raise ValueError("The delivered page is unavailable or unreadable.") from exc
                if path.suffix.lower() in (".html", ".htm"):
                    files.append((path.name, text))
        if not files or {name for name, text in files} != {filename}:
            return False
        if files[-1][1] != refs.get("full_page_html"):
            raise ValueError("The measured page differs from the retained final delivery.")
        if not (
            "<" in files[-1][1]
            and (
                visible(files[-1][1]).strip() or (refs.get("rendered_evidence") or {}).get("rendered_text", "").strip()
            )
        ):
            return False
        sheet = refs.get("reconciliation_sheet") or {}
        content = sheet.get("content")
        if sheet.get("status") == "unavailable":
            raise ValueError("The actual reconciliation sheet state is unavailable.")
        if (
            sheet.get("status") != "read"
            or not sheet.get("has_required_headers")
            or sheet.get("path") != f"{vocabulary.one('sheet_folder')}/{Path(filename).stem}.md"
            or not isinstance(content, str)
            or sheet.get("sha256") != hashlib.sha256(content.encode()).hexdigest()
        ):
            return False
    return True
