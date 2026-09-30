"""Mechanism attribution: before a curation changes anything, locate where each of its inputs stands.

For every requirement, handed-over material or routed node requirement (`subjects`), an attributor finds the
responsible mechanism of the current Harness and its state from a closed set, with the evidence. The curation's
generation consumes the result (`experimental.curator.harness.Attributed`) and grounds each target on it; the loop
records it and joins it to what happened next. The component is its own step: its own tools, budget
(`AttributionLimits`), resumable state (`AttributionState`) and record, and an `Attributor` protocol any
implementation can satisfy. The default, `ModelAttributor`, is the Curator's own model.
"""

from .model import (
    NAME,
    PROMPT_FILES,
    PROMPTS,
    Attributor,
    ModelAttributor,
    SuppliedAttributor,
    effective_model,
    input_id,
    input_key,
    parse,
    submission,
)
from .state import (
    AttributionInterruptedError,
    AttributionLimits,
    AttributionPausedError,
    AttributionState,
)
from .subjects import subjects

__all__ = [
    "NAME",
    "PROMPTS",
    "PROMPT_FILES",
    "AttributionInterruptedError",
    "AttributionLimits",
    "AttributionPausedError",
    "AttributionState",
    "Attributor",
    "ModelAttributor",
    "SuppliedAttributor",
    "effective_model",
    "input_id",
    "input_key",
    "parse",
    "subjects",
    "submission",
]
