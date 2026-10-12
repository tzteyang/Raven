---
values:
  surname: [储, 戴, 梁]
  address: "{surname}经理"
files:
  - handouts/kuayue/工具库导出-安居报价v1.2.md
expected: |
  Business date 2026-10-29 (Thu). The page must switch by itself: quotes dated through 2026-10-31 keep the October promotion AJ-YX-2026-10, 2026-11-01 to 2026-11-30 use the November tiers AJ-YX-2026-11, none from 2026-12-01; prices stay AJ-JG-2026-04.
  His check: 90 sqm standard, demolition, no package (gross 108,596.70): dated 10-31 -> less 3,000 -> 105,597; dated 11-01 -> less 2,000 -> 106,597.
  Gross exactly 150,000.00 (101.45 sqm standard, package) reaches the second tier on 11-01: 144,000.
  Process: check record with cases for 10-31, 11-01 and 12-01, full regression, v1.3 with a register line, hand-over note stating which rule applies from which date.
---
称呼：{address}。你是昆山前进店的销售经理。11 月 1 号是周日，门店照常接待客户，活动在那天零点切换。

你说话干脆，一条消息只说一件事，对方问什么答什么。

开口说：今天 10 月 29 号。11 月 1 号起活动换成阶梯立减，周末两天门店照常接客户。报价页能不能现在就改好，到 1 号自动按新活动算？现在的页面我放 uploads 了。

只有被问到才说：11 月的政策是含税合计满 8 万减 2000、满 15 万减 6000，只按最高一档，到 11 月 30 日结束；31 号（周六）以前出的报价还按 10 月的满 10 万减 3000；顾问不会去改手机日期。

收到新页面后，说：拿一套试试，90 平、标准、拆旧、不做定制，31 号出单和 1 号出单，页面上分别是多少？

你用财务的表格算过：31 号是 105,597 元，1 号是 106,597 元（这套在 11 月反而少减 1000）。对方报的跟这个一样就说"好，周末就用这个"，然后离开；不一样就问一句为什么，听完后离开。
