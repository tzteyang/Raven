"""自检两件事：

1. 另判一遍：只读员工看到的文件（工作规则.md、合同 .docx 的文字），从规则原文读出付款期、修改轮数、争议解决、违约金上限、
   含税和发票的口径，逐条判合同里哪些条款不合规，和参考答案的“逐条处理”比对。
2. 照参考答案用 redline.py 真的审一遍每份合同（标准库写 Word 修订和批注），再用 measure.py 量：不能有没留痕的改动、别人原有的
   修订和批注要都在、加粗要都在、该改的接受修订后要含规定的话——确认每道题都做得出一份全对的答卷，测量值也量得对。

  python3 check.py
"""

import base64
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "common"))
sys.path.insert(0, str(HERE))
from officetext import docx_text  # noqa: E402
from redline import review  # noqa: E402
from measure import measure  # noqa: E402


def judge(rules: str, text: str) -> dict:
    """Which kinds of clause break this rule set, read from the contract's text."""
    line = lambda prefix: next(l for l in text.splitlines() if l.startswith(prefix)).replace("**", "")
    pay_limit = int(re.search(r"付款期不超过 (\d+) 天", rules).group(1))
    rounds_limit = int(re.search(r"修改不超过 (\d+) 轮", rules).group(1))
    out = {}
    tax = line("第三条")
    out["tax"] = "含" not in tax or "税" not in tax or ("开什么发票" in rules and "专用发票" not in tax and "普通发票" not in tax)
    pay = next(l for l in text.splitlines() if "日内支付" in l)
    out["pay"] = int(re.search(r"(\d+) 日内支付", pay).group(1)) > pay_limit
    rounds = line("第五条")
    m = re.search(r"不超过 (\d+) 轮", rounds)
    out["rounds"] = not m or int(m.group(1)) > rounds_limit
    out["ip"] = "不得" in line("第八条")
    venue = line("第十条")
    if "上海仲裁委员会仲裁" in rules:
        out["venue"] = "上海仲裁委员会" not in venue
    else:
        court = re.search(r"把这句改成“由(.+?)管辖”", rules).group(1)
        out["venue"] = court not in venue
    if "违约金累计不超过合同总价的 20%" in rules:
        cap = re.search(r"不超过合同总价的 (\d+)%", line("第九条"))
        out["cap"] = not cap or int(cap.group(1)) > 20
    return out


def edits_for(q: dict) -> tuple[list, list, str]:
    """The edits a correct review makes, from the reference plan and the contract's own wording."""
    ref, rules = q["reference"], q["files"]["工作规则.md"]
    text = ref["原文的文字版"].replace("**", "")
    edits, notes = [], []
    for item in ref["逐条处理"]:
        how, rule_no = item["处理"], item.get("规则")
        tag = f"【规则 {rule_no}】" if "开头写这条批注依据的规则编号" in rules else ""
        if how.startswith("已合规"):
            continue
        if how.startswith("只加批注"):
            notes.append(("第三条 合同总价为人民币", f"{tag}总价没写清含税口径（或发票类型），请补上。"))
            continue
        target = item["接受修订后应含"]
        if "付款期" in item["条款"]:
            days = re.search(r"(\d+) 日改成", how).group(1)
            edits.append((f"{days} 日", target, f"{tag}付款期超过规则上限，改为 {target}。"))
        elif "第五条" in item["条款"]:
            old = re.search(r"修订：“(.+?)”改成", how).group(1)
            edits.append((old, target + "。", f"{tag}修改轮数要设上限，改为“{target}”。"))
        elif "第八条" in item["条款"]:
            old = next(l for l in text.splitlines() if l.startswith("第八条"))[4:]
            kept = old.split("，乙方不得")[0]
            edits.append((old, kept + "；" + target + "。", f"{tag}删去禁止乙方展示的约定，保留作品使用权。"))
        elif "第十条" in item["条款"]:
            old = next(l for l in text.splitlines() if l.startswith("第十条"))[4:]
            new = "因本合同发生的争议，" + (target if target.startswith("提交") else f"由{target}管辖") + "。"
            edits.append((old, new, f"{tag}争议解决按规则改为{target}。"))
        elif "第九条" in item["条款"]:
            tail = re.search(r"支付违约金(.*)。$", next(l for l in text.splitlines() if l.startswith("第九条"))).group(0)
            edits.append((" " + tail, " 支付违约金，乙方累计违约金不超过合同总价的 20%。", f"{tag}乙方违约金要设 20% 上限。"))
    return edits, notes, ref["作者"]


def main() -> None:
    wrong = []
    for q in json.loads((HERE / "questions.json").read_text()):
        rules, ref = q["files"]["工作规则.md"], q["reference"]
        name = next(n for n in q["files"] if n.endswith(".docx"))
        data = base64.b64decode(q["files"][name][len("base64:"):])
        text = docx_text(data)
        mine = judge(rules, text)
        theirs = {}
        for item in ref["逐条处理"]:
            kind = next(k for k, label in (("tax", "第三条"), ("pay", "付款期"), ("rounds", "第五条"), ("ip", "第八条"),
                                           ("venue", "第十条"), ("cap", "第九条")) if label in item["条款"])
            theirs[kind] = not item["处理"].startswith("已合规")
        problems = []
        if mine != theirs:
            problems.append(("plan", mine, theirs))
        edits, notes, author = edits_for(q)
        try:
            reviewed = review(data, edits, notes, author)
        except ValueError as exc:
            problems.append(("redline", str(exc)))
            wrong.append((q["name"], problems))
            continue
        product = f"改了 {len(edits)} 处，加了 {len(edits) + len(notes)} 条批注。\n\n【交付文件 {ref['该交回的文件名']}（文字版）】\n" + docx_text(reviewed)
        got = measure(q, product)
        if got["没有留痕、直接改了正文的段（拒绝全部修订后和原文不一致）"] != "无" or got["没加修订却和原文不一样的段"] != "无":
            problems.append(("silent", got["没有留痕、直接改了正文的段（拒绝全部修订后和原文不一致）"]))
        if isinstance(got["原有的别人的修订还在不在"], dict) and not all(got["原有的别人的修订还在不在"].values()):
            problems.append("client revision lost")
        bold = [v for row in got["逐段对照"] for k, v in row.items() if k.startswith("原文加粗")]
        if not all(all(b.values()) for b in bold):
            problems.append("bold lost")
        accepted = "\n".join(row.get("接受全部修订后", "") for row in got["逐段对照"])
        for item in ref["逐条处理"]:
            if "接受修订后应含" in item and item["接受修订后应含"] not in accepted:
                problems.append(("missing", item["接受修订后应含"]))
            if "接受修订后不应含" in item and any(item["接受修订后不应含"] in row.get("接受全部修订后", "")
                                                for row in got["逐段对照"] if row["原文"].startswith("第八条")):
                problems.append(("still there", item["接受修订后不应含"]))
        if len(got["交回文件新加的批注"]) != len(edits) + len(notes) or any(c["批在哪一段"] == "找不到" for c in got["交回文件新加的批注"]):
            problems.append(("comments", got["交回文件新加的批注"]))
        if problems:
            wrong.append((q["name"], problems))
    print("mismatches:", wrong or "none")
    assert not wrong


if __name__ == "__main__":
    main()
