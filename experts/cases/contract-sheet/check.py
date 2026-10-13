"""独立自检：只从工作规则和合同文字重算风险，再真实生成 xlsx/docx 验证 40 题均可交付。

此脚本不是验收器，不参与员工判卷；验收仍全部由 LLM 完成。uv run --no-project python check.py
"""

import base64
import importlib.util
import io
import json
import re
import sys
import zipfile
from fractions import Fraction
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "common"))
from officetext import docx_text, xlsx_text  # noqa: E402
from measure import measure  # noqa: E402

spec = importlib.util.spec_from_file_location("contract_review_redline", HERE.parent / "contract-review" / "redline.py")
redline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(redline)


def number(text: str) -> int:
    if text.isdigit():
        return int(text)
    digits = dict(zip("零一二三四五六七八九", range(10)))
    digits.update(dict(zip("零壹贰叁肆伍陆柒捌玖", range(10))))
    value = 0
    for part in re.split("[十拾]", text):
        if value == 0 and re.search("[十拾]", text):
            value = (digits[part] if part else 1) * 10
        else:
            value += digits[part] if part else 0
    return value


def rule_spec(rules: str) -> dict:
    lines = re.findall(r"^\d+\. ((?:R\d{3}|CG-\d{2}|XQ\d+) .+?)$", rules, re.M)
    order = ["prepay", "accept", "warranty", "penalty", "secret", "invoice"]
    codes = {kind: (line.split()[0], re.search(r"（([高中低])风险）", line).group(1)) for kind, line in zip(order, lines)}
    return {"codes": codes,
            "prepay": int(re.search(r"预付款不超过合同总价的 (\d+)%", rules).group(1)),
            "accept": int(re.search(r"验收期不少于 (\d+) 个工作日", rules).group(1)),
            "warranty": int(re.search(r"质保期不少于 (\d+) 个月", rules).group(1)),
            "penalty": Fraction(re.search(r"每日不低于合同总价的 ([.\d]+)%", rules).group(1))}


def clauses(text: str) -> dict[str, str]:
    out, appendix = {}, ""
    for line in text.replace("**", "").splitlines():
        if line.startswith("附件"):
            appendix = line.split()[0]
        main = re.match(r"(第[一二三四五六七八九十]+条)", line)
        sub = re.match(r"(\d+)\. ", line)
        if main:
            out[main.group(1)] = line
        elif sub and appendix:
            out[f"{appendix}第 {sub.group(1)} 条"] = line
    return out


def judge(rules: str, text: str) -> list[dict]:
    """数据独立来源：不导入 make.py，不读 reference 计算结果。"""
    policy, source = rule_spec(rules), clauses(text)
    places = {"prepay": "第三条", "accept": "第五条", "warranty": "第七条", "penalty": "第九条", "secret": "第十条", "invoice": "第四条"}
    labels = {"prepay": "付款", "accept": "验收", "warranty": "质保", "penalty": "逾期交货违约金", "secret": "保密", "invoice": "付款前开票"}
    rows = []
    for kind, (code, level) in policy["codes"].items():
        place = places[kind]
        quote = source.get(place)
        if quote and "按附件一执行" in quote:
            place, quote = "附件一第 2 条", source["附件一第 2 条"]
        issues = []
        if quote is None:
            place, quote = "缺失", "无"
            issues = [f"合同缺少{labels[kind]}条款"]
        elif kind == "prepay":
            pct = re.search(r"预付合同总价的\s*(?:百分之([一二三四五六七八九十]+)|(\d+)%)", quote)
            paid = number(pct.group(1) or pct.group(2))
            if paid > policy[kind]:
                issues.append(f"预付 {paid}%，超过 {policy[kind]}%")
            if "验收合格后" not in quote:
                issues.append("尾款按设备到货支付，没约定在验收合格后支付")
        elif kind == "accept":
            period = re.search(r"到货后\s*([0-9一二三四五六七八九十壹贰叁肆伍陆柒捌玖拾]+)\s*(个工作日|日|自然日|天)内", quote)
            days, unit = number(period.group(1)), period.group(2)
            working = Fraction(days) if unit == "个工作日" else Fraction(days * 5, 7)
            if working < policy[kind]:
                issues.append(f"验收期 {days} {unit}，折合 {float(working):.4f} 个工作日，少于 {policy[kind]} 个工作日")
            if "视为验收合格" in quote and "不视为验收合格" not in quote:
                issues.append("逾期未提出异议被视为验收合格")
        elif kind == "warranty":
            period = re.search(r"质保期(?:为)?\s*(半年|一年|\d+ 个月)", quote).group(1)
            months = {"半年": 6, "一年": 12}.get(period, int(period.split()[0]) if period[0].isdigit() else 0)
            start = re.search(r"自(.+?)起计算", quote).group(1)
            if months < policy[kind]:
                issues.append(f"质保 {months} 个月，少于 {policy[kind]} 个月")
            if start != "验收合格之日":
                issues.append(f"从{start}起算，不是从验收合格之日起算")
        elif kind == "penalty":
            rate = Fraction(re.search(r"的\s*([.\d]+)%\s*支付违约金", quote).group(1))
            if rate < policy[kind]:
                issues.append(f"违约金每日 {float(rate):g}%，低于 {float(policy[kind]):g}%")
        elif kind == "invoice":
            assert "付款前" in quote and "增值税专用发票" in quote, quote
        elif kind == "secret":
            assert "保密义务" in quote, quote
        if issues:
            rows.append({"编号": code, "等级": level, "条款位置": place, "合同原文": quote, "问题要点": issues})
    return rows


def spreadsheet(sheets: list[tuple[str, list[list]]]) -> bytes:
    """用标准 OOXML inlineStr 造真实工作簿，供正确样卷和探测使用。"""
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/package/2006/relationships"
    docrel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    files = {
        "_rels/.rels": f'<Relationships xmlns="{rel}"><Relationship Id="rId1" Type="{docrel}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<workbook xmlns="{ns}" xmlns:r="{docrel}"><sheets>' + ''.join(
            f'<sheet name={quoteattr(name)} sheetId="{i}" r:id="rId{i}"/>' for i, (name, _) in enumerate(sheets, 1)) + '</sheets></workbook>',
        "xl/_rels/workbook.xml.rels": f'<Relationships xmlns="{rel}">' + ''.join(
            f'<Relationship Id="rId{i}" Type="{docrel}/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(sheets) + 1)) + '</Relationships>',
    }
    overrides = '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    for i, (_, rows) in enumerate(sheets, 1):
        xml = [f'<worksheet xmlns="{ns}"><sheetData>']
        for row_no, row in enumerate(rows, 1):
            xml.append(f'<row r="{row_no}">')
            for col_no, value in enumerate(row):
                address = f"{chr(65 + col_no)}{row_no}"
                xml.append(f'<c r="{address}" t="inlineStr"><is><t xml:space="preserve">{escape(str(value))}</t></is></c>')
            xml.append('</row>')
        xml.append('</sheetData></worksheet>')
        files[f"xl/worksheets/sheet{i}.xml"] = ''.join(xml)
        overrides += f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    files["[Content_Types].xml"] = ('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                                   '<Default Extension="xml" ContentType="application/xml"/>' + overrides + '</Types>')
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as box:
        for name, value in files.items():
            box.writestr(name, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + value)
    return out.getvalue()


def output(q: dict, rows: list[list], *, notes=None, author=None, reply=None, sheet_names=None) -> tuple[str, bytes, bytes]:
    """rows 是手写六列或参考答案的六列；所有外观参数均从员工的规则读。"""
    rules = q["files"]["工作规则.md"]
    original_name = next(name for name in q["files"] if name.endswith(".docx"))
    source = base64.b64decode(q["files"][original_name][7:])
    original = docx_text(source)
    title = re.search(r"^\*\*(《.+?》)\*\*$", original, re.M).group(1)
    names = re.findall(r'Sheet 名为“(.+?)”', rules)
    header = re.search(r"列和顺序固定为：(.*?)。", rules).group(1).split(" | ")
    basis = re.search(r'审查依据（写“(.+?)”', rules).group(1)
    file_name = re.search(r'Excel 风险清单，文件名“(.+?)”', rules).group(1)
    suffix = re.search(r'去掉“\.docx”后加“(.+?)”', rules).group(1)
    writer = author if author is not None else re.search(r'作者写“(.+?)”', rules).group(1)
    high = sum(row[4] == "高" for row in rows)
    info = [["项目", "内容"], ["合同名称", title], ["审查依据", basis], ["风险项数", len(rows)],
            ["审查结论", "需修改后签署" if rows else "可以签署"]]
    names = sheet_names or names
    book = spreadsheet([(names[0], [header, *rows]), (names[1], info)])
    if notes is None:
        notes = [(title if row[1] == "缺失" else "2. " if row[1].startswith("附件") else row[1], f"{row[0]}：{row[3]}") for row in rows]
    reviewed = redline.review(source, [], notes, writer)
    summary = reply if reply is not None else f"报了 {len(rows)} 项风险，其中 {high} 项高风险。"
    product = summary + f"\n\n【交付文件 {file_name}（文字版）】\n" + xlsx_text(book)
    product += f"\n\n【交付文件 {original_name[:-5] + suffix}（文字版）】\n" + docx_text(reviewed)
    return product, book, reviewed


def main() -> None:
    bank = json.loads((HERE / "questions.json").read_text())
    wrong, checked = [], 0
    stats = {"附件风险": 0, "两条以上缺失": 0, "自然日": 0, "中文数值": 0}
    assert [number(n) for n in ("叁拾", "拾肆", "贰拾壹", "五十", "九", "10")] == [30, 14, 21, 50, 9, 10]
    for q in bank:
        rules, ref = q["files"]["工作规则.md"], q["reference"]
        file_name = next(name for name in q["files"] if name.endswith(".docx"))
        text = docx_text(base64.b64decode(q["files"][file_name][7:]))
        mine = judge(rules, text)
        theirs = [{k: row[k] for k in ("编号", "等级", "条款位置", "合同原文", "问题要点")} for row in ref["该报的风险（一条一行）"]]
        if mine != theirs:
            wrong.append((q["name"], "risk", mine, theirs))
        for key, got in (("风险项数", len(mine)), ("其中高风险", sum(row["等级"] == "高" for row in mine))):
            if ref[key] != got:
                wrong.append((q["name"], key, ref[key], got))
        # 单独检验每一条参考建议：全部代入合同后应不再触发任何采购清单问题。
        corrected = text.replace("**", "")
        policy = rule_spec(rules)
        positions = dict(zip((value[0] for value in policy["codes"].values()),
                             ("第三条", "第五条", "第七条", "第九条", "第十条", "第四条")))
        for row in ref["该报的风险（一条一行）"]:
            prefix = "2." if row["条款位置"].startswith("附件") else positions[row["编号"]]
            replacement = prefix + " " + row["合规改法示例"]
            corrected = (corrected + "\n" + replacement) if row["条款位置"] == "缺失" else corrected.replace(row["合同原文"], replacement)
        if judge(rules, corrected):
            wrong.append((q["name"], "suggestions", judge(rules, corrected)))
        rows = [[row["编号"], row["条款位置"], row["合同原文"], row["为什么"], row["等级"], row["合规改法示例"]]
                for row in ref["该报的风险（一条一行）"]]
        product, _, _ = output(q, rows)
        got = measure(q, product)
        doc = got["Word 文件"][0]
        checks = [not doc["文字差异"], not doc["文字相同段落的加粗差异"], not doc["修订记录"], doc["正文里的修订标记数"] == 0,
                  doc["批注数"] == len(mine), got["回复句数"] == 1,
                  [row["列值"] for row in got["Excel 文件"][0]["各 Sheet"][0]["各行"][1:]] == rows]
        for row, comment in zip(rows, doc["批注"]):
            checks.extend([comment["提到的清单编号"] == [row[0]],
                           comment["锚点所在位置"] == ["合同标题" if row[1] == "缺失" else row[1]],
                           comment["作者"] == ref["批注作者"]])
        if not all(checks):
            wrong.append((q["name"], "deliverable", checks, got))
        stats["附件风险"] += any(row[1].startswith("附件") for row in rows)
        stats["两条以上缺失"] += sum(row[1] == "缺失" for row in rows) >= 2
        stats["自然日"] += bool(re.search(r"到货后 [\d拾叁贰玖柒伍肆壹陆捌 ]+[日天]内完成验收", text))
        stats["中文数值"] += bool(re.search(r"百分之|[叁拾伍贰玖]日|半年|一年", text))
        # 对真实生成的交付故意改正文、去掉金额加粗，确认测量能看到变化。
        changed = product.replace("第一条 乙方向甲方供应", "第一条 乙方向甲方免费赠送")
        assert measure(q, changed)["Word 文件"][0]["文字差异"]
        if q["segment"] == "edge":
            lost_bold = product.replace("**", "")
            assert measure(q, lost_bold)["Word 文件"][0]["文字相同段落的加粗差异"]
        assert measure(q, "没有交付文件。")["交回文件名"] == []
        checked += 1
    assert checked == 40 and all(stats.values()), stats
    # 9 与 10 自然日一进一出，避免“还有默认验收问题”掩盖换算边界。
    for name, new, delta in (("y06", "10 日", -1), ("y08", "9 日", 1)):
        q = next(q for q in bank if q["name"] == name)
        text = q["reference"]["原文的文字版"]
        span = re.search(r"到货后\s*([\d拾玖 ]+日)内完成验收", text)
        assert span, (name, text)
        before = judge(q["files"]["工作规则.md"], text)
        after = judge(q["files"]["工作规则.md"], text[:span.start(1)] + new + text[span.end(1):])
        assert len(after) - len(before) == delta, (name, before, after)
    print("mismatches:", wrong or "none")
    print("40 real xlsx/docx pairs verified; coverage:", stats)
    assert not wrong


if __name__ == "__main__":
    main()
