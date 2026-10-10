"""Exercise cross-role admission, attributed changes and invalidation of actual usage snapshots."""

import pytest

from experimental.harness.experience.governance import Check, Decision, Diagnosis, Experience, Governance


def proposal(text="Check the actual consumer.", *, domain="curator", **kwargs):
    return Experience(domain=domain, scope="project", content={"text": text}, sources={"episode": "v1"}, **kwargs)


def verdict(ledger, entry, *, result="pass", policy="policy-1"):
    return Decision(
        candidate=entry.id,
        baseline=ledger.version(entry.domain, entry.scope),
        policy=policy,
        context="frozen-comparison",
        checks=tuple(
            Check(name=name, result=result if name == "effect" else "pass", evidence=("independent-record",))
            for name in ("grounding", "applicability", "effect")
        ),
    )


def activate(ledger, entry):
    ledger.propose(entry)
    assert ledger.decide(verdict(ledger, entry))


def correction(ledger, target, *, fields=("content.text",), cause="content"):
    return ledger.diagnose(
        Diagnosis(
            target=target.id,
            baseline=ledger.version(target.domain, target.scope),
            cause=cause,
            evidence=("observed-wrong-consumer",),
            reason="The method missed a second consumer.",
            fields=fields,
        )
    )


def test_unknown_or_partial_review_cannot_publish_guidance_for_either_role():
    ledger = Governance()
    for domain in ("curator", "rubric"):
        entry = proposal(domain=domain)
        ledger.propose(entry)
        assert not ledger.decide(verdict(ledger, entry, result="unknown"))
        assert not ledger.active(domain, "project")
        incomplete = verdict(ledger, entry).model_copy(
            update={"checks": (Check(name="grounding", result="pass", evidence=("review",)),)}
        )
        assert not ledger.decide(incomplete)
        assert ledger.decide(verdict(ledger, entry))
        assert ledger.active(domain, "other-project") == ()
    assert len(ledger.active("curator", "project")) == len(ledger.active("rubric", "project")) == 1


def test_evidence_is_required_even_for_host_checks():
    with pytest.raises(ValueError, match="inspectable evidence"):
        Check(name="effect", result="pass")


def test_diagnosed_scope_prevents_incidental_edits_and_stale_adoption():
    ledger = Governance()
    first, unrelated = proposal(), proposal("Preserve external requirements.")
    activate(ledger, first)
    activate(ledger, unrelated)
    diagnosis = correction(ledger, first)
    revised = proposal("Check both consumers.", replaces=(first.id,), diagnoses=(diagnosis,))
    with pytest.raises(ValueError, match="exceeds"):
        ledger.propose(
            revised.model_copy(update={"content": {"text": "Check both consumers.", "disable_checks": None}})
        )
    ledger.propose(revised)
    accepted = verdict(ledger, revised)
    ledger.deactivate(unrelated.id, reason="contradiction", evidence=("new-run",))
    with pytest.raises(ValueError, match="obsolete"):
        ledger.decide(accepted)
    assert ledger.active("curator", "project") == (first.id,)


def test_loading_failure_cannot_authorize_rewriting_correct_experience():
    ledger = Governance()
    entry = proposal()
    activate(ledger, entry)
    with pytest.raises(ValueError, match="does not authorize"):
        correction(ledger, entry, cause="loading")
    issue = correction(ledger, entry, cause="loading", fields=())
    with pytest.raises(ValueError, match="exceeds"):
        ledger.propose(proposal("Unnecessary rewriting.", replaces=(entry.id,), diagnoses=(issue,)))


def test_merge_requires_individual_permissions_and_preserves_other_experience():
    ledger = Governance()
    first, second, other = proposal(), proposal("Check all consumers."), proposal("Preserve task requirements.")
    for entry in (first, second, other):
        activate(ledger, entry)
    issues = tuple(correction(ledger, entry) for entry in (first, second))
    merged = proposal("Inspect every actual consumer.", replaces=(first.id, second.id), diagnoses=issues)
    with pytest.raises(ValueError, match="every revised"):
        ledger.propose(merged.model_copy(update={"diagnoses": issues[:1]}))
    ledger.propose(merged)
    assert not ledger.decide(verdict(ledger, merged, result="fail"))
    assert set(ledger.active("curator", "project")) == {first.id, second.id, other.id}
    assert ledger.decide(verdict(ledger, merged))
    assert set(ledger.active("curator", "project")) == {merged.id, other.id}


def test_saved_usage_is_role_bound_and_revocation_invalidates_resume():
    ledger = Governance()
    entry = proposal()
    activate(ledger, entry)
    arguments = dict(
        domain="curator",
        scope="project",
        task="task-1",
        phase="diagnose",
        inputs="input-1",
        policy="policy-1",
        identities=(entry.id,),
        text="The actual delivered method.",
        rendering="render-1",
    )
    snapshot = ledger.capture(**arguments)
    restored = Governance(ledger.record())
    expected = {key: arguments[key] for key in ("domain", "scope", "inputs", "policy", "rendering")}
    restored.validate_use(snapshot, **expected)
    with pytest.raises(ValueError, match="changed"):
        restored.validate_use({**snapshot, "text": "An unverified method."}, **expected)
    with pytest.raises(ValueError, match="consumer"):
        restored.validate_use(snapshot, **{**expected, "domain": "rubric"})
    restored.observe(snapshot["id"], evidence="trace-1", result="unknown", note="Loaded, application not established.")
    restored.revoke("episode", "v1", reason="Source was corrected.")
    with pytest.raises(ValueError, match="withdrawn"):
        restored.validate_use(snapshot, **expected)


def test_a_withdrawn_method_can_be_repaired_but_its_source_cannot_be_laundered():
    ledger = Governance()
    old = proposal()
    activate(ledger, old)
    ledger.deactivate(old.id, reason="contradiction", evidence=("counterexample",))
    issue = correction(ledger, old)
    new = proposal("Check the actual target and its consumers.", replaces=(old.id,), diagnoses=(issue,))
    activate(ledger, new)
    ledger.revoke("episode", "v1", reason="The observations were retracted.")
    assert ledger.active("curator", "project") == ()
    with pytest.raises(ValueError, match="current active"):
        ledger.rollback(
            new.id,
            baseline=ledger.version("curator", "project"),
            policy="policy-1",
            applicability=Check(name="applicability", result="pass", evidence=("context",)),
        )


def test_loading_cannot_forge_active_status_without_an_admission():
    ledger = Governance()
    entry = proposal()
    ledger.propose(entry)
    changed = ledger.record()
    changed["entries"][entry.id]["state"] = "active"
    with pytest.raises(ValueError, match="lacks an exact"):
        Governance(changed)
    changed = ledger.record()
    changed["entries"][entry.id]["experience"]["content"]["text"] = "Changed without review."
    with pytest.raises(ValueError, match="immutable identity"):
        Governance(changed)
