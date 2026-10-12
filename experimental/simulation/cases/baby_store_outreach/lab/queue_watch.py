"""Read-only patrol readings of a store's outbound queue: the store time, the pending messages and the members' news.

`python3 queue_watch.py --queue <shared folder>/<queue folder>` prints one JSON line per item: an overview (store time,
reading number, the seconds until the next suggested reading, folder counts), then every pending message (file, member,
planned time, whether it is due), then every member event the store system has pushed so far (new orders, replies).

The store time starts on the first reading that finds a pending message and then runs on its own clock; it is kept
in a small state file beside this script (or, when that folder cannot be written, inside the queue folder), keyed by
the queue's path, so every queue has its own clock. The script never changes a queue file; moving files and keeping
the ledger is the on-call colleague's work. Folder names, labels and the pushed member events are read from
`feed_cache.md` beside this script.
"""

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
FEED = HERE / "feed_cache.md"
STORE_SECONDS_PER_SECOND = 90
NEXT_CHECK_SECONDS = 40
MEMBER = re.compile(r"XS\d{6}")
NAMED = re.compile(r"(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})-")
FULL = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2})[:.](\d{2})")
SHORT = re.compile(r"(\d{1,2})-(\d{1,2})\s+(\d{1,2})[:.](\d{2})")
STAMP = "%Y-%m-%d %H:%M"


def tables(text: str) -> list[list[list[str]]]:
    """Every markdown table as rows of cells, the separator row left out."""
    found, rows = [], []
    for line in [*text.splitlines(), ""]:
        if line.strip().startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                rows.append(cells)
        elif rows:
            found.append(rows)
            rows = []
    return found


def load_feed(path: Path = FEED) -> dict:
    """The folder names and labels, the known batches with their anchors and members, their events, and the
    events for a batch the cache does not know."""
    feed = {"labels": {}, "batches": {}, "events": {}, "fallback": []}
    for table in tables(path.read_text(encoding="utf-8")):
        head, rows = table[0], table[1:]
        if head == ["key", "value"]:
            feed["labels"].update({row[0]: row[1] for row in rows})
        elif head == ["batch", "anchor", "members"]:
            for batch, anchor, members in rows:
                feed["batches"][batch] = (datetime.strptime(anchor, STAMP), set(members.split()))
        elif head[:2] == ["batch", "after_minutes"]:
            for batch, minutes, member, kind, channel, detail in rows:
                feed["events"].setdefault(batch, []).append(
                    {"after": int(minutes), "member": member, "kind": kind, "channel": channel, "detail": detail}
                )
        elif head[:1] == ["after_minutes"]:
            for minutes, kind, channel, detail in rows:
                feed["fallback"].append({"after": int(minutes), "kind": kind, "channel": channel, "detail": detail})
    return feed


def planned_of(path: Path, label: str, year: int) -> datetime | None:
    """A queue file's planned time: from its name (`YYYYMMDD-HHMM-...`), else from the labelled line of its text."""
    named = NAMED.match(path.name)
    if named:
        y, mo, d, h, mi = (int(part) for part in named.groups())
        return datetime(y, mo, d, h, mi)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        if label and label not in line:
            continue
        full = FULL.search(line)
        if full:
            y, mo, d, h, mi = (int(part) for part in full.groups())
            return datetime(y, mo, d, h, mi)
        short = SHORT.search(line)
        if short:
            mo, d, h, mi = (int(part) for part in short.groups())
            return datetime(year, mo, d, h, mi)
    return None


def member_of(path: Path) -> str | None:
    found = MEMBER.search(path.name)
    if found:
        return found.group()
    try:
        found = MEMBER.search(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    return found.group() if found else None


def files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(path for path in folder.iterdir() if path.is_file() and not path.name.startswith("."))


def pending_items(queue: Path, feed: dict, year: int) -> list[dict]:
    label = feed["labels"].get("planned_label", "")
    items = []
    for path in files(queue / feed["labels"]["pending"]):
        planned = planned_of(path, label, year)
        items.append({"file": path.name, "member": member_of(path), "planned": planned})
    return items


def state_path(queue: Path, home: Path = HERE) -> Path:
    key = hashlib.sha1(str(queue.resolve()).encode()).hexdigest()[:16]
    folder = home / ".queue_watch"
    try:
        folder.mkdir(exist_ok=True)
        probe = folder / ".probe"
        probe.write_text("")
        probe.unlink()
        return folder / f"{key}.json"
    except OSError:
        return queue / ".queue_watch.json"


def start(items: list[dict], feed: dict) -> dict:
    """The clock's anchor and the events of this queue, fixed on the first reading that finds pending messages."""
    members = {item["member"] for item in items if item["member"]}
    best, overlap = None, 0
    for batch, (_, known) in feed["batches"].items():
        if len(members & known) > overlap:
            best, overlap = batch, len(members & known)
    if best is not None:
        anchor = feed["batches"][best][0]
        events = [dict(event) for event in feed["events"].get(best, [])]
        return {"batch": best, "anchor": anchor.strftime(STAMP), "events": events}
    timed = [item for item in items if item["planned"] is not None]
    earliest = min((item["planned"] for item in timed), default=datetime.now().replace(second=0, microsecond=0))
    anchor = earliest - timedelta(minutes=60)
    anchor = anchor.replace(minute=0 if anchor.minute < 30 else 30)
    ordered = sorted(timed, key=lambda item: (item["planned"], item["file"]))
    events = []
    for event in feed["fallback"]:
        if not ordered:
            break
        target = ordered[-1] if event["kind"] == "order" else ordered[0]
        events.append({**event, "member": target["member"] or target["file"]})
    return {"batch": None, "anchor": anchor.strftime(STAMP), "events": events}


def read(queue: Path, now: float | None = None, feed: dict | None = None, home: Path = HERE) -> list[dict]:
    """One reading of `queue`, as the lines it prints; `home` holds the clocks' state files."""
    feed = feed or load_feed()
    now = time.time() if now is None else now
    labels = feed["labels"]
    if not queue.is_dir():
        return [{"error": f"queue folder not found: {queue}"}]
    keep = state_path(queue, home)
    state = json.loads(keep.read_text()) if keep.is_file() else None
    year = datetime.strptime(state["anchor"], STAMP).year if state else datetime.now().year
    items = pending_items(queue, feed, year)
    counts = {
        "pending": len(items),
        "pushed": len(files(queue / labels["pushed"])),
        "withdrawn": len(files(queue / labels["withdrawn"])),
    }
    if state is None:
        if not items:
            return [{"store_time": None, "reading": 0, "next_check_seconds": NEXT_CHECK_SECONDS, **counts}]
        state = {**start(items, feed), "started": now, "readings": 0, "shown": None}
        items = pending_items(queue, feed, datetime.strptime(state["anchor"], STAMP).year)
    anchor = datetime.strptime(state["anchor"], STAMP)
    store = anchor + timedelta(seconds=(now - state["started"]) * STORE_SECONDS_PER_SECOND)
    shown = datetime.strptime(state["shown"], STAMP) if state.get("shown") else None
    state["readings"] += 1
    lines = [
        {
            "store_time": store.strftime(STAMP),
            "reading": state["readings"],
            "next_check_seconds": NEXT_CHECK_SECONDS,
            **counts,
        }
    ]
    for item in sorted(items, key=lambda item: (item["planned"] or datetime.max, item["file"])):
        planned = item["planned"]
        lines.append(
            {
                "file": item["file"],
                "member": item["member"],
                "planned": planned.strftime(STAMP) if planned else None,
                "due": bool(planned and planned <= store),
            }
        )
    for event in state["events"]:
        at = anchor + timedelta(minutes=event["after"])
        if at > store:
            continue
        lines.append(
            {
                "at": at.strftime(STAMP),
                "member": event["member"],
                "kind": event["kind"],
                "channel": event["channel"],
                "detail": event["detail"],
                "new": shown is None or at > shown,
            }
        )
    state["shown"] = store.strftime(STAMP)
    keep.write_text(json.dumps(state, ensure_ascii=False))
    return lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Read-only patrol readings of a store's outbound queue.")
    parser.add_argument("--queue", required=True, help="the outbound queue folder inside the store's shared folder")
    args = parser.parse_args(argv)
    lines = read(Path(args.queue))
    for line in lines:
        print(json.dumps(line, ensure_ascii=False))
    return 1 if "error" in lines[0] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
