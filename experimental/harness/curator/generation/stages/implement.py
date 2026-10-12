"""Expand selected strategy contracts and parse their factory bindings and supporting assets."""

import json
import re
from difflib import SequenceMatcher
from importlib.util import find_spec

from pydantic import BaseModel, ConfigDict, Field

from experimental.harness.contract import Artifact, Candidate, Declaration, Plan
from experimental.harness.contract.artifact import ArtifactPath, Selection
from experimental.harness.contract.commitments import active, apply, check_artifact
from experimental.harness.contract.declaration import parse_as, schema_for
from experimental.harness.curator.generation.context.collect import Context
from experimental.harness.curator.generation.context.render import tool
from experimental.harness.curator.generation.stages import design
from experimental.harness.participation import audience

NAME = "submit_artifact"
STAGE_FILE = "stage_file"
EDIT_FILE = "edit_file"
STAGE_SOURCE = "stage_source"


class StagedFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: ArtifactPath
    content: str


class FileEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: ArtifactPath
    old: str = Field(min_length=1, description="An exact excerpt of the current file that occurs exactly once.")
    new: str = Field(description="Its replacement; empty deletes the excerpt.")


def stage_tool() -> dict:
    return tool(
        STAGE_FILE,
        "Write one complete supporting file of the authored package, such as a Python module, one file per call; "
        "keep each file to a few hundred lines and split a larger module so each call fits the output limit. "
        "Every staged file is added to the artifact you submit or check; a file you also put in the artifact's "
        "files replaces the staged copy. Staging a path again replaces it.",
        schema_for(StagedFile),
    )


def parse_staged(arguments) -> StagedFile:
    return parse_as(StagedFile, arguments)


def edit_tool() -> dict:
    return tool(
        EDIT_FILE,
        "Change part of one existing file of the authored package by replacing an exact excerpt that occurs once. "
        "The edit applies to the staged copy, or during repair to the submitted candidate's copy, or else to the "
        "installed file, and the result is staged like a file written with stage_file.",
        schema_for(FileEdit),
    )


class StagedSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, description="A registered source, by the name `sources` lists it under.")
    path: ArtifactPath


def stage_source_tool() -> dict:
    return tool(
        STAGE_SOURCE,
        "Copy one registered source, such as a handed-over material, whole into the authored package at `path`, "
        "as if its text had been written with stage_file; nothing of it passes through your output.",
        schema_for(StagedSource),
    )


def parse_staged_source(arguments) -> StagedSource:
    return parse_as(StagedSource, arguments)


def edit(arguments, bases) -> tuple[str, str]:
    """The path and new content of an edit, from the first of `bases` (path to content mappings) that has the file."""
    change = parse_as(FileEdit, arguments)
    base = next((files[change.path] for files in bases if change.path in files), None)
    if base is None:
        raise ValueError(f"{change.path} is neither staged nor authored; write a new file with stage_file")
    count = base.count(change.old)
    if count != 1:
        raise ValueError(
            f"the excerpt occurs {count} times in {change.path}; quote a longer excerpt that occurs exactly once"
        )
    return change.path, base.replace(change.old, change.new, 1)


def commitments_after(context: Context, plan: Plan) -> list:
    """The current commitments once the plan's changes apply, as the Curator may read them."""
    return audience.project(active(apply(context.commitments, plan.commitments)), "curator")


def materials(context: Context, selection: Selection, plan: Plan) -> dict:
    """What implementation adds: the selection, its contracts, the checked plan and the commitments the selected
    surfaces' code must carry out once the plan applies."""
    return {
        **design.materials(context, selection),
        "plan": plan.model_dump(mode="json"),
        "commitments_after": commitments_after(context, plan),
    }


def output() -> dict:
    """The artifact submission for the shared tool list; its schema is the general artifact shape."""
    return tool(
        NAME,
        "Submit strategy bindings and supporting code/assets for exactly the planned targets.",
        schema_for(Artifact),
    )


_REFERENCE = re.compile(r"^([A-Za-z_][\w.]*):[A-Za-z_]\w*$")


def _references(value):
    if isinstance(value, str):
        if match := _REFERENCE.match(value):
            yield match.group(1)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _references(item)
    elif isinstance(value, list):
        for item in value:
            yield from _references(item)


def _module_files(module: str) -> tuple[str, str]:
    """The package files that can provide `module`."""
    path = module.replace(".", "/")
    return f"{path}.py", f"{path}/__init__.py"


def missing_modules(values: dict, files) -> list[str]:
    """Modules that values reference as module:attribute but that no file provides and nothing installed supplies."""
    missing = []
    for module in dict.fromkeys(_references(values)):
        if any(path in files for path in _module_files(module)):
            continue
        try:
            installed = find_spec(module.split(".")[0]) is not None
        except (ImportError, ValueError):
            installed = False
        if not installed:
            missing.append(module)
    return missing


def parse(
    declaration: Declaration, plan: Plan, arguments: dict, staged=None, authored=(), commitments=(), edited=()
) -> Candidate:
    """`staged` files join the artifact's own files, which take precedence except over a file changed with
    `edit_file` (`edited`), whose resubmission is refused; `authored` names files already installed.

    A value referencing a module that neither these files nor an installed package provide is refused here, before
    it can cost a validation round, and so is an artifact that disagrees with the commitment list it will run under
    (`commitments`, the current list, to which the plan's changes apply)."""
    if isinstance(arguments, dict):
        arguments = dict(arguments)
        for field in ("values", "files"):
            value = arguments.get(field)
            if isinstance(value, str):
                try:
                    decoded = json.loads(value)
                except ValueError:
                    continue
                if isinstance(decoded, dict):
                    arguments[field] = decoded
        files = arguments.get("files")
        files = files if isinstance(files, dict) else {}
        overriding = sorted(set(edited) & set(files))
        if overriding:
            raise ValueError(
                f"{overriding} were changed with edit_file; leave them out of the artifact's files, which would "
                "replace the edited copy"
            )
        if staged:
            arguments["files"] = {**staged, **files}
    candidate = declaration.accept(plan, arguments)
    check_artifact(
        apply(commitments, plan.commitments), valued=candidate.artifact.values, removed=candidate.artifact.remove
    )
    missing = missing_modules(dict(candidate.artifact.values), {*candidate.artifact.files, *authored})
    if missing:
        raise ValueError(
            f"values reference {', '.join(repr(m) for m in missing)}, but no such module is staged, in the "
            "artifact's files or already authored; stage each module's complete source with stage_file "
            f"(for example path '{missing[0].replace('.', '/')}.py') and submit again"
        )
    return candidate


def changes(authored: dict, candidate: Candidate) -> list[dict]:
    """How the candidate changes the files the Harness already has: lines kept, removed and added against the
    installed text, and the unselected targets whose bindings name a changed module directly."""
    installed = authored.get("files") or {}
    selected = {change.target for change in candidate.plan.changes}
    users = {}
    for target, value in (authored.get("values") or {}).items():
        if target not in selected:
            for module in _references(value):
                for path in _module_files(module):
                    users.setdefault(path, set()).add(target)
    rows = []
    for path, text in sorted(candidate.artifact.files.items()):
        if path not in installed or installed[path] == text:
            continue
        old, new = installed[path].splitlines(), text.splitlines()
        kept = sum(block.size for block in SequenceMatcher(None, old, new, autojunk=False).get_matching_blocks())
        rows.append({"path": path, "kept": kept, "removed": len(old) - kept, "added": len(new) - kept})
    for path in candidate.artifact.remove_files:
        if path in installed:
            rows.append({"path": path, "kept": 0, "removed": len(installed[path].splitlines()), "added": 0})
    for row in rows:
        if row["path"] in users:
            row["used_by_unselected"] = sorted(users[row["path"]])
    return rows
