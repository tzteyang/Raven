"""评审用的测量值：段名和段外文字、建议话术句数、答应客户的事那一段的行、跟进邮件的字数、首行末行、邮件里的日期，以及邮件里
可疑的写法（阿拉伯数字和中文数字连同前后几个字、折扣和赠送类字眼、竞品全称和简称）。只作评审依据，判定由评审做。"""

import re

SUSPECT = r"\d+(?:\.\d+)?\s*(?:w|W|万|元|折|%|天|周|个月|小时)?|[零一二两三四五六七八九十百千万]+(?:折|万|元|天|周|个月)|半个月|off|OFF|折扣|打折|赠送|免费|送您|送\S{0,3}个月"


def sentences(text: str) -> int:
    """Sentences end with 。！？ (or ! ?); a piece with no letter or character, such as a closing quote, is not one."""
    return len([piece for piece in re.split(r"(?<=[。！？!?])", text) if re.search(r"\w", piece)])


def sections(product: str) -> list[tuple[str, str]]:
    parts = re.split(r"^##\s*(.+?)\s*$", product, flags=re.M)
    return [(parts[i].strip(), parts[i + 1].strip()) for i in range(1, len(parts), 2)]


def measure(question: dict, product: str) -> dict:
    files = question["files"]
    names = [cell.strip() for line in files["竞品名单.md"].splitlines()[4:] for cell in line.strip("|").split("|")[:3:2]]
    parts = sections(product)
    before = product.split("##", 1)[0].strip() if "##" in product else product.strip()
    mail = parts[-1][1] if parts else ""
    script = parts[1][1] if len(parts) > 1 else ""
    mail_lines = [line.strip() for line in mail.splitlines() if line.strip()]
    return {
        "段名（按顺序）": [name for name, _ in parts],
        "第一个段名之前的文字": before or "无",
        "第二段（建议话术）句数": sentences(script),
        "第三段（答应客户的事）各行": [line.strip() for line in (parts[2][1] if len(parts) > 2 else "").splitlines() if line.strip()],
        "最后一段（跟进邮件）字数（字符都算，空格和换行不算）": len(re.sub(r"\s", "", mail)),
        "邮件第一行": mail_lines[0] if mail_lines else "",
        "邮件最后一行": mail_lines[-1] if mail_lines else "",
        "邮件里的日期写法": re.findall(r"\d{4}-\d{2}-\d{2}|\d{1,2}\s*月\s*\d{1,2}\s*日(?:（周.）)?", mail),
        "邮件里可疑的写法（连同前后各 4 个字）": [mail[max(0, m.start() - 4):m.end() + 4] for m in re.finditer(SUSPECT, mail)],
        "邮件里出现的竞品全称或简称": [n for n in names if n and n in mail],
    }


if __name__ == "__main__":
    q = {"files": {"竞品名单.md": "# 竞品名单\n\n| 竞品 | 全称 | 常见简称 |\n|---|---|---|\n| 排班宝 | 上海排班宝信息技术有限公司 | 班宝 |\n"}}
    got = measure(q, "## 改进点\n\n报价后直接给了折扣。\n\n## 建议话术\n\n您在和谁比？我们先看看差在哪。\n\n## 给主管的风险\n\n- 答应两周上线\n\n"
                     "## 跟进邮件\n\n王总您好，9 月 23 日（周三）一起听方案，比班宝便宜，给您打八五折。")
    assert got["第二段（建议话术）句数"] == 2 and got["邮件里出现的竞品全称或简称"] == ["班宝"], got
    assert got["邮件里的日期写法"] == ["9 月 23 日（周三）"] and any("八五折" in s for s in got["邮件里可疑的写法（连同前后各 4 个字）"]), got
    assert got["第一个段名之前的文字"] == "无" and got["第三段（答应客户的事）各行"] == ["- 答应两周上线"], got
    assert sentences('“王总，您在和哪家比吗？他们的报价包含哪些服务？”') == 2 and sentences("好的。”\n") == 1
    print("ok")
