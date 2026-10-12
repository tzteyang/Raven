"""Keep the native workspace Skill baseline separate from later working-file writes."""

import shutil
import tempfile
from pathlib import Path


def bind_workspace_skills(runtime, root: Path) -> Path:
    """Pin the initially granted workspace library for this experimental deployment.

    New workspace files remain materials until Curator adopts them through
    Capability. Revisions and copied checks reuse the host's original library;
    restarting cannot silently promote files written by a worker turn.
    """
    service = runtime.loop.context.skills
    registry = service.registry
    source = registry.workspace_skills
    destination = root / "baseline-skills"
    if not destination.exists():
        staged = Path(tempfile.mkdtemp(prefix=".baseline-skills-", dir=root))
        try:
            if source.exists():
                shutil.copytree(source, staged, dirs_exist_ok=True)
            staged.rename(destination)
        finally:
            if staged.exists():
                shutil.rmtree(staged)
    service.stop_file_watcher()
    registry.workspace_skills = destination
    registry.invalidate_cache()
    return destination
