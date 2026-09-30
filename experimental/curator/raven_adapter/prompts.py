"""Load prompt objects explicitly selected by strategy preparation and expose their input contracts."""

from pathlib import Path

from ..harness.prompts import Prompt
from .materialize import load_object


def bind_prompts(artifact, package: Path, *, references):
    prompts = {}
    for reference in references:
        if reference in prompts:
            raise ValueError(f"duplicate prompt resource: {reference}")
        prompt = load_object(reference, package)
        if not isinstance(prompt, Prompt):
            raise TypeError(f"prompt resource is not a Prompt: {reference}")
        if not prompt.path.is_relative_to(package.resolve()):
            raise ValueError(f"prompt resource escapes the candidate package: {reference}")
        relative = prompt.path.relative_to(package.resolve()).as_posix()
        if artifact.files.get(relative) != prompt.template:
            raise ValueError(f"prompt text differs from the candidate: {reference}")
        prompts[reference] = {**prompt.describe(), "file": relative}
    return prompts
