---
values:
  surname: [郁, 潘, 汪, 范]
  address: "{surname}经理"
files:
  - handouts/chaijiu/顾问反馈-59.9平报价对不上.md
  - handouts/chaijiu/工具库导出-安居报价v1.1.md
expected: |
  Business date 2026-10-20 (Tue). In force: AJ-JG-2026-04 and AJ-YX-2026-10.
  Reported: 59.9 sqm standard, demolition, no package, quoted 2026-10-19. Rules: billed 60 sqm, demolition 2,700.00, gross 72,397.80, total 72,398; v1.1 shows 72,393 because demolition uses 59.9 sqm.
  A full regression also exposes a second fault in v1.1: the promotion threshold is read before tax, so checked sheet AJ20261005-110907 (64 sqm luxury) gives 103,970 instead of 100,970; AJ20261006-163015 gives 72,006 instead of 72,398 (same demolition fault).
  In round 3 the employee may already hold later editions; a page that also carries them and switches by date is acceptable as long as the business date uses the codes above.
  Expected work: reproduce first (expected vs shown in the record), fix both faults, rerun every case, deliver v1.2 with a register line; tell the manager both causes and which kinds of quotes were affected.
---
称呼：{address}。你是相城高铁新城店的销售经理。昨天一个顾问下午给客户报了价，晚上回店用财务的表格复核，差了 5 块钱，顾问把情况截图发给了你。

你说话直接，一条消息只说一件事，对方问什么答什么。

开口说：今天 10 月 20 号。顾问说 59.9 平那套报价页算错了，跟财务表格算的对不上。顾问的反馈截图和现在用的页面我放 uploads 了，你帮忙看看。

只有被问到才说：那套是标准档、要拆旧、不做定制，昨天（10 月 19 日）报的价；页面上是 72,393 元，财务表格算出来 72,398 元；顾问手机上用的是工具库里的 v1.1。

收到修好的页面后，问一句："是哪里错了？别的单子会不会也受影响？" 对方把原因说清楚、说明改完以后核对过，就说"好，那我通知顾问换新版本"，然后离开。如果对方只说改好了、说不出原因，就再问一次原因，听完后离开。
