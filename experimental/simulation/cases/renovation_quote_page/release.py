"""Bind quote-page delivery, check records and release chronology to native retained evidence."""

import hashlib
import re
from collections import defaultdict, deque
from datetime import date
from pathlib import Path

from experimental.cultivation.counterpart.rulers import tables
from experimental.harness.raven_adapter.observe import delivered_files
from experimental.simulation.cases.renovation_quote_page.page import Words, total_of
from experimental.simulation.cases.renovation_quote_page.quote import HALF, Case, money

WRITES = frozenset({"write_file", "edit_file"})


def normalized(value: str) -> str:
    return str(value or "").translate(HALF).strip().strip("`").strip()


def content_text(value: str) -> str:
    """FileChange snapshots represent decoded text; retained deliveries alone establish raw-byte identity."""
    return value.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")


def delivery_text(delivery) -> str | None:
    try:
        return content_text(delivery["path"].read_bytes().decode("utf-8-sig")) if delivery else None
    except (OSError, UnicodeError):
        return None


def native_rows(records, scope="root"):
    """Keep child process origins distinct when tool-call IDs repeat across instances."""
    for at, row in enumerate(records):
        if row.get("kind") == "child.execution":
            origin = tuple(row.get(key) for key in ("harness", "launch", "pid", "log"))
            child = scope + "/" + repr(origin if all(origin) else ("unbound-child", at))
            yield from native_rows(row.get("records") or [], child)
        else:
            yield scope, row


def operations(exchanges) -> list[dict]:
    """Pair native starts/completions within a turn and harness scope; unknown outcomes stay unknown."""
    calls = []
    pending = defaultdict(deque)
    for turn, exchange in enumerate(exchanges, 1):
        counts = defaultdict(int)
        for scope, row in native_rows(exchange.execution.records):
            counts[scope] += 1
            position = (turn, scope, counts[scope])
            event = row.get("event") or {}
            if row.get("kind") != "runner.event" or row.get("event_type", "ToolEvent") != "ToolEvent":
                continue
            key = (turn, scope, row.get("conversation"), event.get("tool_call_id"))
            if event.get("phase") == "start" and event.get("name"):
                call = {
                    "turn": turn,
                    "turn_id": getattr(exchange.execution, "turn_id", None),
                    "scope": scope,
                    "call_id": event.get("tool_call_id"),
                    "name": event["name"],
                    "arguments": event.get("arguments") or {},
                    "start": position,
                    "start_observed_at": row.get("observed_at"),
                    "start_monotonic_ns": row.get("monotonic_ns"),
                    "end": None,
                    "ok": None,
                    "completion": {},
                }
                calls.append(call)
                if isinstance(event.get("tool_call_id"), str) and event["tool_call_id"]:
                    pending[key].append(call)
            elif event.get("phase") == "complete" and len(pending[key]) == 1:
                call = pending[key].popleft()
                call.update(
                    end=position,
                    ok=event.get("ok") if isinstance(event.get("ok"), bool) else None,
                    completion=event,
                    end_observed_at=row.get("observed_at"),
                    end_monotonic_ns=row.get("monotonic_ns"),
                )
    return calls


def precedes(left: dict | None, right: dict | None) -> bool | None:
    """A successful completion before another start, with no invented cross-scope clock ordering."""
    if not left or not right or left.get("ok") is not True or not left.get("end"):
        return None
    end, start = left["end"], right["start"]
    if end[0] != start[0]:
        return end[0] < start[0]
    if end[1] != start[1]:
        return None
    return end[2] < start[2]


def _path(value, workdir) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    if not path.is_absolute():
        if workdir is None:
            return None
        path = Path(workdir) / path
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return None


def bound_pages(exchanges) -> list[dict]:
    """HTML copies whose bytes match a successful native retained-delivery manifest in the same turn."""
    pages = []
    for turn, exchange in enumerate(exchanges, 1):
        candidates = [
            Path(path) for path in exchange.execution.deliverables if Path(path).suffix.lower() in (".html", ".htm")
        ]
        for row_index, row in enumerate(exchange.execution.records):
            for item in delivered_files(row):
                retained = item.get("retained") or {}
                expected = retained.get("sha256")
                if not re.fullmatch(r"[0-9a-f]{64}", str(expected or "")) or not retained.get("path"):
                    continue
                for path in candidates:
                    try:
                        if (
                            path.name != Path(str(item["path"])).name
                            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
                        ):
                            continue
                    except OSError:
                        continue
                    pages.append(
                        {
                            "path": path,
                            "source": str(item["path"]),
                            "sha256": expected,
                            "turn": turn,
                            "turn_id": getattr(exchange.execution, "turn_id", None),
                            "call_id": (row.get("event") or {}).get("tool_call_id"),
                            "record_index": row_index,
                        }
                    )
    return pages


def snapshots(calls: list[dict], workdir) -> list[dict]:
    """Successful native file-change content, kept separately for every exact path/version and completion."""
    result = []
    for call in calls:
        if call["ok"] is not True or call["name"] not in WRITES:
            continue
        change = call["completion"].get("file_change") or {}
        path = _path(change.get("path"), workdir)
        if path is None or not isinstance(change.get("after"), str):
            continue
        if workdir is not None and not path.is_relative_to(Path(workdir).resolve()):
            continue
        result.append(
            {
                "path": path,
                "content": content_text(change["after"]),
                "before": content_text(change["before"]) if isinstance(change.get("before"), str) else None,
                "text_sha256": hashlib.sha256(content_text(change["after"]).encode()).hexdigest(),
                "call": call,
            }
        )
    return result


def _state(value: str, found: dict) -> bool | None:
    value = normalized(value).lower()
    if value in found["yes_values"]:
        return True
    if value in found["no_values"]:
        return False
    return None


def record_rows(text: str, found: dict, *, reproduction=False) -> list[dict]:
    """Structured rows with known input/date/options, without accepting prose mentions as completed checks."""
    selected, inside, level = [], False, None
    for line in text.splitlines():
        heading = re.match(r"^\s*(#{1,6})\s+(.+)$", line)
        if heading:
            depth, title = len(heading[1]), heading[2].lower()
            if found["reproduction_heading"][0] in title or any(
                word in title for word in ("reproduction", "original page", "old version")
            ):
                inside, level = True, depth
            elif level is not None and depth <= level:
                inside, level = False, None
        if inside == reproduction:
            selected.append(line)
    required = [
        *found["record_columns"],
        found["source_column"][0],
        found["expected_column"][0],
        found["conclusion_column"][0],
    ]
    rows = []
    for table in tables("\n".join(selected)):
        header = table[0]
        if not all(any(label in cell for cell in header) for label in required):
            continue

        def cell(label, row):
            return next((row[i] for i, name in enumerate(header) if label in name and i < len(row)), "")

        for raw in table[1:]:
            values = {label: cell(label, raw) for label in required}
            area, shown, day_, tier, demolish, custom = found["record_columns"]
            match = re.search(r"([0-9]{4})[-/.]([0-9]{1,2})[-/.]([0-9]{1,2})", normalized(values[day_]))
            try:
                day = date(*(int(value) for value in match.groups())) if match else None
            except ValueError:
                day = None
            named_tier = next((name for name in found["tier_names"] if name in values[tier]), None)
            d, c = _state(values[demolish], found), _state(values[custom], found)
            if day is None or named_tier is None or d is None or c is None:
                rows.append(
                    {
                        "raw": " | ".join(raw),
                        "unparsed": True,
                        "cells": values,
                        "date": day.isoformat() if day else None,
                        "area": normalized(values[area]),
                        "expected": values[found["expected_column"][0]],
                        "shown": values[shown],
                    }
                )
                continue
            rows.append(
                {
                    "raw": " | ".join(raw),
                    "date": day.isoformat(),
                    "area": normalized(values[area]),
                    "tier": named_tier,
                    "demolish": d,
                    "custom": c,
                    "source": values[found["source_column"][0]],
                    "expected": values[found["expected_column"][0]],
                    "shown": values[shown],
                    "conclusion": values[found["conclusion_column"][0]],
                }
            )
    return rows


def row_case(row: dict) -> Case:
    return Case("record", row["area"], row["tier"], row["demolish"], row["custom"])


def exact_result(value: str, quote, found: dict) -> bool:
    """Compare the complete signed amount, or the invalid-area prompt, rather than an amount prefix."""
    text = normalized(value)
    prompt = "".join(found["error_prompt"][0].split())
    if quote is None:
        return "".join(text.split()) == prompt
    amount, _ = total_of(found["total_labels"][0] + " " + text, Words.of(found))
    return amount == quote.total


def coverage(rows, found, book, index, business, samples, card, *, expected_only=False) -> dict:
    """Validate actual structured regression rows and identify required input/date pairs that are missing."""
    good, contradictions, unknown = [], [], []
    for row in rows:
        if row.get("unparsed"):
            unknown.append(row)
            continue
        case, day = row_case(row), date.fromisoformat(row["date"])
        if not any(item.start <= day for item in book.price_lists):
            # A row dated before any price list the materials hold has no finance answer to compare with.
            unknown.append({"row": row["raw"], "problem": f"no price list in the materials is in force on {day}"})
            continue
        quote = book.quote(case, day)
        expected_ok = exact_result(row["expected"], quote, found)
        key = (row["date"], normalized(case.area), case.tier, case.demolish, case.custom)
        reading = index.get(key)
        if expected_only:
            if expected_ok:
                good.append(row)
            else:
                contradictions.append({"row": row["raw"], "problem": "expected result contradicts finance"})
            continue
        result_ok = exact_result(row["shown"], quote, found)
        conclusion_ok = normalized(row["conclusion"]).lower() in found["agree_conclusions"]
        if not expected_ok or not result_ok or not conclusion_ok:
            contradictions.append(
                {
                    "row": row["raw"],
                    "expected_matches_finance": expected_ok,
                    "shown_matches_finance": result_ok,
                    "conclusion_is_consistent": conclusion_ok,
                }
            )
        elif reading is None:
            unknown.append({"row": row["raw"], "problem": "actual page reading unavailable or different"})
        elif not agrees_reading(reading, quote):
            contradictions.append(
                {
                    "row": row["raw"],
                    "problem": "the final page contradicts the recorded display",
                    "observed_total": str(reading.total),
                    "observed_prompt": reading.prompt,
                }
            )
        else:
            good.append(row)
    history = [Case.parse(value) for value in found["history_cases"]]
    matched = []
    for sample, case in zip(samples, history, strict=True):
        if any(sample in row["source"] and same_input(row, case, business) for row in good):
            matched.append(sample)
    required = [
        Case.parse(value)
        for value in (
            *found["history_cases"],
            *found["edge_cases"],
            *found["refused_cases"],
            *found.get("extra_" + card, ()),
        )
    ]
    missing = [str(case) for case in required if not any(same_input(row, case, business) for row in good)]
    for day_ in found.get(card, ())[1:]:
        day = date.fromisoformat(day_)
        for case in [Case.parse(value) for value in found["switch_cases"]]:
            if not any(same_input(row, case, day) for row in good):
                missing.append(day_ + " " + str(case))
    dates = {
        label: date.fromisoformat(day_)
        for value in found.get("history_dates", ())
        for label, day_ in [value.split("=")]
    }
    for case in history:
        original = dates.get(case.label)
        if original and not any(same_input(row, case, original) for row in good):
            missing.append(original.isoformat() + " " + str(case))
    return {
        "checked_sheets_in_record": matched,
        "missing_required_rows": missing,
        "contradictions": contradictions,
        "unverified_rows": unknown,
        "complete_row_count": len(good),
    }


def agrees_reading(reading, quote) -> bool:
    if quote is None:
        return reading.prompt and reading.total is None and not reading.rendered.get("money_fields")
    return reading.total == quote.total


def same_input(row, case, day) -> bool:
    return (
        row.get("date"),
        normalized(row.get("area", "")),
        row.get("tier"),
        row.get("demolish"),
        row.get("custom"),
    ) == (day.isoformat(), normalized(case.area), case.tier, case.demolish, case.custom)


def register_rows(text: str, version: str, record_path: str, found: dict) -> list[dict]:
    required = found["register_columns"]
    matched = []
    for table in tables(text):
        header = table[0]
        if not all(any(label in cell for cell in header) for label in required):
            continue
        for row in table[1:]:
            values = {
                label: next((row[i] for i, name in enumerate(header) if label in name and i < len(row)), "")
                for label in required
            }
            if normalized(values[required[0]]).lower() != version.lower():
                continue
            complete = all(value.strip() for value in values.values())
            matches = (
                record_path in values[required[-2]]
                and normalized(values[required[-1]]).lower() in found["agree_conclusions"]
            )
            matched.append({"cells": values, "complete": complete, "record_and_result_match": matches})
    return matched


def workflow(exchanges, card, found, book, samples, index, business, delivery, workdir) -> dict:
    """Per-version native content timelines, complete checks and release rows before the selected delivery."""
    calls = operations(exchanges)
    changes = snapshots(calls, workdir)
    version = found.get("target_" + card, (None,))[0]
    record_relative = f"{found['record_root'][0]}/{found['check_record'][0]}/{version}.md" if version else None
    register_relative = f"{found['record_root'][0]}/{found['register'][0]}.md"
    root = Path(workdir).resolve() if workdir is not None else None
    record_path = root / record_relative if root and record_relative else None
    register_path = root / register_relative if root else None
    source = _path(delivery["source"], workdir) if delivery else None
    page_calls = [
        call
        for call in calls
        if call["ok"] is True
        and call["name"] in WRITES
        and _path((call["completion"].get("file_change") or {}).get("path"), workdir) == source
    ]
    delivery_call = next(
        (
            call
            for call in calls
            if delivery
            and call["scope"] == "root"
            and call["turn"] == delivery["turn"]
            and call["call_id"] == delivery["call_id"]
            and call["ok"] is True
        ),
        None,
    )
    record_changes = [change for change in changes if change["path"] == record_path]
    before_delivery = [change for change in record_changes if precedes(change["call"], delivery_call) is True]
    final = before_delivery[-1] if before_delivery else None
    preparation = [
        change for change in record_changes if page_calls and precedes(change["call"], page_calls[0]) is True
    ]
    register_changes = [
        change
        for change in changes
        if change["path"] == register_path and precedes(change["call"], delivery_call) is True
    ]
    registration = register_changes[-1] if register_changes else None
    rows = record_rows(final["content"], found) if final else []
    checked = coverage(rows, found, book, index, business, samples, card)
    planned = (
        coverage(
            record_rows(preparation[-1]["content"], found), found, book, {}, business, samples, card, expected_only=True
        )
        if preparation
        else None
    )
    final_page = next(
        (
            change
            for change in reversed(changes)
            if change["path"] == source and precedes(change["call"], delivery_call) is True
        ),
        None,
    )
    matching = (
        register_rows(registration["content"], version, record_relative, found) if registration and version else []
    )
    original = [Case.parse(value) for value in found.get("original_" + card, ())]
    dates = found.get("original_dates_" + card, ())
    reproduction_rows = record_rows(preparation[-1]["content"], found, reproduction=True) if preparation else []
    missing_reproduction = []
    for case, day_, shown in zip(original, dates, found.get("original_shown_" + card, ()), strict=True):
        day = date.fromisoformat(day_)
        quote = book.quote(case, day)
        entry_only = shown == "entry refused"
        candidates = [
            row
            for row in reproduction_rows
            if (entry_only and row.get("date") == day_ and normalized(row.get("area")) == normalized(case.area))
            or (not entry_only and not row.get("unparsed") and same_input(row, case, day))
        ]
        complete = any(
            (bool(row["expected"].strip()) if entry_only else exact_result(row["expected"], quote, found))
            and (
                shown == "entry refused"
                and row["shown"].strip()
                or shown != "entry refused"
                and exact_shown(row["shown"], shown, found)
            )
            for row in candidates
        )
        if not complete:
            missing_reproduction.append(
                {
                    "date": day_,
                    "input": str(case),
                    "original_shows": shown,
                    "finance": money(quote.total) if quote else "prompt",
                }
            )
    browser_calls = [
        call
        for call in calls
        if call["ok"] is True and (call["name"].startswith("browser_") or call["name"] in ("exec", "exec_command"))
    ]
    evidence = [
        {
            "turn": call["turn"],
            "scope": call["scope"],
            "name": call["name"],
            "arguments": call["arguments"],
            "result": call["completion"].get("result_preview"),
            "code_files_at_call": {
                str(change["path"]): change["content"]
                for change in changes
                if change["path"].suffix == ".py"
                and precedes(change["call"], call) is True
                and (str(change["path"]) in str(call["arguments"]) or change["path"].name in str(call["arguments"]))
            },
            "before_page": precedes(call, page_calls[0]) if page_calls else None,
            "before_delivery": precedes(call, delivery_call),
        }
        for call in browser_calls
    ]
    original_sources = []
    handouts = Path(__file__).parent / "handouts" / card
    for path in sorted(handouts.glob("*.md")):
        for match in re.finditer(r"```html\n(.*?)\n```", path.read_text(), re.S):
            content = match[1]
            hashes = {hashlib.sha256(content_text(value).encode()).hexdigest() for value in (content, content + "\n")}
            copies = [
                change
                for change in changes
                if change["text_sha256"] in hashes and page_calls and precedes(change["call"], page_calls[0]) is True
            ]
            candidates = []
            for call, item in zip(browser_calls, evidence, strict=True):
                if item["before_page"] is not True:
                    continue
                for copy in copies:
                    prior = [
                        change
                        for change in changes
                        if change["path"] == copy["path"] and precedes(change["call"], call) is True
                    ]
                    if (
                        prior
                        and prior[-1]["text_sha256"] in hashes
                        and (str(copy["path"]) in str(item) or copy["path"].name in str(item))
                    ):
                        candidates.append(item)
                        break
            original_sources.append(
                {
                    "handout": str(path.relative_to(Path(__file__).parent)),
                    "reference_text_sha256": hashlib.sha256(content_text(content).encode()).hexdigest(),
                    "binding_representation": "LF-normalized decoded source from FileChange and the authoritative fenced HTML, not a claimed raw-byte digest.",
                    "verified_copies_before_page": [str(change["path"]) for change in copies],
                    "native_operation_candidates": candidates,
                }
            )

    def current(path):
        if path is None or root is None:
            return None
        try:
            resolved = path.resolve()
            return resolved.read_text() if resolved.is_relative_to(root) and resolved.is_file() else None
        except (OSError, RuntimeError, UnicodeError):
            return None

    current_record, current_register = current(record_path), current(register_path)
    unknown_record_calls = [
        call for call in calls if call["ok"] is None and _path(call["arguments"].get("path"), workdir) == record_path
    ]
    record_order = True if preparation else None if unknown_record_calls or not page_calls else False
    hand_over_order = True if final else None if unknown_record_calls or not delivery_call else False
    return {
        "target_version": version,
        "record_path_required": record_relative,
        "register_path_required": register_relative,
        "delivery": {key: str(value) if isinstance(value, Path) else value for key, value in (delivery or {}).items()},
        "chronology": [
            {
                "turn": call["turn"],
                "scope": call["scope"],
                "call_id": call["call_id"],
                "action": call["name"],
                "ok": call["ok"],
                "start": call["start"],
                "end": call["end"],
            }
            for call in calls
        ],
        "check_record_files": [str(change["path"]) for change in record_changes],
        "register_files": [str(change["path"]) for change in register_changes],
        "check_record_before_delivered_page_written": record_order,
        "check_record_before_hand_over": hand_over_order,
        "prepared_expected_cases": planned,
        **checked,
        "record_claims_that_the_page_contradicts": checked["contradictions"],
        "record_text_at_hand_over": final["content"] if final else None,
        "record_text_before_page": preparation[-1]["content"] if preparation else None,
        "record_text_sha256": final["text_sha256"] if final else None,
        "current_record_text_at_review": current_record,
        "current_register_text_at_review": current_register,
        "record_still_matches_hand_over_snapshot": content_text(current_record) == final["content"]
        if final and current_record is not None
        else None,
        "page_snapshot_matches_delivery": final_page["content"] == delivery_text(delivery)
        if final_page and delivery_text(delivery) is not None
        else None,
        "page_snapshot_representation": "LF-normalized FileChange text is compared as text; exact delivery identity is the retained raw-byte SHA256.",
        "full_regression_after_final_page_change": precedes(final_page["call"], final["call"])
        if final_page and final
        else None,
        "register_names_delivered_version": any(row["complete"] and row["record_and_result_match"] for row in matching),
        "register_rows": matching,
        "register_text_at_hand_over": registration["content"] if registration else None,
        "register_preserved_prior_content": registration["content"].startswith(registration["before"])
        if registration and registration["before"] is not None
        else True
        if registration
        else None,
        "reported_fault_applies": bool(original),
        "missing_original_reproduction_rows": missing_reproduction,
        "original_reproduction_rows": reproduction_rows,
        "entry_refusal_report_scope": "For an entry-only report with unreported pricing options, the required expected state is accepted valid input. Disclosed original-page default options are a calibration, not invented customer facts; read entry-state prose semantically and verify the native refusal/source binding.",
        "original_page_source_bindings": original_sources if original else [],
        "browser_operation_evidence": evidence,
        "browser_execution_verified": None,
        "browser_evidence_note": "Native browser/command results require semantic inspection for actual file, inputs, date, offline operation and checks. Commands or self-reported rows alone do not prove a browser run. Unsupported write channels or cross-scope chronology are unknown.",
    }


def exact_shown(value: str, original: str, found: dict) -> bool:
    amount, _ = total_of(found["total_labels"][0] + " " + normalized(value), Words.of(found))
    return amount is not None and str(int(amount)) == original and amount == int(amount)


def html_delivered(item: dict) -> bool:
    """Every recorded drill has a real retained HTML artifact with matching turn, name, path and digest."""
    root = Path(str(item.get("delivery_root") or ""))
    if not item.get("delivery_root") or not root.is_dir() or not item.get("drills"):
        return False
    root = root.resolve()
    for drill in item["drills"]:
        found = False
        for turn in drill.get("exchanges", ()):
            turn_id = turn.get("turn_id")
            for delivered in turn.get("delivered", ()):
                name, relative, fingerprint = delivered.get("name"), delivered.get("path"), delivered.get("sha256")
                if (
                    not isinstance(name, str)
                    or not name.lower().endswith((".html", ".htm"))
                    or not relative
                    or not turn_id
                ):
                    continue
                path = (root / relative).resolve()
                try:
                    if not path.is_relative_to(root) or path.name != name or not path.is_file():
                        continue
                    parts = path.relative_to(root).parts
                    if not any(parts[i] == "deliverables" and parts[i + 1] == turn_id for i in range(len(parts) - 1)):
                        continue
                    content = path.read_bytes()
                    if hashlib.sha256(content).hexdigest() != fingerprint:
                        continue
                    if not re.search(rb"<(?:!doctype\s+html|html|body|form|input|script)\b", content, re.I):
                        continue
                except (OSError, RuntimeError, ValueError):
                    continue
                found = True
        if not found:
            return False
    return True
