"""Bind Curator domain evidence to shared admission and frozen, stage-specific guidance usage."""

from pathlib import Path

from experimental.experience import render
from experimental.experience.admission import AdmissionPolicy
from experimental.experience.contracts import GuidanceBundle, GuidanceItem
from experimental.experience.governance import Check, Decision, Experience, fingerprint
from experimental.experience.journal import GovernanceFile
from experimental.experience.records import RecordAccess
from experimental.experience.retrieve import ExperienceRetriever, GuidanceQuery
from experimental.experience.state import CandidateRef
from experimental.experience.store import ExperienceStore, StoreError

PHASES = ("diagnose", "select", "design", "implement", "repair")


class CuratorExperience:
    """The host owns source grants and adoption; the Curator receives only approved methods."""

    def __init__(
        self,
        store: ExperienceStore,
        policy: AdmissionPolicy,
        access: RecordAccess,
        *,
        journal=None,
        pipeline=None,
        verification=None,
    ):
        self.store, self.policy, self.access, self.pipeline = store, policy, access, pipeline
        self.verification = verification
        if verification is not None and (not hasattr(verification, "identity") or not hasattr(verification, "verify")):
            raise ValueError("an independent method verifier must expose its identity and verification operation")
        self.journal = journal or GovernanceFile(store.path.with_suffix(".governance.json"))
        self.reader = ExperienceRetriever(store, policy)

    @classmethod
    def from_provider(
        cls,
        directory,
        provider,
        *,
        access_scope: str,
        model=None,
        effort=None,
        blocked_text=(),
        migrate=False,
        verification=None,
        writable_roots=(),
    ):
        from experimental.experience.build import ExperiencePipeline
        from experimental.experience.builder import ModelExperienceBuilder
        from experimental.experience.critic import ModelExperienceCritic

        directory = Path(directory).resolve()
        if any(directory.is_relative_to(Path(root).resolve()) for root in writable_roots):
            raise ValueError("experience runtime storage must remain outside Worker writable areas")
        if any((parent / ".git").exists() for parent in (directory, *directory.parents)):
            raise ValueError("experience runtime storage must remain outside version control")
        builder = ModelExperienceBuilder(provider, model=model, effort=effort)
        critic = ModelExperienceCritic(provider, model=model, effort=effort)
        policy = AdmissionPolicy(critic_digest=fingerprint(critic.identity()))
        access = RecordAccess(
            access_scope=access_scope,
            blocked_text=tuple(blocked_text),
            fields=frozenset(
                {
                    "plan.understanding",
                    "plan.design",
                    "change.target",
                    "change.reason",
                    "change.treatment",
                    "requirement.behavior",
                    "requirement.observed",
                    "requirement.acceptance",
                    "feedback.reason",
                    "outcome.held",
                    "outcome.observations",
                }
            ),
        )
        store = ExperienceStore(directory / "curator.sqlite", migrate=migrate)
        try:
            owner = cls(
                store, policy, access, pipeline=ExperiencePipeline(store, builder, critic), verification=verification
            )
            owner.refresh()
        except BaseException:
            store.close()
            raise
        return owner

    def close(self):
        self.store.close()

    async def learn(self, record, *, origin, capabilities=(), contract_ids=()):
        from experimental.experience.learning import learn_record

        return await learn_record(self, record, origin=origin, capabilities=capabilities, contract_ids=contract_ids)

    async def outcome(self, reference, receipt, *, held_out):
        from experimental.experience.learning import observe_outcome

        return await observe_outcome(self, reference, receipt, held_out=held_out)

    def diagnose(self, issue, *, evidence):
        from experimental.experience.repair import diagnose

        return diagnose(self, issue, evidence=set(evidence))

    async def audit(self, snapshot, events):
        from experimental.experience.repair import audit

        return await audit(self, snapshot, tuple(events))

    async def repair(self, diagnosis, events, *, capabilities=(), contract_ids=()):
        from experimental.experience.repair import admit, propose

        result = await propose(self, diagnosis, tuple(events), capabilities=capabilities, contract_ids=contract_ids)
        if result["status"] == "candidate" and self.verification is not None:
            study = await self.verification.verify(self, result["candidate"])
            checked = admit(self, result["candidate"], study)
            return {**result, "status": "adopted" if checked["accepted"] else "candidate", "verification": checked}
        return result

    async def verify_repair(self, candidate, *, cases, evaluate, history=None, purpose="improvement", timeout=180):
        from experimental.experience.repair import verify

        return await verify(
            self, candidate, cases=cases, evaluate=evaluate, history=history, purpose=purpose, timeout=timeout
        )

    @property
    def identity(self):
        return fingerprint(
            {
                "scope": self.access.access_scope,
                "source_grant": self.access.identity,
                "verification": self.verification.identity() if self.verification is not None else None,
                "policy": self.policy.id,
                "rendering": render.version(),
                "store": str(self.store.path.resolve()),
                "journal": str(self.journal.path.resolve()),
            }
        )

    def _binding(self, reference: CandidateRef):
        return self.store.binding(self.access.access_scope, reference, self.policy)

    def _entry(self, binding):
        proposal = binding["proposal"]
        return Experience(
            domain="curator",
            scope=self.access.access_scope,
            content={
                "method": binding["reference"],
                "condition": proposal["condition"],
                "guidance": proposal["guidance"],
                "support_kind": proposal["support_kind"],
            },
            sources=binding["sources"],
        )

    def refresh(self) -> dict:
        from experimental.experience.repair import pending_methods, verified
        from experimental.experience.verification import VALIDATING

        if VALIDATING.get():
            active = self.journal.read().active("curator", self.access.access_scope)
            return {"eligible": list(active), "active": list(active)}

        self.store.refresh_admission(self.access.access_scope, self.policy)
        latest = {}
        for row in self.store.candidates(self.access.access_scope):
            latest[row["id"]] = row
        bindings = [self._binding(CandidateRef(id=row["id"], version=row["version"])) for row in latest.values()]

        def update(ledger):
            eligible = set()
            repairing = pending_methods(self, ledger)
            superseded = {
                row["experience"]["content"]["method"]["id"]
                for row in ledger.data["entries"].values()
                if row["experience"]["domain"] == "curator"
                and row["experience"]["scope"] == self.access.access_scope
                and row.get("reason") in {"superseded", "rolled_back"}
            }
            for binding in bindings:
                entry = self._entry(binding)
                if binding["reference"]["id"] in superseded:
                    continue
                previously_adopted = any(
                    not ledger.experience(id).replaces
                    and ledger.experience(id).content["method"]["id"] == binding["reference"]["id"]
                    for id in ledger.active("curator", self.access.access_scope)
                )
                if binding["reference"]["id"] in repairing and not previously_adopted:
                    for identity in ledger.active("curator", self.access.access_scope):
                        existing = ledger.experience(identity)
                        if (
                            existing.content == entry.content
                            and existing.sources == entry.sources
                            and verified(ledger, identity, binding, owner=self.identity)
                        ):
                            eligible.add(identity)
                    continue
                identity = ledger.propose(entry)
                assessment = binding["assessment"]
                if assessment["status"] == "supported":
                    eligible.add(identity)
                    if ledger.data["entries"][identity]["state"] == "candidate":
                        receipt = fingerprint(binding)
                        ledger.decide(
                            Decision(
                                candidate=identity,
                                baseline=ledger.version(entry.domain, entry.scope),
                                policy=self.policy.id,
                                context=receipt,
                                checks=tuple(
                                    Check(
                                        name=name,
                                        result="pass",
                                        evidence=(receipt,),
                                        reason="Scoped domain evidence; no broader outcome claim is granted.",
                                    )
                                    for name in ("grounding", "applicability", "effect")
                                ),
                            )
                        )
            for identity in ledger.active("curator", self.access.access_scope):
                if identity not in eligible:
                    ledger.deactivate(identity, reason="domain_evidence_changed", evidence=(self.policy.id,))
            return {"eligible": sorted(eligible), "active": list(ledger.active("curator", self.access.access_scope))}

        return self.journal.update(update)

    def _registered(self, item: GuidanceItem, ledger):
        from experimental.experience.repair import verified

        binding = self._binding(CandidateRef(id=item.id, version=item.version))
        if not binding["current"]:
            raise StoreError("the Curator experience no longer has current independent support")
        entry = self._entry(binding)
        for identity in ledger.active("curator", self.access.access_scope):
            active = ledger.experience(identity)
            if active.content == entry.content and active.sources == entry.sources:
                if active.replaces and verified(ledger, identity, binding, owner=self.identity):
                    return identity
                if not active.replaces and binding["assessment"]["status"] == "supported":
                    return identity
        raise StoreError("the Curator method has not passed shared admission")

    def _available(self, query, ledger):
        from experimental.experience.retrieve import _relevance

        items = {}
        for _, _, item in self.reader._items(query):
            try:
                self._registered(item, ledger)
            except StoreError:
                continue
            items[item.id] = item
        for identity in ledger.active("curator", self.access.access_scope):
            entry = ledger.experience(identity)
            if not entry.replaces:
                continue
            content = entry.content
            item = GuidanceItem(
                **content["method"],
                condition=content["condition"],
                guidance=content["guidance"],
                support_kind=content["support_kind"],
                evidence_refs=("evidence-" + identity,),
            )
            if _relevance(item, query) is not None:
                try:
                    self._registered(item, ledger)
                except StoreError:
                    continue
                items.setdefault(item.id, item)
        return tuple(items.values())

    def _validate_bundle(self, bundle, query, ledger):
        from experimental.experience.retrieve import _bundle, export_bundle

        if bundle.snapshot_id != _bundle(bundle.items).snapshot_id or len(export_bundle(bundle)) > 8192:
            raise StoreError("the guidance payload or its export limits changed")
        available = {item.id: item for item in self._available(query, ledger)}
        if any(available.get(item.id) != item for item in bundle.items):
            raise StoreError("guidance evidence, review, scope or version is no longer eligible")

    def prepare(
        self,
        *,
        task: str,
        situation: str,
        inputs: str,
        scope_kind="root",
        capabilities=(),
        contract_ids=(),
        mechanism_states=(),
        worker_root=None,
        workspace_root=None,
        previous=None,
    ) -> dict:
        for writable in (worker_root, workspace_root):
            if writable is None:
                continue
            root = Path(writable).resolve()
            if any(path.resolve().is_relative_to(root) for path in (self.store.path, self.journal.path)):
                raise ValueError("experience storage must remain outside the Worker writable area")
        for path in (self.store.path, self.journal.path):
            if any((parent / ".git").exists() for parent in path.resolve().parents):
                raise ValueError("experience runtime storage must remain outside version control")
        request = {
            "situation": situation,
            "scope_kind": scope_kind,
            "capabilities": list(capabilities),
            "contract_ids": list(contract_ids),
            "mechanism_states": list(mechanism_states),
        }
        if previous is not None:
            if previous.get("request") != request or previous.get("task") != task:
                raise ValueError("the frozen experience request or task changed")
            self.validate(previous, inputs=inputs)
            return previous
        queries = {
            phase: GuidanceQuery(
                access_scope=self.access.access_scope,
                situation=situation,
                phase=phase,
                scope_kind=scope_kind,
                capabilities=tuple(capabilities),
                contract_ids=tuple(contract_ids),
                mechanism_states=tuple(mechanism_states),
            )
            for phase in PHASES
        }
        choices = {}
        remaining, size = 4, 0
        current = self.journal.read()
        for phase, query in queries.items():
            offered = self._available(query, current)
            selected = []
            for item in offered:
                if remaining == 0:
                    break
                try:
                    self._registered(item, current)
                except StoreError:
                    continue
                proposed = [*selected, item]
                from experimental.experience.retrieve import _bundle, export_bundle

                if len(export_bundle(_bundle(tuple(proposed)))) > 8192:
                    continue
                text = render.guidance(
                    [
                        {"id": row.id, "scope": self.access.access_scope, **row.model_dump(exclude={"id"})}
                        for row in proposed
                    ]
                )
                prior = render.guidance(
                    [
                        {"id": row.id, "scope": self.access.access_scope, **row.model_dump(exclude={"id"})}
                        for row in selected
                    ]
                )
                extra = len(text.encode()) - len(prior.encode())
                if size + extra > 8192:
                    continue
                selected = proposed
                remaining -= 1
                size += extra
            if selected:
                from experimental.experience.retrieve import _bundle

                choices[phase] = (query, _bundle(tuple(selected)))

        def capture(ledger):
            stages = {}
            for phase, (query, bundle) in choices.items():
                self._validate_bundle(bundle, query, ledger)
                identities = tuple(self._registered(item, ledger) for item in bundle.items)
                text = render.guidance(
                    [
                        {"id": row.id, "scope": self.access.access_scope, **row.model_dump(exclude={"id"})}
                        for row in bundle.items
                    ]
                )
                usage = ledger.capture(
                    domain="curator",
                    scope=self.access.access_scope,
                    task=task,
                    phase=phase,
                    inputs=inputs,
                    policy=self.policy.id,
                    identities=identities,
                    text=text,
                    rendering=render.version(),
                )
                stages[phase] = {
                    "query": query.model_dump(mode="json"),
                    "bundle": bundle.model_dump(mode="json"),
                    "usage": usage,
                }
            snapshot = {"owner": self.identity, "inputs": inputs, "task": task, "request": request, "stages": stages}
            snapshot = {"id": fingerprint(snapshot), **snapshot}
            if not any(row.get("curator_usage") == snapshot for row in ledger.data["decisions"]):
                ledger.data["decisions"].append({"curator_usage": snapshot})
            return snapshot

        return self.journal.update(capture)

    def validate(self, snapshot: dict, *, inputs: str) -> None:
        content = {key: value for key, value in snapshot.items() if key != "id"}
        if (
            snapshot.get("id") != fingerprint(content)
            or snapshot.get("owner") != self.identity
            or snapshot.get("inputs") != inputs
        ):
            raise ValueError("the frozen Curator experience inputs or owner changed")
        ledger = self.journal.read()
        if not any(row.get("curator_usage") == snapshot for row in ledger.data["decisions"]):
            raise ValueError("the Curator usage was not recorded by the host")
        for phase, stage in snapshot["stages"].items():
            if phase not in PHASES or stage["usage"]["phase"] != phase:
                raise ValueError("the experience belongs to another Curator stage")
            query = GuidanceQuery.model_validate(stage["query"])
            bundle = GuidanceBundle.model_validate(stage["bundle"])
            self._validate_bundle(bundle, query, ledger)
            for item in bundle.items:
                self._registered(item, ledger)
            ledger.validate_use(
                stage["usage"],
                domain="curator",
                scope=self.access.access_scope,
                inputs=inputs,
                policy=self.policy.id,
                rendering=render.version(),
            )

    def provider(self, provider, snapshot, loaded: set[str]):
        expected = {
            f"Experience usage {stage['usage']['id']}\n\n{stage['usage']['text']}": stage["usage"]["id"]
            for stage in snapshot["stages"].values()
        }

        class Observed:
            def __getattr__(self, name):
                return getattr(provider, name)

            async def chat_with_retry(self, **kwargs):
                for message in kwargs.get("messages", ()):
                    if message.get("role") == "user" and isinstance(message.get("content"), str):
                        identity = expected.get(message["content"])
                        if identity is not None:
                            loaded.add(identity)
                return await provider.chat_with_retry(**kwargs)

        return Observed()

    def observe(self, snapshot: dict, *, record: str, loaded=()) -> None:
        def append(ledger):
            for stage in snapshot["stages"].values():
                ledger.observe(
                    stage["usage"]["id"],
                    evidence=record,
                    result="unknown",
                    note=(
                        "Guidance was loaded; the execution record must establish whether it was applied."
                        if stage["usage"]["id"] in loaded
                        else "Guidance was not loaded into a model request in this attempt."
                    ),
                )

        self.journal.update(append)


def stage_guidance(snapshot: dict | None, stage: str) -> dict | None:
    if not snapshot or stage not in snapshot.get("stages", {}):
        return None
    use = snapshot["stages"][stage]["usage"]
    return {"snapshot": snapshot["id"], "usage": use["id"], "text": use["text"]}
