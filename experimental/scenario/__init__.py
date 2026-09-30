"""What a cultivation scenario may consist of: a closed set of input categories, each item with who may see it.

A scenario of interactive Harness improvement describes four things and what came before: the partner as it starts,
the work and the world it happens in, what the interacting party knows and wants, and how the exchange is conducted.
`contract` names those categories and the default visibility of each kind of item to the five roles; `load` reads a
scenario directory into them and refuses a file that belongs to none, so no input arrives outside the categories.
"""

from .contract import (
    KINDS,
    ROLES,
    VIEWS,
    Aids,
    Case,
    Check,
    Exchange,
    Material,
    Origin,
    Prior,
    Provenance,
    Scenario,
    Situation,
    Statements,
    contents,
    default_visibility,
    load,
)
from .disclosure import Disclosure

__all__ = [
    "KINDS",
    "ROLES",
    "VIEWS",
    "Aids",
    "Case",
    "Check",
    "Disclosure",
    "Exchange",
    "Material",
    "Origin",
    "Prior",
    "Provenance",
    "Scenario",
    "Situation",
    "Statements",
    "contents",
    "default_visibility",
    "load",
]
