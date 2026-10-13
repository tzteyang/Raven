"""合同留痕审稿：三套工作规则、40 道题（20 培养 + 10 道同规则考试 + 10 道换规则考试）、参考答案和 Studio 场景包。

  python3 make.py

依据《专家自进化》8.1 的案例改写成「工作规则随题交给员工」：设计和创意工作室（乙方）收到客户发来的服务合同 .docx，要在原文上
用 Word 修订和批注审，交回审过的 Word 文件。口径不同（付款期、修改轮数、作品使用权、争议解决、含税和发票、署名）。培养题和同规则
考试题用 R1（青禾工作室）、R2（光屿影像）交替，换规则考试题全用员工从没见过的 R3（木棉品牌顾问：多一条违约金上限、批注开头
写规则编号）。每题一份合同按种子生成（标准库手写 OOXML：页眉、条款段落、报价表）：常见题要改的文字都在普通段落里；边界题要改的
那段里金额加粗、付款条款写在报价表里、客户已经留过修订和批注（要原样保留）。每题有几条本来就合规的条款（不能改、不能批）。参考
答案逐条写出该改什么、改成什么、哪些只批注、哪些不能动；check.py 只读员工看到的文件另判一遍。
"""

import base64
import io
import json
import random
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "wkr-contract-review"
sys.path.insert(0, str(HERE.parents[1] / "common"))
from officetext import docx_text  # noqa: E402

RULES = {
    "R1": {
        "studio": "青禾工作室", "pay": 30, "rounds": 3, "venue": "杭州市西湖区人民法院", "venue_kind": "court",
        "keep": "乙方有权将本项目设计成果用于作品集展示", "invoice": False, "cap": None, "tag": False,
        "text": """# 青禾工作室 · 合同审稿工作规则

客户发来的合同，按下面的规则在原文上审，交回审过的 Word 文件。

1. 所有改动都用 Word 的修订痕迹（插入、删除）留在原文上，不直接改正文；每处修订配一条批注，批在改动的那句话上，写清问题和理由。
2. 金额条款必须写明是否含税：合同总价那一条没写含不含税的，在那一条加一条批注，提示写明含税口径（只加批注，不改原文）；写了的不用管。
3. 付款期不超过 30 天：付款期超过 30 天的，把天数改成 30。修改不超过 3 轮：写着“无条件修改”“修改至甲方满意”这类不设上限的，把这句改成“乙方提供不超过 3 轮修改”。
4. 保留把作品放进作品集的权利：知识产权条款里禁止乙方展示的话删掉，补上“乙方有权将本项目设计成果用于作品集展示”。
5. 争议由杭州市西湖区人民法院管辖：争议解决条款写的不是由这家法院管辖的（写的是别的法院，或者写的是仲裁），把这句改成“由杭州市西湖区人民法院管辖”。
6. 修订和批注的作者都写“青禾工作室”。

补充口径：

- 只改上面几条要求改的地方：别的段落一个字都不动；同一段里不需要改的文字和格式（例如加粗的金额）保持原样；页眉、条款编号和报价表里不需要改的内容保持原样。要改的条款写在报价表里的，就在表格里改。
- 合同里已有的修订和批注（别人留的）原样保留，不接受也不拒绝。
- 已经符合规则的条款不改、不批注（例如付款期本来就不超过 30 天）。
- 交回的文件名是原文件名去掉“.docx”后加“.reviewed.docx”（例如“设计服务合同.docx”交回“设计服务合同.reviewed.docx”），不覆盖原文件。
- 回复里只写一句话：改了几处（修订）、加了几条批注。一处改动先删后插算一处修订。
""",
    },
    "R2": {
        "studio": "光屿影像", "pay": 15, "rounds": 2, "venue": "上海仲裁委员会", "venue_kind": "arbitration",
        "keep": "乙方保留署名权，并有权将本项目成果用于作品集展示", "invoice": True, "cap": None, "tag": False,
        "text": """# 光屿影像 · 合同审稿工作规则

客户发来的合同，按下面的规则在原文上审，交回审过的 Word 文件。

1. 所有改动都用 Word 的修订痕迹（插入、删除）留在原文上，不直接改正文；每处修订配一条批注，批在改动的那句话上，写清问题和理由。
2. 金额条款必须写明是否含税、开什么发票：合同总价那一条没写含不含税，或者没写发票类型的，在那一条加一条批注，提示补上缺的那项（只加批注，不改原文）；两项都写了的不用管。
3. 付款期不超过 15 天：付款期超过 15 天的，把天数改成 15。修改不超过 2 轮：写着“无条件修改”“修改至甲方满意”这类不设上限的，或者写的轮数超过 2 轮的，把这句改成“乙方提供不超过 2 轮修改”。
4. 保留署名权和作品集展示权：知识产权条款里禁止乙方署名或展示的话删掉，补上“乙方保留署名权，并有权将本项目成果用于作品集展示”。
5. 争议提交上海仲裁委员会仲裁：争议解决条款写的是法院管辖或者别的仲裁机构的，改成“提交上海仲裁委员会仲裁”。
6. 修订和批注的作者都写“光屿影像”。

补充口径：

- 只改上面几条要求改的地方：别的段落一个字都不动；同一段里不需要改的文字和格式（例如加粗的金额）保持原样；页眉、条款编号和报价表里不需要改的内容保持原样。要改的条款写在报价表里的，就在表格里改。
- 合同里已有的修订和批注（别人留的）原样保留，不接受也不拒绝。
- 已经符合规则的条款不改、不批注（例如付款期本来就不超过 15 天）。
- 交回的文件名是原文件名去掉“.docx”后加“.reviewed.docx”（例如“拍摄服务合同.docx”交回“拍摄服务合同.reviewed.docx”），不覆盖原文件。
- 回复里只写一句话：改了几处（修订）、加了几条批注。一处改动先删后插算一处修订。
""",
    },
    "R3": {
        "studio": "木棉品牌顾问", "pay": 20, "rounds": 3, "venue": "杭州市上城区人民法院", "venue_kind": "court",
        "keep": "乙方有权将本项目成果用于作品集展示", "invoice": False, "cap": 20, "tag": True,
        "text": """# 木棉品牌顾问 · 合同审稿工作规则

客户发来的合同，按下面的规则在原文上审，交回审过的 Word 文件。

1. 所有改动都用 Word 的修订痕迹（插入、删除）留在原文上，不直接改正文；每处修订配一条批注，批在改动的那句话上，写清问题和理由。
2. 金额条款必须写明是否含税：合同总价那一条没写含不含税的，在那一条加一条批注，提示写明含税口径（只加批注，不改原文）；写了的不用管。
3. 付款期不超过 20 天：付款期超过 20 天的，把天数改成 20。修改不超过 3 轮：写着“无条件修改”“修改至甲方满意”这类不设上限的，或者写的轮数超过 3 轮的，把这句改成“乙方提供不超过 3 轮修改”。
4. 保留把作品放进作品集的权利：知识产权条款里禁止乙方展示的话删掉，补上“乙方有权将本项目成果用于作品集展示”。
5. 争议由杭州市上城区人民法院管辖：争议解决条款写的不是由这家法院管辖的（写的是别的法院，或者写的是仲裁），把这句改成“由杭州市上城区人民法院管辖”。
6. 乙方违约金累计不超过合同总价的 20%：违约责任条款里乙方的违约金没有写上限、或者上限超过 20% 的，在那一条末尾补上（或把上限改成）“乙方累计违约金不超过合同总价的 20%”。
7. 每条批注开头写这条批注依据的规则编号，例如“【规则 3】付款期……”。
8. 修订和批注的作者都写“木棉品牌顾问”。

补充口径：

- 只改上面几条要求改的地方：别的段落一个字都不动；同一段里不需要改的文字和格式（例如加粗的金额）保持原样；页眉、条款编号和报价表里不需要改的内容保持原样。要改的条款写在报价表里的，就在表格里改。
- 合同里已有的修订和批注（别人留的）原样保留，不接受也不拒绝。
- 已经符合规则的条款不改、不批注（例如付款期本来就不超过 20 天）。
- 交回的文件名是原文件名去掉“.docx”后加“.reviewed.docx”（例如“品牌咨询合同.docx”交回“品牌咨询合同.reviewed.docx”），不覆盖原文件。
- 回复里只写一句话：改了几处（修订）、加了几条批注。一处改动先删后插算一处修订。
""",
    },
}
PROJECTS = {"R1": [("品牌设计服务合同", "品牌视觉识别（VI）设计"), ("包装设计服务合同", "产品包装设计"), ("海报设计服务合同", "门店海报设计")],
            "R2": [("拍摄服务合同", "新品商业摄影"), ("短片拍摄合同", "品牌宣传短片拍摄"), ("活动拍摄合同", "发布会活动拍摄")],
            "R3": [("品牌咨询合同", "品牌定位咨询"), ("命名服务合同", "新品牌命名"), ("营销策划合同", "年度营销策划")]}
CLIENTS = ["杭州鲜语餐饮管理有限公司", "上海禾川茶业有限公司", "宁波海曦电器有限公司", "苏州云麦食品有限公司", "南京拾光文创有限公司"]
DIGITS = "零壹贰叁肆伍陆柒捌玖"

SPECS = []
for i in range(1, 21):
    SPECS.append((f"t{i:02d}", "train", "edge" if i > 10 else "common", "R1" if i % 2 else "R2"))
for i in range(1, 11):
    SPECS.append((f"x{i:02d}", "same", "edge" if i > 5 else "common", "R1" if i % 2 else "R2"))
for i in range(1, 11):
    SPECS.append((f"y{i:02d}", "new", "edge" if i > 5 else "common", "R3"))

TASK = (
    "你是创意工作室的合同助理。客户发来的合同（.docx）在工作目录里，按这次适用的合同审稿工作规则在原文上用修订和批注审，"
    "把审过的 Word 文件交付给我。工作目录里有工作规则和合同原件。"
)
ONBOARDING = "以后客户发来的合同，我都会把这次适用的合同审稿工作规则和合同 .docx 一起给你，你审完把 Word 文件交给我。不同工作室的规则不一样，以当次给的为准。"
CRITERIA = [
    ("V-fix", "red_line",
     "该改的都改对：参考答案逐条列了这份合同里要处理的地方（改成什么、哪些只加批注不改原文）和已经合规、不能动的条款。按修订全部接受后"
     "的文字看（测量值给了每段“接受全部修订后”的文字），要改的地方改成了规则要求的内容；只批注的那条没改原文；合规的条款没改、没批。"
     "漏改、改错、改了不该改的，每处记一处。"),
    ("V-track", "standard",
     "留痕和原样：所有改动都是修订（测量值给了每段“拒绝全部修订后”的文字和原文是否一致，不一致就是直接改了正文）；不需要改的段落、"
     "页眉、报价表、加粗格式和原来一样；合同里原有的别人的修订和批注还在。每处不符记一处。"),
    ("V-comment", "standard",
     "批注：每处修订都有一条批注批在这条修订所在的条款上，写清问题和理由；规则要求只批注的那条有批注；批注和修订的作者是规则要求的"
     "名字（测量值列了作者）；规则要求批注开头写规则编号的，要写对编号。每处不符记一处。"),
    ("V-file", "standard",
     "交付：交了一个审过的 .docx，文件名按规则（原文件名去掉 .docx 加 .reviewed.docx）；回复只有一句话，写的修订处数和批注条数和"
     "交付的文件对得上（一处修订指一次改动，删加成对算一处）。每处不符记一处。没交 .docx 时，本项记一处，其余各项按没改处理。"),
]


def upper_amount(n: int) -> str:
    """Chinese financial numerals for whole yuan below 1,000,000 (e.g. 50000 -> 伍万元整)."""
    wan, rest = divmod(n, 10000)
    out = ""
    if wan:
        out += (DIGITS[wan // 10] + "拾" if wan >= 10 else "") + (DIGITS[wan % 10] if wan % 10 else "") + "万"
    thousands = rest // 1000
    if thousands:
        out += DIGITS[thousands] + "仟"
    elif rest and out:
        out += "零"
    hundreds = (rest % 1000) // 100
    if hundreds:
        out += DIGITS[hundreds] + "佰"
    return out + "元整"


def run(text: str, bold=False) -> str:
    props = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return f'<w:r>{props}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def para(pieces) -> str:
    """A paragraph from pieces: plain text, ("b", text) for bold, ("ins"/"del", text, author, id) for a client's revision,
    ("cs", id) / ("ce", id) for a client's comment range."""
    xml = []
    for piece in pieces:
        if isinstance(piece, str):
            xml.append(run(piece))
        elif piece[0] == "b":
            xml.append(run(piece[1], bold=True))
        elif piece[0] == "ins":
            xml.append(f'<w:ins w:id="{piece[3]}" w:author="{piece[2]}" w:date="2026-09-20T10:00:00Z">{run(piece[1])}</w:ins>')
        elif piece[0] == "del":
            xml.append(f'<w:del w:id="{piece[3]}" w:author="{piece[2]}" w:date="2026-09-20T10:00:00Z"><w:r><w:delText xml:space="preserve">'
                       f'{escape(piece[1])}</w:delText></w:r></w:del>')
        elif piece[0] == "cs":
            xml.append(f'<w:commentRangeStart w:id="{piece[1]}"/>')
        elif piece[0] == "ce":
            xml.append(f'<w:commentRangeEnd w:id="{piece[1]}"/><w:r><w:commentReference w:id="{piece[1]}"/></w:r>')
    return "<w:p>" + "".join(xml) + "</w:p>"


def table(rows) -> str:
    out = ['<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="0" w:type="auto"/></w:tblPr>']
    for row in rows:
        out.append("<w:tr>" + "".join(f"<w:tc>{para(cell if isinstance(cell, list) else [cell])}</w:tc>" for cell in row) + "</w:tr>")
    return "".join(out) + "</w:tbl>"


NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')


def package(header: str, blocks: list[str], comments: list[tuple[str, str, str]]) -> bytes:
    """A minimal valid .docx: document with a header, optional comments part."""
    body = "".join(blocks) + ('<w:sectPr><w:headerReference w:type="default" r:id="rIdHeader"/>'
                              '<w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
                              'w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>')
    document = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS}><w:body>{body}</w:body></w:document>'
    head = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:hdr {NS}>{para([header])}</w:hdr>'
    rels = ['<Relationship Id="rIdHeader" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>',
            '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>']
    types = ['<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>',
             '<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>',
             '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>']
    parts = {}
    if comments:
        rels.append('<Relationship Id="rIdComments" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="comments.xml"/>')
        types.append('<Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>')
        parts["word/comments.xml"] = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:comments {NS}>' + "".join(
            f'<w:comment w:id="{cid}" w:author="{author}" w:date="2026-09-20T10:00:00Z" w:initials="KH">{para([text])}</w:comment>'
            for cid, author, text in comments) + "</w:comments>")
    styles = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {NS}><w:docDefaults><w:rPrDefault><w:rPr>'
              '<w:rFonts w:ascii="Microsoft YaHei" w:eastAsia="Microsoft YaHei" w:hAnsi="Microsoft YaHei"/><w:sz w:val="22"/></w:rPr>'
              '</w:rPrDefault></w:docDefaults><w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders>'
              + "".join(f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="auto"/>' for side in ("top", "left", "bottom", "right", "insideH", "insideV"))
              + '</w:tblBorders></w:tblPr></w:style></w:styles>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as box:
        box.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="xml" ContentType="application/xml"/>' + "".join(types) + "</Types>")
        box.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                     '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        box.writestr("word/_rels/document.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                     + "".join(rels) + "</Relationships>")
        box.writestr("word/document.xml", document)
        box.writestr("word/header1.xml", head)
        box.writestr("word/styles.xml", styles)
        for name, xml in parts.items():
            box.writestr(name, xml)
    return buf.getvalue()


def build(spec, rng):
    """One contract: its clauses (some breaking the rule, some already fine), where they sit, and what the review must do."""
    name, group, segment, rule = spec
    r = RULES[rule]
    edge = segment == "edge"
    title, project = rng.choice(PROJECTS[rule])
    client = rng.choice(CLIENTS)
    amount = rng.choice(range(30000, 200001, 5000))
    number = f"HT-2026-{rng.randint(100, 999)}"
    todo, fine = [], []
    # 每条要审的条款：随机定它合不合规（每题至少 3 处要处理、至少 1 条合规）
    kinds = ["tax", "pay", "rounds", "ip", "venue"] + (["cap"] if r["cap"] else [])
    broken = set(rng.sample(kinds, rng.randint(3, min(5, len(kinds)))))
    if rule == "R3" and "cap" not in broken and rng.random() < 0.7:
        broken.add("cap")
    if len(broken) == len(kinds):
        broken.discard(rng.choice(sorted(broken - {"cap"})))
    cap_clause = None
    clauses = {}
    # 第三条 总价
    taxed = "tax" not in broken
    if rule == "R2" and taxed:
        tax_tail = "，含 6% 增值税，乙方开具增值税专用发票"
    elif taxed:
        tax_tail = "，含 6% 增值税"
    elif rule == "R2" and rng.random() < 0.5:
        tax_tail = "，乙方开具增值税普通发票"  # 写了发票、没写含税：R2 仍要批
    else:
        tax_tail = ""
    clauses["tax"] = ["第三条 合同总价为人民币", ("b", f"{upper_amount(amount)}（¥{amount:,}）") if edge else f"{upper_amount(amount)}（¥{amount:,}）", tax_tail + "。"]
    # 第四条 付款
    days = rng.choice([d for d in (45, 60, 90, 25, 40) if d > r["pay"]]) if "pay" in broken else rng.choice([d for d in (7, 10, 15, 20, 30) if d <= r["pay"]])
    pay_text = f"甲方在收到全部设计成果后 {days} 日内支付全部款项"
    pay_in_table = edge and rng.random() < 0.5
    clauses["pay"] = ["第四条 ", pay_text, "（" if not pay_in_table else "", ("b", f"¥{amount:,}") if edge and not pay_in_table else (f"¥{amount:,}" if not pay_in_table else ""), "）。" if not pay_in_table else "，详见报价表付款说明。"]
    if pay_in_table:
        clauses["pay"] = ["第四条 付款方式和期限见报价表付款说明。"]
    # 第五条 修改
    if "rounds" in broken:
        rounds_text = rng.choice(["甲方有权对设计成果提出修改意见，乙方应无条件修改直至甲方满意。", "乙方应根据甲方意见修改，修改至甲方满意为止。",
                                  f"乙方提供不超过 {r['rounds'] + 2} 轮修改。"])
        if rule == "R1" and "轮修改" in rounds_text:
            rounds_text = "甲方有权对设计成果提出修改意见，乙方应无条件修改直至甲方满意。"
    else:
        rounds_text = f"乙方提供不超过 {rng.randint(1, r['rounds'])} 轮修改，超出部分另行计费。"
    clauses["rounds"] = ["第五条 ", rounds_text]
    # 第八条 知识产权
    if "ip" in broken:
        ip_text = rng.choice(["设计成果的全部知识产权自交付之日起归甲方所有，乙方不得以任何形式展示。",
                              "设计成果的著作权归甲方所有，乙方不得署名，也不得在任何场合展示。" if rule == "R2" else
                              "设计成果的著作权归甲方所有，乙方不得在任何场合展示或宣传。"])
    else:
        ip_text = "设计成果的著作权归甲方所有；" + r["keep"] + "。"
    clauses["ip"] = ["第八条 ", ip_text]
    # 第九条 违约（R3 有上限要求）
    rate = rng.choice([1, 2, 3])
    if r["cap"]:
        if "cap" in broken:
            cap_clause = rng.choice(["", "，累计不超过合同总价的 50%"])
        else:
            cap_clause = f"，乙方累计违约金不超过合同总价的 {rng.choice([10, 15, 20])}%"
    clauses["breach"] = ["第九条 乙方逾期交付的，每逾期一日按合同总价的 ", f"{rate}%", f" 支付违约金{cap_clause or ''}。"]
    # 第十条 争议
    if "venue" in broken:
        venue_text = rng.choice(["因本合同发生的争议，由甲方所在地人民法院管辖。", "因本合同发生的争议，提交北京仲裁委员会仲裁。",
                                 "因本合同发生的争议，由上海市浦东新区人民法院管辖。"])
    else:
        venue_text = ("因本合同发生的争议，提交上海仲裁委员会仲裁。" if r["venue_kind"] == "arbitration" else
                      f"因本合同发生的争议，由{r['venue']}管辖。")
    clauses["venue"] = ["第十条 ", venue_text]
    # 客户已留的修订和批注（边界题）
    client_rev = edge and rng.random() < 0.7
    second = ["第二条 交付时间：乙方在合同签订后 ", f"{rng.choice([10, 15, 20])}", " 个工作日内交付初稿"]
    comments = []
    if client_rev:
        second += [("ins", "（含 2 套备选方案）", "客户法务", 901)]
    second += ["。"]
    seventh = ["第七条 验收：甲方在收到设计成果后 5 个工作日内验收，逾期未提出书面意见的视为验收合格。"]
    if client_rev and rng.random() < 0.6:
        seventh = [("cs", 0), "第七条 验收：甲方在收到设计成果后 5 个工作日内验收，逾期未提出书面意见的视为验收合格。", ("ce", 0)]
        comments.append(("0", "客户法务", "验收期请再确认。"))
    rows = [["项目", "数量", "金额"], [project, "1 项", f"¥{amount:,}"], ["合计", "", f"¥{amount:,}"]]
    if pay_in_table:
        rows.append(["付款说明", "", pay_text + "。"])
    blocks = [
        para([("b", f"《{title}》")]),
        para([f"甲方：{client}"]), para([f"乙方：{r['studio']}"]),
        para([f"第一条 服务内容：乙方为甲方提供{project}服务，具体范围以报价表为准。"]),
        para(second), para(clauses["tax"]), table(rows), para(clauses["pay"]), para(clauses["rounds"]),
        para(["第六条 保密：双方对合作中知悉的对方商业信息负有保密义务。"]), para(seventh), para(clauses["ip"]),
        para(clauses["breach"]), para(clauses["venue"]),
        para(["第十一条 本合同一式两份，双方各执一份，自双方签字盖章之日起生效。"]),
        para([f"甲方（盖章）：{client}"]), para([f"乙方（盖章）：{r['studio']}"]),
    ]
    data = package(f"合同编号：{number} · {title}", blocks, comments)
    return {"title": title, "client": client, "amount": amount, "days": days, "broken": broken, "kinds": kinds,
            "pay_in_table": pay_in_table, "client_rev": client_rev, "client_comment": bool(comments), "rounds_text": rounds_text,
            "ip_text": ip_text, "venue_text": venue_text, "tax_tail": tax_tail, "cap_clause": cap_clause, "edge": edge,
            "docx": data, "file": f"{title}.docx"}


def plan(rule, d) -> list[dict]:
    """What the review must do, clause by clause."""
    r = RULES[rule]
    out = []
    labels = {"tax": "第三条（合同总价）", "pay": "付款期（" + ("报价表“付款说明”一行" if d["pay_in_table"] else "第四条") + "）",
              "rounds": "第五条（修改）", "ip": "第八条（知识产权）", "venue": "第十条（争议解决）", "cap": "第九条（违约责任）"}
    for kind in d["kinds"]:
        if kind not in d["broken"]:
            out.append({"条款": labels[kind], "处理": "已合规，不改、不批注"})
            continue
        if kind == "tax":
            missing = "含税口径" if rule != "R2" else ("含税口径" + ("" if d["tax_tail"] else "和发票类型"))
            out.append({"条款": labels[kind], "处理": f"只加批注（提示写明{missing}），不改原文", "规则": 2})
        elif kind == "pay":
            out.append({"条款": labels[kind], "处理": f"修订：{d['days']} 日改成 {r['pay']} 日，配批注", "接受修订后应含": f"{r['pay']} 日", "规则": 3})
        elif kind == "rounds":
            out.append({"条款": labels[kind], "处理": f"修订：“{d['rounds_text']}”改成“乙方提供不超过 {r['rounds']} 轮修改”，配批注",
                        "接受修订后应含": f"乙方提供不超过 {r['rounds']} 轮修改", "规则": 3})
        elif kind == "ip":
            out.append({"条款": labels[kind], "处理": f"修订：删去禁止乙方{'署名或' if rule == 'R2' else ''}展示的话，补上“{r['keep']}”，配批注",
                        "接受修订后应含": r["keep"], "接受修订后不应含": "不得", "规则": 4})
        elif kind == "venue":
            target = "提交上海仲裁委员会仲裁" if r["venue_kind"] == "arbitration" else r["venue"]
            out.append({"条款": labels[kind], "处理": f"修订：改成“{target}”，配批注", "接受修订后应含": target, "规则": 5})
        elif kind == "cap":
            out.append({"条款": labels[kind], "处理": "修订：在末尾补上（或把上限改成）“乙方累计违约金不超过合同总价的 20%”，配批注",
                        "接受修订后应含": "不超过合同总价的 20%", "规则": 6})
    return out


def reference(spec, d) -> dict:
    name, group, segment, rule = spec
    r = RULES[rule]
    todo = plan(rule, d)
    revisions = sum(1 for t in todo if t["处理"].startswith("修订"))
    notes = sum(1 for t in todo if "批注" in t["处理"] and not t["处理"].startswith("已合规"))
    return {
        "规则集": f"{rule}（{r['studio']}）",
        "原文件": d["file"],
        "该交回的文件名": d["file"][:-5] + ".reviewed.docx",
        "逐条处理": todo,
        "修订处数（最少）": revisions,
        "批注条数（最少）": notes,
        "作者": r["studio"],
        "批注开头要写规则编号": "要（例如“【规则 3】”）" if r["tag"] else "规则没要求",
        "合同里别人已有的修订和批注（要原样保留）": (["第二条里客户法务插入的“（含 2 套备选方案）”"] if d["client_rev"] else [])
        + (["第七条上客户法务的批注“验收期请再确认。”"] if d["client_comment"] else []) or "无",
        "要保留的格式": (["第三条里加粗的金额"] + ([] if d["pay_in_table"] else ["第四条里加粗的金额"])) if d["edge"] else "无特殊格式",
        "原文的文字版": docx_text(d["docx"]),
    }


def scenario_package():
    (SCENARIO / "personas").mkdir(parents=True, exist_ok=True)
    (SCENARIO / "profile.md").write_text(TASK + "\n")
    (SCENARIO / "onboarding.md").write_text(ONBOARDING + "\n")
    (SCENARIO / "personas" / "owner.md").write_text("工作室负责人每收到客户的合同就要审稿件；每道题的合同 .docx 和规则由脚本给出。\n")
    (SCENARIO / "scenario.json").write_text(json.dumps({
        "initial": [],
        "criteria": [{"id": i, "check": text, "severity": severity} for i, severity, text in CRITERIA],
    }, ensure_ascii=False, indent=1) + "\n")
    visible = ["counterpart", "analyst", "curator"]
    (SCENARIO / "contract.json").write_text(json.dumps(
        {"checks": {i: {"visibility": visible} for i, _, _ in CRITERIA}}, ensure_ascii=False, indent=1) + "\n")


def main():
    assert len({s[0] for s in SPECS}) == 40
    assert upper_amount(50000) == "伍万元整" and upper_amount(125000) == "壹拾贰万伍仟元整" and upper_amount(30500) == "叁万零伍佰元整"
    (HERE / "rules").mkdir(exist_ok=True)
    bank, scripts = [], []
    for spec in SPECS:
        name, group, segment, rule = spec
        d = build(spec, random.Random(name))
        assert len([k for k in d["kinds"] if k in d["broken"]]) >= 3 and len(d["broken"]) < len(d["kinds"])
        files = {"工作规则.md": RULES[rule]["text"], d["file"]: "base64:" + base64.b64encode(d["docx"]).decode()}
        task = (f"{d['client']}发来了《{d['title']}》，在工作目录：{d['file']}。按这次适用的合同审稿工作规则（工作规则.md）在原文上审，"
                "把审过的 Word 文件交付给我。")
        bank.append({"name": name, "group": group, "segment": segment, "rules": rule, "text": task, "files": files,
                     "reference": reference(spec, d)})
        label = {"train": "培养", "same": "考试·同规则", "new": "考试·新规则"}[group]
        scripts.append({"name": name, "title": f"{name} · {label} · {RULES[rule]['studio']}", "exam": group != "train",
                        "steps": [{"text": task, "files": files}]})
    for rule, r in RULES.items():
        (HERE / "rules" / f"{rule}.md").write_text(r["text"])
    (HERE / "questions.json").write_text(json.dumps(bank, ensure_ascii=False, indent=1) + "\n")
    (HERE / "scripts.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=1) + "\n")
    scenario_package()
    print(f"{len(bank)} questions, scenario at {SCENARIO.name}")


if __name__ == "__main__":
    main()
