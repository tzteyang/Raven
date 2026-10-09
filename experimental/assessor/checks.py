"""Execute bounded evidence checks and combine their results without voting away failures or unknowns."""

import ast
import asyncio
import copy
import json
import math
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Result = Literal["pass", "fail", "unknown", "not_applicable"]
EVIDENCE_LIMIT = 512_000
EXPRESSION_LIMIT = 4_000


@dataclass(frozen=True)
class Finding:
    """One check's observed outcome; the caller retains the input packet beside this finding."""

    result: Result
    actual: str = ""
    note: str = ""
    session: str | None = None

    def __post_init__(self):
        if self.result not in ("pass", "fail", "unknown", "not_applicable"):
            raise ValueError("unknown check result")


Verifier = Callable[[dict], Awaitable[Finding]]
Examples = Sequence[tuple[dict, bool]]


async def completed_turns(evidence: dict) -> Finding:
    """Every supplied turn produced a reply without timing out; this does not establish task correctness."""
    rows = [row for turns in evidence.get("conversations", {}).values() for row in turns]
    if not rows:
        return Finding("unknown", note="No completed-turn evidence was supplied.")
    if any(row.get("stopped") or not row.get("assistant") for row in rows):
        return Finding("fail", actual="At least one turn stopped without a reply.")
    return Finding("pass", actual=f"All {len(rows)} turns produced replies.")


async def readable_deliverables(evidence: dict) -> Finding:
    """Delivered text is present and fully readable; this checks availability, not content quality."""
    rows = [row for turns in evidence.get("conversations", {}).values() for row in turns]
    unavailable = [reason for row in rows for reason in row.get("unavailable", {}).values()]
    if unavailable:
        return Finding("unknown", note="; ".join(unavailable))
    if not any(row.get("delivered") for row in rows):
        return Finding("fail", actual="No delivered file was recorded.")
    return Finding("pass", actual="Delivered text files were read in full.")


VERIFIERS = {"completed_turns": completed_turns, "readable_deliverables": readable_deliverables}


def combine(findings: Sequence[Finding]) -> Finding:
    """All necessary checks must support acceptance; inconsistent applicability is unresolved."""
    if failed := next((finding for finding in findings if finding.result == "fail"), None):
        return failed
    unknown = [finding for finding in findings if finding.result == "unknown"]
    if unknown:
        return Finding("unknown", note="\n".join(dict.fromkeys(finding.note for finding in unknown if finding.note)))
    if not findings:
        return Finding("unknown", note="No check produced evidence.")
    if all(finding.result == "not_applicable" for finding in findings):
        return findings[0]
    if any(finding.result == "not_applicable" for finding in findings):
        return Finding("unknown", note="Necessary checks disagree about applicability.")
    return Finding(
        "pass",
        actual="\n".join(finding.actual for finding in findings if finding.actual),
        session=next((finding.session for finding in findings if finding.session is not None), None),
    )


_FUNCTIONS = {
    "all": all,
    "any": any,
    "len": len,
    "sum": sum,
    "min": min,
    "max": max,
    "abs": abs,
    "sorted": sorted,
    "round": round,
    "json_loads": json.loads,
}
_NODES = (
    ast.Expression,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Subscript,
    ast.Slice,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.Set,
    ast.ListComp,
    ast.GeneratorExp,
    ast.comprehension,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.IfExp,
    ast.Call,
)


def _expression(source: str, evidence: dict) -> bool:
    if len(source) > EXPRESSION_LIMIT:
        raise ValueError("program expression is too long")
    tree = ast.parse(source, mode="eval")
    nodes = list(ast.walk(tree))
    if len(nodes) > 400 or any(not isinstance(node, _NODES) for node in nodes):
        raise ValueError("program uses syntax outside the evidence-only expression language")
    local = {node.id for node in nodes if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)}
    for node in nodes:
        if isinstance(node, ast.Name) and node.id not in {*_FUNCTIONS, "evidence", *local}:
            raise ValueError(f"program cannot access {node.id!r}")
        if isinstance(node, ast.Call) and (not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS):
            raise ValueError("program may call only the supplied evidence functions")
        if isinstance(node, ast.comprehension) and node.is_async:
            raise ValueError("asynchronous comprehensions are unavailable")
    result = eval(compile(tree, "<evidence-check>", "eval"), {"__builtins__": {}, **_FUNCTIONS, "evidence": evidence})
    if type(result) is not bool:
        raise ValueError("program must return a boolean")
    return result


async def expression(source: str, evidence: dict, *, timeout: float = 2) -> Finding:
    """Run restricted Python in a resource-limited child with JSON input and an empty environment."""
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("program timeout must be positive and finite")
    try:
        packet = json.dumps({"expression": source, "evidence": evidence}, allow_nan=False).encode()
    except (ValueError, TypeError) as exc:
        return Finding("unknown", note=f"Program input is not finite JSON evidence: {exc}")
    if len(packet) > EVIDENCE_LIMIT:
        return Finding("unknown", note="Evidence packet exceeds the program input limit.")
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        str(Path(__file__).resolve()),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={},
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(packet), timeout)
        if process.returncode:
            return Finding("unknown", note=f"Program exited with status {process.returncode}.")
        value = json.loads(output)
        if "error" in value:
            return Finding("unknown", note=value["error"])
        return Finding("pass" if value["passed"] is True else "fail", actual=f"Program returned {value['passed']}.")
    except TimeoutError:
        return Finding("unknown", note="Program exceeded its time limit.")
    except (ValueError, KeyError) as exc:
        return Finding("unknown", note=f"Program returned invalid evidence: {exc}")
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()


async def program(
    evidence: dict,
    *,
    verifier: str | None = None,
    expression_source: str | None = None,
    verifiers: Mapping[str, Verifier],
    examples: Examples = (),
    complete: bool = False,
    timeout: float = 2,
) -> Finding:
    """Whole-criterion programs and generated expressions require bound independent calibration."""
    if (verifier is None) == (expression_source is None):
        return Finding("unknown", note="Exactly one verifier or expression is required.")
    if verifier is not None and verifier not in verifiers:
        return Finding("unknown", note=f"No verifier is registered for {verifier!r}.")

    async def run(sample):
        if expression_source is not None:
            return await expression(expression_source, sample, timeout=timeout)
        try:
            finding = await asyncio.wait_for(verifiers[verifier](copy.deepcopy(sample)), timeout)
            if not isinstance(finding, Finding):
                raise TypeError("a verifier must return a Finding")
            return finding
        except Exception as exc:
            return Finding("unknown", note=f"Verifier {verifier!r} failed: {str(exc)[:500]}")

    if complete or expression_source is not None:
        if len(examples) > 20 or {expected for _, expected in examples if type(expected) is bool} != {True, False}:
            return Finding(
                "unknown",
                note="This program needs criterion-bound independent positive and negative calibration cases.",
            )
        for sample, expected in examples:
            if type(expected) is not bool:
                return Finding("unknown", note="Calibration labels must be independently known booleans.")
            observed = await run(sample)
            if observed.result != ("pass" if expected else "fail"):
                return Finding("unknown", note=f"Program failed calibration: {observed.note or observed.actual}")
    return await run(evidence)


def _main():
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (1, 1))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    try:
        packet = json.loads(sys.stdin.buffer.read(EVIDENCE_LIMIT + 1))
        answer = {"passed": _expression(packet["expression"], packet["evidence"])}
    except Exception as exc:
        answer = {"error": f"{type(exc).__name__}: {str(exc)[:500]}"}
    print(json.dumps(answer))


if __name__ == "__main__":
    _main()
