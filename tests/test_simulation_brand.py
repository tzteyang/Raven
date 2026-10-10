"""The brand strategist's facts: forbidden words, slogan consistency, unsourced figures and on-call evidence, computed
from what the assistant said and delivered with the scenario's own word table."""

from experimental.iteration.protocols import Exchange, Execution
from experimental.simulation.brand import (
    Vocabulary,
    facts,
    forbidden_words,
    oncall_evidence,
    slogan_lines,
    unsourced_figures,
)
from experimental.simulation.scenario import Scenario

VOCABULARY = Vocabulary(
    forbidden=("best", "only", "100%"),
    slogan_markers=("Slogan:", "Slogan -"),
    figure_units=("k", "%"),
    source_marks=("source",),
    report_prefix="watch-report-",
)


def turn(reply, records=(), files=()):
    rows = [{"kind": "runner.event", "event_type": "Text", "event": {"content": reply}}, *records]
    return Exchange("request", Execution("t1", [], rows, {}, "a", tuple(str(path) for path in files)))


def test_forbidden_words_are_listed_in_table_order_each_with_the_lines_it_stands_on():
    text = "the only best, the best only\n  the only way we say it  \nnothing here"
    assert forbidden_words(text, VOCABULARY) == {
        "best": ["the only best, the best only"],
        "only": ["the only best, the best only", "the only way we say it"],
    }
    long = "x" * 100 + " the best " + "y" * 100
    assert [len(line) for line in forbidden_words(long, VOCABULARY)["best"]] == [60]
    assert "best" in forbidden_words(long, VOCABULARY)["best"][0]
    assert forbidden_words("", VOCABULARY) == {} and forbidden_words(None, VOCABULARY) == {}


def test_slogan_lines_follow_every_marker_and_figures_need_a_source_on_their_line():
    text = "Slogan: Learn more\nbody\n  Slogan - Learn more \nSlogan: Learn less"
    assert slogan_lines(text, VOCABULARY) == ["Learn more", "Learn more", "Learn less"]
    text = "users 6,000k (source: store)\nusers 6,000k\nshare 12 %\nno figure 2026"
    assert unsourced_figures(text, VOCABULARY) == ["users 6,000k", "share 12 %"]


def test_oncall_evidence_counts_child_executions_tools_and_delivered_reports(tmp_path):
    report = tmp_path / "watch-report-2026-10-08.md"
    report.write_text("# watch\n")
    other = tmp_path / "proposal.md"
    other.write_text("Slogan: x\n")
    records = [
        {"kind": "child.execution", "harness": "Raven-Oncall", "records": [{"tool": "ops_declare"}, "ops_finish"]},
        {"kind": "child.execution", "harness": "Raven-PPT", "records": ["ops_submit"]},
        {"kind": "runner.event", "event": {"name": "ops_check_later"}},
    ]
    exchanges = [turn("done", records, files=[report, other])]
    assert oncall_evidence(exchanges, VOCABULARY) == {
        "oncall_executions": 1,
        "campaign_tools": ["ops_check_later", "ops_declare", "ops_finish"],
        "watch_reports": ["watch-report-2026-10-08.md"],
    }


def test_facts_keys_only_what_was_found(tmp_path):
    proposal = tmp_path / "q4-brand-proposal.md"
    proposal.write_text("Slogan: Learn more\nthe best app\nSlogan: Learn less\nreach 30% (source: survey)\n")
    exchanges = [turn("reach 30% of students, the only one"), turn("file delivered", files=[proposal])]
    found = facts(exchanges, VOCABULARY)
    assert found == {
        "forbidden_words": {
            "message 1": {"only": ["reach 30% of students, the only one"]},
            "file q4-brand-proposal.md": {"best": ["the best app"]},
        },
        "slogan_lines": {"q4-brand-proposal.md": {"distinct": ["Learn less", "Learn more"], "consistent": False}},
        "unsourced_figures": {"message 1": ["reach 30% of students, the only one"]},
        "delivered_files": ["q4-brand-proposal.md"],
    }
    assert facts([turn("nothing to report")], VOCABULARY) == {}


def test_the_bundled_scenario_carries_the_vocabulary():
    vocabulary = Vocabulary.load(Scenario.load("brand_strategist"))
    assert len(vocabulary.forbidden) >= 10 and len(vocabulary.slogan_markers) == 2
    assert vocabulary.report.match("watch-report-2026-10-08.md") and not vocabulary.report.match("report.md")
    assert vocabulary.figure.search("600" + vocabulary.figure_units[0])
