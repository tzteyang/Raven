"""给生成的合同 .docx 加 Word 修订和批注（只用标准库），用来做探测答卷和自检：

  review(data, edits, notes, author) -> bytes
    edits: [(原文片段, 改成, 批注)]，原文片段要整个落在某一个文字块（run）里；改成写 "" 就是只删
    notes: [(批在哪段文字上, 批注)]，只加批注、不改原文
已有的修订、批注、加粗都原样保留：只拆开要改的那个 run，前后两截沿用它原来的格式。
"""

import io
import re
import zipfile
from xml.sax.saxutils import escape

RUN = re.compile(r'<w:r>(<w:rPr>.*?</w:rPr>)?<w:t xml:space="preserve">([^<]*)</w:t></w:r>')
NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')


def _find(xml: str, text: str):
    for m in RUN.finditer(xml):
        if text in m.group(2).replace("&amp;", "&"):
            return m
    raise ValueError(f"no single run holds {text!r}")


def review(data: bytes, edits, notes, author: str) -> bytes:
    src = zipfile.ZipFile(io.BytesIO(data))
    files = {name: src.read(name) for name in src.namelist()}
    xml = files["word/document.xml"].decode()
    old_comments = files.get("word/comments.xml", b"").decode()
    ids = [int(i) for i in re.findall(r'w:comment w:id="(\d+)"', old_comments)]
    next_id, new_comments, rev = (max(ids) + 1 if ids else 0) + 100, [], 500
    for old, new, comment in edits:
        m = _find(xml, escape(old))
        props, text = m.group(1) or "", m.group(2)
        before, after = text.split(escape(old), 1)
        cid = next_id
        next_id += 1
        rev += 2
        piece = (f'<w:r>{props}<w:t xml:space="preserve">{before}</w:t></w:r>' if before else "")
        piece += f'<w:commentRangeStart w:id="{cid}"/>'
        piece += (f'<w:del w:id="{rev}" w:author="{author}" w:date="2026-10-11T10:00:00Z"><w:r>{props}'
                  f'<w:delText xml:space="preserve">{escape(old)}</w:delText></w:r></w:del>')
        if new:
            piece += (f'<w:ins w:id="{rev + 1}" w:author="{author}" w:date="2026-10-11T10:00:00Z"><w:r>{props}'
                      f'<w:t xml:space="preserve">{escape(new)}</w:t></w:r></w:ins>')
        piece += f'<w:commentRangeEnd w:id="{cid}"/><w:r><w:commentReference w:id="{cid}"/></w:r>'
        piece += (f'<w:r>{props}<w:t xml:space="preserve">{after}</w:t></w:r>' if after else "")
        xml = xml[:m.start()] + piece + xml[m.end():]
        new_comments.append((cid, comment))
    for anchor, comment in notes:
        m = _find(xml, escape(anchor))
        cid = next_id
        next_id += 1
        xml = (xml[:m.start()] + f'<w:commentRangeStart w:id="{cid}"/>' + m.group(0) + f'<w:commentRangeEnd w:id="{cid}"/>'
               f'<w:r><w:commentReference w:id="{cid}"/></w:r>' + xml[m.end():])
        new_comments.append((cid, comment))
    files["word/document.xml"] = xml.encode()
    body = "".join(f'<w:comment w:id="{cid}" w:author="{author}" w:date="2026-10-11T10:00:00Z" w:initials="SH"><w:p><w:r>'
                   f'<w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p></w:comment>' for cid, text in new_comments)
    if old_comments:
        files["word/comments.xml"] = old_comments.replace("</w:comments>", body + "</w:comments>").encode()
    else:
        files["word/comments.xml"] = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:comments {NS}>{body}</w:comments>'.encode()
        rels = files["word/_rels/document.xml.rels"].decode().replace(
            "</Relationships>", '<Relationship Id="rIdComments" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" '
            'Target="comments.xml"/></Relationships>')
        files["word/_rels/document.xml.rels"] = rels.encode()
        types = files["[Content_Types].xml"].decode().replace(
            "</Types>", '<Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.'
            'wordprocessingml.comments+xml"/></Types>')
        files["[Content_Types].xml"] = types.encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as box:
        for name, content in files.items():
            box.writestr(name, content)
    return out.getvalue()
