"""Read-only live console of the farm live room: one JSON line with a live session's numbers at this moment.

`python3 live_console.py read <session number>` prints, for the session numbered on that live's product card, the
console time, how long the session has been on air, the viewers online, what is left of each link's presale quota and
whether the link is sold out, and every platform notice raised so far, with its time. The numbers come from
`sessions.md` beside the script. A session's clock starts at the first read of it and then runs in real time, so a
watch sees the session unfold while it watches; a session not read for `IDLE` seconds starts afresh at its next read.
The start times are the only thing the script writes, in a state file beside it (or in the temporary directory when
that folder is read-only).
"""

import contextlib
import fcntl
import hashlib
import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "sessions.md"
STATE = ".live_console_state.json"
IDLE = 600
USAGE = "usage: python3 live_console.py read <session number>   (the session number is on the live's product card)"


def seconds(text: str) -> int:
    """`MM:SS` (minutes may exceed 59) as seconds."""
    minutes, _, rest = text.strip().partition(":")
    return int(minutes) * 60 + int(rest)


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def sessions(text: str) -> dict[str, dict]:
    """The sessions of the data file: start time, first-read offset, links, stock anchors and notices of each."""
    found: dict[str, dict] = {}
    current, table = None, None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            current = {"start": "00:00", "first_read": 0, "links": [], "stock": [], "notices": []}
            found[stripped[3:].strip()] = current
            table = None
        elif current is None:
            continue
        elif stripped.startswith("### "):
            table = stripped[4:].strip()
        elif stripped.startswith("- ") and ":" in stripped:
            key, _, value = stripped[2:].partition(":")
            if key.strip() == "start":
                current["start"] = value.strip()
            elif key.strip() == "first_read":
                current["first_read"] = seconds(value)
        elif stripped.startswith("|") and table:
            cells = _cells(stripped)
            if not cells or set(cells[0]) <= set("-:") or not cells[0][:1].isdigit():
                continue
            if table == "links":
                current["links"].append({"no": int(cells[0]), "name": cells[1], "quota": int(cells[2])})
            elif table == "stock":
                current["stock"].append((seconds(cells[0]), [float(cell) for cell in cells[1:]]))
            elif table == "notices":
                current["notices"].append((seconds(cells[0]), cells[1]))
    return found


def _values(anchors, on_air: int) -> list[float]:
    """The stock of each link and the viewers online at `on_air`, read linearly between the anchors around it."""
    if on_air <= anchors[0][0]:
        return anchors[0][1]
    for (left, low), (right, high) in zip(anchors, anchors[1:]):
        if left <= on_air <= right:
            share = (on_air - left) / (right - left)
            return [a + (b - a) * share for a, b in zip(low, high)]
    return anchors[-1][1]


def clock(start: str, on_air: int) -> str:
    hours, _, minutes = start.partition(":")
    total = int(hours) * 3600 + int(minutes) * 60 + on_air
    return f"{total // 3600 % 24:02d}:{total // 60 % 60:02d}:{total % 60:02d}"


def reading(number: str, session: dict, on_air: int) -> dict:
    """What the console shows of one session `on_air` seconds after it went on air."""
    values = _values(session["stock"], on_air)
    links = []
    for item, value in zip(session["links"], values):
        left = max(0, math.ceil(value - 1e-9))
        links.append(
            {"no": item["no"], "name": item["name"], "stock": left, "state": "sold_out" if left == 0 else "on_sale"}
        )
    return {
        "session": number,
        "clock": clock(session["start"], on_air),
        "on_air": f"{on_air // 60:02d}:{on_air % 60:02d}",
        "online": round(values[len(session["links"])]),
        "links": links,
        "notices": [
            {"at": clock(session["start"], at), "text": text} for at, text in session["notices"] if at <= on_air
        ],
    }


def state_file(folder: Path = HERE) -> Path:
    """Where the start times live: beside the script, or in the temporary directory when that folder is read-only."""
    if os.access(folder, os.W_OK):
        return folder / STATE
    digest = hashlib.sha1(str(folder).encode()).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"live-console-{digest}.json"


@contextlib.contextmanager
def _locked(path: Path):
    with open(path.with_name(path.name + ".lock"), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def started(number: str, now: float, path: Path) -> float:
    """When this session's clock started: at its first read, or afresh after `IDLE` seconds without a read."""
    with _locked(path):
        try:
            state = json.loads(path.read_text())
        except (OSError, ValueError):
            state = {}
        entry = state.get(number)
        if (
            not isinstance(entry, dict)
            or "started" not in entry
            or now - float(entry.get("last", 0)) > IDLE
            or now < float(entry["started"])
        ):
            entry = {"started": now}
        entry["last"] = now
        state[number] = entry
        spare = path.with_name(path.name + ".tmp")
        spare.write_text(json.dumps(state))
        os.replace(spare, path)
    return float(entry["started"])


def read(number: str, *, now: float | None = None, data: Path = DATA, path: Path | None = None) -> dict:
    """The console's reading of one session now; an unknown number or missing data is reported, never guessed."""
    if not data.is_file():
        return {"session": number, "error": f"the console data {data.name} is missing beside the script"}
    found = sessions(data.read_text(encoding="utf-8"))
    if number not in found:
        return {"session": number, "error": "no live session with this number on the console"}
    now = time.time() if now is None else now
    began = started(number, now, path or state_file(data.parent))
    session = found[number]
    return reading(number, session, session["first_read"] + int(now - began))


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] != "read":
        print(USAGE, file=sys.stderr)
        return 2
    shown = read(argv[1].strip())
    print(json.dumps(shown, ensure_ascii=False))
    return 1 if "error" in shown else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
