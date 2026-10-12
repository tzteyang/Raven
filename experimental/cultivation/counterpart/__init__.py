"""The counterpart side of the cultivation loop as a protocol with case-specific pieces plugged in.

The loop (`experimental.harness.loop`) owns the shape of a feedback signal and what each role may receive of it. A case
contributes who faces the worker and who judges it: `Owner` is the generic model-played owner who reviews a round's
sessions and deliverables, decides what it hands over and speaks to the Curator; a case supplies the two things that
differ between businesses, the facts computed from its own materials for each drill (`facts`) and how it looks at a
delivered file that is not text (`pictures`). `case` holds what a run is judged by that differs between cases.
"""

from experimental.cultivation.counterpart.case import deck_delivered, files_delivered
from experimental.cultivation.counterpart.owner import (
    NAME,
    REFERENCES,
    Owner,
    attached,
    back_office,
    cut,
    deliverables,
    reports,
    research,
    written,
)

__all__ = [
    "NAME",
    "REFERENCES",
    "Owner",
    "attached",
    "back_office",
    "cut",
    "deck_delivered",
    "deliverables",
    "files_delivered",
    "reports",
    "research",
    "written",
]
