"""Studio 的通用评审插件：每道题按这道题适用的工作规则逐项判，判定全部由评审模型做。

LiveConfig 里写 "assessor": "<这个文件>:make"。场景目录的上一级是案例目录，里面有：
- questions.json：每道题的题号、适用的工作规则（rules/<规则集>.md）、员工看到的原文和随题文件、脚本算好的参考答案；
- 可选 measure.py：measure(question, product) 返回脚本对员工产出的测量值（例如字数），只作评审的依据，不作判定。
验收项取场景 scenario.json 的 criteria。评审读工作规则全文、原题、参考答案、测量值和员工这道题的全部产出（回复正文加
交付的文本文件），对每个验收项数出违反之处并逐字引用员工原文；引用找不到的要求评审重交。不是题库里的会话不判。
评审调用失败时整题重做，最多 ATTEMPTS 次，等待逐次加长。
"""

import asyncio
import base64
import importlib.util
import json
import re
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
sys.path.insert(0, str(REPOSITORY))

from experimental.assessor.standard import TEXT_FILES  # noqa: E402
from experimental.experience.model import ModelCallError, ModelClient, ModelLimits  # noqa: E402
from experimental.iteration.protocols import Item, Signal  # noqa: E402
from raven.providers.factory import make_lazy_provider  # noqa: E402

AT_ONCE, ATTEMPTS = 3, 10
FILE_LIMIT, FILES_SHOWN = 40_000, 12_000
sys.path.insert(0, str(Path(__file__).resolve().parent))
from officetext import BINARY, render  # noqa: E402
MISSING = "（缺失）"
PROMPT = """你是验收考官。员工收到一条工作任务、这次适用的工作规则和随题的数据，交出产出。你只依据给你的工作规则、
参考答案和测量值判卷，不用自己的知识补充或改动它们。

做法：
1. 读工作规则全文、员工看到的原题和随题文件、参考答案、测量值，再读员工这道题的全部产出（回复正文和交付的文件）。
2. 对每一个验收项，找出员工产出里违反它的每一处：quote 逐字摘自员工产出（必须能在员工产出里原样找到）；
   该有而没有的内容（例如漏了必须写的话），quote 写「（缺失）」。problem 写清违反了哪条规则、正确的应该是什么。
   count 等于 errors 的条数。
3. 参考答案是按工作规则算好的标准结果，金额、日期、名单、结论以它为准；测量值是脚本对员工产出的统计（例如字数），以它为准。
4. 某个验收项在这道题里用不上（参考答案注明不适用，或题里根本没有这类情况），applicable 写 false，count 写 0。
5. 同一处错误只记在最贴切的那一个验收项下，不要重复计数。
最后调用 submit_verdicts，一次交齐全部验收项。"""


class Error(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote: str = Field(min_length=1, description="员工产出里出错的原文，逐字摘录；缺了该有的内容写「（缺失）」")
    problem: str = Field(min_length=1, description="违反了哪条规则，正确的应该是什么")


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    applicable: bool
    count: int = Field(ge=0)
    errors: list[Error]
    reason: str = Field(min_length=1, description="一两句话说明这一项为什么这样判")


class Scoring(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[Verdict]


def _plain(text: str) -> str:
    """Text as compared for quoting: no whitespace, no Markdown emphasis, quote or table marks."""
    return re.sub(r"[\s*_`>#|]", "", text)


def unquoted(scoring: Scoring, product: str) -> list[str]:
    """The quotes of a submission that are not in the product."""
    plain = _plain(product)
    return [
        error.quote
        for item in scoring.items
        for error in item.errors
        if error.quote != MISSING and _plain(error.quote) not in plain
    ]


def validate(scoring: Scoring, ids: list[str], product: str) -> str | None:
    """Why a submission cannot stand, or None."""
    got = [item.id for item in scoring.items]
    if sorted(got) != sorted(ids):
        return f"items must be exactly {ids}, got {got}"
    for item in scoring.items:
        if item.count != len(item.errors):
            return f"{item.id}: count {item.count} does not equal {len(item.errors)} listed errors"
        if not item.applicable and item.count:
            return f"{item.id}: an inapplicable item counts no errors"
    missing = unquoted(scoring, product)
    if missing:
        return f"these quotes are not in the employee's output, quote it verbatim or write {MISSING}: {missing[:5]}"
    return None


class Case:
    """One case directory: its questions, work rules, checks and optional measurements."""

    def __init__(self, scenario: Path):
        self.scenario = Path(scenario).resolve()
        self.root = self.scenario.parent
        self.bank = {q["name"]: q for q in json.loads((self.root / "questions.json").read_text())}
        self.criteria = json.loads((self.scenario / "scenario.json").read_text())["criteria"]
        found = self.root / "measure.py"
        self.measure = None
        if found.is_file():
            spec = importlib.util.spec_from_file_location(f"measure_{self.root.name.replace('-', '_')}", found)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.measure = module.measure

    def rules(self, question: dict) -> str:
        return (self.root / "rules" / f"{question['rules']}.md").read_text()

    def packet(self, question: dict, product: str) -> dict:
        shown = {name: (f"（{name} 的文字版）\n" + render(name, base64.b64decode(text[len(BINARY):])) if text.startswith(BINARY)
                        else text)[:FILES_SHOWN] for name, text in question.get("files", {}).items()}
        return {
            "工作规则": self.rules(question),
            "员工看到的原题": question["text"],
            "随题文件": shown,
            "参考答案": question["reference"],
            "测量值": self.measure(question, product) if self.measure else "本案例没有测量值",
            "验收项": [{"id": c["id"], "内容": c["check"]} for c in self.criteria],
            "员工产出": product or "（员工没有交出任何文字）",
        }


def said(exchanges) -> str:
    """员工这道题交出的全部文字：每一轮回复正文，加交付的文本文件。"""
    parts = []
    for exchange in exchanges:
        parts.append(exchange.assistant or "")
        for path in exchange.execution.deliverables if exchange.execution else ():
            file = Path(path)
            if file.suffix.lower() in TEXT_FILES and file.is_file():
                parts.append(f"【交付文件 {file.name}】\n{file.read_text(errors='replace')[:FILE_LIMIT]}")
            elif file.suffix.lower() in (".docx", ".xlsx") and file.is_file():
                parts.append(f"【交付文件 {file.name}（文字版）】\n{render(file.name, file.read_bytes())[:FILE_LIMIT]}")
    return "\n\n".join(part for part in parts if part)


class Examiner:
    name = "rules-judge"

    def __init__(self, provider, scenario: Path):
        self.provider, self.case = provider, Case(scenario)
        self.model, self.effort = judge_settings(self.case.root)
        self.gate = asyncio.Semaphore(AT_ONCE)
        self.text = "每道题按这道题适用的工作规则，逐条数员工交付里违反之处：\n" + "\n".join(
            f"- {c['id']}：{c['check']}" for c in self.case.criteria
        )

    async def judge(self, question: dict, product: str) -> tuple[Scoring, list[str]]:
        """The verdicts on one answer, and the quotes the judge kept giving that are not in the answer."""
        ids = [c["id"] for c in self.case.criteria]
        packet = self.case.packet(question, product)
        correction, last = None, None
        for attempt in range(1, ATTEMPTS + 1):
            client = ModelClient(
                self.provider, PROMPT, model=self.model, effort=self.effort, limits=ModelLimits(timeout=1200), source="exam answer"
            )
            try:
                async with self.gate:
                    scoring = await client.submit(packet, Scoring, "submit_verdicts", correction=correction)
                problem = validate(scoring, ids, product)
                if problem is None:
                    return scoring, []
                last = scoring
                correction = problem
            except ModelCallError as exc:
                if exc.kind == "invalid_submission":
                    correction = str(exc)
                elif attempt == ATTEMPTS:
                    raise
            if attempt == ATTEMPTS:
                if last is not None and sorted(item.id for item in last.items) == sorted(ids) and all(
                    item.count == len(item.errors) and (item.applicable or not item.count) for item in last.items
                ):
                    return last, unquoted(last, product)
                raise RuntimeError(f"the judge gave no valid verdicts for {question['name']}: {correction}")
            await asyncio.sleep(min(600, 30 * attempt))
        raise RuntimeError("unreachable")

    async def evaluate(self, sessions):
        bank = self.case.bank
        scored = [key for key in sessions if key in bank]
        if not scored:
            return None
        results = await asyncio.gather(*(self.judge(bank[key], said(sessions[key])) for key in scored))
        checks = {c["id"]: c["check"] for c in self.case.criteria}
        items = []
        for key, (scoring, loose) in zip(scored, results):
            for verdict in scoring.items:
                if not verdict.applicable:
                    continue
                listed = "\n".join(f"- 原文：{e.quote}\n  问题：{e.problem}" for e in verdict.errors)
                flagged = f"\n（评审有引用在产出里找不到：{loose[:3]}）" if loose else ""
                items.append(
                    Item(
                        id=f"{verdict.id}:{key}",
                        result="pass" if verdict.count == 0 else "fail",
                        session=key,
                        expected=checks[verdict.id],
                        actual=" / ".join(e.quote for e in verdict.errors)[:2000],
                        note=(f"这道题 {verdict.count} 处错误。{verdict.reason}\n{listed}{flagged}")[:3600],
                        basis="material",
                    )
                )
        errors = {
            f"errors:{key}": float(sum(v.count for v in scoring.items if v.applicable))
            for key, (scoring, _) in zip(scored, results)
        }
        failed = sum(item.result == "fail" for item in items)
        return Signal(
            self.name,
            self.text,
            items=tuple(items),
            metrics={**errors, "failed_items": float(failed)},
            satisfied=failed == 0,
        )


def judge_settings(case: Path) -> tuple[str, str]:
    """评审的模型和强度：案例 live.json 里 assessor 角色的 models / efforts。"""
    live = json.loads((Path(case) / "live.json").read_text())
    return live["models"]["assessor"], live["efforts"]["assessor"]


def judging(config, case: Path):
    """Raven 配置 `config` 的副本，改成调评审：模型和强度取自案例，服务商按模型名在配置的 providers 里找（auto），
    单次调用最长 20 分钟。"""
    config = config.model_copy(deep=True)
    defaults = config.agents.defaults
    defaults.model, defaults.reasoning_effort = judge_settings(case)
    defaults.provider = "auto"
    defaults.llm_call_timeout, defaults.llm_first_byte_timeout, defaults.stream_idle_timeout = 1200, 600, 600
    return config


def make(spec, employee):
    """Studio 的评审插件：用员工配置里的 providers 调案例指定的评审模型。"""
    scenario = Path(spec["scenario"])
    return Examiner(make_lazy_provider(judging(employee.baseline.config, scenario.parent)), scenario)
