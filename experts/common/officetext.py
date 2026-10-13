"""Word 和 Excel 文件的文字版，给评审和测量值看（只用标准库）。

docx：按顺序列出页眉、正文段落和表格（表格一行一行，单元格之间用 “ | ” 隔开），修订写成 [+插入的字+] 和 [-删除的字-]，
加粗写成 **字**；批注列在文末，带编号、作者、批在哪段文字上、批注内容。xlsx：每个 Sheet 一节，一行一行列出单元格的值。

  docx_text(data: bytes) -> str
  xlsx_text(data: bytes) -> str
  render(name: str, data: bytes) -> str | None     按扩展名选上面两个，别的返回 None
"""

import io
import re
import zipfile
from xml.etree import ElementTree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
BINARY = "base64:"


def _runs(node, state: dict) -> str:
    """The text under a paragraph-level node, with revisions and bold marked and comment anchors collected."""
    out = []
    for child in node:
        tag = child.tag
        if tag == W + "r":
            bold = child.find(f"{W}rPr/{W}b")
            on = bold is not None and bold.get(W + "val", "true") not in ("0", "false")
            text = "".join((t.text or "") if t.tag in (W + "t", W + "delText") else "\t" if t.tag == W + "tab" else ""
                           for t in child.iter())
            text = f"**{text}**" if on and text.strip() else text
            out.append(text)
            for cid in state["open"]:
                state["anchor"][cid] = state["anchor"].get(cid, "") + re.sub(r"\*\*", "", text)
        elif tag == W + "ins":
            text = _runs(child, state)
            state["revisions"].append(f"插入（作者：{child.get(W + 'author', '')}）：{text}")
            out.append(f"[+{text}+]")
        elif tag == W + "del":
            text = _runs(child, state)
            state["revisions"].append(f"删除（作者：{child.get(W + 'author', '')}）：{text}")
            out.append(f"[-{text}-]")
        elif tag == W + "commentRangeStart":
            state["open"].add(child.get(W + "id"))
        elif tag == W + "commentRangeEnd":
            state["open"].discard(child.get(W + "id"))
        elif tag in (W + "hyperlink", W + "smartTag", W + "sdt", W + "sdtContent", W + "fldSimple"):
            out.append(_runs(child, state))
    return "".join(out)


def _block(node, state: dict, lines: list[str]) -> None:
    for child in node:
        if child.tag == W + "p":
            lines.append(_runs(child, state))
        elif child.tag == W + "tbl":
            for row in child.iter(W + "tr"):
                cells = [" ".join(_runs(p, state) for p in cell.iter(W + "p")) for cell in row.findall(W + "tc")]
                lines.append("| " + " | ".join(cells) + " |")
        elif child.tag in (W + "sdt", W + "sdtContent", W + "customXml"):
            _block(child, state, lines)


def docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as box:
        names = box.namelist()
        state = {"open": set(), "anchor": {}, "revisions": []}
        parts = []
        for header in sorted(n for n in names if re.fullmatch(r"word/header\d*\.xml", n)):
            lines = []
            _block(ElementTree.fromstring(box.read(header)), state, lines)
            if any(l.strip() for l in lines):
                parts.append("【页眉】" + " / ".join(l for l in lines if l.strip()))
        body = ElementTree.fromstring(box.read("word/document.xml")).find(W + "body")
        lines = []
        _block(body, state, lines)
        parts += [l for l in lines if l.strip()]
        if "word/comments.xml" in names:
            notes = []
            for comment in ElementTree.fromstring(box.read("word/comments.xml")).findall(W + "comment"):
                cid = comment.get(W + "id")
                text = " ".join(_runs(p, {"open": set(), "anchor": {}, "revisions": []}) for p in comment.iter(W + "p")).strip()
                where = state["anchor"].get(cid, "")
                notes.append(f"【批注 #{cid}】作者：{comment.get(W + 'author', '')}；批在：“{where.strip()}”；内容：{text}")
            if notes:
                parts += ["", "—— 批注 ——"] + notes
        if state["revisions"]:
            parts += ["", "—— 修订 ——"] + state["revisions"]
        return "\n".join(parts)


def xlsx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as box:
        names = box.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            for item in ElementTree.fromstring(box.read("xl/sharedStrings.xml")).findall(S + "si"):
                shared.append("".join(t.text or "" for t in item.iter(S + "t")))
        rels = {r.get("Id"): r.get("Target") for r in ElementTree.fromstring(box.read("xl/_rels/workbook.xml.rels"))
                .findall(REL + "Relationship")}
        out = []
        for sheet in ElementTree.fromstring(box.read("xl/workbook.xml")).iter(S + "sheet"):
            target = rels[sheet.get(R + "id")].lstrip("/")
            path = target if target.startswith("xl/") else "xl/" + target
            out.append(f"## Sheet：{sheet.get('name')}")
            for row in ElementTree.fromstring(box.read(path)).iter(S + "row"):
                values = []
                for cell in row.findall(S + "c"):
                    kind, value = cell.get("t"), cell.find(S + "v")
                    if kind == "s" and value is not None:
                        text = shared[int(value.text)]
                    elif kind == "inlineStr":
                        text = "".join(t.text or "" for t in cell.iter(S + "t"))
                    else:
                        text = value.text if value is not None else ""
                    values.append(f"{cell.get('r')}={text}")
                if values:
                    out.append(" | ".join(values))
        return "\n".join(out)


def render(name: str, data: bytes) -> str | None:
    lower = name.lower()
    try:
        if lower.endswith(".docx"):
            return docx_text(data)
        if lower.endswith(".xlsx"):
            return xlsx_text(data)
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        return f"（{name} 打不开：{type(exc).__name__}: {exc}）"
    return None


def _demo_docx() -> bytes:
    body = (
        f'<w:document xmlns:w="{W[1:-1]}"><w:body>'
        '<w:p><w:r><w:t>第三条 合同总价为人民币</w:t></w:r><w:r><w:rPr><w:b/></w:rPr><w:t>伍万元</w:t></w:r><w:r><w:t>整。</w:t></w:r></w:p>'
        '<w:p><w:commentRangeStart w:id="0"/><w:r><w:t>第四条 甲方在收到全部设计稿后</w:t></w:r>'
        '<w:del w:author="青禾工作室"><w:r><w:delText>90</w:delText></w:r></w:del>'
        '<w:ins w:author="青禾工作室"><w:r><w:t>30</w:t></w:r></w:ins><w:r><w:t> 日内支付。</w:t></w:r><w:commentRangeEnd w:id="0"/></w:p>'
        '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>项目</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>金额</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
        '</w:body></w:document>')
    comments = (f'<w:comments xmlns:w="{W[1:-1]}"><w:comment w:id="0" w:author="青禾工作室">'
                '<w:p><w:r><w:t>付款期不超过 30 天。</w:t></w:r></w:p></w:comment></w:comments>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as box:
        box.writestr("word/document.xml", body)
        box.writestr("word/comments.xml", comments)
    return buf.getvalue()


if __name__ == "__main__":
    text = docx_text(_demo_docx())
    assert "**伍万元**" in text and "[-90-][+30+]" in text and "| 项目 | 金额 |" in text, text
    assert "【批注 #0】作者：青禾工作室；批在：“第四条 甲方在收到全部设计稿后9030 日内支付。”" in text, text
    assert "删除（作者：青禾工作室）：90" in text and "插入（作者：青禾工作室）：30" in text, text
    print("ok")
