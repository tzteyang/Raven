"""只提供评审依据：解析 Excel 文字版、比对 Word 原文与格式、列出批注和锚点；不产生合格判定。"""

import base64
import difflib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))
from officetext import docx_text  # noqa: E402

DELIVERED = re.compile(r"^【交付文件 (.+?)】\n(.*?)(?=^【交付文件 |\Z)", re.M | re.S)
SHEET = re.compile(r"^## Sheet：(.*)$", re.M)
CELL = re.compile(r"(?:^|\n| \| )([A-Z]+)([1-9]\d*)=", re.M)
COMMENT = re.compile(r"^【批注 #(.+?)】作者：(.*?)；批在：“(.*?)”；内容：(.*)$", re.M)
CODE = re.compile(r"\b(?:R\d{3}|CG-\d{2}|XQ\d+)\b")


def sentences(text: str) -> int:
    return sum(bool(re.search(r"\w", part)) for part in re.split(r"[。！？!?]+", text))


def column(name: str) -> int:
    out = 0
    for char in name:
        out = out * 26 + ord(char) - ord("A") + 1
    return out


def workbook(text: str) -> list[dict]:
    """保留 Sheet 和物理行列；空行号或空单元格不能被压缩成正常结构。"""
    found = list(SHEET.finditer(text))
    out = []
    for i, part in enumerate(found):
        section = text[part.end():found[i + 1].start() if i + 1 < len(found) else len(text)].strip("\n")
        cells = list(CELL.finditer(section))
        rows = {}
        for j, cell in enumerate(cells):
            col_name, row_no = cell.group(1), int(cell.group(2))
            value = section[cell.end():cells[j + 1].start() if j + 1 < len(cells) else len(section)].rstrip("\n")
            rows.setdefault(row_no, {})[col_name] = value
        values = []
        for row_no, row in sorted(rows.items()):
            width = max(column(col) for col in row)
            ordered = [""] * width
            for col_name, value in row.items():
                ordered[column(col_name) - 1] = value
            values.append({"行号": row_no, "列值": ordered, "单元格": {f"{col}{row_no}": value for col, value in row.items()}})
        out.append({"Sheet 名": part.group(1), "各行": values, "第一行表头": next((r["列值"] for r in values if r["行号"] == 1), []),
                    "非空数据行数": sum(r["行号"] > 1 and any(str(v).strip() for v in r["列值"]) for r in values)})
    return out


def body(text: str) -> list[str]:
    part = re.split(r"\n\n—— (?:批注|修订) ——", text, maxsplit=1)[0]
    return [line for line in part.splitlines() if line.strip()]


def plain(text: str) -> str:
    return text.replace("**", "")


def bold_positions(text: str) -> list[tuple[int, int]]:
    """加粗文本拆成多个连续 run 时，其加粗区间仍一致。"""
    parts = text.split("**")
    at, spans = 0, []
    for i, part in enumerate(parts):
        if i % 2 and part:
            if spans and spans[-1][1] == at:
                spans[-1] = (spans[-1][0], at + len(part))
            else:
                spans.append((at, at + len(part)))
        at += len(part)
    return spans


def locations(lines: list[str]) -> list[dict]:
    out, annex = [], ""
    for number, line in enumerate(lines, 1):
        text = plain(line)
        appendix = re.match(r"(附件[一二三四五六七八九十]+)", text)
        clause = re.match(r"(第[一二三四五六七八九十百]+条)", text)
        subclause = re.match(r"(\d+)\.", text)
        if appendix:
            annex = appendix.group(1)
        if text.startswith("《"):
            place = "合同标题"
        elif clause:
            place = clause.group(1)
        elif subclause and annex:
            place = f"{annex}第 {subclause.group(1)} 条"
        elif text.startswith("【页眉】"):
            place = "页眉"
        else:
            place = f"第 {number} 段"
        out.append({"位置": place, "文字": text, "段号": number})
    return out


def word(original: str, delivered: str) -> dict:
    before, after = body(original), body(delivered)
    original_plain, delivered_plain = list(map(plain, before)), list(map(plain, after))
    changes, format_changes = [], []
    for tag, a, b, c, d in difflib.SequenceMatcher(a=original_plain, b=delivered_plain, autojunk=False).get_opcodes():
        if tag != "equal":
            changes.append({"原文起始段": a + 1, "交回起始段": c + 1, "原文": before[a:b], "交回": after[c:d]})
        else:
            for left, right in zip(range(a, b), range(c, d)):
                if bold_positions(before[left]) != bold_positions(after[right]):
                    format_changes.append({"段号": left + 1, "原文": before[left], "交回": after[right]})
    marked = locations(after)
    comments = []
    for cid, author, anchor, text in COMMENT.findall(delivered):
        match = plain(anchor)
        places = [row["位置"] for row in marked if match and match in row["文字"]]
        comments.append({"id": cid, "作者": author, "锚点原文": anchor, "锚点所在位置": places,
                         "内容": text, "提到的清单编号": CODE.findall(text)})
    revisions = re.findall(r"^(?:插入|删除)（作者：.*$", delivered, re.M)
    return {"原文段数": len(before), "交回段数": len(after), "文字差异": changes,
            "文字相同段落的加粗差异": format_changes, "修订记录": revisions,
            "正文里的修订标记数": len(re.findall(r"\[(?:\+.*?\+|-.*?-)]", "\n".join(after))),
            "批注数": len(comments), "批注": comments,
            "未能解析的批注行": [line for line in delivered.splitlines() if line.startswith("【批注 #") and not COMMENT.fullmatch(line)],
            "交回正文各段": marked}


def measure(question: dict, product: str) -> dict:
    found = [(name.removesuffix("（文字版）"), text.rstrip()) for name, text in DELIVERED.findall(product)]
    reply = DELIVERED.sub("", product).strip()
    original_name = next(name for name in question["files"] if name.endswith(".docx"))
    original = docx_text(base64.b64decode(question["files"][original_name][len("base64:"):]))
    books, documents = [], []
    for name, text in found:
        if name.lower().endswith(".xlsx"):
            sheets = workbook(text)
            books.append({"文件名": name, "Sheet 名和顺序": [s["Sheet 名"] for s in sheets], "各 Sheet": sheets})
        elif name.lower().endswith(".docx"):
            documents.append({"文件名": name, **word(original, text)})
    return {"交回文件名": [name for name, _ in found], "Excel 文件": books, "Word 文件": documents,
            "回复正文（不含文件）": reply, "回复句数": sentences(reply),
            "回复逐行": [{"文字": line, "句数": sentences(line)} for line in reply.splitlines() if line.strip()]}


if __name__ == "__main__":
    assert sentences('“共发现 4 项风险，其中 1 项高风险。”') == 1
    assert sentences('（**报了 3 项风险，其中 2 项高风险！**）') == 1
    assert sentences('已核对。\n“共发现 4 项风险，其中 1 项高风险。”') == 2
    assert bold_positions('甲**合同总价**乙') == bold_positions('甲**合同****总价**乙')
    demo = workbook('## Sheet：风险项\nA1=编号 | B1=条款位置\nA2=R001 | B2=第三条\nA4=R003 | C4=含\n换行和 | 分隔符\n## Sheet：审查说明\nA1=项目 | B1=内容')
    assert demo[0]["各行"][2]["行号"] == 4
    assert demo[0]["各行"][2]["列值"] == ['R003', '', '含\n换行和 | 分隔符']
    assert demo[0]["非空数据行数"] == 2
    assert word('**《采购合同》**\n第五条 验收。', '**《采购合同》**\n第五条 验收。')["文字差异"] == []
    assert word('**《采购合同》**\n第五条 验收。', '《采购合同》\n第五条 验收。')["文字相同段落的加粗差异"]
    print("ok")
