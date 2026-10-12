"""The three layers of experimental/ depend downward only: simulation on cultivation on harness, never the reverse."""

import re
from pathlib import Path

EXPERIMENTAL = Path(__file__).resolve().parents[1] / "experimental"
LAYERS = {"harness": 1, "cultivation": 2, "simulation": 3, "webui": 4}
IMPORT = re.compile(r"^\s*(?:from|import) (experimental(?:\.\w+)+)", re.M)
SKIPPED = {"node_modules", "notes", "showcase", "__pycache__", "dist"}


def modules():
    for path in sorted(EXPERIMENTAL.rglob("*.py")):
        if not SKIPPED & set(path.parts):
            yield path.relative_to(EXPERIMENTAL).parts, path.read_text()


def test_the_first_level_is_the_three_layers_and_their_tools():
    packages = sorted(p.name for p in EXPERIMENTAL.iterdir() if p.is_dir() and p.name not in SKIPPED)
    assert packages == ["cultivation", "docs", "harness", "simulation", "webui"]
    assert [p.name for p in EXPERIMENTAL.glob("*.py")] == ["__init__.py"]


def test_no_module_imports_a_layer_above_its_own():
    upward = []
    for parts, source in modules():
        own = LAYERS.get(parts[0], 0)
        for match in IMPORT.finditer(source):
            target = match.group(1).split(".")[1:]
            if LAYERS.get(target[0], 0) > own:
                upward.append(("/".join(parts), ".".join(target)))
    assert upward == []


def test_the_bench_and_the_cases_face_one_way():
    """A case is a task package the bench plays; the bench never imports a case, and the harness never names one."""
    named = set()
    for parts, source in modules():
        if parts[:2] == ("simulation", "cases"):
            continue
        for match in IMPORT.finditer(source):
            if match.group(1).startswith("experimental.simulation.cases"):
                named.add("/".join(parts))
    assert named <= {"simulation/__main__.py"}
