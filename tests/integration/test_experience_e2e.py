"""Exercise durable retrieval across processes and admission of archived real-model candidates."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from experimental.harness.experience.admission import AdmissionPolicy
from experimental.harness.experience.contracts import digest
from experimental.harness.experience.retrieve import ExperienceRetriever, GuidanceQuery
from experimental.harness.experience.store import ExperienceStore, StoreError
from tests.experience_helpers import event, reviewed

pytestmark = pytest.mark.integration


def query(scope="project"):
    return GuidanceQuery(
        access_scope=scope,
        situation="The actual consumer did not consume a mechanism result.",
        phase="design",
        scope_kind="root",
    )


def test_revocation_from_another_process_invalidates_a_live_readers_guidance(tmp_path):
    path = tmp_path / "experience.sqlite"
    policy = AdmissionPolicy(critic_digest=digest({"rule": "test-critic"}))
    with ExperienceStore(path) as store:
        reviewed(store, (event("one"),))
        reviewed(store, (event("two"),))
        store.refresh_admission("project", policy)
        reader = ExperienceRetriever(store, policy)
        bundle = reader.retrieve(query())
        assert bundle.items
        script = """from pathlib import Path
import sys
from experimental.harness.experience.store import ExperienceStore
with ExperienceStore(Path(sys.argv[1])) as store:
    store.revoke_event('project', sys.argv[2], expected_version=1)
"""
        subprocess.run([sys.executable, "-c", script, str(path), event("one").view.reference], check=True, timeout=30)
        assert not reader.retrieve(query()).items
        with pytest.raises(StoreError, match="no longer eligible"):
            reader.validate(bundle, query())


def test_archived_real_model_candidates_preserve_unknown_effects_after_migration(tmp_path):
    location = os.environ.get("EXPERIENCE_TEST_ARCHIVE")
    if not location:
        pytest.skip("Set EXPERIENCE_TEST_ARCHIVE to the approved real-model archive directory.")
    root = Path(location).resolve()
    report = json.loads((root / "validation.json").read_text())
    path = tmp_path / "experience.sqlite"
    shutil.copyfile(root / "experience.sqlite", path)
    with ExperienceStore(path, migrate=True) as store:
        row = store.connection.execute("SELECT scope,identities FROM candidates LIMIT 1").fetchone()
        assert row is not None
        scope = row["scope"]
        policy = AdmissionPolicy(critic_digest=digest(json.loads(row["identities"])["critic"]))
        assessments = store.refresh_admission(scope, policy)
        assert len(assessments) == len(report["candidates"]) > 0
        assert all(assessment.status == "candidate" for assessment in assessments)
        assert not ExperienceRetriever(store, policy).retrieve(query(scope)).items
        summary = {
            "candidates": len(assessments),
            "recommended": 0,
            "assessments": [assessment.model_dump() for assessment in assessments],
        }
        (tmp_path / "archive-admission.json").write_text(json.dumps(summary, indent=2))
