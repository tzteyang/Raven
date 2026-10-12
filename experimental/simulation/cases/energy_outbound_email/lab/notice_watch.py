"""Announcement readings for the sales team's signal watch: what the watched companies have published so far.

Usage: python3 notice_watch.py read <watch list file or company name> [...]

The first line describes the reading: `read_at`, `watch_started`, `reading` (which reading of this watch it is),
`watching` (the companies matched) and `unmatched` (names given that the feed does not know). Every following line is
one announcement of a watched company, newest first: `id`, `company`, `source`, `published`, `title`, `summary`,
`link`, and `new`, true when it was published after the watch started. Times are China Standard Time on the watch day.

The announcements come from `feed.md` beside this script. A watch starts at the first reading of a set of companies
(or of a list file) and runs in real time from there; it is kept in a state file beside this script, and a set not
read for IDLE_MINUTES starts a new watch at its next reading. Nothing else is written.
"""

import fcntl
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
FEED = HERE / "feed.md"
STATE = HERE / ".notice_watch_state.json"
LOCK = HERE / ".notice_watch_state.lock"
IDLE_MINUTES = 15
CST = timezone(timedelta(hours=8))
USAGE = "usage: python3 notice_watch.py read <watch list file or company name> [...]"


def tables(text):
    """Each markdown table under its nearest heading, as a list of dicts keyed by the header cells."""
    found, heading, rows = {}, "", []
    for line in [*text.splitlines(), ""]:
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                rows.append(cells)
            continue
        if rows:
            head, *body = rows
            found[heading] = [dict(zip(head, cells, strict=False)) for cells in body]
            rows = []
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
    return found


def load_feed():
    found = tables(FEED.read_text(encoding="utf-8"))
    day = next(row["value"] for row in found["feed"] if row["key"] == "day")
    companies = [(row["name"], row["short"]) for row in found["companies"]]
    return day, companies, found["notices"]


def watched(arguments, companies):
    """The companies the arguments name, the arguments that name none, and the files among them."""
    chosen, unmatched, files = set(), [], []
    for argument in arguments:
        path = Path(argument)
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            files.append(str(path.resolve()))
            chosen |= {name for name, short in companies if name in text or short in text}
            continue
        hits = {name for name, short in companies if name in argument or short in argument or argument in name}
        if len(argument) < 2:
            hits = set()
        if hits:
            chosen |= hits
        else:
            unmatched.append(argument)
    return sorted(chosen), unmatched, files


def advance(key, now):
    """This reading's watch: (started, reading number), started afresh when the key was idle too long."""
    with LOCK.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            state = json.loads(STATE.read_text()) if STATE.is_file() else {}
        except ValueError:
            state = {}
        entry = state.get(key)
        if entry is None or now - entry["last"] > IDLE_MINUTES * 60:
            entry = {"started": now, "last": now, "readings": 0}
        entry["readings"] += 1
        entry["last"] = now
        state[key] = entry
        temporary = STATE.with_suffix(".tmp")
        temporary.write_text(json.dumps(state))
        temporary.replace(STATE)
        return entry["started"], entry["readings"]


def on_day(day, moment, started=None):
    """`moment` (epoch seconds) as a time on the watch day, China Standard Time."""
    started = moment if started is None else started
    baseline = datetime.fromtimestamp(started, CST)
    year, month, date_day = map(int, day.split("-"))
    virtual = baseline.replace(year=year, month=month, day=date_day) + timedelta(seconds=moment - started)
    return virtual.strftime("%Y-%m-%d %H:%M:%S")


def reading(arguments, now=None):
    day, companies, notices = load_feed()
    names, unmatched, files = watched(arguments, companies)
    if not names:
        return [{"error": "none of the arguments names a company in the feed", "unmatched": unmatched, "usage": USAGE}]
    now = time.time() if now is None else now
    key = "files:" + "|".join(sorted(files)) if files else "names:" + "|".join(names)
    started, number = advance(key, now)
    shorts = {short: name for name, short in companies}
    seen = []
    for notice in notices:
        company = shorts.get(notice["company"], notice["company"])
        if company not in names:
            continue
        published = notice["published"]
        if published.startswith("+"):
            offset = int(published[1:])
            if started + offset > now:
                continue
            seen.append(((1, offset), notice, company, on_day(day, started + offset, started), True))
        else:
            seen.append(((0, published), notice, company, published, False))
    lines = [
        {
            "read_at": on_day(day, now, started),
            "elapsed_seconds": now - started,
            "watch_id": hashlib.sha256(f"{HERE}:{key}:{started}".encode()).hexdigest(),
            "script_path": str(Path(__file__).resolve()),
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "feed_sha256": hashlib.sha256(FEED.read_bytes()).hexdigest(),
            "input_files": [
                {"name": Path(path).name, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
                for path in files
            ],
            "watch_started": on_day(day, started),
            "reading": number,
            "watching": names,
            "unmatched": unmatched,
        }
    ]
    for _, notice, company, published, new in sorted(seen, key=lambda item: item[0], reverse=True):
        lines.append(
            {
                "id": notice["id"],
                "company": company,
                "source": notice["source"],
                "published": published,
                "title": notice["title"],
                "summary": notice["summary"],
                "link": notice["link"],
                "new": new,
            }
        )
    return lines


def main(argv):
    if len(argv) < 2 or argv[0] != "read":
        print(USAGE)
        return 2
    try:
        lines = reading(argv[1:])
    except OSError as exc:
        print(json.dumps({"error": f"the watch state beside the script cannot be kept: {exc}"}))
        return 1
    for line in lines:
        print(json.dumps(line, ensure_ascii=False))
    return 2 if "error" in lines[0] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
