"""Give each drill a fresh local lab and its own machine registry, and recognise runs of a lab script.

A drill's lab is a pristine copy of the scenario's ``lab/`` folder in a directory of its own, registered as the
``local-lab`` machine. Raven runs a command on that machine in the caller's working directory unless the call names
one, and the registry's ``paths`` are not shown to the on-call colleague, so the copy's absolute path is also written
into the row's ``note``, the field the colleague's machine listing shows.

Owners bind a reading to the drill's lab by the command that produced it. ``script_run`` reads the shell command the
way the shell would for the spellings a colleague naturally uses (directory changes, waits, stderr redirection,
unbuffered Python) and resolves the script and path arguments against the effective working directory. A command
that does anything else is not recognised as a reading. Readings declared in an on-call campaign's readings table
run inside the on-call tools and leave no execution row with their output or host timing; ``declared_runs`` finds
them so an owner can report them without counting them.
"""

import json
import re
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path

PYTHON = re.compile(r"python(?:3(?:\.\d+)?)?")
PYTHON_FLAGS = frozenset({"-u", "-B"})
OPERATOR_CHARS = ";&|<>()"
SEPARATORS = frozenset({"&&", ";"})
STDERR_REDIRECTS = (("2", ">&", "1"), ("2", ">", "/dev/null"))
WAIT = re.compile(r"\d+(?:\.\d+)?s?")


def placement_note(workdir: Path) -> str:
    """The sentence a machine listing shows about where the lab's scripts are and how to run them."""
    return (
        f"The department's scripts live in {workdir}; run them with that as the working directory "
        "(working_dir) or call them by their absolute path."
    )


def _local_lab(data: dict) -> list[dict]:
    return [
        row for row in data.get("connections", []) if row.get("id") == "local-lab" and row.get("transport") == "local"
    ]


def lab_placement(registry: Path) -> dict:
    """The host-configured local lab location supplied privately to a case's evaluator."""
    machines = _local_lab(json.loads(registry.read_text()))
    if len(machines) != 1 or len(machines[0].get("paths", [])) != 1:
        raise ValueError("a replica lab needs one configured local-lab workdir")
    return {"machine": "local-lab", "workdir": Path(machines[0]["paths"][0]).resolve(), "registry": registry.resolve()}


def replica_lab(source: Path, target: Path, registry: Path) -> Path:
    """Copy pristine scenario inputs, retaining the configured lab's machine metadata and naming the copy's path."""
    data = json.loads(registry.read_text())
    machines = _local_lab(data)
    if len(machines) != 1:
        raise ValueError("a scenario lab needs one local-lab machine in RAVEN_CONNECTIONS")
    work = target / "work"
    shutil.copytree(source, work, ignore=shutil.ignore_patterns(".*", "__pycache__", "*.pyc"))
    machines[0]["paths"] = [str(work.resolve())]
    machines[0]["note"] = placement_note(work.resolve())
    path = target / "connections.json"
    path.write_text(json.dumps(data, indent=2))
    return path


@dataclass(frozen=True)
class ScriptRun:
    """One direct run of a lab script inside a shell command, with the directory it ran in when that is known."""

    script: str
    arguments: tuple[str, ...]
    cwd: Path | None

    def path(self, value: str) -> Path | None:
        """``value`` as the script saw it: absolute as written, else under the effective directory, else unknown."""
        candidate = Path(value)
        if candidate.is_absolute():
            return candidate
        return self.cwd / candidate if self.cwd is not None else None

    @property
    def script_path(self) -> Path | None:
        return self.path(self.script)


class _Operator(str):
    """A shell operator as written, kept apart from a quoted word that spells the same characters."""


def _tokens(command: str) -> list[str] | None:
    try:
        lexer = shlex.shlex(command, posix=False, punctuation_chars=OPERATOR_CHARS)
        lexer.whitespace_split = True
        return [
            _Operator(token) if set(token) <= set(OPERATOR_CHARS) else (shlex.split(token) or [""])[0]
            for token in lexer
        ]
    except ValueError:
        return None


def _operator(token: str) -> bool:
    return isinstance(token, _Operator)


def _segments(command: str, tokens: list[str]) -> list[list[str]] | None:
    segments, current, index = [], [], 0
    while index < len(tokens):
        token = tokens[index]
        redirect = next(
            (
                shape
                for shape in STDERR_REDIRECTS
                if tuple(tokens[index : index + 3]) == shape
                and _operator(tokens[index + 1])
                and current
                and "".join(shape) in command
                and (index + 3 == len(tokens) or (_operator(tokens[index + 3]) and tokens[index + 3] in SEPARATORS))
            ),
            None,
        )
        if redirect:
            index += 3
            continue
        if _operator(token) and token in SEPARATORS:
            if current:
                segments.append(current)
            current = []
        elif _operator(token):
            return None
        else:
            current.append(token)
        index += 1
    if current:
        segments.append(current)
    return segments


def script_run(command: str, script: str, working_dir: str | None = None) -> ScriptRun | None:
    """The single run of ``script`` in ``command``, or None when the command is not just that run.

    Accepted around the run: ``cd <dir>``, ``sleep <seconds>``, ``&&`` or ``;`` between them, a trailing ``2>&1`` or
    ``2>/dev/null`` on a step, and ``-u``/``-B`` before the script. ``working_dir`` is the call's own directory
    argument; without it, and without a ``cd`` to an absolute path, relative paths stay unresolved.
    """
    tokens = _tokens(command or "")
    segments = _segments(command, tokens) if tokens else None
    if not segments:
        return None
    cwd = Path(working_dir) if working_dir and Path(working_dir).is_absolute() else None
    found = None
    for segment in segments:
        head = segment[0]
        if head == "cd" and len(segment) == 2 and not segment[1].startswith("-"):
            target = Path(segment[1])
            cwd = target if target.is_absolute() else cwd / target if cwd is not None else None
        elif head == "sleep" and len(segment) == 2 and WAIT.fullmatch(segment[1]):
            continue
        elif PYTHON.fullmatch(Path(head).name):
            rest = segment[1:]
            while rest and rest[0] in PYTHON_FLAGS:
                rest = rest[1:]
            if found is not None or not rest or Path(rest[0]).name != script:
                return None
            found = ScriptRun(rest[0], tuple(rest[1:]), cwd)
        else:
            return None
    return found


def invokes(command: str, script: str) -> bool:
    """Whether ``command`` starts ``script`` with Python at some command boundary, however else it is spelled."""
    tokens = _tokens(command or "")
    if not tokens:
        return False
    for index, token in enumerate(tokens):
        if not PYTHON.fullmatch(Path(token).name) or (index and not _operator(tokens[index - 1])):
            continue
        rest = tokens[index + 1 :]
        while rest and rest[0] in PYTHON_FLAGS:
            rest = rest[1:]
        if rest and Path(rest[0]).name == script:
            return True
    return False


def declared_runs(arguments: dict, script: str) -> list[str]:
    """The commands of an on-call campaign's readings table that start ``script``."""
    table = arguments.get("readings") if isinstance(arguments, dict) else None
    return [
        str(row.get("command"))
        for row in table or ()
        if isinstance(row, dict) and invokes(str(row.get("command") or ""), script)
    ]
