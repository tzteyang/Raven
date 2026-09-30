"""The research stage: what the party handed over, read into the contract's categories before a cultivation starts.

`slots` reports what each category gives and how a gap could be filled; `induce` reads the rules the exemplars and
counterexamples show and the norms leave unstated; `inquire` researches on the web what an empty slot needs, by an
agent or this stage's own model, and keeps only findings that quote a page it can read again; the party settles
each rule and finding (`Decisions`, or `ModelParty` in a simulation); `package` writes a new scenario directory with
the settled items as materials and a `provenance.json`. The loop never runs this stage: it loads the written
directory as it loads any other, so its starting point stays one frozen package whose origin is on record.
"""

from .confirm import Decision, Decisions, ModelParty, settle, worded
from .induction import Rule, induce
from .inquiry import Finding, Researched, inquire
from .slots import Slot, slots

__all__ = [
    "Decision",
    "Decisions",
    "Finding",
    "ModelParty",
    "Researched",
    "Rule",
    "Slot",
    "induce",
    "inquire",
    "settle",
    "slots",
    "worded",
]
