"""Composition preserves source identity and includes all known uses of selected children."""

import json

import pytest

from experimental.curator.composition.context import execution_turns, merge_sources
from experimental.curator.composition.run import _groups


def test_execution_identity_survives_restart_but_changes_for_new_or_revised_turns():
    original = [
        {"kind": "hosting.ready", "turn_id": None, "pid": 100},
        {"kind": "memory.result", "turn_id": "first", "result": {"fact": "cobalt"}},
    ]
    restarted = [{"kind": "hosting.ready", "turn_id": None, "pid": 200}]
    identity = execution_turns(original)
    assert execution_turns(original, restarted) == identity
    newer = [{"kind": "action.result", "turn_id": "second", "result": {"control": "continue"}}]
    assert set(execution_turns(original, newer)) == {"first", "second"}
    corrected = [{"kind": "memory.result", "turn_id": "first", "result": {"fact": "amber"}}]
    assert execution_turns(original, corrected) != identity
    identity["first"][0]["result"]["fact"] = "changed copy"
    assert original[1]["result"]["fact"] == "cobalt"


@pytest.mark.parametrize("reverse", [False, True])
def test_shared_uses_are_context_without_enrolling_unrequested_children(reverse):
    nodes = {
        "support/revise": {
            "node": {"subagent": "Shared", "prompt_template": "Revise confirmed work"},
            "requirements": [],
        },
        "sales/prepare": {
            "node": {"subagent": "Shared", "prompt_template": "Prepare new work"},
            "requirements": [{"behavior": "Collect missing inputs"}],
        },
        "other/prepare": {"node": {"subagent": "Other"}, "requirements": []},
    }
    if reverse:
        nodes = dict(reversed(nodes.items()))
    grouped = _groups(nodes, {"Shared"})
    assert set(grouped) == {"Shared"}
    assert grouped["Shared"] == {key: nodes[key] for key in ("support/revise", "sales/prepare")}
    assert nodes["support/revise"]["requirements"] == []
    nodes["sales/prepare"]["requirements"] = []
    assert _groups(nodes, {"Shared"}) == {}
    nodes["other/prepare"]["requirements"] = [{"behavior": "Collect missing inputs"}]
    with pytest.raises(ValueError, match="unprepared child Harness: Other"):
        _groups(nodes, {"Shared"})


def test_shared_protocols_reuse_sources_but_child_implementations_keep_their_own_names():
    protocol = {"path": "/repo/protocol.py", "digest": "same", "start": 1, "end": 40}
    sources = {"protocol": protocol}
    incoming = {
        "strategy.protocol": dict(protocol),
        "strategy.impl": {"path": "/child/impl.py", "digest": "own", "start": 1, "end": 20},
        "strategy.other_excerpt": {**protocol, "start": 20},
    }
    aliases = merge_sources(sources, incoming, "child.Research")
    assert aliases["strategy.protocol"] == "protocol"
    assert sources[aliases["strategy.impl"]] == incoming["strategy.impl"]
    assert aliases["strategy.other_excerpt"] != "protocol"
    assert len(sources) == 3
    with pytest.raises(ValueError, match="collision"):
        merge_sources(sources, {"strategy.impl": {**incoming["strategy.impl"], "digest": "changed"}}, "child.Research")


def test_only_dag_playbooks_contribute_nodes_that_can_hold_requirements(tmp_path):
    from types import SimpleNamespace

    from experimental.curator.raven_adapter.inspection.runtime import playbook_nodes
    from raven.playbook import NodeSpec, PlaybookSpec, PlaybookStore
    from raven.playbook.executor import PlaybookExecutor
    from raven.playbook.runtime import PlaybookRuntime

    home = tmp_path / "home"
    store = PlaybookStore(home / "playbooks", builtin_root=tmp_path / "empty")
    common = {
        "description": "Do the work",
        "task_summary": "Work",
        "confirm": False,
        "triggers": {"keywords": ["work"]},
    }
    store.save(
        PlaybookSpec(
            name="work",
            mode="dag",
            nodes=[
                NodeSpec(id="draft", subagent="Writer", node_summary="Draft", prompt_template="Draft it."),
                NodeSpec(id="check", subagent="Reviewer", node_summary="Check", prompt_template="Check it."),
            ],
            **common,
        )
    )
    store.save(PlaybookSpec(name="composed", mode="prompt", prompts="Compose the graph from the request.", **common))
    requirement = {
        "behavior": "Follow the procedure",
        "observed": "The draft skipped it",
        "evidence": ["the first drill"],
        "expectation": "new",
        "acceptance": "The draft follows it",
        "strength": "must_hold",
    }
    draft = home / "playbooks" / "work" / "nodes" / "draft" / "requirements.json"
    draft.parent.mkdir(parents=True)
    draft.write_text(json.dumps([requirement]))
    library = PlaybookRuntime(store=store, executor=PlaybookExecutor())
    runtime = SimpleNamespace(loop=SimpleNamespace(_playbooks=library))
    baseline = SimpleNamespace(config=SimpleNamespace(workspace_path=home))
    nodes = playbook_nodes(runtime, baseline)
    assert set(nodes) == {"work/draft", "work/check"}
    assert nodes["work/draft"]["playbook"] == "work" and nodes["work/draft"]["node"]["subagent"] == "Writer"
    assert [row["behavior"] for row in nodes["work/draft"]["requirements"]] == ["Follow the procedure"]
    assert nodes["work/check"]["requirements"] == []
    (draft.parent.parent / "check").mkdir()
    (draft.parent.parent / "check" / "requirements.json").write_text("[]")
    with pytest.raises(ValueError, match="nonempty"):
        playbook_nodes(runtime, baseline)


def test_requirement_files_are_read_only_beside_a_playbook_node():
    from experimental.curator.composition.requirements import requirement_node

    assert requirement_node("work/nodes/step/requirements.json") == "work/step"
    assert requirement_node("work/step/requirements.json") is None
    assert requirement_node("work/nodes/step/notes.json") is None
    assert requirement_node("deep/work/nodes/step/requirements.json") is None


def test_the_shared_budget_is_what_the_scopes_consumed_plus_what_a_scope_may_still_spend(tmp_path):
    """Each scope's generation keeps its own counters; the composite budget is their sum. A scope resumes with its
    own count plus what the whole composition has left, so the total exceeds the limits by no more than a
    correction call; with nothing left, lowered limits or such a call included, a scope pauses."""
    from experimental.curator.composition.state import Progress
    from experimental.curator.generation.run import GenerationPausedError, Limits
    from experimental.curator.generation.state import GenerationState

    def spent(scope, **counters):
        path = tmp_path / scope / "progress" / "generation.json"
        path.parent.mkdir(parents=True)
        path.write_text(GenerationState(input_id="x", **counters).model_dump_json())

    progress = Progress(input_id="composite", directory=str(tmp_path))
    assert progress.totals() == {"calls": 0, "queries": 0, "checks": 0, "repairs": 0}
    spent("root", stage="implement", calls=3, queries=1, checks=1, repairs=1)
    spent("child-a", calls=2, queries=2)
    assert progress.totals() == {"calls": 5, "queries": 3, "checks": 1, "repairs": 1}
    limits = Limits(max_calls=10, max_queries=8, max_checks=3, max_repairs=3, call_timeout=9)
    root = progress.limits_for("root", limits)
    assert (root.max_calls, root.max_queries, root.max_checks, root.max_repairs) == (8, 6, 3, 3)
    fresh = progress.limits_for("child-b", limits)
    assert (fresh.max_calls, fresh.max_queries, fresh.max_checks, fresh.max_repairs) == (5, 5, 2, 2)
    assert fresh.call_timeout == 9
    with pytest.raises(GenerationPausedError, match="budget exhausted"):
        progress.limits_for("root", Limits(max_calls=4))
    with pytest.raises(GenerationPausedError) as paused:
        progress.limits_for("root", Limits(max_calls=5, max_queries=8))
    assert paused.value.state.stage == "implement" and paused.value.state.calls == 5
    with pytest.raises(GenerationPausedError) as paused:
        progress.limits_for("child-b", Limits(max_calls=5, max_queries=8))
    assert paused.value.state.stage == "select"
    spent("child-c", calls=6)
    with pytest.raises(GenerationPausedError, match="budget exhausted"):
        progress.limits_for("child-b", Limits(max_calls=10, max_queries=8))


class Composite:
    """A root worker with one hosted child, as `composition.run.improve` sees it, without any process.

    `propose` is replaced by `Proposals`; the worker itself answers inspection, previews the proposed graph from the
    requirement files the root candidate authors, and installs by adopting the candidates.
    """

    def __init__(self, tmp_path, *, nodes_now=None):
        from experimental.curator.harness import Artifact, Task
        from experimental.curator.raven_adapter.baselines import Baseline
        from experimental.curator.raven_adapter.deployment import Child
        from experimental.curator.raven_adapter.exploration import Withheld
        from experimental.curator.raven_adapter.inspection.runtime import declaration_for
        from raven.config.raven import RavenConfig
        from raven.config.schema import Config

        def baseline(home):
            config = Config()
            config.agents.defaults.workspace = str(home)
            return Baseline(config, RavenConfig(), tmp_path, task=Task(id="task", text="Work"))

        self.root = self.area = tmp_path / "worker"
        self.confinement = None
        self.baseline = baseline(tmp_path / "home")
        self.children = {"Hosted": Child(baseline(tmp_path / "home" / "subagents" / "Hosted"))}
        self.child_declaration = declaration_for("hosted@1", {})
        self.artifact = Artifact(values={})
        self.last_plan = self.last_execution = None
        self.timeout = 5
        self.withheld = Withheld()
        self._content_baseline = {}
        self.nodes_now = nodes_now or {}
        self.composition_checks = []
        self.installed = []
        self.composition_errors = []

    @property
    def revision_id(self):
        from experimental.curator.raven_adapter.inspection import fingerprint

        return fingerprint(
            {
                "root": self.artifact.model_dump(mode="json"),
                "children": {name: child.artifact.model_dump(mode="json") for name, child in self.children.items()},
            }
        )

    def child_payload(self):
        return {
            "identity": "hosted@1",
            "unavailable": {},
            "facts": {"hosting": "acp", "backend": "hosted", "allow_delegation": False},
            "sources": {},
        }

    async def agent_state(self, name):
        from experimental.curator.raven_adapter.inspection import fingerprint

        return {
            "inspection": self.child_payload(),
            "records": [{"kind": "action.result"}, {"kind": "action.result"}, {"kind": "loop.control"}],
            "revision": fingerprint(self.children[name].artifact.model_dump(mode="json")),
        }

    async def inspect(self):
        from experimental.curator.harness import Declaration
        from experimental.curator.raven_adapter.inspection import Inspection
        from experimental.curator.raven_adapter.targets import catalogue

        return Inspection(
            Declaration("root@1", catalogue()),
            {"task": {"id": "task", "text": "Work"}, "composition": {"nodes": self.nodes_now}},
            {"skill.workspace/sop": {"path": "/x", "start": 1, "end": 1, "digest": "d1"}},
        )

    async def check(self, candidate, *, probe=None):
        from experimental.curator.harness import Validation

        return Validation([], [{"kind": "root.checked"}])

    async def preview_nodes(self, candidate):
        nodes = {}
        for item in json.loads(candidate.artifact.files.get("procedures.json", "[]")):
            spec = item["spec"]
            for node in spec["nodes"]:
                nodes[f"{spec['name']}/{node['id']}"] = {
                    "playbook": spec["name"],
                    "node": node,
                    "requirements": item["requirements"].get(node["id"], []),
                }
        return nodes

    async def preview_materials(self, candidate, *, children=()):
        return {"content": {"memory": json.loads(candidate.artifact.files["memory_profile.json"])}, "skills": {}}

    async def check_composition(self, candidate, children, *, probe=None):
        from experimental.curator.harness import Validation

        self.composition_checks.append(dict(children))
        if self.composition_errors:
            return Validation([self.composition_errors.pop(0)], [])
        return Validation([], [{"kind": "composition.child_ready", "harness": "Hosted"}])

    async def install(self, candidate, *, children=None):
        from experimental.curator.raven_adapter.materialize import extend_artifact

        self.installed.append((candidate, dict(children or {})))
        self.artifact = extend_artifact(self.artifact, candidate.artifact)
        for name, submitted in (children or {}).items():
            child = self.children[name]
            child.artifact = child.original if submitted is None else submitted.artifact
            child.plan = None if submitted is None else submitted.plan


class Proposals:
    """Stands in for `workflow.propose`: answers each scope with a scripted candidate or failure, checks a root
    candidate through the subject as the real proposal would, and leaves the generation checkpoint a real one leaves."""

    def __init__(self, monkeypatch, root_candidate, child_candidate):
        from experimental.curator.composition import run as composition

        self.root_candidate, self.child_candidate = root_candidate, child_candidate
        self.calls, self.failures, self.attributed = [], [], False
        monkeypatch.setattr(composition, "propose", self)

    async def __call__(
        self,
        subject,
        provider,
        *,
        feedback,
        model,
        limits,
        probe=None,
        repair=None,
        observations=None,
        attributor=None,
        attribution=None,
    ):
        from dataclasses import replace

        from experimental.curator.attribution import AttributionState
        from experimental.curator.generation.run import Generated, GenerationError
        from experimental.curator.generation.state import GenerationState
        from experimental.curator.harness import Attributed, Attribution, Validation
        from tests.test_harness_curator_generation import diagnosis

        scope = "root" if subject.root.name == "root" else "child"
        self.calls.append(
            {
                "scope": scope,
                "feedback": feedback,
                "limits": limits,
                "repair": repair,
                "observations": observations,
                "attributor": attributor,
                "attribution": attribution,
            }
        )
        state = subject.root / "progress" / "generation.json"
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(
            GenerationState(input_id="x", stage="implement", calls=2, repairs=int(repair is not None)).model_dump_json()
        )
        record = subject.root / "attribution" / f"{scope}-{len(self.calls)}.json"
        if self.attributed:
            record.parent.mkdir(parents=True, exist_ok=True)
            record.write_text(json.dumps({"scope": scope}))
            (subject.root / "progress" / "attribution.json").write_text(
                AttributionState(input_id="x", identity={}, subjects=("task",), calls=1, queries=2).model_dump_json()
            )
        if self.failures and self.failures[0][0] == scope:
            _, error = self.failures.pop(0)
            raise error
        candidate = self.root_candidate if scope == "root" else self.child_candidate
        if self.attributed and scope == "root":
            attributed = Attributed(
                attribution=Attribution.model_validate(diagnosis()),
                identity={"implementation": "model"},
                record=record.name,
            )
            candidate = replace(candidate, attribution=attributed)
        if scope == "root":
            checked = await subject.check(candidate)
            if not checked.passed:
                raise GenerationError("; ".join(checked.errors))
        return Generated(candidate, Validation([], [{"kind": f"{scope}.generated"}]), ({"event": "validation"},))


REQUIREMENT = {
    "behavior": "Follow the supplied work procedure",
    "observed": "New working requirement",
    "evidence": ["Mentor material"],
    "expectation": "new",
    "acceptance": "The assigned work follows the procedure",
    "strength": "must_hold",
}


async def candidates(worker, *, node_reasons=None, withdraw=False):
    """A root candidate that authors the requirement file beside `work/step` (or retires it) and a child candidate."""
    from tests.fixtures.harness_curator.authoring import action, combine, planning, profile
    from tests.test_harness_curator_generation import plan

    root_plan = plan("planning.strategy", "memory.strategy")
    root_plan["node_reasons"] = (
        {"work/step": "The child realises the requirement"} if node_reasons is None else node_reasons
    )
    procedures = [
        {
            "spec": {
                "name": "work",
                "description": "Do the work",
                "task_summary": "Work",
                "mode": "dag",
                "triggers": {"keywords": ["work"]},
                "nodes": [
                    {
                        "id": "step",
                        "subagent": "Hosted",
                        "node_summary": "Work",
                        "prompt_template": "Follow the procedure.",
                    },
                ],
            },
            "requirements": {} if withdraw else {"step": [REQUIREMENT]},
        }
    ]
    artifact = combine(planning(procedures), profile({"TOOLS.md": "Root rules"}))
    root = (await worker.inspect()).declaration.accept(root_plan, artifact)
    child = worker.child_declaration.accept(plan("action.strategy"), action(generation={"temperature": 0.2}))
    return root, child


async def curated(worker, provider=None, **arguments):
    from experimental.curator.composition.run import improve
    from experimental.curator.generation.run import Limits

    arguments = {
        "feedback": {"text": "Train the child"},
        "model": "m",
        "limits": Limits(),
        "probe": None,
        "resume": True,
        **arguments,
    }
    return await improve(worker, provider, **arguments)


def records_of(worker):
    paths = sorted((worker.root / "curation").glob("*.json"))
    return [json.loads(path.read_text()) for path in paths if path.name != "composition.json"]


def test_child_trial_evidence_keeps_scope_and_excludes_other_children():
    from experimental.curator.composition.context import child_observations

    rows = [
        {
            "kind": "task.execution",
            "session": "replica/session",
            "turn_id": "parent-turn",
            "artifact_id": "root-revision",
            "records": [
                {"kind": "provider.response", "response": "root-only"},
                {
                    "kind": "child.execution",
                    "harness": "A",
                    "revision": "a-revision",
                    "records": [
                        {"kind": "action.control", "receipt": {"status": "applied"}, "turn_id": "child-turn"},
                    ],
                },
                {
                    "kind": "child.execution",
                    "harness": "B",
                    "revision": "b-revision",
                    "records": [
                        {"kind": "provider.response", "response": "other-child-private"},
                    ],
                },
            ],
        }
    ]
    (observed,) = child_observations(rows, "A")
    assert observed["session"] == "replica/session" and observed["turn_id"] == "parent-turn"
    assert observed["revision"] == "a-revision" and observed["records"][0]["turn_id"] == "child-turn"
    assert "root-only" not in str(observed) and "other-child-private" not in str(observed)
    observed["records"].clear()
    assert rows[0]["records"][1]["records"]


@pytest.mark.asyncio
async def test_a_composition_proposes_the_root_then_each_assigned_child_and_activates_them_once(tmp_path, monkeypatch):
    worker = Composite(tmp_path)
    root, child = await candidates(worker)
    proposals = Proposals(monkeypatch, root, child)
    result = await curated(worker)
    assert [call["scope"] for call in proposals.calls] == ["root", "child"]
    assert proposals.calls[0]["feedback"] == {"text": "Train the child"} and proposals.calls[0]["repair"] is None
    relevant = proposals.calls[1]["feedback"]
    assert relevant["parent_materials"] == {"content": {"memory": {"TOOLS.md": "Root rules"}}, "skills": {}}
    assert list(relevant["requirements"]) == ["work/step"]
    assert relevant["requirements"]["work/step"][0].items() >= REQUIREMENT.items()
    assert relevant["feedback"] == {"text": "Train the child"}
    (observation,) = proposals.calls[1]["observations"]
    assert observation["kind"] == "child.execution" and observation["record_kinds"] == {
        "action.result": 2,
        "loop.control": 1,
    }
    assert [row["kind"] for row in observation["records"]] == ["action.result", "action.result", "loop.control"]
    assert proposals.calls[1]["limits"].max_calls == 10
    assert worker.composition_checks == [{"Hosted": child}] and worker.installed == [(root, {"Hosted": child})]
    assert worker.children["Hosted"].artifact == child.artifact and worker.children["Hosted"].plan == child.plan
    assert result.candidate == root and result.validation.passed
    kinds = [row["kind"] for row in result.validation.observations]
    assert kinds == ["root.generated", "composition.child_ready", "child.generated", "composition.activated"]
    assert not (worker.root / "curation/composition.json").exists()
    (record,) = records_of(worker)
    assert record["changed"] is True and record["withdrawn_children"] == []
    assert record["child_changes"]["Hosted"]["candidate"]["artifact"]["values"] == child.artifact.values
    assert record["revision"]["children"]["Hosted"]["artifact"]["values"] == child.artifact.values
    assert record["active_artifact_id"] == worker.revision_id


@pytest.mark.asyncio
async def test_a_root_whose_node_reasons_miss_a_node_or_name_an_unprepared_child_is_sent_back(tmp_path, monkeypatch):
    from experimental.curator.generation.run import GenerationError, Limits

    worker = Composite(tmp_path)
    root, child = await candidates(worker, node_reasons={})
    Proposals(monkeypatch, root, child)
    with pytest.raises(GenerationError, match="node reasons must cover"):
        await curated(worker, limits=Limits(max_repairs=0))
    other = Composite(tmp_path / "other")
    other.children = {"Elsewhere": other.children["Hosted"]}
    root, child = await candidates(other)
    Proposals(monkeypatch, root, child)
    with pytest.raises(GenerationError, match="unprepared child Harness: Hosted"):
        await curated(other, limits=Limits(max_repairs=0))


@pytest.mark.asyncio
async def test_a_failed_composite_check_repairs_the_root_and_reuses_the_child_whose_inputs_did_not_change(
    tmp_path, monkeypatch
):
    worker = Composite(tmp_path)
    root, child = await candidates(worker)
    proposals = Proposals(monkeypatch, root, child)
    worker.composition_errors.append("the child could not start beside the root")
    await curated(worker)
    assert [call["scope"] for call in proposals.calls] == ["root", "child", "root"]
    repair = proposals.calls[2]["repair"]
    assert repair.errors == ["composite validation failed: the child could not start beside the root"]
    assert repair.observations[0]["kind"] == "composition.failure" and repair.observations[0]["scope"] == "composition"
    assert len(worker.composition_checks) == 2 and len(worker.installed) == 1
    (record,) = records_of(worker)
    assert record["composition"]["repair"] is None and record["changed"] is True


@pytest.mark.asyncio
async def test_a_child_that_fails_to_generate_sends_the_root_back_with_its_scope_and_nodes(tmp_path, monkeypatch):
    from experimental.curator.generation.run import GenerationError

    worker = Composite(tmp_path)
    root, child = await candidates(worker)
    proposals = Proposals(monkeypatch, root, child)
    failure = GenerationError("the child could not realise the requirement")
    failure.trace = ({"event": "report_gap", "reason": "missing input"}, {"event": "model.call"})
    proposals.failures.append(("child", failure))
    await curated(worker)
    assert [call["scope"] for call in proposals.calls] == ["root", "child", "root", "child"]
    observation = proposals.calls[2]["repair"].observations[0]
    assert observation["scope"] == "child/Hosted" and observation["nodes"] == ["work/step"]
    assert observation["evidence"] == [{"event": "report_gap", "reason": "missing input"}]
    assert len(worker.installed) == 1


@pytest.mark.asyncio
async def test_an_exhausted_repair_budget_keeps_the_failure_until_an_explicit_restart(tmp_path, monkeypatch):
    from experimental.curator.generation.run import GenerationError, Limits

    worker = Composite(tmp_path)
    root, child = await candidates(worker)
    proposals = Proposals(monkeypatch, root, child)
    worker.composition_errors.append("first failure")
    with pytest.raises(GenerationError, match="composite repair budget exhausted: composite validation failed: first"):
        await curated(worker, limits=Limits(max_repairs=0))
    checkpoint = worker.root / "curation/composition.json"
    assert "first failure" in json.loads(checkpoint.read_text())["error"]
    with pytest.raises(GenerationError, match="previous composite curation failed"):
        await curated(worker, limits=Limits(max_repairs=0))
    assert len(proposals.calls) == 2 and worker.installed == []
    await curated(worker, limits=Limits(max_repairs=0), resume=False)
    assert [call["scope"] for call in proposals.calls] == ["root", "child", "root", "child"]
    assert len(worker.installed) == 1 and not checkpoint.exists()
    assert sorted((record.get("error") for record in records_of(worker)), key=str) == [
        None,
        "composite repair budget exhausted: composite validation failed: first failure",
    ]


@pytest.mark.asyncio
async def test_a_paused_composition_resumes_in_a_new_worker_object_without_proposing_the_root_again(
    tmp_path, monkeypatch
):
    from experimental.curator.generation.run import GenerationPausedError
    from experimental.curator.generation.state import GenerationState

    worker = Composite(tmp_path)
    root, child = await candidates(worker)
    proposals = Proposals(monkeypatch, root, child)
    proposals.failures.append(("child", GenerationPausedError(GenerationState(input_id="x", stage="design", calls=2))))
    with pytest.raises(GenerationPausedError) as paused:
        await curated(worker)
    assert paused.value.state.stage == "design" and paused.value.state.calls == 4
    checkpoint = worker.root / "curation/composition.json"
    held = json.loads(checkpoint.read_text())
    assert json.loads(held["root"]["candidate"]["artifact"]["files"]["memory_profile.json"]) == {
        "TOOLS.md": "Root rules"
    }
    assert held["error"] is None and list(held["scopes"]) == ["Hosted"]
    (record,) = records_of(worker)
    assert record["paused"]["checkpoint"] == str(checkpoint) and record["paused"]["calls"] == 4
    assert (record["paused"]["stage"], record["paused"]["scope"]) == ("design", "child/Hosted")
    again = Composite(tmp_path)
    result = await curated(again, feedback=None, model=None)
    assert [call["scope"] for call in proposals.calls] == ["root", "child", "child"]
    assert proposals.calls[2]["feedback"]["feedback"] == {"text": "Train the child"}
    assert result.candidate == root and len(again.installed) == 1 and not checkpoint.exists()
    proposals.failures.append(("child", GenerationPausedError(GenerationState(input_id="x", calls=2))))
    with pytest.raises(GenerationPausedError):
        await curated(Composite(tmp_path))
    with pytest.raises(ValueError, match="composite inputs changed"):
        await curated(Composite(tmp_path), feedback={"text": "Something else"})
    assert checkpoint.exists()


@pytest.mark.asyncio
async def test_a_child_no_node_needs_any_more_is_withdrawn_to_its_original_artifact(tmp_path, monkeypatch):
    from experimental.curator.harness import Artifact

    served = {"work/step": {"playbook": "work", "node": {"subagent": "Hosted"}, "requirements": [REQUIREMENT]}}
    worker = Composite(tmp_path, nodes_now=served)
    from tests.fixtures.harness_curator.authoring import action

    initial, _ = await candidates(worker)
    worker.artifact = initial.artifact
    worker.children["Hosted"].artifact = action(generation={"temperature": 0.5})
    root, child = await candidates(worker, node_reasons={"work/step": "Retire the requirement"}, withdraw=True)
    proposals = Proposals(monkeypatch, root, child)
    result = await curated(worker)
    assert [call["scope"] for call in proposals.calls] == ["root"]
    assert worker.composition_checks == [{"Hosted": None}] and worker.installed == [(root, {"Hosted": None})]
    assert worker.children["Hosted"].artifact == worker.children["Hosted"].original == Artifact(values={})
    assert json.loads(worker.artifact.files["procedures.json"])[0]["requirements"] == {}
    assert [row["kind"] for row in result.validation.observations][-1] == "composition.activated"
    (record,) = records_of(worker)
    assert record["withdrawn_children"] == ["Hosted"] and record["child_changes"] == {}


@pytest.mark.asyncio
async def test_every_scope_attributes_on_its_own_and_every_record_reaches_the_worker(tmp_path, monkeypatch):
    from experimental.curator.attribution import ModelAttributor
    from experimental.curator.generation.run import GenerationError
    from experimental.curator.harness import Attribution
    from tests.test_harness_curator_generation import diagnosis

    worker = Composite(tmp_path)
    root, child = await candidates(worker)
    proposals = Proposals(monkeypatch, root, child)
    proposals.attributed = True
    proposals.failures.append(("child", GenerationError("the child could not realise the requirement")))
    attributor, supplied = ModelAttributor(model="diagnoser"), Attribution.model_validate(diagnosis())
    await curated(worker, attributor=attributor, attribution=supplied)
    assert [call["scope"] for call in proposals.calls] == ["root", "child", "root", "child"]
    assert all(call["attributor"] is attributor for call in proposals.calls)
    assert [call["attribution"] is supplied for call in proposals.calls] == [True, False, True, False]
    surfaced = sorted(path.name for path in (worker.root / "attribution").glob("*.json"))
    assert surfaced == ["child-2.json", "child-4.json", "root-1.json", "root-3.json"]
    (record,) = records_of(worker)
    assert record["attribution"] == "root-3.json" and record["attributor"] == {"implementation": "model"}
    assert record["budget"]["attribution"] == {"calls": 3, "queries": 6}


@pytest.mark.asyncio
async def test_attributing_a_composite_alone_sees_the_root_scope_and_records_beside_the_worker(tmp_path, monkeypatch):
    from experimental.curator import workflow
    from experimental.curator.composition import run as composition

    worker = Composite(tmp_path)
    seen = {}

    async def local(subject, provider, **options):
        seen["root"], seen["facts"], seen["options"] = subject.root, (await subject.inspect()).facts, options
        (subject.root / "attribution").mkdir(parents=True, exist_ok=True)
        (subject.root / "attribution" / "a.json").write_text("{}")
        return "attributed"

    monkeypatch.setattr(composition, "attribute_local", local)
    assert await workflow.attribute(worker, object(), feedback={"text": "Train"}, model="m") == "attributed"
    assert (
        set(seen["facts"]["composition"]) == {"nodes", "children"}
        and "Hosted" in seen["facts"]["composition"]["children"]
    )
    assert seen["root"] == worker.root / "curation" / composition.SCOPE / "root"
    assert seen["options"]["feedback"] == {"text": "Train"} and seen["options"]["model"] == "m"
    assert (worker.root / "attribution" / "a.json").is_file()
