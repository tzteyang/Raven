"""评审用的测量值：员工回复的字数（按工作规则的数法：字符都算，空格和换行不算）。只作评审依据，判定由评审做。"""

import re


def measure(question: dict, product: str) -> dict:
    return {
        "回复字数（字符都算，空格和换行不算）": len(re.sub(r"\s", "", product)),
        "这套规则的字数上限": question["reference"]["字数上限"],
    }


if __name__ == "__main__":
    assert measure({"reference": {"字数上限": 150}}, "同学 你好，\n退 1999 元。")["回复字数（字符都算，空格和换行不算）"] == 12
    print("ok")
