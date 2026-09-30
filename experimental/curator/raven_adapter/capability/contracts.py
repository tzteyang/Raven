"""Capability authoring names the implementation that prepares and selects resources."""

from ..strategy import TaskBinding

TARGET = "capability.strategy"


class CapabilityBinding(TaskBinding):
    """Construct prepare/register/select with explicit registrar and host dependencies.

    Resources are produced by prepare or its protected helpers, never by a
    binding payload. Cross-strategy tools use the same registration policy.
    Runtime selection has its own session checkpoint and a closed registrar.
    """
