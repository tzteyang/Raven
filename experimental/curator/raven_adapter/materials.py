"""Stage and describe complete input packages before Curator decides whether to adopt them."""

from pathlib import Path

from .capability.catalog import inspect_package, materialize_tree, package_digest, package_files


def stage_skill_package(source: Path, agent_home: Path) -> dict:
    """Copy a pinned package into uploads; staging never makes it a runtime skill."""
    files = package_files(Path(source))
    digest = package_digest(files)
    destination = Path(agent_home) / "uploads" / f"skill-{digest}"
    materialize_tree(files, destination)
    result = inspect_package(destination)
    result["root"] = destination.relative_to(agent_home).as_posix()
    result["entry"] = f"upload.{destination.relative_to(Path(agent_home) / 'uploads').as_posix()}/SKILL.md"
    return result


def skill_package_inputs(agent_home: Path) -> list[dict]:
    """Expose actual package manifests and errors without installing or rewriting input bytes."""
    uploads = Path(agent_home) / "uploads"
    if not uploads.is_dir():
        return []
    result = []
    for entry in sorted(uploads.rglob("SKILL.md")):
        root = entry.parent
        if root.name.startswith(".staging-"):
            continue
        relative = root.relative_to(agent_home).as_posix()
        try:
            inspected = inspect_package(root)
            result.append(
                {
                    **inspected,
                    "root": relative,
                    "entry": f"upload.{entry.relative_to(uploads).as_posix()}",
                }
            )
        except (ValueError, OSError, UnicodeError) as exc:
            result.append({"root": relative, "error": str(exc)})
    return result
