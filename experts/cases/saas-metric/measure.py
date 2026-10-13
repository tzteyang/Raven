"""评审用的测量值：员工交付的段名，以及把交付里第一个 ```sql 代码块放到按 schema.sql 建好、导入 CSV 的 SQLite 库上实际
运行的结果（或报错）。只作评审依据，判定由评审做。"""

import csv
import io
import re
import sqlite3

STEPS = 50_000_000


def database(files: dict) -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.executescript(files["schema.sql"])
    for table in ("users", "subscriptions", "merges"):
        rows = list(csv.DictReader(io.StringIO(files[f"{table}.csv"])))
        if rows:
            columns = list(rows[0])
            db.executemany(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
                           [tuple(row[c] for c in columns) for row in rows])
    return db


def measure(question: dict, product: str) -> dict:
    found = {"交付里的段名（按顺序）": re.findall(r"^\s*##(?!#)\s*(.+?)\s*$", product, re.M)}
    block = re.search(r"```sql\s*\n(.*?)```", product, re.S | re.I)
    if block is None:
        found["SQL 运行结果"] = "交付里没有 ```sql 代码块"
        return found
    db = database(question["files"])
    budget = {"left": STEPS}

    def guard():
        budget["left"] -= 1000
        return budget["left"] < 0

    db.set_progress_handler(guard, 1000)
    try:
        statements = [part for part in block.group(1).split(";") if part.strip()]
        rows = []
        for statement in statements:
            rows = db.execute(statement).fetchall()
        found["SQL 运行结果"] = {"最后一条语句返回的行数": len(rows), "前 5 行": [list(row) for row in rows[:5]]}
    except sqlite3.Error as exc:
        found["SQL 运行结果"] = f"运行报错：{type(exc).__name__}: {exc}"
    return found


if __name__ == "__main__":
    import json
    from pathlib import Path

    q = json.loads((Path(__file__).parent / "questions.json").read_text())[0]
    sql = "SELECT COUNT(DISTINCT company_id) FROM users;"
    got = measure(q, f"## SQL\n```sql\n{sql}\n```\n## 结果\n1\n")
    assert got["交付里的段名（按顺序）"] == ["SQL", "结果"], got
    assert got["SQL 运行结果"]["最后一条语句返回的行数"] == 1, got
    assert "报错" in measure(q, "```sql\nSELECT nope FROM users\n```")["SQL 运行结果"]
    print("ok", got)
