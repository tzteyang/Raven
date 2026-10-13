"""评审用的测量值：员工回复的第一行和第一句（去掉开头的 Markdown 标记）。只作评审依据，判定由评审做。"""

import re


def measure(question: dict, product: str) -> dict:
    lines = [line.strip() for line in product.splitlines() if line.strip()]
    first_line = re.sub(r"^[#>*\-\s]+", "", lines[0]) if lines else ""
    first = re.split(r"(?<=[。！？!?])", first_line)[0]
    return {"回复第一行": first_line, "回复第一句": first}


if __name__ == "__main__":
    got = measure({}, "## 结论\n外卖下降最多的是高新店，下降 9.8%。原因如下")
    assert got == {"回复第一行": "结论", "回复第一句": "结论"}, got
    assert measure({}, "外卖：高新店下降 9.8%；堂食：锦江店下降 15.5%。原因")["回复第一句"] == "外卖：高新店下降 9.8%；堂食：锦江店下降 15.5%。"
    print("ok")
