"""自检：另写一遍算法——用 SQL 在 SQLite 里算，只读员工看到的文件（工作规则、schema.sql、数据说明、三张 CSV）和题面，
重算每道题的企业数和结束日早于开始日的订阅，和参考答案（make.py 用 Python 算的）逐题比对。

  python3 check.py
"""

import calendar
import csv
import io
import json
import re
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent

ACTIVE = {
    "days": "COUNT(DISTINCT d) >= 3",
    "logins": "COUNT(*) >= 5",
    "workdays": "COUNT(DISTINCT CASE WHEN strftime('%w', d) NOT IN ('0', '6') THEN d END) >= 3",
}


def load(files: dict) -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.executescript(files["schema.sql"])
    for table in ("users", "subscriptions", "merges"):
        rows = list(csv.DictReader(io.StringIO(files[f"{table}.csv"])))
        if rows:
            columns = list(rows[0])
            db.executemany(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
                           [tuple(row[c] for c in columns) for row in rows])
    return db


def count(db, kind: str, paid: str, start: str, end: str, shift: str, plan: str | None, excluded: str | None) -> int:
    window = "s.start_date <= :end AND s.end_date >= :end" if paid == "month_end" else "s.start_date <= :end AND s.end_date >= :start"
    filters = (" AND s.plan = :plan" if plan else "") + (" AND s.plan <> :excluded" if excluded else "")
    sql = f"""
    WITH owner AS (SELECT old_company_id AS id, new_company_id AS to_id FROM merges),
    seen AS (
      SELECT COALESCE(o.to_id, u.company_id) AS company, date(datetime(u.login_at, :shift)) AS d
      FROM users u LEFT JOIN owner o ON o.id = u.company_id
    ),
    active AS (SELECT company FROM seen WHERE d BETWEEN :start AND :end GROUP BY company HAVING {ACTIVE[kind]}),
    paid AS (
      SELECT DISTINCT COALESCE(o.to_id, s.company_id) AS company
      FROM subscriptions s LEFT JOIN owner o ON o.id = s.company_id
      WHERE s.end_date >= s.start_date AND s.is_trial = 0 AND {window}{filters}
    )
    SELECT COUNT(*) FROM active WHERE company IN (SELECT company FROM paid)"""
    return db.execute(sql, {"start": start, "end": end, "shift": shift, "plan": plan, "excluded": excluded}).fetchone()[0]


def main() -> None:
    wrong = []
    for q in json.loads((HERE / "questions.json").read_text()):
        files, ref = q["files"], q["reference"]
        rules = files["工作规则.md"]
        kind = "logins" if "登录记录至少 5 条" in rules else "workdays" if "不同的工作日" in rules else "days"
        paid = "any_day" if "当月任意一天" in rules else "month_end"
        excluded = "基础版" if "套餐不是“基础版”" in rules else None
        year, month = map(int, re.search(r"(\d{4}) 年 (\d+) 月", q["text"]).groups())
        plan = (re.search(r"（只算(\S+?)）", q["text"]) or [None, None])[1]
        start, end = f"{year}-{month:02d}-01", f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"
        shift = "+8 hours" if "时区是 UTC" in files["数据说明.md"] else "+0 hours"
        db = load(files)
        got = count(db, kind, paid, start, end, shift, plan, excluded)
        bad = sorted(f"{c}：{s} 到 {e}" for c, s, e in
                     db.execute("SELECT company_id, start_date, end_date FROM subscriptions WHERE end_date < start_date"))
        expected_bad = ref["数据问题（结束日早于开始日的订阅）"]
        if got != ref["结果"] or bad != (sorted(expected_bad) if expected_bad != "无" else []):
            wrong.append((q["name"], got, ref["结果"], bad, expected_bad))
    print("mismatches:", wrong or "none")
    assert not wrong


if __name__ == "__main__":
    main()
