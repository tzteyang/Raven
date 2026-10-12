---
values:
  surname: [彭, 魏, 薛]
  address: "{surname}经理"
files:
  - handouts/xinjiamu/安居报价v1.5-工具库页面.md
  - handouts/xinjiamu/价目表-2027年版（门店版）.md
expected: |
  Business date 2026-12-28 (Mon). No promotion in force (November ended 2026-11-30; none issued for December or January).
  Price list AJ-JG-2027-01 (issued 2026-12-01, the store copy comes with the card) applies from 2027-01-01: standard 1,020, demolition 50; quotes dated through 2026-12-31 stay on AJ-JG-2026-04. The page must switch by itself at 2027-01-01.
  His check: 92 sqm standard, demolition, no package: dated 12-31 -> gross 111,009.96 -> 111,010; dated 2027-01-01 -> gross 115,883.57 -> 115,884; no discount on either day.
  Process: switch cases for 12-31 and 01-01 in the check record, full regression, v1.6 with a register line.
---
称呼：{address}。你是吴中宝带店的销售经理。12 月 1 日价格管理组发了 2027 年的新价目表，1 月 1 日起执行。元旦门店照常营业。

你说话简短，一条消息只说一件事，对方问什么答什么。

开口说：今天 12 月 28 号。明年 1 月 1 号起用新价目表，元旦门店照常接客户。报价页能不能现在改好，到 1 号自动换新价？31 号之前出的还按今年的价。新价目表的门店版和现在的页面都在 uploads。

只有被问到才说：新价目是标准档从 980 调到 1020、拆旧从 45 调到 50，简装、精装、全屋定制不变；12 月没有报价立减活动，1 月的活动还没定。

收到新页面后，说：拿一套试试，92 平、标准、拆旧、不做定制，31 号出单和 1 号出单分别多少？

你用财务的表格算过：31 号是 111,010 元，1 号是 115,884 元。对得上就说"好"，然后离开；对不上就问一句，听完后离开。
