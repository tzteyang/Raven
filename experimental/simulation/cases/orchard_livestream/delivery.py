"""Verify the orchard task's retained Markdown handoff and bound live-file placement."""

import hashlib
import re
from pathlib import Path

from experimental.harness.assessor.rubric import digest as evidence_digest
from experimental.harness.scenario.digest import digest as source_digest
from experimental.simulation.bench.scenario import Scenario


def retained(file, root):
    if not root or not file.get("path") or not file.get("sha256"):
        raise ValueError("The delivery has no retained root, path or byte hash.")
    root = Path(root).resolve()
    path = (root / file["path"]).resolve()
    if not path.is_relative_to(root):
        raise ValueError("The delivery escaped its archived root.")
    try:
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != file["sha256"]:
            raise ValueError("The retained delivery bytes changed.")
        return path.name, raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError("The delivered document is unavailable or unreadable.") from exc


def delivered_as_requested(item):
    """Check actual task artifacts; content quality remains in the source-backed semantic criteria."""
    from .owner import Vocabulary, cards

    root = Path(item.get("scenario_root") or Path(__file__).parent)
    scenario = Scenario.load(root)
    vocabulary = Vocabulary.load(scenario)
    products = cards(scenario, vocabulary)
    personas = {persona.name: persona for persona in scenario.personas}
    owner = bool(item.get("owner_assessments"))
    assessments = item.get("owner_assessments") if owner else item.get("assessments")
    binding = item.get("owner_assessment_binding") if owner else item.get("assessment_binding")
    if binding != "session_and_turn_ids" or not assessments:
        raise ValueError("No verified assessment packet binds the live-file evidence to these executions.")
    assessment = assessments[-1]
    packet = assessment.get("evidence") or {}
    if assessment.get("evidence_digest") != evidence_digest(packet):
        raise ValueError("The retained assessment evidence changed.")
    if not assessment.get("execution_digest") or (owner and assessment.get("scenario_digest") != source_digest(root)):
        raise ValueError("The retained assessment lacks execution/source identity.")
    drills = item.get("drills") or []
    if not drills:
        return False
    for drill in drills:
        played, session = drill.get("card"), drill.get("session")
        refs = drill.get("references") or {}
        if (
            played not in personas
            or refs.get("persona") != played
            or refs != (packet.get("references") or {}).get(session)
        ):
            raise ValueError("The task's references do not match the actual assessment packet.")
        if not owner and refs.get("scenario_digest") != source_digest(root):
            raise ValueError("The held-out source identity is unavailable.")
        files = [
            retained(file, item.get("delivery_root"))
            for exchange in drill.get("exchanges") or []
            for file in exchange.get("delivered") or []
        ]
        product = products[played]
        if played in ("kaibo", "kanzhe", "tishi"):
            states = (refs.get("live_watch") or {}).get("final_files") or {}
            for kind in ("board", "record"):
                state = states.get(kind) or {}
                expected = f"{vocabulary.one('live_folder')}/{product.room}/{vocabulary.one(kind)}.md"
                content = state.get("content")
                if state.get("status") == "unavailable":
                    raise ValueError("The session's actual live-file state was unavailable.")
                if (
                    state.get("status") != "read"
                    or state.get("path") != expected
                    or not isinstance(content, str)
                    or not content.strip()
                    or state.get("sha256") != hashlib.sha256(content.encode()).hexdigest()
                ):
                    return False
            if played != "tishi" and not any(
                name == f"{vocabulary.one('record')}.md" and text == states["record"]["content"] for name, text in files
            ):
                return False
        else:
            expected = personas[played].expected
            if "Q&A" in expected:
                filename = f"{vocabulary.script_names[1]}-{product.room}.md"
            else:
                match = re.search(r"pitch for link (\d)", expected, re.I)
                suffix = f"{match[1]}{vocabulary.one('link_word')}" if match else vocabulary.one("whole_session")
                filename = f"{vocabulary.script_names[0]}-{product.room}-{suffix}.md"
            if not any(name == filename and text.strip() for name, text in files):
                return False
    return True
