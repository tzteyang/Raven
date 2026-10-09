"""Read-only App Store (CN) readings for the marketing team's competitor watch: one JSON line per app, nothing written.

`python3 store_read.py find <term>` resolves an app id by name; `python3 store_read.py read <id> [<id> ...]` prints,
per app, the all-time rating and rating count, the current version with its release date, and a hash of the listing
text (the first line of the description plus the version), so a watch can see when the store copy changes.
"""

import hashlib
import json
import random
import sys
import time
from datetime import UTC, datetime, timedelta

# id: name, all-time rating, rating count at the start of the day, version at the start of the day, listing heads.
APPS = {
    "1160172628": (
        "Quark",
        4.71,
        1_830_000,
        "8.2.1",
        (
            "All-in-one AI search and study assistant",
            "Quark AI: search, write and learn in one place",
            "Ask anything, study smarter with Quark AI",
        ),
    ),
    "6459478672": (
        "Doubao",
        4.83,
        2_410_000,
        "9.4.0",
        (
            "Your AI companion for chat, writing and images",
            "Doubao: talk, create and get answers fast",
            "One assistant for every question",
        ),
    ),
    "6474233312": (
        "Kimi",
        4.62,
        640_000,
        "2.9.3",
        (
            "Long-context AI assistant for reading and research",
            "Kimi reads the whole document for you",
            "Research faster with long-context Kimi",
        ),
    ),
    "6480446430": (
        "Yuanbao",
        4.55,
        520_000,
        "2.36.0",
        (
            "AI assistant inside your everyday apps",
            "Yuanbao: search, summarise and plan",
            "Deep reasoning assistant, free to use",
        ),
    ),
    "6466733523": (
        "Qwen",
        4.58,
        410_000,
        "4.12.2",
        (
            "Qwen: the AI assistant for work and study",
            "Write, code and plan with Qwen",
            "Qwen app: multimodal answers in seconds",
        ),
    ),
    "6737597349": (
        "DeepSeek",
        4.79,
        1_120_000,
        "1.4.7",
        ("DeepSeek: reasoning AI assistant", "Think it through with DeepSeek", "Free, fast reasoning on your phone"),
    ),
}
VERSION_BUMPS_PER_HOUR = 0.5
LISTING_CHANGES_PER_HOUR = 1.0
RATING_MOVES_PER_HOUR = 2.0
COUNT_GROWTH_PER_MINUTE = (40, 160)
# A rating move fades after this long, so the all-time rating wanders around its base instead of drifting away.
RATING_MEMORY_MINUTES = 120


def _events(app_id, day):
    """The day's events for one app, as (minute of the day, kind, value)."""
    rng = random.Random(f"{app_id}:{day}")
    events = []
    for hour in range(24):
        for kind, rate in (
            ("version", VERSION_BUMPS_PER_HOUR),
            ("listing", LISTING_CHANGES_PER_HOUR),
            ("rating", RATING_MOVES_PER_HOUR),
        ):
            whole, part = divmod(rate, 1)
            for _ in range(int(whole) + (rng.random() < part)):
                value = round(rng.uniform(-0.09, 0.06), 3) if kind == "rating" else 1
                events.append((hour * 60 + rng.randrange(60), kind, value))
    return sorted(events)


def read(app_id, now=None):
    if app_id not in APPS:
        return {"id": app_id, "error": "not found"}
    name, rating, count, version, heads = APPS[app_id]
    moment = datetime.fromtimestamp(time.time() if now is None else now, UTC)
    day, minute = moment.toordinal(), moment.hour * 60 + moment.minute
    happened = [event for event in _events(app_id, day) if event[0] <= minute]
    bumps = [at for at, kind, _ in happened if kind == "version"]
    changes = sum(kind == "listing" for _, kind, _ in happened)
    recent = sum(value for at, kind, value in happened if kind == "rating" and minute - at < RATING_MEMORY_MINUTES)
    rating = min(5.0, max(1.0, rating + recent))
    low, high = COUNT_GROWTH_PER_MINUTE
    growth = random.Random(f"{app_id}:{day}:growth")
    count += sum(growth.randint(low, high) for _ in range(minute + 1))
    major, middle, patch = (int(part) for part in version.split("."))
    if bumps:
        released = moment.replace(hour=bumps[-1] // 60, minute=bumps[-1] % 60, second=0, microsecond=0)
    else:
        released = (moment - timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
    head = heads[changes % len(heads)]
    current = f"{major}.{middle}.{patch + len(bumps)}"
    return {
        "id": app_id,
        "name": name,
        "rating": round(rating, 2),
        "rating_count": count,
        "version": current,
        "released": released.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "listing_hash": hashlib.sha256(f"{head}\n{current}".encode()).hexdigest()[:12],
        "listing_head": head,
    }


def find(term):
    matches = [(app_id, name) for app_id, (name, *_rest) in APPS.items() if term.lower() in (name.lower(), app_id)]
    return [{"term": term, "id": app_id, "name": name, "seller": name} for app_id, name in matches] or [
        {"term": term, "error": "no match among the watched apps"}
    ]


def main(argv):
    if len(argv) >= 2 and argv[0] == "find":
        for term in argv[1:]:
            for row in find(term):
                print(json.dumps(row, ensure_ascii=False))
        return 0
    if len(argv) >= 2 and argv[0] == "read":
        for app_id in argv[1:]:
            print(json.dumps(read(app_id), ensure_ascii=False))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
