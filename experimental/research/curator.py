"""Adapt interaction inputs and optional research guidance to one reviewed Curator information handoff."""

import hashlib
import json
import re
import shutil
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from raven.config.live import hold_for_this_turn
from raven.permissions.turn import start_permission_turn

from ..curator.generation.context.render import tool
from ..curator.harness.declaration import schema_for
from ..curator.raven_adapter.exploration import Exploration, Withheld
from ..curator.raven_adapter.inspection import Inspection, file_source
from ..curator.raven_adapter.materialize import _write
from ..curator.workflow import information_scope, unfinished
from ..iteration.exchange import exchange, messages
from .collection import CollectionLimits, _Calls, collect_information
from .guidance import derive_guidance
from .information import Manifest, Request, ResearchReview, Result, Review, render
from .researchers import Agent, Exchange, ResearchError
from .review import review_research
from .voice import prompt
from .web import Web

INFORMATION_FILE = "uploads/information/expert.md"
MATERIAL_PREFIX = "information.material."
GUIDANCE_PREFIX = "research.example."
SOURCE_ROOT = Path(__file__).resolve().parents[2]
CHILD_DEFINITION = re.compile(r"(/[^\s\"]+/versions/)([0-9a-f]{64})(/deployment\.json)")


def _paths(paths):
    result = []
    for path in map(Path, paths):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError(f"material must be an existing regular file or directory: {path}")
        root = path.resolve()
        if root.is_dir() and any(item.is_symlink() for item in root.rglob("*")):
            raise ValueError(f"material contains a symbolic link: {root}")
        result.append(root)
    return tuple(result)


def _sources(paths, prefix):
    sources = {}
    for index, root in enumerate(paths, 1):
        for path in [root] if root.is_file() else sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in (
                ".md",
                ".txt",
                ".json",
                ".py",
                ".cjs",
                ".yaml",
                ".yml",
                ".csv",
                ".tsv",
                ".html",
            ):
                name = path.name if root.is_file() else path.relative_to(root).as_posix()
                try:
                    sources[f"{prefix}{index}.{name}"] = {**file_source(path), "root": str(root)}
                except UnicodeDecodeError:
                    continue
    return sources


def stage_materials(paths, home: Path) -> tuple[Path, ...]:
    """Preserve interaction input files for coverage assessment and later Curator inspection."""
    home = Path(home).resolve()
    copied = []
    for number, source in enumerate(_paths(paths), 1):
        target = home / "uploads" / "materials" / f"{number}-{source.name}"
        if target.is_relative_to(source):
            raise ValueError("input material cannot contain its staging destination")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise ValueError(f"staged material already exists: {target}")
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
        copied.append(target)
    return tuple(copied)


def _environment(worker, inspection, home):
    payload = {
        "sources": {name: row["digest"] for name, row in inspection.sources.items() if not name.startswith("upload.")},
        "facts": {
            name: inspection.facts.get(name)
            for name in (
                "tools",
                "plugins",
                "mcp",
                "hosting",
                "configuration",
                "skills",
                "capability_resources",
                "mode",
                "backend",
            )
        },
    }
    locations = [
        (home, "<home>"),
        (getattr(worker.baseline, "workdir", None), "<workdir>"),
        (getattr(worker, "root", None), "<run>"),
    ]

    def relocated(text):
        for path, label in sorted(locations, key=lambda item: len(str(item[0])), reverse=True):
            if path is not None:
                text = text.replace(str(Path(path).resolve()), label)
        return text.replace(worker.baseline.task.id, "<task-id>")

    # A child's definition is versioned by a digest of content that holds this run's paths and task id, so the same
    # child prepared for another run gets another version; bind its relocated content instead of that version.
    def definition(match):
        content = relocated(Path(match.group(0)).read_text(encoding="utf-8"))
        return f"{match.group(1)}{hashlib.sha256(content.encode()).hexdigest()}{match.group(3)}"

    text = relocated(CHILD_DEFINITION.sub(definition, json.dumps(payload, sort_keys=True, default=str)))
    return hashlib.sha256(text.encode()).hexdigest()


async def collect_for_curator(
    worker,
    provider,
    request: Request,
    *,
    materials: tuple[Path, ...] = (),
    research_references: tuple[Path, ...] = (),
    records: Path,
    ask=None,
    model=None,
    review_model=None,
    effort="high",
    researcher="exchange",
    research_model=None,
    research_effort=None,
    research_budget=None,
    limits=CollectionLimits(),
    wait_for_input=False,
    replay: Result | None = None,
    admit=None,
) -> Result:
    """Assess interaction material directly; derive research-only guidance lazily in a separate source snapshot."""
    if unfinished(worker):
        raise ValueError("resolve the paused curation before collecting new information")
    inspection = await worker.inspect()
    materials, research_references = _paths(materials), _paths(research_references)
    records = Path(records).resolve()
    home = worker.baseline.config.workspace_path.resolve()
    _recover_publication(home / "uploads/information")
    published = (home / INFORMATION_FILE).parent / "version.json"
    if published.is_file():
        version = json.loads(published.read_text()).get("version")
        if request.previous is None or request.previous.identity != version:
            raise ValueError("existing information requires its current snapshot before collection")
    for root in (*materials, *research_references):
        if records.is_relative_to(root) or root.is_relative_to(records):
            raise ValueError("collection records and input materials must be separate trees")
    for root in research_references:
        if root.is_relative_to(home) or home.is_relative_to(root):
            raise ValueError("research-only references must remain outside the worker workspace")
    sources = {**inspection.sources, **_sources(materials, MATERIAL_PREFIX)}
    facts = {**inspection.facts, "source_roots": [*inspection.facts.get("source_roots", ()), *map(str, materials)]}

    base = replay.snapshot if replay is not None else request.previous
    hidden = list(base.manifest.excluded_sources) if base is not None and base.manifest is not None else []
    existing_roots = [Path(path) for path in inspection.facts.get("source_roots", ())]
    existing_roots.extend(Path(source.get("root", source["path"])) for source in inspection.sources.values())
    for reference in research_references:
        if any(reference.is_relative_to(path) for path in materials):
            continue
        if reference.is_relative_to(SOURCE_ROOT):
            files = (reference,) if reference.is_file() else tuple(reference.rglob("*"))
            hidden.extend(
                file.relative_to(SOURCE_ROOT).as_posix()
                for file in files
                if file.is_file() and not any(file.is_relative_to(path) for path in materials)
            )
        elif any(reference.is_relative_to(path) or path.is_relative_to(reference) for path in existing_roots):
            raise ValueError("research-only references overlap an existing collector source scope")
    hidden = sorted(set(hidden))
    withheld = Withheld(paths=(*worker.withheld.paths, *hidden), markers=worker.withheld.markers)

    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()

    supplied = {}
    for name, source in sources.items():
        path = Path(source["path"])
        if name.startswith((MATERIAL_PREFIX, "upload.")) and not path.is_relative_to(home / "uploads/information"):
            key = path.relative_to(home).as_posix() if path.is_relative_to(home) else name
            supplied[key] = source["digest"]
    for number, root in enumerate(materials):
        for path in [root] if root.is_file() else sorted(root.rglob("*")):
            if path.is_file():
                key = (
                    path.relative_to(home).as_posix()
                    if path.is_relative_to(home)
                    else f"material-{number}/{path.relative_to(root) if root.is_dir() else path.name}"
                )
                supplied[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = Manifest(
        task=worker.baseline.task.text,
        objective=request.objective,
        scope=request.scope,
        sources=supplied,
        context=digest(
            {
                "context": request.context,
                "answers": request.answers,
                "answers_version": request.answers_version,
                "previous": request.previous.identity if request.previous else None,
                "focus": request.focus,
            }
        ),
        environment=_environment(worker, inspection, home),
        excluded_sources=tuple(hidden),
    )
    request = request.model_copy(update={"manifest": manifest})
    if replay is not None:
        replay = Result.model_validate(replay.model_dump())
        if not replay.ready or replay.snapshot.manifest != manifest:
            raise ValueError(
                "reviewed information does not match the current task, released inputs or environment; reassess"
            )
        if admit is not None:
            admit(replay.model_dump(mode="json"), "information.replay")
        records.mkdir(parents=True, exist_ok=False)
        (records / "result.json").write_text(replay.model_dump_json(indent=2))
        (records / "snapshot.json").write_text(replay.snapshot.model_dump_json(indent=2))
        return replay
    collected_inspection = replace(inspection, sources=sources, facts=facts)
    records.parent.mkdir(parents=True, exist_ok=True)
    web = None

    async def guidance():
        guide_inspection = Inspection(
            inspection.declaration,
            {"authored": {"values": {}}, "source_roots": list(map(str, research_references))},
            _sources(research_references, GUIDANCE_PREFIX),
        )
        async with Exploration(
            worker.baseline.config, guide_inspection, repository=SOURCE_ROOT, source_paths=(), withheld=Withheld()
        ) as exploration:
            result = await derive_guidance(
                provider,
                request.objective,
                exploration,
                model=model,
                limits=limits,
                records=records / "guidance",
                effort=effort,
            )
            return result

    async def review_packet(packet, destination, prompt, name, agent=None, output=Review):
        def complete(review):
            delivered = {finding["id"] for finding in packet.get("delivery", {}).get("findings", [])}
            if isinstance(review, ResearchReview) and {verdict.id for verdict in review.findings} != delivered:
                raise ValueError(f"give one verdict for each delivered finding, by id: {sorted(delivered)}")
            return review

        if researcher == "claude":
            actor = agent or Agent(
                "claude", model=research_model, effort=research_effort, budget=research_budget, timeout=limits.timeout
            )
            review, _ = await actor.stage(
                prompt + "\n\n" + json.dumps(packet, ensure_ascii=False), output, records=destination
            )
            try:
                return complete(review)
            except ValueError as exc:
                raise ResearchError(str(exc)) from exc
        destination.mkdir(parents=True, exist_ok=False)
        calls, trace = _Calls(provider), []

        def accept(arguments):
            calls.check(arguments)
            return complete(output.model_validate(arguments))

        try:
            _, review = await exchange(
                calls,
                messages(prompt, packet),
                [tool(name, "Review the supplied content and its actual inputs.", schema_for(output))],
                submit={name: accept},
                model=review_model or model,
                effort="high",
                max_calls=limits.review_calls,
                timeout=limits.timeout,
                trace=trace,
                label=name,
            )
            return review
        finally:
            (destination / "trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2))

    async def research(task):
        nonlocal web
        timeout = min(limits.research_window, task.remaining_seconds)
        acquisition = limits.acquisition_window(timeout)
        if web is None:
            web = Web.of(
                worker.baseline.config, searching=researcher == "exchange", page_chars=60_000, log=records / "web.jsonl"
            )
        agent = (
            Exchange(provider, model=research_model or model, effort=research_effort or "high", timeout=limits.timeout)
            if researcher == "exchange"
            else Agent(
                researcher,
                model=research_model,
                effort=research_effort,
                budget=research_budget,
                timeout=acquisition,
            )
        )

        async def review_delivery(packet, destination):
            return await review_packet(
                packet, destination, prompt("review_research.md"), "review_research", agent, ResearchReview
            )

        return await review_research(
            agent,
            task.brief,
            web,
            review_delivery,
            records=records / task.attempt,
            previous=records / task.previous_attempt if task.previous_attempt else None,
            timeout=timeout,
            admit=admit,
        )

    async with Exploration(
        worker.baseline.config, collected_inspection, repository=SOURCE_ROOT, withheld=withheld
    ) as exploration:
        context = {
            **request.context,
            "exploration": exploration.describe(),
            "interaction_sources": {
                name: {
                    "path": value["snapshot_path"],
                    "source_path": value["path"],
                    "worker_path": str(Path(value["path"]).relative_to(home))
                    if Path(value["path"]).is_relative_to(home)
                    else None,
                    "purpose": "interaction",
                    "digest": value["digest"],
                }
                for name, value in exploration.sources.items()
                if name.startswith(MATERIAL_PREFIX) or name.startswith("upload.")
            },
            "host_sources": {
                name: {"path": value["snapshot_path"], "digest": value["digest"]}
                for name, value in exploration.sources.items()
                if not name.startswith((MATERIAL_PREFIX, "upload."))
            },
        }
        effective = request.model_copy(update={"context": context})
        start_permission_turn(None, conversation_id=worker.baseline.task.id, turn_id=uuid4().hex, origin="curator")
        with exploration.registry.turn_scope(), hold_for_this_turn(**{"tools.exec.timeout": limits.timeout}):
            result = await collect_information(
                provider,
                effective,
                registry=exploration.registry,
                research=research if researcher is not None else None,
                guidance=guidance if research_references else None,
                ask=ask,
                wait_for_input=wait_for_input,
                model=model,
                review_model=review_model,
                limits=limits,
                records=records,
                effort=effort,
            )
        if admit is not None:
            admit(result.model_dump(mode="json"), "information.result")
        try:
            exploration.verify()
        except ValueError as exc:
            (records / "result.json").write_text(json.dumps({"status": "invalid", "error": str(exc)}, indent=2))
            raise
    return result


def _recover_publication(folder):
    journal = folder / "publication.json"
    if not journal.exists():
        return
    pending = json.loads(journal.read_text())
    target, version = folder / "expert.md", folder / "version.json"
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() not in pending["allowed_content"]:
        raise ValueError("published information changed during an interrupted publication")
    current = json.loads(version.read_text()).get("version") if version.exists() else None
    if current not in pending["allowed_versions"]:
        raise ValueError("information version changed during an interrupted publication")
    _write(target, pending["content"].encode())
    _write(version, json.dumps(pending["version"], indent=2).encode())
    journal.unlink()


def handover_information(worker, result: Result) -> str:
    """Publish one recoverable version, never over unfinished local or composite curation."""
    result = Result.model_validate(result.model_dump())
    if not result.ready:
        raise ValueError(f"information is not ready for Curator: {result.status}")
    if unfinished(worker):
        raise ValueError("resolve the paused curation before publishing new information")
    target = worker.baseline.config.workspace_path / INFORMATION_FILE
    version = target.parent / "version.json"
    _recover_publication(target.parent)
    content = render(result.snapshot)
    current = json.loads(version.read_text()) if version.exists() else None
    if current is not None:
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != current.get("content_digest"):
            raise ValueError("the published information was changed outside its version record")
        if current["version"] == result.snapshot.identity:
            information_scope(worker, {"information": information_feedback(result)})
            return INFORMATION_FILE
        if current["version"] != result.previous:
            raise ValueError("information base version changed; collect against the current snapshot")
    elif target.exists():
        raise ValueError("existing information has no version record")
    published = {
        "version": result.snapshot.identity,
        "previous": result.previous,
        "content_digest": hashlib.sha256(content.encode()).hexdigest(),
        "changed_dimensions": result.changed_dimensions,
        "resources_changed": result.resources_changed,
        "questions_changed": result.questions_changed,
        "manifest": result.snapshot.manifest.model_dump(mode="json") if result.snapshot.manifest else None,
    }
    journal = {
        "content": content,
        "version": published,
        "allowed_content": [published["content_digest"], *([current["content_digest"]] if current else [])],
        "allowed_versions": [result.snapshot.identity, current["version"] if current else None],
    }
    _write(target.parent / "publication.json", json.dumps(journal).encode())
    _recover_publication(target.parent)
    information_scope(worker, {"information": information_feedback(result)})
    return INFORMATION_FILE


def information_feedback(result: Result) -> dict:
    """Describe this handoff as an attribution input, independently of material kinds."""
    return {
        "version": result.snapshot.identity,
        "file": INFORMATION_FILE,
        "excluded_sources": list(result.snapshot.manifest.excluded_sources) if result.snapshot.manifest else [],
        "changed_dimensions": list(result.changed_dimensions),
        "resources_changed": result.resources_changed,
        "questions_changed": result.questions_changed,
    }
