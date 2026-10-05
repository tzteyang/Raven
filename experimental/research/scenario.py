"""Project actually released Scenario inputs into shared information preparation."""

import shutil
from pathlib import Path

from ..iteration.compartment import Guard
from ..iteration.hearing import heard
from ..iteration.protocols import Handover, Signal
from ..scenario import Scenario
from ..scenario.sealed import sealed_for
from .curator import collect_for_curator, handover_information
from .information import Request


def released_materials(scenario: Scenario, released) -> dict:
    names = tuple(dict.fromkeys(released))
    unknown = set(names) - scenario.materials.keys()
    if unknown:
        raise ValueError(f"unknown released materials: {sorted(unknown)}")
    for name in names:
        if not {"partner", "curator"} <= scenario.materials[name].visibility:
            raise ValueError(f"material is not available for expert preparation: {name}")
    return {name: scenario.materials[name] for name in names}


def stage_released(scenario: Scenario, released, home: Path) -> tuple[Path, ...]:
    """Stage only the selected release, without exporting or rewriting a Scenario."""
    paths = []
    for name, material in released_materials(scenario, released).items():
        if material.path.is_symlink() or any(path.is_symlink() for path in material.path.rglob("*")):
            raise ValueError("released material must not contain symbolic links")
        target = Path(home) / "uploads" / name
        if target.exists():
            raise ValueError(f"release destination already exists: {target}")
        shutil.copytree(material.path, target)
        paths.append(target)
    return tuple(paths)


def release_guard(scenario, released, *, log=None):
    """Keep later-disclosed material sealed during preparation of an earlier release."""
    selected = released_materials(scenario, released)
    view = scenario.model_copy(
        update={
            "materials": {
                name: item
                if name in selected
                else item.model_copy(update={"visibility": item.visibility - {"partner", "curator"}})
                for name, item in scenario.materials.items()
            }
        }
    )
    return Guard("curator", sealed_for(view, "curator"), log=log)


def opening_feedback(scenario, released):
    attachments = []
    files = []
    for name, material in released_materials(scenario, released).items():
        paths = tuple(
            f"uploads/{name}/{path.relative_to(material.path).as_posix()}"
            for path in sorted(material.path.rglob("*"))
            if path.is_file()
        )
        files.extend(paths)
        attachments.append(Handover(name, material.kind, paths))
    text = scenario.exchange.onboarding.replace("{files}", "\n".join(f"- {path}" for path in files))
    return {"signals": heard((Signal("agency", text, attachments=tuple(attachments)),))}


def scenario_request(
    scenario: Scenario, released, *, previous=None, answers=None, answers_version=None, focus=None, feedback=None
) -> Request:
    materials = released_materials(scenario, released)
    return Request(
        objective=f"Prepare expert information for this task: {scenario.situation.profile}",
        context={
            "business_task": scenario.situation.profile,
            "feedback": opening_feedback(scenario, released) if feedback is None else feedback,
            "materials": {
                name: {"kind": item.kind, "adopted": scenario.confirmed(name)} for name, item in materials.items()
            },
        },
        previous=previous,
        answers=answers or {},
        answers_version=answers_version,
        **({"focus": focus} if focus is not None else {}),
    )


def scenario_preparer(scenario, released, material_root, *, records, **options):
    """Configure first-onboarding preparation; no later-round scheduling is installed."""

    async def prepare(worker, provider, *, feedback=None, model=None, admit=None):
        names = tuple(released() if callable(released) else released)
        selected = released_materials(scenario, names)
        request = scenario_request(scenario, names, feedback=feedback)
        guard = release_guard(scenario, names, log=worker.root / "boundaries.jsonl")

        def checked(value, where):
            guard.check(value, where)
            if admit is not None:
                admit(value, where)

        if feedback:
            checked(feedback, "information.feedback")
        result = await collect_for_curator(
            worker,
            guard.provider(provider),
            request,
            materials=tuple(Path(material_root) / name for name in selected),
            records=records,
            model=model,
            admit=checked,
            **options,
        )
        if result.ready:
            handover_information(worker, result)
        return result

    return prepare
