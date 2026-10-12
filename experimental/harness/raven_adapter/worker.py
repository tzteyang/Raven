"""A persistent experimental worker process owning Raven's native runtime and configuration."""

import asyncio
import base64
import hashlib
import json
import os
import shutil
import signal
import tempfile
import time
import traceback
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from math import isfinite
from pathlib import Path
from typing import ClassVar
from uuid import uuid4

from pydantic import TypeAdapter

from experimental.harness.contract import Artifact, Candidate, Validation
from experimental.harness.participation.audience import HEARD
from experimental.harness.participation.compartment import CURRENT, Compartment
from experimental.harness.raven_adapter.deployment import Child, bind_children, child_directory
from experimental.harness.raven_adapter.exploration import Withheld
from experimental.harness.raven_adapter.inspection import (
    Baseline,
    Inspection,
    declaration_for,
    fingerprint,
    unavailable_targets,
)
from experimental.harness.raven_adapter.inspection.runtime import describe_bound, playbook_nodes
from experimental.harness.raven_adapter.launch import Process
from experimental.harness.raven_adapter.materialize import (
    _write,
    copy_local_state,
    extend_artifact,
    restore_content,
)
from experimental.harness.raven_adapter.observe import Recorder, delivered_files, observed_errors, plain
from experimental.harness.raven_adapter.preparation import PreparedHarness
from raven.observability import execution
from raven.spine.message import ChatType, Source
from raven.spine.scheduler import conversation_id
from raven.spine.turn import AnswerlessTurnError, TurnRequest


def _send(connection, value):
    connection.send_bytes(json.dumps(plain(value), ensure_ascii=False).encode())


def _receive(connection):
    return json.loads(connection.recv_bytes())


async def follow_up(busy, announcements, run_turn, *, poll=0.5, away=None):
    """Run what finished background work announces, as follow-up turns.

    Raven delivers a background sub-agent's or playbook graph's result to its conversation as a new turn; the worker
    does the same before it returns. `busy` says whether any background work is still in flight. Without `away`, the
    conversant waits in the chat until nothing is running or waiting, so a delegated deliverable lands in the exchange
    that asked for it. With `away`, the conversant is gone that many seconds and comes back whether or not the work is
    done: what is announced meanwhile runs as it comes, and work still in flight keeps running for a later exchange.
    """
    clock = asyncio.get_running_loop().time
    until = None if away is None else clock() + away
    while True:
        while announcements.empty() and (busy() if until is None else clock() < until):
            await asyncio.sleep(poll)
        if announcements.empty():
            return
        request = announcements.get_nowait()
        context = execution.current()
        if isinstance(request, tuple):
            request, context = request
        with execution.bind(context):
            await run_turn(request if request.turn_id else replace(request, turn_id=uuid4().hex))


async def trial_turn(run_turn, turn, follow) -> dict:
    """The outcome of one trial turn, then `follow` for the work the turn started. Raven ends a turn the model never
    answered with `AnswerlessTurnError`; that is the worker's outcome for the turn, kept for the assessors like a
    timed-out one (`Exchange.stopped`), not a fault of the worker, so nothing follows it."""
    try:
        outcome = await run_turn(turn)
    except AnswerlessTurnError as exc:
        return {"answerless": True, "error": str(exc), "explicit_reply": False}
    await follow()
    return plain(outcome)


def _serve(
    connection,
    baseline_data,
    artifact_data,
    limits,
    root,
    provider_factory,
    start_resources,
    probe,
    copy_inputs,
    planning_state,
    restored_content,
    children_data,
    restored_children,
    execution_context=None,
):
    from experimental.harness.raven_adapter.bind import assemble

    if os.name == "posix":
        os.setsid()

    async def main():
        baseline = Baseline.restore(baseline_data)
        children = {name: Child.restore(value) for name, value in children_data.items()}
        artifact = Artifact.model_validate(artifact_data)
        root_path = Path(root)
        recorder = Recorder(root_path / "observations.jsonl")
        bound = None
        ready = False
        try:
            if copy_inputs is not None:
                original = (baseline.config.workspace_path, baseline.workdir)
                baseline = copy_local_state(baseline, root_path / "state", copy_inputs)
                parent = tuple(zip(original, (baseline.config.workspace_path, baseline.workdir)))
                for name, child in children.items():
                    child.baseline = copy_local_state(
                        child.baseline,
                        root_path / "state" / "children" / fingerprint(name)[:16],
                        copy_inputs,
                        remap=parent,
                    )
            if restored_content:
                restore_content(
                    baseline.config.workspace_path,
                    {baseline.config.workspace_path / name: value for name, value in restored_content.items()},
                )
            for name, content in restored_children.items():
                home = children[name].baseline.config.workspace_path
                restore_content(home, {home / path: value for path, value in content.items()})
            baseline = bind_children(baseline, children, Path(planning_state).parent)
            recorder.delivery_roots = (baseline.workdir, root_path.parent)
            from experimental.harness.raven_adapter.hosting.lifecycle import configure_role

            configure_role(baseline)
            os.chdir(baseline.workdir)
            declaration = declaration_for("assembly", unavailable_targets(baseline), **limits)
            # Assembly sources outlive a process so paused curation keeps the same material locations.
            assembly_root = root_path.parent / "assembly"
            with execution.scope("worker.assembly"):
                bound = assemble(
                    baseline, artifact, declaration, assembly_root, recorder, provider_factory, Path(planning_state)
                )
                if children:
                    from experimental.harness.raven_adapter.capability.protected import protect_delegation

                    protect_delegation(
                        bound.runtime.loop,
                        [row for row in baseline.config.subagents.agents if row.name in children],
                    )
                await bound.prepare()
            announcements = asyncio.Queue()
            loop = bound.runtime.loop
            loop.subagents.set_submit(lambda request: announcements.put_nowait((request, execution.current())))

            async def dag_progress(conversation, name, payload):
                recorder.add("dag.progress", conversation=conversation, name=name, payload=payload)

            loop.set_dag_progress_sink(dag_progress)

            def busy():
                from raven.agent.subagent.dag_live import live_run_ids

                return bool(loop.subagents.get_running_count() or live_run_ids(loop))

            if start_resources:
                await bound.start()
            _send(connection, {"ok": True, "data": {"records": recorder.rows, "prepared": bound.prepared}})
            ready = True
            spoken = {}
            from experimental.harness.raven_adapter.hosting.evidence import record_children, snapshots

            child_before = await snapshots(children)
            while True:
                request = await asyncio.to_thread(_receive, connection)
                offset = len(recorder.rows)
                with execution.receive(request.get("execution"), root_path):
                    try:
                        operation = request["operation"]
                        if operation == "close":
                            from raven.acp_client.pool import close_pool

                            try:
                                await bound.close()
                            finally:
                                bound = None
                                await close_pool()
                            _send(connection, {"ok": True})
                            break
                        if operation == "idle":
                            data = not busy() and announcements.empty()
                        elif operation == "inspect":
                            data = describe_bound(bound, recorder.rows[:offset])
                            if children:
                                from experimental.harness.raven_adapter.inspection import redact

                                data["facts"]["scope"] = {"kind": "root"}
                                data["facts"]["composition"] = {
                                    "nodes": playbook_nodes(bound.runtime, bound.baseline),
                                    "children": {name: redact(child.export()) for name, child in children.items()},
                                }
                                data["identity"] = fingerprint(
                                    {"root": data["identity"], "composition": data["facts"]["composition"]}
                                )
                        elif operation == "inspect_agent":
                            from experimental.harness.raven_adapter.hosting.connection import (
                                connection as agent_connection,
                            )
                            from experimental.harness.raven_adapter.hosting.evidence import inspect as inspect_child

                            backend = loop.subagents._resolve_backend(request["agent"])
                            if getattr(backend, "kind", None) != "acp":
                                raise ValueError("this child has not been prepared for full Harness hosting")
                            session = request.get("session_key")
                            binding = loop.binding_for_session(session) if session is not None else loop.default_binding
                            active = await agent_connection(
                                backend, workspace=baseline.workdir, provider=binding.provider, model=binding.model
                            )
                            data = await inspect_child(active.client, offset=0)
                        elif operation == "probe":
                            from experimental.harness.raven_adapter.validate import run_probe

                            await run_probe(bound, probe)
                            data = {"records": recorder.rows[offset:]}
                        elif operation == "materials":
                            data = {
                                "content": bound.prepared.content,
                                "skills": {
                                    name: {
                                        path: {
                                            "content": base64.b64encode(content).decode()
                                            if content is not None
                                            else None,
                                            "mode": mode,
                                        }
                                        for path, (content, mode) in files.items()
                                    }
                                    for name, files in (
                                        bound.capability.catalog.skills.items() if bound.capability else ()
                                    )
                                },
                            }
                        elif operation == "run":
                            from experimental.harness.raven_adapter.runner import run_turn as run_scoped_turn

                            turn = TypeAdapter(TurnRequest).validate_python(request["turn"])
                            if turn.origin != baseline.origin:
                                raise ValueError("turn origin differs from the inspected worker origin")
                            spoken[conversation_id(turn)] = request.get("spoken", ())
                            if baseline.mode is not None:
                                from raven.config.mode_catalogue import build_mode_catalogue

                                profile = build_mode_catalogue(bound.baseline.config).get(baseline.mode)
                                if profile is None:
                                    raise ValueError(f"configured worker mode is unavailable: {baseline.mode}")
                                bound.runtime.loop.set_session_policy(
                                    turn.conversation or f"{turn.source.channel}:{turn.source.chat_id}",
                                    max_iterations=profile.max_iterations,
                                    mode=profile.id,
                                    mode_overlay=profile.overlay,
                                    reasoning_effort=profile.reasoning_effort,
                                )
                            recorder.turn_id = turn.turn_id
                            events = []

                            async def emit(event):
                                events.append(plain(event))

                            async def run_turn(request_turn):
                                with Compartment("partner", spoken=spoken.get(conversation_id(request_turn), ())):
                                    return await run_scoped_turn(
                                        bound, request_turn, emit, lambda: [], stream=request.get("stream", False)
                                    )

                            try:
                                # Announcements that came after the previous exchange ended run before the new message.
                                await follow_up(busy, announcements, run_turn, away=0)
                                outcome = await trial_turn(
                                    run_turn,
                                    turn,
                                    lambda: follow_up(busy, announcements, run_turn, away=request.get("away")),
                                )
                                await record_children(
                                    children, child_before, recorder, conversation_id(turn), recorder.rows[offset:]
                                )
                            finally:
                                recorder.turn_id = None
                            data = {"events": events, "records": recorder.rows[offset:], "outcome": outcome}
                        else:
                            raise ValueError(f"unknown worker operation: {operation}")
                        _send(connection, {"ok": True, "data": data})
                    except Exception as exc:
                        recorder.add(
                            "runtime.error", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc()
                        )
                        _send(
                            connection,
                            {"ok": False, "error": f"{type(exc).__name__}: {exc}", "records": recorder.rows[offset:]},
                        )
        except Exception as exc:
            if bound is not None and not ready and bound.content_installation is not None:
                bound.content_installation.rollback()
            recorder.add("runtime.error", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
            _send(connection, {"ok": False, "error": f"{type(exc).__name__}: {exc}", "records": recorder.rows})
        finally:
            from raven.acp_client.pool import close_pool

            try:
                if bound is not None:
                    await bound.close()
            finally:
                await close_pool()
                connection.close()

    with execution.receive(execution_context, Path(root)):
        asyncio.run(main())


@dataclass(frozen=True)
class Execution:
    """One turn's evidence; `deliverables` are copies of the files the turn handed over through deliver_files."""

    # Who may receive each field (experimental.harness.participation.audience): a turn's evidence is heard by the counterpart that
    # judges it, the Analyst and the Curator.
    AUDIENCES: ClassVar[dict[str, frozenset[str]]] = {
        name: HEARD for name in ("turn_id", "events", "records", "outcome", "artifact_id", "deliverables")
    }

    turn_id: str
    events: list[dict]
    records: list[dict]
    outcome: dict
    artifact_id: str = ""
    deliverables: tuple[str, ...] = ()

    @property
    def errors(self):
        return observed_errors(self.records)

    @property
    def text(self):
        return "\n".join(
            row["event"]["content"]
            for row in self.records
            if row["kind"] == "runner.event" and row["event_type"] == "Text"
        )


class WorkerError(RuntimeError):
    def __init__(self, message, records=()):
        super().__init__(message)
        self.records = list(records)


class WorkerTimeoutError(WorkerError):
    """An operation ran past the worker's timeout, and the worker process was stopped."""


class TurnTimeoutError(WorkerTimeoutError):
    """A turn ran past the worker's timeout. `execution` is the turn as far as it got, with an outcome that says it
    timed out, so a trial can keep what the conversant was left with: no answer in time."""

    def __init__(self, message, records, execution: "Execution"):
        super().__init__(message, records)
        self.execution = execution


class Worker:
    """Keep native state across turns; rebuild only when the Harness changes.

    `root` keeps what the process never reads: the loop's records, the kept deliverables and prepared materials.
    `area` is where the process runs and writes (each generation's root, the assembly, saved strategy state and the
    child harnesses' folders); it is `root` unless given. With `confinement` the process runs as the confinement's
    user from its code image, and its area must be apart from `root` (see `confinement`).
    `withheld` names the repository files its Curator may not read while it curates this worker and its children.
    """

    def __init__(
        self,
        baseline: Baseline,
        root: Path,
        *,
        provider_factory=None,
        names=None,
        fields=None,
        phases=None,
        timeout: float = 120,
        children=None,
        withheld: Withheld = Withheld(),
        area: Path | None = None,
        confinement=None,
    ):
        if not isfinite(timeout) or timeout <= 0:
            raise ValueError("worker timeout must be finite and positive")
        self.baseline = Baseline.restore(baseline.export())
        self.root = Path(root).resolve()
        self.area = Path(area).resolve() if area is not None else self.root
        self.confinement = confinement
        self.provider_factory = provider_factory
        self._prepare_children = children if callable(children) else None
        supplied_children = {} if self._prepare_children else children or {}
        self.children = {
            name: Child.restore(child.export()) if isinstance(child, Child) else Child(child)
            for name, child in supplied_children.items()
        }
        for child in self.children.values():
            if child.baseline.task is None:
                child.baseline.task = self.baseline.task
        self.limits = {
            "names": list(names) if names is not None else None,
            "fields": {name: list(value) for name, value in fields.items()} if fields is not None else None,
            "phases": {name: list(value) for name, value in phases.items()} if phases is not None else None,
        }
        self.timeout = timeout
        self.withheld = withheld
        self.artifact = Artifact(values={})
        self.last_plan = None
        self.last_attribution = None
        self.last_selection = None
        # The Harness commitments the installed code carries out (experimental.harness.contract.commitments).
        self.commitments = ()
        # The child candidates the last activation installed, by name: what a composite curation revised in them.
        self.last_children = {}
        self.last_execution = None
        self._process = None
        self._connection = None
        self._generation_root = None
        self._diagnostic_root = self.root / "startup-diagnostics"
        self._copy_inputs = None
        self.prepared = PreparedHarness()
        self._preview = None
        self._restored_content = {}
        self._restored_children = {}
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        await self.start()
        return self

    async def stage_skill_package(self, source: Path) -> dict:
        """Make an uploaded package inspectable; Curator still must explicitly adopt it."""
        from experimental.harness.raven_adapter.materials import stage_skill_package

        async with self._lock:
            return stage_skill_package(source, self.baseline.config.workspace_path)

    async def __aexit__(self, *exc):
        await self.close()

    async def start(self, *, start_resources=True, probe=None):
        async with self._lock:
            await self._start(start_resources=start_resources, probe=probe)

    async def _start(self, *, start_resources=True, probe=None):
        if self._process is not None:
            raise RuntimeError("worker is already started")
        if self.confinement is not None and self.area == self.root:
            raise ValueError("a confined worker needs an area apart from its root, which keeps the records")
        self.root.mkdir(parents=True, exist_ok=True)
        self.area.mkdir(parents=True, exist_ok=True)
        if self.confinement is not None:
            self.root.chmod(0o711)
        if self._prepare_children is not None:
            prepared = self._prepare_children(self.baseline)
            self.children = {
                name: child if isinstance(child, Child) else Child(child) for name, child in prepared.items()
            }
            for child in self.children.values():
                if child.baseline.task is None:
                    child.baseline.task = self.baseline.task
            self._prepare_children = None
        self._generation_root = self.area / uuid4().hex
        data = (
            self.baseline.export(),
            self.artifact.model_dump(mode="json"),
            self.limits,
            str(self._generation_root),
        )
        passed = (
            self._copy_inputs,
            str(self.area / "planning.json"),
            self._restored_content,
            {name: child.export() for name, child in self.children.items()},
            self._restored_children,
        )
        if self.confinement is not None:
            data, passed = self.confinement.translate(data), self.confinement.translate(passed)
            self._hand_over()
        diagnostic = self._diagnostic_root / self._generation_root.name
        started = time.monotonic()
        process = Process(
            (*data, self.provider_factory, start_resources, probe, *passed, execution.carrier()),
            confinement=self.confinement,
            area=self.area,
            stderr_path=diagnostic.with_suffix(".stderr"),
        )
        parent = self._connection = process.start()
        self._process = process
        try:
            reply = await asyncio.wait_for(asyncio.to_thread(_receive, parent), self.timeout)
            data = self._check_reply(reply)
            self._assembly_records = data["records"]
            self.prepared = PreparedHarness.model_validate(data["prepared"])
        except WorkerError as exc:
            self._record_startup_failure(diagnostic, started, exc, process)
            await self._terminate(grace=5)
            raise
        except (asyncio.TimeoutError, EOFError) as exc:
            self._record_startup_failure(diagnostic, started, exc, process)
            await self._terminate()
            reason = "timed out" if isinstance(exc, asyncio.TimeoutError) else "closed its startup pipe"
            raise WorkerError(f"worker {reason}; diagnostics: {diagnostic}", self.records()) from exc
        except BaseException:
            await self._terminate()
            raise

    def _record_startup_failure(self, diagnostic, started, exc, process):
        data = {
            "exception_type": type(exc).__name__,
            "elapsed_seconds": time.monotonic() - started,
            "timeout_seconds": self.timeout,
            "pid": process.pid,
            "exit_code_before_cleanup": process.exitcode,
            "stderr_path": str(diagnostic.with_suffix(".stderr")),
            "generation_root": str(self._generation_root),
            "validation_copy": self._copy_inputs is not None,
        }
        diagnostic.parent.mkdir(parents=True, exist_ok=True)
        with os.fdopen(
            os.open(diagnostic.with_suffix(".json"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
        ) as stream:
            json.dump(data, stream, indent=2)

    def _hand_over(self):
        """Give the confinement's user what the process works in; this process writes there between operations."""
        places = [self.area, self.baseline.workdir, self.baseline.config.workspace_path]
        kept = [path for path in places if not any(path != other and path.is_relative_to(other) for other in places)]
        self.confinement.hand_over(*dict.fromkeys(kept))

    @staticmethod
    def _check_reply(reply):
        if not reply["ok"]:
            raise WorkerError(reply["error"], reply.get("records", ()))
        return reply.get("data")

    async def _exchange(self, request):
        if self._process is None or not self._process.is_alive():
            raise WorkerError("worker is not running")
        if self.confinement is not None:
            self._hand_over()
        try:
            _send(self._connection, {**request, "execution": execution.carrier()})
            reply = await asyncio.wait_for(asyncio.to_thread(_receive, self._connection), self.timeout)
            return self._check_reply(reply)
        except asyncio.CancelledError:
            await self._terminate()
            raise
        except asyncio.TimeoutError as exc:
            await self._terminate()
            raise WorkerTimeoutError(
                f"worker timed out after {self.timeout}s during the operation", self.records()
            ) from exc
        except EOFError as exc:
            await self._terminate()
            raise WorkerError("worker exited during the operation", self.records()) from exc

    def records(self) -> list[dict]:
        if self._generation_root is None:
            return []
        path = self._generation_root / "observations.jsonl"
        if not path.is_file():
            return []
        result = []
        for line in path.read_text(errors="replace").splitlines():
            try:
                result.append(json.loads(line))
            except ValueError:
                result.append({"kind": "runtime.error", "error": "An observation record was incomplete at shutdown."})
        return result

    async def inspect(self) -> Inspection:
        async with self._lock:
            return await self._inspect()

    async def agent_state(self, name: str, *, session_key: str | None = None):
        """Read facts and execution evidence from the child selected by the native launch binding."""
        async with self._lock:
            return await self._exchange({"operation": "inspect_agent", "agent": name, "session_key": session_key})

    async def inspect_agent(self, name: str, *, session_key: str | None = None) -> Inspection:
        return Inspection.restore((await self.agent_state(name, session_key=session_key))["inspection"])

    @property
    def revision_id(self):
        if not self.children:
            return fingerprint(self.artifact.model_dump(mode="json"))
        return fingerprint(
            {
                "root": self.artifact.model_dump(mode="json"),
                "children": {
                    name: {
                        "baseline": child.baseline.export(),
                        "artifact": child.artifact.model_dump(mode="json"),
                        "grants": child.grants,
                    }
                    for name, child in self.children.items()
                },
            }
        )

    async def _inspect(self) -> Inspection:
        data = await self._exchange({"operation": "inspect"})
        return Inspection.restore(data, **self.limits)

    async def run(
        self, request: str | TurnRequest, *, session_key="curator:task", stream=False, away: float | None = None
    ) -> Execution:
        """One turn and the follow-up turns of the background work it started (see `follow_up`): by default the
        exchange lasts until that work is done; with `away`, the conversant is gone that many seconds and the exchange
        ends then, the work still in flight announcing itself in a later exchange. An explicit partner compartment
        supplies entitled speech across the process boundary; runtime message roles grant no such permission."""
        if isinstance(request, str):
            channel, _, chat_id = session_key.partition(":")
            request = TurnRequest(
                origin=self.baseline.origin,
                source=Source(channel=channel, chat_id=chat_id, sender_id="user", chat_type=ChatType.DM),
                text=request,
                conversation=session_key,
                turn_id=uuid4().hex,
            )
        if request.turn_id is None:
            request = replace(request, turn_id=uuid4().hex)
        async with self._lock:
            artifact_id = self.revision_id
            scope = CURRENT.get()
            try:
                data = await self._exchange(
                    {
                        "operation": "run",
                        "turn": TypeAdapter(TurnRequest).dump_python(request, mode="json"),
                        "stream": stream,
                        "away": away,
                        "spoken": scope.spoken if scope is not None and scope.role == "partner" else (),
                    }
                )
            except WorkerTimeoutError as exc:
                rows = [row for row in exc.records if row.get("turn_id") == request.turn_id]
                self.last_execution = Execution(
                    request.turn_id,
                    [],
                    rows,
                    {"timed_out": True, "timeout": self.timeout, "explicit_reply": False},
                    artifact_id,
                    self._keep_deliverables(request.turn_id, rows),
                )
                raise TurnTimeoutError(str(exc), exc.records, self.last_execution) from exc
            self.last_execution = Execution(
                request.turn_id,
                data["events"],
                data["records"],
                data["outcome"],
                artifact_id,
                self._keep_deliverables(request.turn_id, data["records"]),
            )
            return self.last_execution

    async def keep(self):
        """Record the active deployment so `reinstate` can return to it after later revisions."""
        from experimental.harness.raven_adapter.deployment import keep

        return await keep(self)

    async def reinstate(self, kept):
        """Return exactly to a deployment recorded by `keep`."""
        from experimental.harness.raven_adapter.deployment import reinstate

        return await reinstate(self, kept)

    def _keep_deliverables(self, turn_id, records) -> tuple[str, ...]:
        """Copy what the turn delivered, so a later turn rewriting the same file does not erase this one.

        A file counts as delivered once Raven's tool handed it over (see `delivered_files`), so a refused or failed
        call keeps nothing. Only a file inside the worker's workdir or area is kept, once links are resolved: this
        process reads it with its own rights, so a path or a link the worker names elsewhere is never copied.
        """
        places = [self.baseline.workdir.resolve(), self.area.resolve()]
        kept = []
        for row in records:
            for item in delivered_files(row):
                retained = item.get("retained")
                if isinstance(retained, dict) and not retained.get("path"):
                    continue
                source = Path(str(retained["path"] if isinstance(retained, dict) else item["path"]))
                source = (source if source.is_absolute() else self.baseline.workdir / source).resolve()
                if source.is_file() and any(source.is_relative_to(place) for place in places):
                    content = source.read_bytes()
                    if isinstance(retained, dict) and hashlib.sha256(content).hexdigest() != retained.get("sha256"):
                        continue
                    folder = self.root / "deliverables" / turn_id
                    if isinstance(retained, dict):
                        folder /= source.parent.name
                    target = folder / source.name
                    _write(target, content)
                    kept.append(str(target))
        return tuple(kept)

    def _accept(self, candidate, inspection):
        candidate = inspection.declaration.validate(candidate)
        for name in candidate.artifact.remove:
            if name not in self.artifact.values:
                raise ValueError(f"cannot retire a target that is not currently authored: {name}")
            inspection.declaration.target(name).parse(self.artifact.values[name])
        return candidate

    async def install(self, candidate: Candidate, *, children=None):
        """Activate one set; an explicit child value of None restores its supplied baseline artifact."""
        from experimental.harness.raven_adapter.deployment import activate

        return await activate(self, candidate, children)

    async def _terminate(self, *, grace=0):
        process, connection = self._process, self._connection
        self._process = self._connection = None
        if process is not None:
            if grace:
                await asyncio.to_thread(process.join, grace)
            try:
                if process.is_alive():
                    if os.name == "posix" and os.getpgid(process.pid) == process.pid:
                        os.killpg(process.pid, signal.SIGTERM)
                    else:
                        process.terminate()
            except ProcessLookupError:
                pass
            await asyncio.to_thread(process.join, 5)
            try:
                if process.is_alive():
                    if os.name == "posix" and os.getpgid(process.pid) == process.pid:
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                    await asyncio.to_thread(process.join, 5)
            except ProcessLookupError:
                pass
            process.close()
        if connection is not None:
            connection.close()

    async def _close(self):
        if self._process is None:
            return
        try:
            if self._process.is_alive():
                await asyncio.wait_for(self._exchange({"operation": "close"}), self.timeout)
        finally:
            await self._terminate(grace=1)

    async def close(self):
        if self._lock.locked():
            await self._terminate()
        else:
            async with self._lock:
                await self._close()

    async def check(self, candidate: Candidate, *, probe=None):
        """Construct a candidate on copied local state; optional host probes exercise behavior."""
        async with self._lock:
            return await self._check(candidate, probe=probe)

    async def _check(self, candidate: Candidate, *, probe=None, inspection=None):
        try:
            async with self._validation_copy(candidate, probe=probe, inspection=inspection) as trial:
                data = await trial._exchange({"operation": "probe"})
                await trial.inspect()
                observations = [*trial._assembly_records, *data["records"]]
                return Validation(
                    [row.get("error", row["kind"]) for row in observed_errors(observations)], observations
                )
        except (WorkerError, asyncio.TimeoutError, ValueError) as exc:
            return Validation([str(exc) or "validation timed out"], getattr(exc, "records", []))

    async def check_composition(self, candidate, children, *, probe=None):
        """Start the complete proposed set on copied state before touching the active deployment."""
        async with self._lock:
            try:
                async with self._validation_copy(candidate, children=children, probe=probe) as trial:
                    observations = list(trial._assembly_records)
                    for name in trial.children:
                        report = await trial.agent_state(name)
                        observations.append(
                            {
                                "kind": "composition.child_ready",
                                "harness": name,
                                "revision": report["revision"],
                                "pid": report["pid"],
                            }
                        )
                        observations.append(
                            {
                                "kind": "child.execution",
                                "harness": name,
                                "revision": report["revision"],
                                "records": report["records"],
                            }
                        )
                    tested = await trial._exchange({"operation": "probe"})
                    observations.extend(tested["records"])
                    return Validation(
                        [row.get("error", row["kind"]) for row in observed_errors(observations)], observations
                    )
            except (WorkerError, asyncio.TimeoutError, ValueError) as exc:
                return Validation([str(exc) or "composition validation timed out"], getattr(exc, "records", []))

    async def preview_nodes(self, candidate):
        """Read the proposed native graph on an isolated copy; no temporary source paths escape."""
        async with self._lock:
            async with self._validation_copy(candidate) as trial:
                viewed = await trial.inspect()
                nodes = viewed.facts.get("composition", {}).get("nodes", {})
                materials = await trial._exchange({"operation": "materials"})
                self._preview = (
                    (candidate.baseline, candidate.contract_id, fingerprint(candidate.artifact.model_dump())),
                    nodes,
                    materials,
                )
                return nodes

    async def preview_materials(self, candidate, *, children=()):
        """Hand children actual prepared resources as durable inputs, including binary assets."""
        from experimental.harness.raven_adapter.capability.catalog import inspect_package, materialize_tree
        from experimental.harness.raven_adapter.materials import stage_skill_package

        async with self._lock:
            self._accept(candidate, await self._inspect())
            identity = (candidate.baseline, candidate.contract_id, fingerprint(candidate.artifact.model_dump()))
            if self._preview is not None and self._preview[0] == identity:
                data = self._preview[2]
            else:
                async with self._validation_copy(candidate) as trial:
                    data = await trial._exchange({"operation": "materials"})
            result = {"content": data["content"], "skills": {}}
            for name, entries in data["skills"].items():
                files = {
                    path: (
                        base64.b64decode(row["content"], validate=True) if row["content"] is not None else None,
                        row["mode"],
                    )
                    for path, row in entries.items()
                }
                destination = self.root / "prepared-materials" / fingerprint(data["skills"]) / name
                materialize_tree(files, destination)
                inspected = inspect_package(destination)
                for child_name in children:
                    child = self.children[child_name]
                    home = child.baseline.config.workspace_path
                    staged = stage_skill_package(destination, home)
                    inspected = staged
                result["skills"][name] = inspected
            return result

    @asynccontextmanager
    async def _validation_copy(self, candidate, *, probe=None, inspection=None, children=None):
        from experimental.harness.raven_adapter.validate import static_checks

        inspection = await self._inspect() if inspection is None else inspection
        candidate = self._accept(candidate, inspection)
        errors = static_checks(candidate)
        if errors:
            raise ValueError("; ".join(errors))
        with tempfile.TemporaryDirectory(prefix="raven-curator-check-") as temporary:
            temp = Path(temporary)
            if self.confinement is not None:
                temp.chmod(0o711)
            trial = Worker(
                self.baseline,
                temp / "runtime",
                provider_factory=self.provider_factory,
                timeout=self.timeout,
                children=self.children,
                area=temp / "runtime" / "area",
                confinement=self.confinement,
                **self.limits,
            )
            trial._diagnostic_root = self._diagnostic_root
            trial._copy_inputs = (str(self.root), str(temp))
            from experimental.harness.raven_adapter.deployment import child_artifact

            for name, submitted in (children or {}).items():
                child = trial.children[name]
                report = await self._exchange({"operation": "inspect_agent", "agent": name})
                viewed = Inspection.restore(report["inspection"])
                effective = child_artifact(child, submitted, viewed, restoring=submitted is None)
                child.artifact = effective
            from experimental.harness.raven_adapter.checkpoints import CHECKPOINT_FILES

            for original, copied in (
                (self.area, trial.area),
                *((child_directory(self.area, name), child_directory(trial.area, name)) for name in self.children),
            ):
                for name in CHECKPOINT_FILES:
                    checkpoint = original / name
                    if checkpoint.is_file() and not checkpoint.is_symlink():
                        _write(copied / name, checkpoint.read_bytes())
                source = original / "assembly"
                destination = copied / "assembly"
                ledger = source / "content-state.json"
                if ledger.is_file() and not ledger.is_symlink():
                    _write(destination / ledger.name, ledger.read_bytes())
                for directory in ("skill-inputs", "baseline-skills"):
                    if (source / directory).is_dir() and not (source / directory).is_symlink():
                        shutil.copytree(source / directory, destination / directory, symlinks=True)
            try:
                trial.artifact = extend_artifact(self.artifact, candidate.artifact)
                await trial.start(start_resources=False, probe=probe)
                yield trial
            finally:
                await trial.close()
                if context := execution.current():
                    from raven.observability.ledger import read_tree

                    for row in read_tree(trial.root):
                        if row["run_id"] == context.run_id:
                            context.ledger.put(row)
