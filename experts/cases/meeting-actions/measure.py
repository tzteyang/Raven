"""评审用的测量值：员工回复里的段名（按顺序）；每段本身的字数（只算段名、表格行、“需确认”那种条目和“无”）和合计；
两段以外的文字（第一个段名之前的、段里表格和条目以外的）逐行列出并给出每行字数，评审据此把多出来的行扣掉；每张表的
表头和行数；交付的文件。字数都不算空格和换行。只作评审依据，判定由评审做。"""

import re

SEPARATOR = re.compile(r":?-{2,}:?")
ENTRY = re.compile(r"^[-*]\s*(负责人|截止日期)待确认\s*[:：]")


def chars(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def measure(question: dict, product: str) -> dict:
    reply = product.split("【交付文件", 1)[0]
    own, extra, tables, current, section = {}, [], [], None, None
    for line in reply.splitlines():
        text = line.strip()
        header = re.match(r"##(?!#)\s*(.+)", text)
        if header:
            section = header.group(1).strip()
            own[section] = own.get(section, 0) + chars(text)
            current = None
            continue
        if not text.startswith("|"):
            current = None
        if not text:
            continue
        if text.startswith("|"):
            cells = [c.strip() for c in text.strip("|").split("|")]
            if current is None:
                current = []
                tables.append(current)
            if not all(SEPARATOR.fullmatch(c) for c in cells):
                current.append(cells)
        if section is not None and (text.startswith("|") or re.fullmatch(r"无[。.]?", text) or ENTRY.match(text)):
            own[section] += chars(text)
        else:
            extra.append(f"{text}（{chars(text)} 字）")
    found = {
        "交付里的段名（按顺序）": re.findall(r"^\s*##(?!#)\s*(.+?)\s*$", reply, re.M),
        "每段本身的字数（只算段名、表格行、需确认条目和“无”）": own or "没有以“## ”开头的段",
        "两段本身字数合计": sum(own.values()),
        "这套规则的字数上限（只算两段本身）": question["reference"]["格式"]["字数上限"],
        "两段以外多出来的文字（逐行，括号里是这一行的字数；这些行不算进两段本身）": extra or "无",
        "交付的文件": re.findall(r"【交付文件 (.+?)】", product) or "无",
    }
    for i, rows in enumerate(tables, 1):
        found[f"第 {i} 张表"] = {"表头": rows[0], "表头以外的行数": len(rows) - 1}
    return found


if __name__ == "__main__":
    q = {"reference": {"格式": {"字数上限": 300}}}
    got = measure(q, "好的，整理如下：\n## 待办\n\n| 负责人 | 事项 | 截止日期 |\n|---|---|---|\n| 王磊 | 改活动页 | 待定 |\n\n"
                     "## 待认领\n\n无\n\n说明：数据看板已撤回。\n\n【交付文件 todo.md】\n- 改活动页")
    assert got["交付里的段名（按顺序）"] == ["待办", "待认领"], got
    assert got["每段本身的字数（只算段名、表格行、需确认条目和“无”）"] == {"待办": 4 + 13 + 13 + 12, "待认领": 5 + 1}, got
    assert got["两段本身字数合计"] == 48, got
    assert got["两段以外多出来的文字（逐行，括号里是这一行的字数；这些行不算进两段本身）"] == [
        "好的，整理如下：（8 字）", "说明：数据看板已撤回。（11 字）"], got
    assert got["第 1 张表"] == {"表头": ["负责人", "事项", "截止日期"], "表头以外的行数": 1}, got
    assert got["交付的文件"] == ["todo.md"], got
    r2 = measure(q, "## 行动项\n\n| 序号 | 事项 | 负责人 | 截止日期 |\n|---|---|---|---|\n| 1 | 改详情页 | 张伟（市场部） | 待定 |\n\n"
                    "## 需确认\n\n- 截止日期待确认：改详情页\n- 注：以上已核对")
    assert r2["两段以外多出来的文字（逐行，括号里是这一行的字数；这些行不算进两段本身）"] == ["- 注：以上已核对（8 字）"], r2
    print("ok")
