"""Prepared native content preserves outside edits, exact originals and withdrawal semantics."""

from types import SimpleNamespace

import pytest

from experimental.curator.raven_adapter.content import ContentInstallation
from experimental.curator.raven_adapter.observe import Recorder
from experimental.curator.raven_adapter.preparation import PreparedHarness


def install(tmp_path, files):
    home, root = tmp_path / "home", tmp_path / "runtime"
    home.mkdir(exist_ok=True)
    root.mkdir(exist_ok=True)
    transaction = ContentInstallation(
        home, root, PreparedHarness(content={"memory": files}), Recorder(root / "records.jsonl")
    )
    transaction.apply()
    return transaction


def test_untouched_prepared_files_can_be_revised_and_withdrawn(tmp_path):
    first = install(tmp_path, {"TOOLS.md": "first", "agent_memory/profile/soul.md": "retained"})
    second = install(tmp_path, {"TOOLS.md": "second", "agent_memory/profile/soul.md": "retained"})
    assert (first.home / "TOOLS.md").read_text() == "second"
    install(tmp_path, {})
    assert not (first.home / "TOOLS.md").exists()
    assert not (first.home / "agent_memory/profile/soul.md").exists()
    assert second.saved[first.home / "TOOLS.md"][0] == b"first"


def test_an_outside_edit_is_relinquished_and_survives_restart_and_withdrawal(tmp_path):
    first = install(tmp_path, {"TOOLS.md": "generated", "agent_memory/profile/soul.md": "retained"})
    path = first.home / "TOOLS.md"
    path.write_text("The owner's corrected rules")
    held = install(tmp_path, {"TOOLS.md": "generated", "agent_memory/profile/soul.md": "retained"})
    assert "TOOLS.md" not in held.prepared.files()
    install(tmp_path, {"TOOLS.md": "generated", "agent_memory/profile/soul.md": "retained"})
    install(tmp_path, {})
    assert path.read_text() == "The owner's corrected rules"


def test_a_revised_proposal_cannot_overwrite_an_outside_editor(tmp_path):
    first = install(tmp_path, {"TOOLS.md": "generated"})
    path = first.home / "TOOLS.md"
    path.write_text("Human change")
    with pytest.raises(ValueError, match="outside editor"):
        install(tmp_path, {"TOOLS.md": "revised generated rules"})
    assert path.read_text() == "Human change"


def test_rollback_restores_prior_ledger_and_the_exact_previous_revision(tmp_path):
    first = install(tmp_path, {"TOOLS.md": "first"})
    ledger = first.path.read_bytes()
    second = install(tmp_path, {"TOOLS.md": "second", "agent_memory/profile/soul.md": "new"})
    second.rollback()
    assert first.path.read_bytes() == ledger
    assert (first.home / "TOOLS.md").read_text() == "first"
    assert not (first.home / "agent_memory/profile/soul.md").exists()
    install(tmp_path, {})
    assert not (first.home / "TOOLS.md").exists()


def test_withdrawal_restores_original_symlink_and_file_permissions(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    original = tmp_path / "original.md"
    original.write_text("Original shared profile")
    (home / "TOOLS.md").symlink_to(original)
    executable = home / "run.sh"
    executable.write_text("Original script")
    executable.chmod(0o755)
    install(tmp_path, {"TOOLS.md": "Owned profile", "run.sh": "Owned script"})
    assert not (home / "TOOLS.md").is_symlink()
    assert executable.stat().st_mode & 0o777 == 0o755
    install(tmp_path, {})
    assert (home / "TOOLS.md").is_symlink()
    assert executable.read_text() == "Original script"
    assert executable.stat().st_mode & 0o777 == 0o755


def test_content_cannot_write_through_an_escaping_parent(tmp_path):
    home, outside = tmp_path / "home", tmp_path / "outside"
    home.mkdir()
    outside.mkdir()
    (home / "agent_memory").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes"):
        install(tmp_path, {"agent_memory/profile/soul.md": "Unexpected write"})
    assert not list(outside.rglob("*"))


def test_prepared_playbooks_require_a_real_native_consumer():
    from experimental.curator.raven_adapter.bind import _verify_playbooks

    runtime = SimpleNamespace(loop=SimpleNamespace(_playbooks=SimpleNamespace(names=lambda: ["plan-delivery"])))
    _verify_playbooks(runtime, PreparedHarness(content={"planning": {"playbooks/plan-delivery/playbook.md": "spec"}}))
    with pytest.raises(ValueError, match="was not loaded"):
        _verify_playbooks(runtime, PreparedHarness(content={"planning": {"playbooks/missing/playbook.md": "spec"}}))


def test_a_playbook_that_did_not_load_is_reported_with_the_loaders_own_reason(tmp_path):
    from experimental.curator.raven_adapter.bind import _verify_playbooks
    from raven.playbook.store import PlaybookStore

    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "playbook.md").write_text(
        "---\nname: broken\ndescription: A procedure.\n---\n\n```yaml playbook-spec\naction: go\n```\n"
    )
    (tmp_path / "bare").mkdir()
    (tmp_path / "bare" / "playbook.md").write_text("A procedure without frontmatter.\n")
    library = SimpleNamespace(names=lambda: [], store=PlaybookStore(tmp_path), _known_agents=lambda: None)
    runtime = SimpleNamespace(loop=SimpleNamespace(_playbooks=library))
    for name, reason in (("broken", "ValidationError.*action"), ("bare", "no frontmatter")):
        prepared = PreparedHarness(content={"planning": {f"playbooks/{name}/playbook.md": "spec"}})
        with pytest.raises(ValueError, match=f"(?s)was not loaded: {name}/playbook.md: .*{reason}"):
            _verify_playbooks(runtime, prepared)
    disabled = SimpleNamespace(loop=SimpleNamespace(_playbooks=None))
    with pytest.raises(ValueError, match="library is not enabled"):
        _verify_playbooks(disabled, PreparedHarness(content={"planning": {"playbooks/broken/playbook.md": "spec"}}))
