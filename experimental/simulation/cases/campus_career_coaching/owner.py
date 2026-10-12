"""The career centre's owner: the generic `Owner` with the facts the coaching lead judges a one-on-one session by.

The facts are computed, never judged. For each resume the session delivered: its module headings in order and whether
education leads, its length in rows by the template's page rule, the CPA subjects its certificate lines name, the
pending wording it keeps, the role words it uses (each with its line and whether the student's own files carry that
wording), and the figures no handout but the uploaded draft holds, each with what the student said about it in the
chat. From the session's records: writes into the student's uploaded draft, the consultation record files under the
records folder (from the session's working folder when the bench kept it, otherwise rebuilt from the recorded writes)
with the fields they lack, the dates they cite and whether the session wrote them, and the turns of questions,
deliveries and record writes. For a session booked as interview practice: the turns of the student's long answers, the
passages in the assistant's messages that read as an answer for the student to recite, and the outline points and
STAR words of each feedback turn. For a signing or job-safety question: which offices and which cap the assistant
named.

The student's proof is the card's handouts other than the uploaded draft (the draft is what gets corrected, never its
own proof); what the student said in the chat is reported beside each figure, for the lead to weigh. The words, the
page rule and the labels come from the scenario's `reference.md`, so nothing here names a word of the case.
"""

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path

from experimental.cultivation.counterpart.owner import Owner
from experimental.cultivation.counterpart.rulers import CONFIG, delivered, messages, occurrences, tables, words
from experimental.harness.raven_adapter.action.runtime import REFUSED

SNIPPET = 60
WRITES = frozenset({"write_file", "edit_file"})
UPLOADS = "uploads"
TEXT_SUFFIXES = frozenset({".md", ".txt"})
_HAN = re.compile(f"[{chr(0x3400)}-{chr(0x4DBF)}{chr(0x4E00)}-{chr(0x9FFF)}]")
_NUMBER = re.compile(r"\d+(?:\.\d+)?\s*[%" + chr(0xFF05) + r"]?")
_YEAR, _MONTH, _DAY = chr(0x5E74), chr(0x6708), chr(0x65E5)
# A full date; the day may not run on into more digits or a dot, so a period written 2021.09-2025.06 is not a date.
_DATE = re.compile(rf"(20\d\d)\s*[-./{_YEAR}]\s*(\d{{1,2}})\s*[-./{_MONTH}]\s*(\d{{1,2}})(?![\d.])")
_MONTH_DAY = re.compile(rf"(?<!\d)(\d{{1,2}})\s*{_MONTH}\s*(\d{{1,2}})\s*{_DAY}")
_LIST_ITEM = re.compile(
    r"^\s*(?:\d{1,2}\s*[.)"
    + chr(0x3001)
    + chr(0xFF09)
    + r"]|["
    + chr(0x2460)
    + "-"
    + chr(0x2468)
    + r"]|[-*+"
    + chr(0x2022)
    + chr(0x00B7)
    + r"]\s)"
)
_LEADING_DATE = re.compile(r"^\s*(\d{4}-\d{2}-\d{2})")
_SESSION = re.compile(r"(?:holdout-|s\d+-)?(?P<card>[a-z]+)(?:-\d+)?$")
# A start or end month written other than YYYY.MM (template section 5.1): with year and month words, a slash or a
# hyphen, or a one-digit month.
_OFF_STYLE = re.compile(rf"20\d\d\s*(?:{_YEAR}\s*\d{{1,2}}\s*{_MONTH}|[/-]\s*\d{{1,2}}(?!\d)|\.\d(?!\d))")
_SUBJECT_COUNT = re.compile(r"\d\s*/\s*6")
_NEGATION_REACH = 6


@dataclass(frozen=True)
class Vocabulary:
    """The words and measures of the coaching lead's facts, from the scenario's `reference.md` table."""

    records_folder: str
    record_fields: tuple[str, ...]
    record_metadata: tuple[str, ...]
    record_identity_fields: tuple[str, ...]
    record_types: tuple[str, ...]
    role_words: tuple[str, ...]
    role_exempt: tuple[str, ...]
    cpa_markers: tuple[str, ...]
    cpa_subjects: tuple[str, ...]
    certificate_heading: str
    education_heading: str
    personal_heading: str
    pending_terms: tuple[str, ...]
    pending_exempt: tuple[str, ...]
    count_words: tuple[str, ...]
    numerals: str
    subject_unit: str
    row_width: int
    row_limit: int
    heading_rows: int
    school: str
    draft_marks: tuple[str, ...]
    number_label: str
    name_label: str
    date_label: str
    topic_label: str
    practice_topic: str
    resume_topic: str
    first_person: str
    second_person: str
    answer_marks: tuple[str, ...]
    answer_negations: tuple[str, ...]
    answer_length: int
    star_words: tuple[str, ...]
    signing_cues: tuple[str, ...]
    desks: tuple[str, ...]
    penalty_cap: str
    cap_words: tuple[str, ...]

    @classmethod
    def load(cls, root) -> "Vocabulary":
        found = words(Path(root) / CONFIG)
        one = {key: found[key][0] for key in found}
        return cls(
            records_folder=one["records_folder"],
            record_fields=found["record_fields"],
            record_metadata=found["record_metadata"],
            record_identity_fields=found["record_identity_fields"],
            record_types=found["record_types"],
            role_words=found["role_words"],
            role_exempt=found["role_exempt"],
            cpa_markers=found["cpa_markers"],
            cpa_subjects=found["cpa_subjects"],
            certificate_heading=one["certificate_heading"],
            education_heading=one["education_heading"],
            personal_heading=one["personal_heading"],
            pending_terms=found["pending_terms"],
            pending_exempt=found["pending_exempt"],
            count_words=found["count_words"],
            numerals=one["numerals"],
            subject_unit=one["subject_unit"],
            row_width=int(one["row_width"]),
            row_limit=int(one["row_limit"]),
            heading_rows=int(one["heading_rows"]),
            school=one["school"],
            draft_marks=found["draft_marks"],
            number_label=one["number_label"],
            name_label=one["name_label"],
            date_label=one["date_label"],
            topic_label=one["topic_label"],
            practice_topic=one["practice_topic"],
            resume_topic=one["resume_topic"],
            first_person=one["first_person"],
            second_person=one["second_person"],
            answer_marks=found["answer_marks"],
            answer_negations=found["answer_negations"],
            answer_length=int(one["answer_length"]),
            star_words=found["star_words"],
            signing_cues=found["signing_cues"],
            desks=found["desks"],
            penalty_cap=one["penalty_cap"],
            cap_words=found["cap_words"],
        )


def snippet(line: str) -> str:
    return line.strip()[:SNIPPET]


def han(text: str) -> int:
    """How many CJK characters `text` holds."""
    return len(_HAN.findall(text or ""))


# The page rule (template section 7) --------------------------------------------------------------------------------


def width(line: str) -> float:
    """A line's width in characters: CJK and full-width forms one each, ASCII half; leading markers and bold left out."""
    text = re.sub(r"^(?:#+\s*|[-*+]\s+|>\s*)", "", line.strip()).replace("**", "")
    return sum(0.5 if ord(char) < 0x80 else 1 for char in text)


def rows(text: str, vocabulary: Vocabulary) -> int:
    """The resume's length in rows: the name line and each module heading count as `heading_rows`, every other
    non-empty line as many rows as it fills at `row_width` characters a row."""
    total = 0
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("<!--"):
            continue
        if re.match(r"^#{1,2}\s", stripped):
            total += vocabulary.heading_rows
        else:
            total += max(1, math.ceil(width(stripped) / vocabulary.row_width))
    return total


# Reading a resume ---------------------------------------------------------------------------------------------------


def sections(text: str) -> list[tuple[str, list[str]]]:
    """The module headings (`## `) in order, each with the lines under it."""
    found: list[tuple[str, list[str]]] = []
    for line in (text or "").splitlines():
        heading = re.match(r"^##\s+(.*\S)", line.strip())
        if heading and not line.strip().startswith("###"):
            found.append((heading.group(1), []))
        elif found:
            found[-1][1].append(line)
    return found


def is_resume(text: str, vocabulary: Vocabulary) -> bool:
    """A delivered file that reads as a resume: modules under level-two headings, one of them education or
    certificates, and not a record of the session or a note of changes."""
    headings = [heading for heading, _ in sections(text)]
    return (
        len(headings) >= 2
        and any(
            vocabulary.education_heading in heading or vocabulary.certificate_heading in heading for heading in headings
        )
        and not any(field in (text or "") for field in vocabulary.record_fields[1:3])
    )


def cpa_subjects(text: str, vocabulary: Vocabulary) -> list[str]:
    """The CPA subjects named on any line of the file that carries a CPA marker, longest names matched first."""
    named: list[str] = []
    for line in (text or "").splitlines():
        if not any(marker in line for marker in vocabulary.cpa_markers):
            continue
        rest = line
        for marker in vocabulary.cpa_markers:
            rest = rest.replace(marker, " ")
        for subject in vocabulary.cpa_subjects:
            if subject in rest:
                named.append(subject)
                rest = rest.replace(subject, " ")
    return list(dict.fromkeys(named))


def pending_wording(text: str, vocabulary: Vocabulary) -> dict[str, list[str]]:
    """Each pending, sitting, preparing or count-of-subjects wording on the file's lines, the exempt phrases (such
    as 'obtained') blanked first."""
    cleaned = text or ""
    for phrase in vocabulary.pending_exempt:
        cleaned = cleaned.replace(phrase, " " * len(phrase))
    found = occurrences(cleaned, vocabulary.pending_terms)
    counted = re.compile(
        "(?:"
        + "|".join(map(re.escape, vocabulary.count_words))
        + r")\s*[\d"
        + vocabulary.numerals
        + r"]+\s*"
        + vocabulary.subject_unit
    )
    for line in cleaned.splitlines():
        for pattern in (counted, _SUBJECT_COUNT):
            for hit in pattern.findall(line):
                found.setdefault(hit, []).append(snippet(line))
    return found


def role_words(text: str, proof: str, vocabulary: Vocabulary) -> list[dict]:
    """Each role word on a resume line, the fixed phrases that merely contain one left out, with whether the
    student's own files carry the word with the same two characters after it."""
    hits = []
    for line in (text or "").splitlines():
        masked = line
        for phrase in vocabulary.role_exempt:
            masked = masked.replace(phrase, " " * len(phrase))
        for word in vocabulary.role_words:
            for found in re.finditer(re.escape(word), masked):
                if any(longer != word and word in longer and longer in masked for longer in vocabulary.role_words):
                    continue
                phrase = line[found.start() : found.end() + 2]
                hits.append({"word": word, "line": snippet(line), "in_student_files": phrase in proof})
    return hits


def numbers(text: str) -> list[str]:
    return [found.group().replace(" ", "").replace(chr(0xFF05), "%") for found in _NUMBER.finditer(text or "")]


def held(figure: str, sources: str) -> bool:
    """Whether a source holds the figure: a percentage as written, a decimal as written or part by part, a whole
    number as a number of its own."""
    exact = set(numbers(sources))
    whole = {int(digits) for digits in re.findall(r"\d+", sources or "")}
    if figure.endswith("%"):
        return figure in exact
    if "." in figure:
        return figure in exact or all(int(part) in whole for part in figure.split("."))
    return int(figure) in whole


def mentions(figure: str, texts: list[str]) -> list[str]:
    """The lines of `texts` that carry the figure as a number of its own."""
    digits = figure.rstrip("%")
    pattern = re.compile(rf"(?<![\d.]){re.escape(digits)}(?![\d.])")
    return [snippet(line) for text in texts for line in text.splitlines() if pattern.search(line)]


def unsourced(text: str, proof: str, draft: str, asked: list[str]) -> list[dict]:
    """Figures on the resume's lines that no handout but the uploaded draft holds, each with whether the draft holds
    it and every line the student said that carries it (for the lead to read: a confirmation, a correction, or a
    figure the student only ever gave in the chat)."""
    missing = []
    for line in (text or "").splitlines():
        for figure in numbers(line):
            if held(figure, proof):
                continue
            missing.append(
                {
                    "figure": figure,
                    "line": snippet(line),
                    "in_draft": held(figure, draft),
                    "student_said": mentions(figure, asked),
                }
            )
    return missing


def education_first(headings: list[str], vocabulary: Vocabulary) -> bool:
    """Whether education is the first module once a personal-details module (template section 3, module 1) is
    passed over."""
    modules = [heading for heading in headings if vocabulary.personal_heading not in heading]
    return bool(modules) and vocabulary.education_heading in modules[0]


def resume_facts(
    name: str, text: str, proof: str, draft: str, asked: list[str], student: dict, vocabulary: Vocabulary
) -> dict:
    headings = [heading for heading, _ in sections(text)]
    figures = unsourced(text, proof, draft, asked)
    return {
        "sections": headings,
        "education_first": education_first(headings, vocabulary),
        "rows": rows(text, vocabulary),
        "row_limit": vocabulary.row_limit,
        "cpa_subjects": cpa_subjects(text, vocabulary),
        "pending_wording": pending_wording(text, vocabulary),
        "role_words": role_words(text, proof, vocabulary),
        "unsourced_numbers": figures,
        "draft_figures_kept": [item for item in figures if item["in_draft"]],
        "dates_off_style": [snippet(line) for line in (text or "").splitlines() if _OFF_STYLE.search(line)],
        "named_by_template": bool(student.get("name"))
        and name.startswith(f"{student['name']}-{vocabulary.school}-")
        and Path(name).suffix == ".md",
    }


# The records of a session --------------------------------------------------------------------------------------------


def tool_events(records, turn: int, scope: tuple = ()):
    """Tool events with their turn and child-execution scope; call IDs are local to that scope."""
    for index, row in enumerate(records or ()):
        if row.get("kind") == "child.execution":
            yield from tool_events(row.get("records"), turn, (*scope, index))
        elif row.get("kind") == "runner.event" and row.get("event_type", "ToolEvent") == "ToolEvent":
            yield turn, scope, row.get("event") or {}


def writes(exchanges) -> list[dict]:
    """The file writes of a drill in order: turn, path, whether it succeeded, the content after it when known."""
    started, pending = [], {}
    for turn, exchange in enumerate(exchanges, 1):
        for at, scope, event in tool_events(exchange.execution.records, turn):
            key = (at, scope, event.get("tool_call_id"))
            if event.get("phase") == "start" and event.get("name"):
                entry = {"turn": at, "event": event, "finished": {}}
                started.append(entry)
                pending.setdefault(key, []).append(entry)
            elif event.get("phase") == "complete" and event.get("tool_call_id"):
                if pending.get(key):
                    pending[key].pop(0)["finished"] = event
    found = []
    for entry in started:
        turn, event, finished = entry["turn"], entry["event"], entry["finished"]
        arguments = event.get("arguments") or {}
        change = finished.get("file_change") or {}
        if event.get("name") not in WRITES and not change and not finished.get("file_written"):
            continue
        refused = str(finished.get("result_preview") or "").startswith(REFUSED)
        ok = (
            False
            if refused or finished.get("ok") is False
            else (True if finished.get("ok") is True or isinstance(change.get("after"), str) else None)
        )
        changes = [change] if change or event.get("name") in WRITES else []
        changes.extend(item for item in finished.get("file_written") or () if item.get("path") != change.get("path"))
        for changed in changes:
            found.append(
                {
                    "turn": turn,
                    "tool": event.get("name"),
                    "path": str(changed.get("path") or arguments.get("path") or ""),
                    "ok": ok,
                    "after": changed.get("after"),
                    "before_known": "before" in changed,
                    "before": changed.get("before"),
                    "created": changed.get("created"),
                    "arguments": arguments,
                }
            )
    return found


def tail(path: str, parts: int = 2) -> str:
    return "/".join(Path(path).parts[-parts:])


def in_folder(path: str, folder: str) -> bool:
    return folder in Path(path).parts[:-1] and UPLOADS not in Path(path).parts


def rebuilt(written: list[dict], folder: str) -> dict[str, dict]:
    """The record files a drill wrote under the records folder, rebuilt from its writes: the content after the last
    write when the record holds it, an appended part added to what came before."""
    files: dict[str, dict] = {}
    for write in written:
        if not write["ok"] or not in_folder(write["path"], folder):
            continue
        key = tail(write["path"])
        entry = files.setdefault(key, {"content": None, "content_complete": False, "turns": [], "pre_existing": None})
        entry["turns"].append(write["turn"])
        if entry["pre_existing"] is None:
            if write["before_known"]:
                entry["pre_existing"] = write["before"] is not None
            elif write["created"] is not None:
                entry["pre_existing"] = not write["created"]
        arguments = write["arguments"]
        if write["after"] is not None:
            entry["content"] = write["after"]
            entry["content_complete"] = True
        elif write["tool"] == "write_file" and arguments.get("mode") == "append":
            previous = entry["content"] if entry["content"] is not None else write["before"]
            entry["content_complete"] = entry["content_complete"] or write["before_known"]
            entry["content"] = (previous or "") + str(arguments.get("content") or "")
        elif write["tool"] == "write_file":
            entry["content"] = str(arguments.get("content") or "")
            entry["content_complete"] = True
        elif entry["content"] is not None:
            entry["content"] = entry["content"].replace(
                str(arguments.get("old_text") or ""), str(arguments.get("new_text") or ""), 1
            )
    return files


def dates(text: str, year: str | None = None) -> list[str]:
    """The dates a text cites, as YYYY-MM-DD: full dates, and month-and-day ones read in `year` (the session's)."""
    found = {(year_, month, day) for year_, month, day in _DATE.findall(text or "")}
    if year:
        found |= {(year, month, day) for month, day in _MONTH_DAY.findall(text or "")}
    return sorted(
        f"{year_}-{int(month):02d}-{int(day):02d}"
        for year_, month, day in found
        if 1 <= int(month) <= 12 and 1 <= int(day) <= 31
    )


def field_text(content: str, field: str, vocabulary: Vocabulary) -> str:
    """What the record writes under `field`: from its label to the next field label or blank line."""
    lines = content.splitlines()
    pattern = re.compile(rf"^\s*(?:[-*+]\s+)?{re.escape(field)}\s*[:{chr(0xFF1A)}]\s*(.*)$")
    labels_ = (*vocabulary.record_fields, *vocabulary.record_metadata)
    for at, line in enumerate(lines):
        matched = pattern.match(line)
        if not matched:
            continue
        parts = [matched.group(1)]
        for later in lines[at + 1 :]:
            if not later.strip() or later.lstrip().startswith("## ") or any(other in later for other in labels_):
                break
            parts.append(later.strip())
        return snippet(" ".join(part for part in parts if part).replace("\n", " ") or "")
    return ""


def record_facts(files: dict[str, dict], student: dict, vocabulary: Vocabulary, source: str) -> list[dict]:
    year = (student.get("date") or "")[:4] or None
    found = []
    for path, entry in sorted(files.items()):
        content = entry["content"] or ""
        sessions = list(re.finditer(r"^##\s+(\d{4}-\d{2}-\d{2})\s+([^\n]+)", content, re.M))
        current = next((match for match in reversed(sessions) if match.group(1) == student.get("date")), None)
        following = next(
            (match.start() for match in sessions if current and match.start() > current.start()), len(content)
        )
        block = content[current.end() : following] if current else ""
        session_type = next(
            (type_ for type_ in vocabulary.record_types if current and current.group(2).startswith(type_)), None
        )
        fields = (*vocabulary.record_fields, *vocabulary.record_metadata)
        first_line = content.strip().splitlines()[0] if content.strip() else ""
        present = {
            field
            for field in fields
            if re.search(rf"^\s*(?:[-*+]\s+)?{re.escape(field)}\s*[:{chr(0xFF1A)}]", block, re.M)
        }
        found.append(
            {
                "path": path,
                "from": source,
                "named_by_student_number": bool(student.get("number")) and Path(path).stem == student["number"],
                "identity_matches": bool(student.get("number") and student.get("name"))
                and all(student[key] in first_line for key in ("number", "name")),
                "current_session_found": current is not None,
                "session_type_matches": bool(session_type) and session_type == student.get("topic"),
                "missing_identity_fields": [
                    field for field in vocabulary.record_identity_fields if not field_text(content, field, vocabulary)
                ],
                "missing_fields": [field for field in fields if field not in present],
                "empty_fields": [
                    field for field in fields if field in present and not field_text(block, field, vocabulary)
                ],
                "previous_session": field_text(block, vocabulary.record_fields[0], vocabulary),
                "dates_cited": dates((current.group(0) + "\n" + block) if current else "", year),
                "written_in_turns": entry.get("turns", []),
                "pre_existing": entry.get("pre_existing"),
                "changed_this_session": entry.get("changed_this_session", True if entry.get("turns") else None),
                "previous_content_preserved": entry.get("previous_content_preserved"),
                "content_available": entry["content"] is not None,
                "content_complete": entry.get("content_complete", True),
                "characters": len(content),
            }
        )
        if entry["content"] is None:
            for key in (
                "identity_matches",
                "current_session_found",
                "session_type_matches",
                "missing_identity_fields",
                "missing_fields",
                "empty_fields",
                "previous_session",
                "dates_cited",
                "characters",
            ):
                found[-1][key] = None
    return found


# Practice questions and signing questions -----------------------------------------------------------------------------


def passages(text: str) -> list[str]:
    """A message's paragraphs, its quoted spans and its quoted lines, the units a ready answer would stand in."""
    found = [part for part in re.split(r"\n\s*\n|\n(?=\s*(?:[-*>]|\d+[.)]))", text or "") if part.strip()]
    quoted = re.findall(
        "[" + chr(0x201C) + chr(0x300C) + '"](.+?)[' + chr(0x201D) + chr(0x300D) + '"]', text or "", re.S
    )
    return found + quoted


def recited(passage: str, student: str) -> bool:
    """Whether a passage mostly repeats what the student said: most of its eight-character runs occur there."""
    letters = "".join(_HAN.findall(passage))
    said = "".join(_HAN.findall(student))
    runs = [letters[at : at + 8] for at in range(0, max(len(letters) - 7, 0), 4)]
    return bool(runs) and sum(run in said for run in runs) >= 0.6 * len(runs)


def labels(passage: str, vocabulary: Vocabulary) -> list[str]:
    """The answer labels a passage wears, a label preceded within a few characters by a negation (the assistant
    saying it gives none) left out."""
    found = []
    for mark in vocabulary.answer_marks:
        for hit in re.finditer(re.escape(mark), passage):
            before = passage[max(0, hit.start() - _NEGATION_REACH) : hit.start()]
            if not any(negation in before for negation in vocabulary.answer_negations):
                found.append(mark)
                break
    return found


def interview_facts(said: list[str], asked: list[str], vocabulary: Vocabulary) -> dict:
    """Answer and feedback candidates, with every assistant turn scanned against only student speech available then."""
    least = vocabulary.answer_length * 2 // 3
    long_answers = [turn for turn, text in enumerate(asked, 1) if turn > 1 and han(text) >= least]
    ready = []
    for turn, text in enumerate(said, 1):
        student = "\n".join(asked[:turn])
        for passage in passages(text):
            first, second = passage.count(vocabulary.first_person), passage.count(vocabulary.second_person)
            labelled = labels(passage, vocabulary)
            voiced = han(passage) >= vocabulary.answer_length and first >= 3 and second == 0
            if (voiced or (labelled and han(passage))) and not recited(passage, student):
                ready.append({"turn": turn, "labels": labelled, "passage": snippet(passage.replace("\n", " "))})
    feedback = [
        {
            "turn": turn,
            "outline_points": sum(bool(_LIST_ITEM.match(line)) for line in text.splitlines()),
            "star_words": [word for word in vocabulary.star_words if word in text],
        }
        for turn, text in enumerate(said, 1)
        if long_answers and turn >= long_answers[0]
    ]
    unique = {(item["turn"], item["passage"]): item for item in ready}
    return {"student_long_answers": long_answers, "model_answers": list(unique.values()), "feedback_turns": feedback}


def compact(text: str) -> str:
    """Text with its whitespace and the separators inside numbers removed, so 'Building 112' and '5,000' match."""
    return re.sub(r"(?<=\d)[,\s](?=\d)", "", re.sub(r"\s+", "", text or ""))


def signing_facts(said: list[str], cues: str, vocabulary: Vocabulary) -> dict | None:
    """Which offices and which cap the assistant named; None when nothing in the session is about signing or fees."""
    if not any(cue in cues for cue in vocabulary.signing_cues):
        return None
    text = compact("\n".join(said))
    return {
        "offices_named": [desk for desk in vocabulary.desks if compact(desk) in text],
        "cap_named": vocabulary.penalty_cap in text or any(word in text for word in vocabulary.cap_words),
    }


# The facts of one drill ------------------------------------------------------------------------------------------------


def student_of(texts: list[str], vocabulary: Vocabulary) -> dict:
    """The student's number, name and session date from the appointment slip's table."""
    labels = {
        "number": vocabulary.number_label,
        "name": vocabulary.name_label,
        "date": vocabulary.date_label,
        "topic": vocabulary.topic_label,
    }
    found = {}
    for text in texts:
        for table in tables(text):
            for row in table:
                for key, label in labels.items():
                    if len(row) > 1 and row[0] == label and key not in found:
                        value = row[1]
                        found[key] = (
                            _LEADING_DATE.match(value).group(1)
                            if key == "date" and _LEADING_DATE.match(value)
                            else value
                        )
    return found


def facts(
    exchanges,
    handouts: dict[str, str],
    vocabulary: Vocabulary,
    placed: Path | None = None,
    before: Path | None = None,
) -> dict:
    """The coaching lead's facts for one drill, keyed by what each measures. `handouts` maps each file the student
    handed over to its text; `placed` is the drill's working folder and `before` its baseline, when retained."""
    said, asked = messages(exchanges), [exchange.user for exchange in exchanges]
    drafts = {name for name in handouts if any(mark in name for mark in vocabulary.draft_marks)}
    proof = "\n".join(text for name, text in handouts.items() if name not in drafts)
    draft = "\n".join(handouts[name] for name in drafts)
    student = student_of(list(handouts.values()), vocabulary)
    found: dict = {"student": student} if student else {}
    files = delivered(exchanges)
    resumes = {
        name: resume_facts(name, text, proof, draft, asked, student, vocabulary)
        for name, text in files.items()
        if Path(name).suffix.lower() in TEXT_SUFFIXES and is_resume(text, vocabulary)
    }
    if resumes:
        found["resume"] = resumes
    versions = []
    last = {str(path): turn for turn, exchange in enumerate(exchanges, 1) for path in exchange.execution.deliverables}
    for turn, exchange in enumerate(exchanges, 1):
        for path in exchange.execution.deliverables:
            file = Path(path)
            version = {"turn": turn, "file": file.name, "content_available": False}
            if last[str(path)] != turn or not file.is_file():
                version["unavailable"] = "The delivery has no independently retained readable version."
            elif file.suffix.lower() in TEXT_SUFFIXES:
                try:
                    data = file.read_bytes()
                    content = data.decode("utf-8")
                except (OSError, UnicodeError):
                    version["unavailable"] = "The retained text could not be read as UTF-8."
                    versions.append(version)
                    continue
                version.update(
                    {
                        "content_available": True,
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "recognized_as_resume": is_resume(content, vocabulary),
                        "facts": resume_facts(file.name, content, proof, draft, asked[:turn], student, vocabulary),
                    }
                )
            else:
                version["unavailable"] = "The delivery is not the prescribed Markdown resume format."
            versions.append(version)
    if versions:
        found["resume_versions"] = versions
    written = writes(exchanges)
    touched = [
        {"turn": write["turn"], "path": tail(write["path"]), "ok": write["ok"]}
        for write in written
        if UPLOADS in Path(write["path"]).parts and Path(write["path"]).name in drafts
    ]
    if touched:
        found["draft_writes"] = touched
    on_disk = sorted((Path(placed) / vocabulary.records_folder).glob("*.md")) if placed else []
    turns = rebuilt(written, vocabulary.records_folder)
    if placed is not None and Path(placed).is_dir():
        kept = {}
        for path in on_disk:
            key = f"{vocabulary.records_folder}/{path.name}"
            content = path.read_text(errors="replace")
            entry = {**turns.get(key, {}), "content": content, "content_complete": True}
            if before is not None:
                old = Path(before) / vocabulary.records_folder / path.name
                previous = old.read_text(errors="replace") if old.is_file() else None
                entry.update(
                    {
                        "pre_existing": previous is not None,
                        "changed_this_session": previous != content,
                        "previous_content_preserved": content.startswith(previous) if previous is not None else None,
                    }
                )
            kept[key] = entry
        found["records"] = record_facts(kept, student, vocabulary, "working folder")
    elif turns:
        found["records"] = record_facts(turns, student, vocabulary, "rebuilt from the recorded writes")
    else:
        found["records"] = []
    deliveries = [
        {"turn": turn, "files": [Path(path).name for path in exchange.execution.deliverables]}
        for turn, exchange in enumerate(exchanges, 1)
        if exchange.execution.deliverables
    ]
    first = deliveries[0]["turn"] if deliveries else len(said) + 1
    found["process"] = {
        "questions_before_first_delivery": sum(("?" in text or chr(0xFF1F) in text) for text in said[: first - 1]),
        "deliveries": deliveries,
        "record_write_turns": sorted({turn for entry in turns.values() for turn in entry["turns"]}),
        "files_written": [{"turn": write["turn"], "path": tail(write["path"]), "ok": write["ok"]} for write in written],
    }
    if student.get("topic") == vocabulary.practice_topic:
        found["interview"] = interview_facts(said, asked, vocabulary)
    signing = signing_facts(said, "\n".join([*asked, *handouts.values()]), vocabulary)
    if signing:
        found["signing"] = signing
    if files:
        found["delivered_files"] = sorted(files)
    return found


def card_of(name: str, card) -> str:
    """The drill card a session played: the card's own name, else the session name without the bench's prefix and
    repeat number (`holdout-jiayi-2` played `jiayi`)."""
    if card is not None and getattr(card, "name", None):
        return card.name
    matched = _SESSION.match(name)
    return matched.group("card") if matched else name


class CareerCentreOwner(Owner):
    """The coaching lead of the career centre scenario, judging with the centre's word lists, page rule and records."""

    def __init__(self, scenario, provider, skills, **options):
        super().__init__(scenario, provider, skills, facts=self._facts, **options)
        self.vocabulary = Vocabulary.load(scenario.root)
        self.handouts = {persona.name: tuple(persona.files) for persona in getattr(scenario, "personas", ())}

    def _facts(self, name, exchanges, card) -> dict:
        handed = {
            Path(path).name: Path(path).read_text(errors="replace")
            for path in self.handouts.get(card_of(name, card), ())
            if Path(path).is_file()
        }
        placed = (self.workdirs.get(name) or {}).get("workdir")
        return facts(exchanges, handed, self.vocabulary, Path(placed) if placed else None, self.workdir)


def resumes_delivered(item: dict) -> bool:
    """Whether known resume appointments have a retained readable resume; advice appointments require no delivery."""
    from experimental.harness.scenario.contract import load

    root = Path(item.get("scenario_root") or Path(__file__).parent)
    vocabulary = Vocabulary.load(root)
    topics = {
        card.id: student_of([(root / path).read_text() for path in card.files], vocabulary).get("topic")
        for card in load(root).situation.cases
    }
    drills = item.get("drills") or []
    for drill in drills:
        card = card_of(str(drill.get("card") or drill.get("session") or ""), None)
        if card not in topics:
            return False
        if topics[card] != vocabulary.resume_topic:
            continue
        files = {
            (file.get("name"), file.get("sha256"))
            for exchange in drill.get("exchanges") or []
            for file in exchange.get("delivered") or []
            if file.get("path") and file.get("sha256") and Path(file.get("name") or "").suffix == ".md"
        }
        versions = (drill.get("references") or {}).get("resume_versions") or []
        if not any(
            version.get("content_available")
            and version.get("recognized_as_resume")
            and (version.get("file"), version.get("sha256")) in files
            for version in versions
        ):
            return False
    return bool(drills)


# The owner the simulation entry judges this case by (`experimental.simulation.__main__.owner_of`).
OWNER = CareerCentreOwner
DELIVERED = resumes_delivered
