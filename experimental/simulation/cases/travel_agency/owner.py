"""The travel agency's owner: the generic `Owner` (`experimental.cultivation.counterpart.owner`) with the agency's own facts and looks.

The agency computes, from its price list and booking policy, what each product costs for the card a drill played, and
reads facts from the structure of a delivered deck (`reference`); it flips through a delivered deck's rendered pages
the way a customer would (`looks`). Everything else about judging a round, handing materials over and speaking to the
Curator is the owner's.
"""

import base64
from pathlib import Path

from experimental.cultivation.counterpart.owner import (
    NAME,
    REFERENCES,
    Owner,
    attached,
    back_office,
    cut,
    reports,
    research,
    written,
)
from experimental.harness.participation.files import page_images
from experimental.simulation.bench.scenario import Scenario
from experimental.simulation.cases.travel_agency.reference import Rules, references

PAGES = 24

__all__ = ["NAME", "REFERENCES", "Agency", "attached", "back_office", "cut", "looks", "reports", "research", "written"]


def looks(sessions) -> tuple[dict, list[dict], str]:
    """Per drill, the page count of each deck it delivered (last version), and those pages as image message parts.

    The owner flips through the rendered pages the way a customer would; a deck that cannot be rendered says so.
    """
    shown, parts = {}, []
    for name, exchanges in sessions.items():
        decks = {
            Path(path).name: Path(path)
            for turn in exchanges
            for path in turn.execution.deliverables
            if Path(path).suffix.lower() == ".pptx" and Path(path).is_file()
        }
        for deck, path in decks.items():
            try:
                images = page_images(path)[:PAGES]
            except Exception as exc:  # noqa: BLE001 -- a deck that cannot be rendered is reported, not fatal
                shown.setdefault(name, {})[deck] = f"could not be rendered: {exc}"[:200]
                continue
            shown.setdefault(name, {})[deck] = len(images)
            parts.append({"type": "text", "text": f"[{name}] {deck}"})
            for number, image in enumerate(images, start=1):
                url = "data:image/png;base64," + base64.b64encode(image.read_bytes()).decode()
                parts += [{"type": "text", "text": f"page {number}"}, {"type": "image_url", "image_url": {"url": url}}]
    return shown, parts, "The pages of the delivered decks, in the order `pictures` lists them."


class Agency(Owner):
    """The owner of the travel agency scenario: prices and deck facts computed by its `reference` rules."""

    def __init__(self, scenario: Scenario, provider, skills: Path, **options):
        super().__init__(scenario, provider, skills, facts=self._facts, pictures=looks, **options)
        self.rules = Rules.load(scenario)

    def _facts(self, name, exchanges, card) -> dict:
        if not self.rules:
            return {}
        return references(self.rules, exchanges, getattr(card, "trip", None))
