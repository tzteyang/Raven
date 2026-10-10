"""The counterpart side of the cultivation loop as a protocol with case-specific pieces plugged in.

The loop (`experimental.iteration`) owns the shape of a feedback signal and what each role may receive of it. A case
contributes who faces the worker and who judges it: `Owner` is the generic model-played owner who reviews a round's
sessions and deliverables, decides what it hands over and speaks to the Curator; a case supplies the two things that
differ between businesses, the facts computed from its own materials for each drill (`facts`) and how it looks at a
delivered file that is not text (`pictures`). `drills` plays a case's cards on replicas of the worker, and `case`
holds what a run is judged by that differs between cases.
"""

from experimental.counterpart.case import deck_delivered, delivered_for, files_delivered
from experimental.counterpart.drills import enlist, grouped
from experimental.counterpart.owner import (
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
    "delivered_for",
    "deliverables",
    "enlist",
    "files_delivered",
    "grouped",
    "reports",
    "research",
    "written",
]
