"""评审用的测量值：员工交回的 .docx（产出里“【交付文件 ……docx（文字版）】”那一节）和原合同逐段对照。只作评审依据，判定由评审做。

每段给出：原文、交回文件里这一段（修订标成 [+插入+] [-删除-]，加粗标成 **字**）、“接受全部修订后”的文字、“拒绝全部修订后”的
文字和原文是否一致（不一致就是没留痕直接改了正文）、原文里的加粗还在不在。另列交回文件新加的修订和批注（作者、批在哪段文字上、
批在哪一条）、原有的别人的修订和批注还在不在、页眉一样不一样、文件名、回复正文。
"""

import base64
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))
from officetext import docx_text  # noqa: E402

DELIVERED = re.compile(r"【交付文件 (.+?\.docx)（文字版）】\n(.*?)(?=\n【交付文件 |\Z)", re.S)
CLAUSE = re.compile(r"^(第[一二三四五六七八九十]+条|\| 付款说明|\| 项目|\| 合计|甲方|乙方|\*\*《|【页眉】)")


def accept(line: str) -> str:
    return re.sub(r"\[\+(.*?)\+\]", r"\1", re.sub(r"\[-.*?-\]", "", line))


def reject(line: str) -> str:
    return re.sub(r"\[-(.*?)-\]", r"\1", re.sub(r"\[\+.*?\+\]", "", line))


def split(text: str) -> tuple[list[str], list[str], list[str]]:
    body, rest = (text.split("\n\n—— ", 1) + [""])[:2]
    comments = re.findall(r"^【批注 #.+$", text, re.M)
    revisions = re.findall(r"^(?:插入|删除)（作者：.+$", text, re.M)
    return [l for l in body.splitlines() if l.strip()], comments, revisions


def key(line: str) -> str:
    m = CLAUSE.match(reject(line).replace("**", ""))
    return m.group(1) if m else reject(line)[:12]


def measure(question: dict, product: str) -> dict:
    files = question["files"]
    name = next(n for n in files if n.endswith(".docx"))
    original = docx_text(base64.b64decode(files[name][len("base64:"):]))
    found = DELIVERED.findall(product)
    reply = DELIVERED.sub("", product).strip()
    if not found:
        return {"交回的 .docx": "没有（产出里没有 .docx 文件）", "回复正文": reply[:800]}
    got_name, text = next(((n, t) for n, t in found if n.endswith(".reviewed.docx")), found[-1])
    o_body, o_comments, o_revs = split(original)
    d_body, d_comments, d_revs = split(text)
    by_key = {}
    for line in d_body:
        by_key.setdefault(key(line), []).append(line)
    rows, silent, untouched_changed = [], [], []
    for index, line in enumerate(o_body):
        same = d_body[index] if len(d_body) == len(o_body) else (by_key.get(key(line)) or [None])[0]
        if same is None:
            rows.append({"原文": line, "交回文件里": "（找不到这一段）"})
            continue
        new_marks = set(re.findall(r"\[[+-].*?[+-]\]", same)) - set(re.findall(r"\[[+-].*?[+-]\]", line))
        bold = re.findall(r"\*\*(.+?)\*\*", reject(line))
        row = {"原文": line}
        if new_marks:
            row.update({"交回文件里": same, "接受全部修订后": accept(same), "拒绝全部修订后和原文一致": reject(same) == reject(line)})
        else:
            row["交回文件里"] = "和原文完全一样" if same == line else same
            if same != line:
                untouched_changed.append(line[:30])
        if bold:
            row["原文加粗的字在交回文件里还加粗"] = {b: f"**{b}**" in same or any(f"**{b}**" in v for v in (accept(same), reject(same))) for b in bold}
        if reject(same) != reject(line):
            silent.append(line[:30])
        rows.append(row)
    def where(anchor: str) -> str:
        both = lambda l: re.sub(r"\[[+-]|[+-]\]", "", l).replace("**", "")  # deleted and inserted text kept side by side
        hits = [key(l) for l in d_body if anchor and anchor.replace("**", "")[:6] in "\n".join(
            (accept(l).replace("**", ""), reject(l).replace("**", ""), both(l)))]
        return "、".join(dict.fromkeys(hits)) or "找不到"
    new_comments = []
    for c in d_comments:
        if c in o_comments:
            continue
        m = re.match(r"【批注 #(.+?)】作者：(.*?)；批在：“(.*?)”；内容：(.*)$", c)
        new_comments.append({"作者": m.group(2), "批在": m.group(3), "批在哪一段": where(m.group(3)), "内容": m.group(4)} if m else c)
    return {
        "交回的文件名": got_name,
        "原文件名": name,
        "逐段对照": rows,
        "没有留痕、直接改了正文的段（拒绝全部修订后和原文不一致）": silent or "无",
        "没加修订却和原文不一样的段": untouched_changed or "无",
        "交回文件新加的修订（作者：内容）": [r for r in d_revs if r not in o_revs] or "无",
        "交回文件新加的批注": new_comments or "无",
        "原有的别人的修订还在不在": {r: r in d_revs for r in o_revs} or "原文没有",
        "原有的别人的批注还在不在": {c: c in d_comments for c in o_comments} or "原文没有",
        "交回文件段数 / 原文段数": f"{len(d_body)} / {len(o_body)}",
        "回复正文（除了交付文件以外的文字）": reply[:800],
    }


if __name__ == "__main__":
    import json
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from redline import review
    bank = {q["name"]: q for q in json.loads((Path(__file__).resolve().parent / "questions.json").read_text())}
    q = bank["t12"]
    name = next(n for n in q["files"] if n.endswith(".docx"))
    data = base64.b64decode(q["files"][name][7:])
    good = review(data, [("90 日", "15 日", "付款期改为 15 日。")], [("，乙方开具增值税普通发票。", "请写明含税口径。")], "光屿影像")
    got = measure(q, "改了 1 处，加了 2 条批注。\n\n【交付文件 活动拍摄合同.reviewed.docx（文字版）】\n" + docx_text(good))
    assert got["没有留痕、直接改了正文的段（拒绝全部修订后和原文不一致）"] == "无", got
    assert len(got["交回文件新加的批注"]) == 2 and got["交回文件新加的批注"][0]["批在哪一段"] == "| 付款说明", got
    assert got["原有的别人的修订还在不在"] == {"插入（作者：客户法务）：（含 2 套备选方案）": True}, got
    assert all(all(v.values()) for row in got["逐段对照"] for k, v in row.items() if k.startswith("原文加粗")), got
    silent = docx_text(good).replace("第一条 服务内容", "第一条 服务范围")
    assert got["回复正文（除了交付文件以外的文字）"] == "改了 1 处，加了 2 条批注。"
    bad = measure(q, "【交付文件 活动拍摄合同.reviewed.docx（文字版）】\n" + silent)
    assert bad["没加修订却和原文不一样的段"] != "无" and bad["没有留痕、直接改了正文的段（拒绝全部修订后和原文不一致）"] != "无", bad
    print("ok")
