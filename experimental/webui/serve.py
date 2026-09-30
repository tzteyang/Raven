"""Serve the built page and the recorded runs under one directory as JSON; with `--live-config`, also the Studio's
live cultivation sessions (`experimental.webui.live`), whose steps are the only requests that change anything."""

import argparse
import hashlib
import importlib
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from functools import lru_cache, partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from mimetypes import guess_type
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from ..automation.employee import AREA, HOME, REPLICAS
from ..iteration.records import runs
from .live import Live, LiveConfig
from .process import SUBHARNESS_SECRET, node_process, redact, state_root, subharness_homes
from .rundir import RecordError, annex, curator_progress, joined, labels, pending_stage, progress_path, verdicts
from .studio import event_summary, raw_record, studio_index, studio_run

DIST = Path(__file__).resolve().parent / "dist"
SCENARIO = Path(__file__).resolve().parents[1] / "simulation" / "scenarios" / "travel_agency" / "scenario.json"
DECKS = {".pptx", ".ppt", ".odp", ".pdf"}
TEXTS = {".md", ".markdown", ".txt", ".csv", ".json", ".yaml", ".yml"}
# Upload thumbnails live outside the run: the uploads folder is the employee's own, and a cache there would be
# something it can see, and something the scenario's withdraw_uploads glob (<name>.*) would trip over.
THUMB_CACHE = Path(tempfile.gettempdir()) / "raven-webui-thumbs"
THUMB_WIDTH = 480
CONVERT_TIMEOUT = 180

LIVE_TAIL = 8_000_000
LIVE_CHUNK = 4_000_000
# Concurrent drills write one log each; the live view follows at most this many of the most recently written.
LIVE_LOGS = 6
# A simulated customer answers within the run's model timeout (180 s by default), so a longer silence
# after the last turn closed means the trial is over and the owner or the Analyst is at work.
QUIET = 240
STALLED = 45 * 60

RECORD_UNAVAILABLE = "record builder not available"
BUNDLE_ARCHIVES = (".zip", ".tar", ".tar.gz", ".tgz")
MAX_BODY = 1_000_000
LOOPBACK = ("127.0.0.1", "localhost", "::1")
BUNDLE_LISTED = 400

_locks: dict[Path, threading.Lock] = {}
_locks_guard = threading.Lock()
_records: dict[Path, tuple[tuple, dict]] = {}


def _analysis(worker_root: Path, name) -> dict:
    """One analysis record of a run by file name, read once per version of the file."""
    path = Path(worker_root) / "analysis" / str(name)
    try:
        stat = path.stat()
    except OSError:
        return {}
    return _analysis_record(str(path), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=4096)
def _analysis_record(path: str, mtime_ns: int, size: int) -> dict:
    return _small_json(Path(path))


def passes(worker_root: Path, run: dict) -> list[list[int]]:
    """Per round, how many checks passed and how many failed among its verdicts (`rundir.verdicts`, which reads the
    scorecard a speaking assessor kept in the analysis records); unknown verdicts count in neither."""
    counts = []
    for round_ in run.get("rounds", []):
        records = [_analysis(worker_root, name) for name in round_.get("analysis") or () if isinstance(name, str)]
        items = [item for signal in verdicts(round_, records) for item in signal.get("items", [])]
        counts.append(
            [sum(item.get("result") == "pass" for item in items), sum(item.get("result") == "fail" for item in items)]
        )
    return counts


def index(root: Path, now: float | None = None) -> list[dict]:
    """Every run under `root`, one entry per iteration record, newest first; `name` is the run's folder.

    A record that says running while nothing of the run was written for `STALLED` seconds is listed as stalled:
    its process most likely died without saving an ending.
    """
    now = time.time() if now is None else now
    entries = []
    for worker_root in sorted(path for path in Path(root).iterdir() if path.is_dir()):
        for path in runs(worker_root):
            try:
                run = json.loads(path.read_text())
            except (OSError, ValueError) as exc:
                run = {"status": "error", "error": f"the run record could not be read: {type(exc).__name__}: {exc}"}
            status = run.get("status", "finished")
            if status == "running" and now - activity(worker_root, path) >= STALLED:
                status = "stalled"
            entries.append(
                {
                    "id": f"{worker_root.name}/{path.stem}",
                    "name": worker_root.name,
                    "task": run.get("task", ""),
                    "curator": run.get("curator"),
                    **setup(worker_root, path, run),
                    "passes": passes(worker_root, run),
                    "rounds": len(run.get("rounds", [])),
                    "status": status,
                    "error": run.get("error"),
                    "recorded": path.stat().st_mtime,
                }
            )
    return sorted(entries, key=lambda entry: entry["recorded"], reverse=True)


def _small_json(path: Path) -> dict:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 1_000_000:
        return {}
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def setup(worker_root: Path, record_path: Path, run: dict) -> dict:
    """How the run was set up and how it ended, for the run list: its chain and models from `settings.json`, and the
    suite's stop reason, spend and value verdict from `suite-summary.json`. Only these fields are read out of either
    file; a cultivation record already built here fills a chain neither file names."""
    settings = _small_json(worker_root / "settings.json")
    summary = _small_json(worker_root / "suite-summary.json")
    models = settings.get("models")
    models = {key: value for key, value in models.items() if isinstance(value, str)} if isinstance(models, dict) else {}
    chain = settings.get("chain") or run.get("chain")
    if not chain:
        cached = _records.get(record_path.resolve())
        chain = (cached[1].get("run") or {}).get("chain") if cached else None
    total = (summary.get("spend") or {}).get("total") if isinstance(summary.get("spend"), dict) else None
    stopped = summary.get("stopped")
    value = summary.get("value") if isinstance(summary.get("value"), dict) else {}
    return redact(
        {
            "chain": chain if isinstance(chain, str) else None,
            "models": models,
            "stopped": stopped if isinstance(stopped, str) else None,
            "spend": total if isinstance(total, (int, float)) else None,
            "verdict": value.get("verdict") if isinstance(value.get("verdict"), str) else None,
            "score": value.get("score") if isinstance(value.get("score"), (int, float)) else None,
        }
    )


def mining(root: Path) -> list[dict]:
    """The mining summaries the suite wrote into the runs root, newest first, each with its runs ranked by score."""
    out = []
    for file in sorted(root.glob("*mining-*.json"), key=lambda path: path.stat().st_mtime, reverse=True):
        data = _small_json(file)
        ranking = []
        for item in data.get("ranking") or []:
            if not isinstance(item, dict):
                continue
            spend = item.get("spend") if isinstance(item.get("spend"), dict) else {}
            ranking.append(
                {
                    **{key: item.get(key) for key in ("label", "plan", "name", "status", "rounds", "stopped")},
                    "spend": spend.get("total"),
                    "value": item.get("value") if isinstance(item.get("value"), dict) else None,
                }
            )
        out.append(
            {"file": file.name, "modified": file.stat().st_mtime, "spend": data.get("spend"), "ranking": ranking}
        )
    return redact(out)


def detail(root: Path, run_id: str) -> dict | None:
    """The joined run (`rundir.joined`) with its sessions' opaque labels (`rundir.labels`) and the run directory's
    standard and compartment log; None refuses the run, and a record that fails to load raises `rundir.RecordError`."""
    paths = _run_paths(root, run_id)
    if paths is None:
        return None
    run = joined(paths[1])
    return {**run, "labels": labels(run), **annex(paths[0])}


def deliverable(root: Path, path: str) -> Path | None:
    """A kept copy of a delivered file under `root`; anything else is refused."""
    file = Path(path).resolve()
    if not file.is_file() or not file.is_relative_to(Path(root).resolve()) or "deliverables" not in file.parts:
        return None
    return file


def scenario(path: Path | None) -> dict:
    """The scenario's criteria with their severity, its opening materials and every material name; empty when unreadable."""
    empty = {"criteria": [], "initial": [], "materials": []}
    if path is None or not Path(path).is_file():
        return empty
    try:
        spec = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        return {**empty, "error": f"{type(exc).__name__}: {exc}"}
    materials = Path(path).parent / "materials"
    return {
        "criteria": [
            {"id": str(row["id"]), "check": str(row.get("check", "")), "severity": row.get("severity", "standard")}
            for row in spec.get("criteria", [])
            if isinstance(row, dict) and "id" in row
        ],
        "initial": [str(name) for name in spec.get("initial", [])],
        "materials": sorted(entry.parent.name for entry in materials.glob("*/SKILL.md")) if materials.is_dir() else [],
    }


def _render(file: Path, out: Path, width: int) -> None:
    """Write one PNG per page of a deck into `out`: LibreOffice makes a PDF, PyMuPDF rasterises it."""
    import pymupdf

    with tempfile.TemporaryDirectory(prefix="webui-deck-") as work:
        pdf = file
        if file.suffix.lower() != ".pdf":
            # A private profile per conversion: two soffice processes sharing one profile block or fail silently.
            command = [
                "soffice",
                f"-env:UserInstallation=file://{work}/profile",
                "--headless",
                "--norestore",
                "--convert-to",
                "pdf",
                "--outdir",
                work,
                str(file),
            ]
            done = subprocess.run(command, capture_output=True, text=True, timeout=CONVERT_TIMEOUT, check=False)
            pdf = Path(work) / f"{file.stem}.pdf"
            if not pdf.is_file():
                raise RuntimeError(f"LibreOffice produced no PDF: {(done.stderr or done.stdout).strip()[-400:]}")
        with pymupdf.open(pdf) as document:
            for number, page in enumerate(document, 1):
                zoom = width / page.rect.width
                page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).save(out / f"page-{number:02d}.png")
    if not any(out.glob("page-*.png")):
        raise RuntimeError("the deck has no pages")


def _pages(directory: Path) -> list[Path]:
    return sorted(directory.glob("page-*.png"))


def _cached(file: Path, cache: Path, width: int, render) -> list[Path]:
    """Render a deck into `cache` once. A per-file lock serialises this process, and the finished folder appears
    by an atomic rename from a staging folder beside it, so another process never sees a half-written cache."""
    if _pages(cache):
        return _pages(cache)
    with _locks_guard:
        lock = _locks.setdefault(file, threading.Lock())
    with lock:
        if _pages(cache):
            return _pages(cache)
        cache.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{cache.name}-", dir=cache.parent))
        try:
            render(file, staging, width)
            try:
                os.rename(staging, cache)
            except OSError:
                if not _pages(cache):
                    raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    return _pages(cache)


def thumbnails(root: Path, path: str, *, width: int = THUMB_WIDTH, render=_render) -> list[Path] | None:
    """Page images of a delivered deck under `root`, rendered on first request and cached beside it as `<file>.thumbs/`.

    None refuses the path, exactly as `deliverable` does, or a file that is not a deck.
    """
    file = deliverable(root, path)
    if file is None or file.suffix.lower() not in DECKS:
        return None
    return _cached(file, file.with_name(f"{file.name}.thumbs"), width, render)


def upload(root: Path, run_id: str, path: str) -> Path | None:
    """A file the owner handed over, named relative to the run's agent home; only `home/uploads` is reachable."""
    paths = _run_paths(root, run_id)
    if paths is None or not path or Path(path).is_absolute():
        return None
    uploads = (paths[0] / AREA / HOME / "uploads").resolve()
    file = (paths[0] / AREA / HOME / path).resolve()
    if not uploads.is_relative_to(Path(root).resolve()) or not file.is_relative_to(uploads) or not file.is_file():
        return None
    return file


def upload_thumbnails(
    root: Path, run_id: str, path: str, cache: Path = THUMB_CACHE, *, width: int = THUMB_WIDTH, render=_render
) -> list[Path] | None:
    """Page images of an uploaded deck, cached under `cache` by the file's identity rather than beside it."""
    file = upload(root, run_id, path)
    if file is None or file.suffix.lower() not in DECKS:
        return None
    stat = file.stat()
    key = hashlib.sha256(f"{file}:{stat.st_mtime_ns}:{stat.st_size}".encode()).hexdigest()[:24]
    return _cached(file, Path(cache) / key, width, render)


def cached_page(cache: Path, path: str) -> Path | None:
    """A rendered page inside the thumbnail cache; anything else is refused."""
    file = Path(path).resolve()
    if file.suffix != ".png" or not file.is_file() or not file.is_relative_to(Path(cache).resolve()):
        return None
    return file


def _run_paths(root: Path, run_id: str) -> tuple[Path, Path] | None:
    """The worker root and iteration record a run id names, only when both sit where `index` found them."""
    worker, _, stem = run_id.partition("/")
    path = Path(root) / worker / "iteration" / f"{stem}.json"
    if not worker or not stem or not path.is_file() or path.resolve().parent.parent.parent != Path(root).resolve():
        return None
    return path.resolve().parent.parent, path


def node(root: Path, run_id: str, state_roots, dag: str, node_id: str, **options) -> dict | None:
    """One playbook node's process in a run (see `process.node_process`); None refuses the run or the node."""
    paths = _run_paths(root, run_id)
    if paths is None:
        return None
    return node_process(paths[0], state_roots, dag, node_id, **options)


def subharnesses(root: Path, run_id: str) -> list[dict] | None:
    """The run's housed sub-harness homes as the record keeps them now; None refuses the run."""
    paths = _run_paths(root, run_id)
    return None if paths is None else subharness_homes(paths[0])


def _builder():
    """`build_record` of the simulation, imported on each call until it succeeds, so a builder that lands while the
    server runs is picked up; None with the reason while it cannot be imported."""
    try:
        from ..simulation.record import build_record
    except Exception as exc:  # noqa: BLE001 -- any import failure means the page shows the builder as unavailable
        importlib.invalidate_caches()
        return None, f"{type(exc).__name__}: {exc}"
    return build_record, None


def _record_files(worker_root: Path, record_path: Path) -> tuple:
    """The record files a cultivation record is built from, by name, size and modification time."""
    files = [record_path, *sorted(worker_root.glob("analysis/*.json")), *sorted(worker_root.glob("curation/*.json"))]
    stamps = []
    for file in files:
        try:
            stat = file.stat()
        except OSError:
            continue
        stamps.append((file.name, stat.st_size, stat.st_mtime_ns))
    return tuple(stamps)


def record(root: Path, run_id: str, state_roots=(), scenario_dir: Path | None = None, builder=None) -> dict | None:
    """The run's cultivation record from `build_record`, rebuilt only when one of its record files changed.

    None refuses the run; while the builder cannot be imported the reply names `RECORD_UNAVAILABLE` and why.
    """
    paths = _run_paths(root, run_id)
    if paths is None:
        return None
    worker_root, record_path = paths
    problem = None
    if builder is None:
        builder, problem = _builder()
    if builder is None:
        return {"error": RECORD_UNAVAILABLE, "detail": redact(problem)}
    key = record_path.resolve()
    stamps = _record_files(worker_root, record_path)
    cached = _records.get(key)
    if cached and cached[0] == stamps:
        return cached[1]
    with _locks_guard:
        lock = _locks.setdefault(key, threading.Lock())
    with lock:
        cached = _records.get(key)
        if cached and cached[0] == stamps:
            return cached[1]
        state = state_root(state_roots, worker_root.name)
        built = redact(
            builder(worker_root, scenario_dir or SCENARIO.parent, state_root=state.parent if state else None)
        )
        _records[key] = (stamps, built)
    return built


def _bundle_files(bundle: Path) -> list[Path]:
    return sorted(
        path
        for path in bundle.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and not any(part.startswith(".") for part in path.relative_to(bundle).parts)
        and not SUBHARNESS_SECRET.search(path.name)
    )


def exported(root: Path, run_id: str) -> dict | None:
    """Where the newest exported bundle under `<run dir>/record/` is, with its files by name; None refuses the run.

    The exporter writes bundles; the page only points at them. A bundle is the newest folder or archive there, or
    the folder itself when the exporter wrote its files straight into it. Nothing named like a config or a secret is
    listed and no file content is served.
    """
    paths = _run_paths(root, run_id)
    if paths is None:
        return None
    folder = paths[0] / "record"
    reply = {"folder": str(folder), "bundle": None}
    if not folder.is_dir() or folder.is_symlink():
        return reply
    entries = [path for path in folder.iterdir() if not path.name.startswith(".") and not path.is_symlink()]
    bundles = [path for path in entries if path.is_dir() or path.name.lower().endswith(BUNDLE_ARCHIVES)]
    if bundles:
        bundle = max(bundles, key=lambda path: path.stat().st_mtime)
    elif any(path.is_file() for path in entries):
        bundle = folder
    else:
        return reply
    files = [bundle] if bundle.is_file() else _bundle_files(bundle)
    base = bundle.parent if bundle.is_file() else bundle
    reply["bundle"] = {
        "name": bundle.name,
        "path": str(bundle),
        "kind": "archive" if bundle.is_file() else "folder",
        "modified": max([bundle.stat().st_mtime, *(file.stat().st_mtime for file in files)]),
        "size": sum(file.stat().st_size for file in files),
        "count": len(files),
        "files": [file.relative_to(base).as_posix() for file in files[:BUNDLE_LISTED]],
    }
    return redact(reply)


def _observations(worker_root: Path) -> list[Path]:
    """The run's worker observation logs, most recently written last: the employee's own, and each replica's, which
    is where a drill played on a replica (`replicas/<round>-<session label>/employee/<worker>`) records its turns."""
    logs = [
        *worker_root.glob(f"{AREA}/*/observations.jsonl"),
        *worker_root.glob(f"{REPLICAS}/*/{AREA}/*/observations.jsonl"),
    ]
    return sorted(logs, key=lambda path: path.stat().st_mtime)


def activity(worker_root: Path, record_path: Path) -> float:
    """When anything of the run was last written: its record, its latest worker log or the Curator's progress."""
    times = [record_path.stat().st_mtime]
    logs = _observations(worker_root)
    if logs:
        times.append(logs[-1].stat().st_mtime)
    progress = progress_path(worker_root)
    if progress is not None:
        times.append(progress.stat().st_mtime)
    return max(times)


_CHAT = re.compile(r"Chat ID: (\S+)")


def _said(content) -> str:
    """What the person typed, without the runtime context and skill catalogue Raven prepends."""
    if isinstance(content, list):
        content = "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    text = str(content or "")
    marker = text.rfind("[END UNTRUSTED")
    if marker >= 0:
        text = text[text.find("]", marker) + 1 :]
    elif text.startswith("[Runtime Context"):
        text = text.split("\n\n", 1)[1] if "\n\n" in text else ""
    return text.strip()


def _cut(value, limit: int):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "..."


def _delivery(metadata) -> dict | None:
    """What a deliver_files call handed over, from its result's metadata, without the file's path in the workdir."""
    delivery = metadata.get("raven_delivery") if isinstance(metadata, dict) else None
    if not isinstance(delivery, dict):
        return None
    fields = ("name", "title", "description", "size", "media_type")
    return {
        "message": _cut(str(delivery.get("message") or ""), 1500),
        "files": [
            {key: item.get(key) for key in fields} for item in delivery.get("files") or [] if isinstance(item, dict)
        ],
    }


def _decision(value) -> dict:
    """An Action decision's control and the texts it would show the model or the customer, cut."""
    if not isinstance(value, dict):
        return {}
    limits = {"reason": 800, "feedback": 1500, "reply": 2000, "guidance": 800}
    return {
        "control": value.get("control"),
        **{key: _cut(value[key], limit) for key, limit in limits.items() if isinstance(value.get(key), str)},
    }


def compact(row: dict) -> dict | None:
    """The part of one observation row the live view draws; None for rows it does not draw.

    Model requests carry whole conversations and strategy calls whole states; a live page needs only the
    customer's latest message, the replies and tool calls, playbook progress, the Action controls with their
    receipts (only an applied receipt is an intervention), and errors.
    """
    kind, turn = row.get("kind"), row.get("turn_id")
    base = {"kind": kind, "turn_id": turn}
    if kind == "runner.event":
        event = row.get("event") or {}
        kind_of = row.get("event_type")
        if kind_of == "Text":
            return {**base, "event_type": kind_of, "event": {"content": event.get("content", "")}}
        if kind_of == "ToolEvent":
            keep = {"phase": event.get("phase"), "tool_call_id": event.get("tool_call_id"), "name": event.get("name")}
            if event.get("phase") == "start":
                arguments = event.get("arguments")
                small = len(json.dumps(arguments, ensure_ascii=False)) <= 600
                keep["arguments"] = arguments if small else _cut(arguments, 600)
            else:
                keep.update(ok=event.get("ok"), result_preview=_cut(event.get("result_preview") or "", 1500))
                delivery = _delivery(event.get("metadata"))
                if delivery is not None:
                    keep["delivery"] = delivery
            return {**base, "event_type": kind_of, "event": keep}
        return None
    if kind == "provider.request":
        messages = (row.get("parameters") or {}).get("messages") or []
        last = messages[-1] if messages and isinstance(messages[-1], dict) else {}
        if last.get("role") != "user":
            return None
        content = last.get("content")
        chat = _CHAT.search(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False))
        # Only the employee's own turns carry the runtime context; a permission judge's request does not.
        if chat is None:
            return None
        return {**base, "text": _cut(_said(content), 4000), "drill": chat.group(1).split(":")[0]}
    if kind == "dag.progress":
        payload = dict(row.get("payload") or {})
        manifest = payload.get("manifest")
        if isinstance(manifest, dict):
            fields = ("node", "subagent", "status", "started_at", "ended_at", "error", "output_file", "depends_on")
            payload["manifest"] = {
                **{key: manifest[key] for key in ("error", "stopped") if key in manifest},
                "files": [
                    {key: entry.get(key) for key in fields}
                    for entry in manifest.get("files") or []
                    if isinstance(entry, dict)
                ],
            }
        return {**base, "name": row.get("name"), "payload": payload}
    if kind == "action.call":
        return {**base, "operation": row.get("operation"), "arguments": event_summary(row.get("arguments"))}
    if kind == "action.result":
        result = row.get("result") if isinstance(row.get("result"), dict) else {}
        decision = result.get("decision") if row.get("operation") == "handle_request" else result
        return {**base, "operation": row.get("operation"), "result": _decision(decision)}
    if kind == "action.control":
        receipt = row.get("receipt") if isinstance(row.get("receipt"), dict) else {}
        fields = ("control_id", "source_id", "control", "status")
        kept = {key: receipt.get(key) for key in fields}
        return {**base, "receipt": {**kept, "reason": _cut(receipt.get("reason") or "", 800)}}
    if kind == "loop.control":
        return {**base, "rollbacks": row.get("rollbacks", 0), "rollbacks_refused": row.get("rollbacks_refused", 0)}
    if kind in ("runtime.bound", "runtime.closed"):
        return {**base, "targets": row.get("targets")} if kind == "runtime.bound" else base
    if isinstance(kind, str) and kind.endswith(".error"):
        return {**base, "error": _cut(row.get("error") or "", 600)}
    return None


def _read(file: Path, start: int, limit: int) -> tuple[list[dict], int]:
    """Complete lines from `start`, up to about `limit` bytes; a line still being written is left for the next read."""
    with file.open("rb") as stream:
        stream.seek(start)
        block = stream.read(limit)
        if len(block) == limit and b"\n" not in block:
            # A row longer than a whole read is skipped once it is complete, rather than waited on forever.
            stream.seek(start)
            line = stream.readline()
            return [], start + len(line) if line.endswith(b"\n") else start
    end = block.rfind(b"\n") + 1
    rows = []
    for line in block[:end].splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and (kept := compact(row)) is not None:
            rows.append(kept)
    return rows, start + end


def _tail_start(file: Path, size: int) -> int:
    if size <= LIVE_TAIL:
        return 0
    with file.open("rb") as stream:
        stream.seek(size - LIVE_TAIL)
        stream.readline()
        return stream.tell()


def _turn_open(file: Path | None) -> bool:
    """Whether the log's last turn has started and not yet closed with its loop.control row."""
    if file is None:
        return False
    size = file.stat().st_size
    rows, _ = _read(file, max(0, size - 400_000), 400_000 + 1)
    for row in reversed(rows):
        if row["kind"] in ("loop.control", "runtime.closed"):
            return False
        if row.get("turn_id"):
            return True
    return False


def phase(worker_root: Path, record: dict, record_path: Path, now: float | None = None) -> dict:
    """Which step a run is at, with the evidence the answer rests on.

    The Curator's progress file says a curation is under way and at which stage (`diagnose` while it attributes its
    inputs, then the generation's stages) until it is marked finished. The iteration record is saved as soon as a
    round is analysed and again after its curation, so a round marked `curated` with no curation yet is being
    curated; turn rows newer than the record are this round's trial, until every log has been quiet longer than a
    customer takes to answer.
    """
    now = time.time() if now is None else now
    status = record.get("status", "finished")
    rounds = record.get("rounds", [])
    progress = curator_progress(worker_root)
    ended = progress.get("error") if progress and progress.get("finished") else None
    stage = pending_stage(worker_root) or (progress.get("stage") if progress else None)
    if status == "error":
        return {
            "name": "error",
            "round": len(rounds),
            "stage": None,
            "basis": record.get("error") or ended or "the run ended with an error",
        }
    if status == "paused":
        return {
            "name": "paused",
            "round": len(rounds),
            "stage": stage,
            "basis": record.get("stop") or ended or "the Curator's call budget ran out",
        }
    if status != "running":
        return {
            "name": "finished",
            "round": len(rounds),
            "stage": None,
            "basis": record.get("stop") or "the run is finished",
        }
    quiet = now - activity(worker_root, record_path)
    onboarding = "initial_curation" not in record
    curated_round = 0 if onboarding else len(rounds)
    if quiet >= STALLED:
        return {
            "name": "stalled or stopped",
            "round": curated_round if onboarding else len(rounds) + 1,
            "stage": None,
            "basis": f"the record says running, but nothing of the run was written for {int(quiet // 60)} min",
        }
    if progress and not progress.get("finished") and now - progress_path(worker_root).stat().st_mtime < STALLED:
        counts = ", ".join(f"{progress.get(key, 0)} {key}" for key in ("calls", "queries", "checks", "repairs"))
        return {
            "name": "curating",
            "round": curated_round,
            "stage": progress.get("stage") or stage,
            "basis": f"the Curator's progress file is being written ({counts})",
        }
    if ended and progress_path(worker_root).stat().st_mtime >= record_path.stat().st_mtime:
        return {
            "name": "error",
            "round": curated_round,
            "stage": progress.get("stage"),
            "basis": f"the Curator's revision failed: {ended}",
        }
    if onboarding:
        return {"name": "curating", "round": 0, "stage": stage, "basis": "the onboarding revision is not recorded yet"}
    last = rounds[-1] if rounds else None
    if last and last.get("curated") and not last.get("curation"):
        return {
            "name": "curating",
            "round": len(rounds),
            "stage": stage,
            "basis": f"round {len(rounds)} was analysed for curation and its revision is not recorded yet",
        }
    logs = _observations(worker_root)
    latest = logs[-1] if logs else None
    written = latest.stat().st_mtime if latest else 0.0
    trial = {"round": len(rounds) + 1, "stage": None}
    pending = record.get("pending") or {}
    if latest is None or written <= record_path.stat().st_mtime:
        if pending.get("sessions"):
            return {
                "name": "judging or analysing",
                **trial,
                "basis": f"round {len(rounds) + 1}'s trials are recorded; the assessors and the Analyst are at work",
            }
        return {"name": "unknown", **trial, "basis": "nothing has been logged since the run record was last saved"}
    if any(_turn_open(log) for log in _following(logs)):
        return {"name": "trial", **trial, "basis": "a turn is in progress"}
    idle = now - written
    if idle < QUIET:
        return {
            "name": "trial",
            **trial,
            "basis": f"the last turn closed {int(idle)} s ago; the next customer message may still come",
        }
    return {
        "name": "judging or analysing",
        **trial,
        "basis": f"no turn for {int(idle // 60)} min, longer than a customer takes to answer; the owner is judging or the Analyst is analysing",
    }


def deliveries(worker_root: Path, limit: int = 40) -> list[dict]:
    """The copies the worker and its replicas kept of files handed over through deliver_files, newest first.

    A worker copies them to `<its root>/deliverables/<turn>/<file>` as the turn closes, before the round is recorded,
    so a delivery can be shown while the trial is still going.
    """
    base = Path(worker_root).resolve()
    kept = []
    for folder in (Path(worker_root) / "deliverables", *Path(worker_root).glob("replicas/*/deliverables")):
        if not folder.is_dir() or not folder.resolve().is_relative_to(base):
            continue
        for turn in folder.iterdir():
            if not turn.is_dir() or turn.name.startswith("."):
                continue
            for file in turn.iterdir():
                if file.name.startswith(".") or file.is_symlink() or not file.is_file():
                    continue
                if not file.resolve().is_relative_to(base):
                    continue
                stat = file.stat()
                kept.append(
                    {
                        "turn": turn.name,
                        "name": file.name,
                        "path": str(file.resolve()),
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                    }
                )
    return sorted(kept, key=lambda row: row["modified"], reverse=True)[:limit]


def _following(logs: list[Path]) -> list[Path]:
    """The logs the live view follows: the most recently written one and every other written within `STALLED` of it,
    such as the replicas of drills played at the same time, at most `LIVE_LOGS`, oldest first."""
    if not logs:
        return []
    newest = logs[-1].stat().st_mtime
    return [log for log in logs if newest - log.stat().st_mtime < STALLED][-LIVE_LOGS:]


def _log_name(log: Path, worker_root: Path) -> str:
    """A log's name as the reader knows it: the worker's folder, under `replicas/<round>-<label>/` for a replica's,
    without the area every worker writes in."""
    parts = [part for part in log.parent.relative_to(worker_root).parts if part != AREA]
    return "/".join(parts)


def cursors(text: str) -> dict[str, int]:
    """The `logs` query value, `<log>:<offset>` pairs separated by commas, as a mapping; malformed pairs are dropped."""
    out = {}
    for part in text.split(","):
        key, _, offset = part.rpartition(":")
        if key and offset.isdigit():
            out[key] = int(offset)
    return out


def live(root: Path, run_id: str, offsets: dict[str, int] | None = None, now: float | None = None) -> dict | None:
    """New rows of the run's current worker logs since each one's offset in `offsets`, with the phase the run is in;
    None refuses the run.

    Each followed log (`_following`) is named by its worker's folder (`_log_name`); a log with no matching
    offset starts a fresh tail near its end and says `reset`. Every row carries the name of the log it came from.
    `labels` names the sessions the record already holds by their opaque labels (`rundir.labels`), which a drill's
    session key and replica folder carry instead of its name.
    """
    paths = _run_paths(root, run_id)
    if paths is None:
        return None
    worker_root, record_path = paths
    record = json.loads(record_path.read_text())
    offsets = offsets or {}
    followed = _following(_observations(worker_root))
    budget = LIVE_CHUNK // max(len(followed), 1)
    logs, rows = [], []
    for file in followed:
        key = _log_name(file, worker_root)
        size = file.stat().st_size
        offset = offsets.get(key)
        same = offset is not None and 0 <= offset <= size
        start = offset if same else _tail_start(file, size)
        read, end = _read(file, start, budget)
        rows.extend({**row, "file": key} for row in read)
        logs.append(
            {
                "file": key,
                "start": start,
                "offset": end,
                "size": size,
                "reset": not same,
                "last_event": file.stat().st_mtime,
            }
        )
    return {
        "logs": logs,
        "rows": rows,
        "last_event": max((log["last_event"] for log in logs), default=None),
        "phase": phase(worker_root, record, record_path, now),
        "status": record.get("status", "finished"),
        "curator": curator_progress(worker_root),
        "deliveries": deliveries(worker_root),
        "labels": labels(record),
        "now": time.time() if now is None else now,
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(
        self,
        *args,
        root: Path,
        scenario: Path | None = None,
        cache: Path = THUMB_CACHE,
        state_roots=(),
        builder=None,
        live: Live | None = None,
        **kwargs,
    ):
        self.root = root
        self.scenario = scenario
        self.cache = cache
        self.state_roots = tuple(state_roots)
        self.builder = builder
        self.live = live
        super().__init__(*args, directory=str(DIST), **kwargs)

    def _paths(self, run_id: str) -> tuple[Path, Path] | None:
        """A recorded run's paths, or a live session's run when live sessions are served."""
        return _run_paths(self.root, run_id) or (_run_paths(self.live.runs, run_id) if self.live else None)

    def do_GET(self):
        if self.path == "/api/runs":
            return self._json(index(self.root))
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        if url.path == "/files":
            path = query.get("path", [""])[0]
            kept = deliverable(self.root, path) or (deliverable(self.live.runs, path) if self.live else None)
            return self._file(kept or cached_page(self.cache, path))
        if url.path == "/api/upload":
            file = upload(self.root, query.get("run", [""])[0], query.get("path", [""])[0])
            if file is None or file.suffix.lower() not in TEXTS | DECKS:
                return self._json({"error": "not an uploaded file of this run"}, 404)
            return self._file(file, "text/plain; charset=utf-8" if file.suffix.lower() in TEXTS else None)
        if url.path == "/api/scenario":
            return self._json(scenario(self.scenario))
        if url.path == "/api/live":
            body = live(self.root, query.get("run", [""])[0], cursors(query.get("logs", [""])[0]))
            return self._json(body if body is not None else {"error": "no such run"}, 200 if body is not None else 404)
        if url.path == "/api/node":
            raw = query.get("attempt", [""])[0]
            body = node(
                self.root,
                query.get("run", [""])[0],
                self.state_roots,
                query.get("dag", [""])[0],
                query.get("node", [""])[0],
                attempt=int(raw) if raw.isdigit() else None,
                source=query.get("source", ["auto"])[0],
                summary=query.get("summary", [""])[0] in ("1", "true"),
            )
            return self._json(body if body is not None else {"error": "no such node"}, 200 if body is not None else 404)
        if url.path == "/api/record":
            scenario_dir = Path(self.scenario).parent if self.scenario else None
            try:
                body = record(self.root, query.get("run", [""])[0], self.state_roots, scenario_dir, self.builder)
            except Exception as exc:  # noqa: BLE001 -- a builder failure is this request's answer, not the server's
                return self._json({"error": redact(f"the record builder failed: {type(exc).__name__}: {exc}")}, 500)
            if body is None:
                return self._json({"error": "no such run"}, 404)
            return self._json(body, 503 if body.get("error") == RECORD_UNAVAILABLE else 200)
        if url.path == "/api/mining":
            return self._json({"sessions": mining(self.root)})
        if url.path == "/api/record/export":
            body = exported(self.root, query.get("run", [""])[0])
            return self._json(body if body is not None else {"error": "no such run"}, 200 if body is not None else 404)
        if url.path == "/api/subharnesses":
            homes = subharnesses(self.root, query.get("run", [""])[0])
            return self._json(
                {"homes": homes} if homes is not None else {"error": "no such run"}, 200 if homes is not None else 404
            )
        if url.path == "/api/thumbs":
            try:
                if "upload" in query:
                    pages = upload_thumbnails(self.root, query.get("run", [""])[0], query["upload"][0], self.cache)
                else:
                    pages = thumbnails(self.root, query.get("path", [""])[0])
            except Exception as exc:  # noqa: BLE001 -- any rendering failure is this request's answer, not the server's
                return self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)
            if pages is None:
                return self._json({"error": "not a kept deck"}, 404)
            return self._json({"pages": [str(page) for page in pages]})
        if url.path == "/api/studio/runs":
            return self._json(studio_index(self.root, index))
        if url.path.startswith("/api/studio/runs/"):
            paths = _run_paths(self.root, url.path.removeprefix("/api/studio/runs/"))
            if paths is None:
                return self._json({"error": "no such run"}, 404)
            try:
                return self._json(studio_run(paths[1]))
            except RecordError as exc:
                return self._json({"error": str(exc)}, 422)
        if url.path == "/api/studio/live" or url.path.startswith("/api/studio/live/"):
            return self._live(url.path.removeprefix("/api/studio/live").strip("/"), query)
        if url.path == "/api/studio/raw":
            paths = self._paths(query.get("run", [""])[0])
            try:
                ref = [query.get(key, [""])[0] for key in ("round", "session", "turn", "index", "child", "part")]
                round_ = None if ref[0] == "pending" else int(ref[0])
                child = int(ref[4]) if ref[4] else None
                part = ref[5] or "sessions"
                kept = raw_record(paths[1], round_, ref[1], int(ref[2]), int(ref[3]), child, part) if paths else None
            except ValueError:
                kept = None
            except RecordError as exc:
                return self._json({"error": str(exc)}, 422)
            return self._json(kept if kept is not None else {"error": "no such record"}, 200 if kept else 404)
        if self.path.startswith("/api/runs/"):
            try:
                run = detail(self.root, self.path.removeprefix("/api/runs/"))
            except RecordError as exc:
                return self._json({"error": str(exc)}, 422)
            return self._json(run if run is not None else {"error": "no such run"}, 200 if run is not None else 404)
        if url.path.startswith("/api/"):
            return self._json({"error": "unknown endpoint"}, 404)
        # The Studio opens at the root, which is where an IDE's port forwarding lands; the run viewer answers every
        # other extension-less path, such as /viewer.
        if url.path.rstrip("/") in ("", "/studio"):
            self.path = "/studio.html"
        elif "." not in self.path.rsplit("/", 1)[-1]:
            self.path = "/index.html"
        return super().do_GET()

    def _live(self, session: str, query: dict):
        if self.live is None:
            return self._json({"error": "live sessions are off; the server was started without --live-config"}, 404)
        if not session:
            return self._json(self.live.info())
        try:
            body = self.live.snapshot(session, query.get("stamp", [None])[0])
        except RecordError as exc:
            return self._json({"error": str(exc)}, 422)
        return self._json(body if body is not None else {"error": "no such session"}, 200 if body else 404)

    def do_POST(self):
        url = urlsplit(self.path)
        if self.live is None or not (url.path == "/api/studio/live" or url.path.startswith("/api/studio/live/")):
            return self._json({"error": "unknown endpoint"}, 404)
        if self.headers.get_content_type() != "application/json":
            return self._json({"error": "a step is a JSON request"}, 415)
        origin = self.headers.get("Origin")
        if origin and urlsplit(origin).netloc != self.headers.get("Host"):
            return self._json({"error": "steps are taken from this server's own page"}, 403)
        body = self._body()
        if body is None:
            return self._json({"error": f"the body must be a JSON object of at most {MAX_BODY} bytes"}, 400)
        parts = url.path.removeprefix("/api/studio/live").strip("/").split("/")
        if parts == [""]:
            status, value = self.live.create(body)
        elif len(parts) == 2:
            status, value = self.live.step(parts[0], parts[1], body)
        else:
            status, value = 404, {"error": "unknown endpoint"}
        return self._json(value, status)

    def _body(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if not 0 <= length <= MAX_BODY:
            return None
        try:
            value = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return None
        return value if isinstance(value, dict) else None

    def _file(self, file, kind=None):
        if file is None:
            return self._json({"error": "not a kept deliverable"}, 404)
        body = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", kind or guess_type(file.name)[0] or "application/octet-stream")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        # A delivered page is the model's output: render it, never let it run script as this origin.
        self.send_header("Content-Security-Policy", "sandbox")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description="Serve recorded RSI runs for the experimental web view.")
    parser.add_argument("--runs", type=Path, required=True, help="Directory whose subdirectories are worker roots")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--host", default="127.0.0.1", help="Bind address; 0.0.0.0 to reach the page from another machine"
    )
    parser.add_argument(
        "--scenario", type=Path, default=SCENARIO, help="scenario.json whose criteria mark red lines on the page"
    )
    parser.add_argument(
        "--thumbs-cache", type=Path, default=THUMB_CACHE, help="Where page images of uploaded decks are cached"
    )
    parser.add_argument(
        "--state-roots",
        type=Path,
        action="append",
        default=[],
        help="Directory holding each run's state root as <dir>/<run name>, where sub-harness frame journals are read",
    )
    parser.add_argument(
        "--live-config",
        type=Path,
        help="JSON configuration of live cultivation sessions (experimental.webui.live.LiveConfig); without it the "
        "server only replays recorded runs",
    )
    args = parser.parse_args()
    live = Live(LiveConfig.load(args.live_config)) if args.live_config else None
    if not DIST.is_dir():
        print(f"No built page at {DIST}; run `npm run build` in experimental/webui first. Serving the API only.")
    handler = partial(
        Handler,
        root=args.runs.resolve(),
        scenario=args.scenario.resolve(),
        cache=args.thumbs_cache.resolve(),
        state_roots=tuple(path.resolve() for path in args.state_roots),
        live=live,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving {args.runs.resolve()} at http://{args.host}:{args.port}/")
    if live is not None:
        print(f"Live sessions are kept under {live.config.root}")
        if args.host not in LOOPBACK:
            print(f"Warning: live sessions spend the configured keys and are reachable at {args.host}")
        signal.signal(signal.SIGTERM, _interrupt)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if live is not None:
            live.close()


def _interrupt(_signum, _frame):
    # A terminated server stops its sessions' processes the way an interrupted one does.
    raise KeyboardInterrupt


if __name__ == "__main__":
    main()
