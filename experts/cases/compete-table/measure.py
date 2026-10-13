"""评审用的测量值：员工回复里的 Markdown 表格（张数、表头、行数、每行第一格）和表格以外的非空行。只作评审依据，判定由评审做。"""

import re

SEPARATOR = re.compile(r":?-{2,}:?")


def measure(question: dict, product: str) -> dict:
    tables, current, outside = [], None, []
    for line in product.splitlines():
        text = line.strip()
        if text.startswith("|"):
            cells = [c.strip() for c in text.strip("|").split("|")]
            if current is None:
                current = []
                tables.append(current)
            if not all(SEPARATOR.fullmatch(c) for c in cells):
                current.append(cells)
        else:
            current = None
            if text:
                outside.append(text)
    found = {"表格张数": len(tables), "表格以外的非空行": outside}
    for i, rows in enumerate(tables, 1):
        found[f"第 {i} 张表"] = {"表头": rows[0], "列数": len(rows[0]), "表头以外的行数": len(rows) - 1,
                              "每行第一格": [row[0] for row in rows[1:]]}
    return found


if __name__ == "__main__":
    got = measure({}, "定位语：云笺支持离线编辑\n\n| 功能 | 云笺 | 书契 |\n|---|---|---|\n| 离线编辑 | 有 | 无 |\n| 价格 | 24.0 | 25.6 |\n注：按年付")
    assert got["表格张数"] == 1 and got["第 1 张表"]["表头以外的行数"] == 2, got
    assert got["表格以外的非空行"] == ["定位语：云笺支持离线编辑", "注：按年付"], got
    print("ok")
