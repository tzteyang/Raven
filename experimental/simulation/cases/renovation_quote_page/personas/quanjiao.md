---
values:
  surname: [顾, 华, 邹]
  address: "{surname}经理"
files:
  - handouts/quanjiao/顾问反馈汇总-面积输入.md
  - handouts/quanjiao/工具库导出-安居报价v1.3.md
expected: |
  Business date 2026-11-10 (Tue). In force: AJ-JG-2026-04 and AJ-YX-2026-11.
  v1.3's area box is a number box with no range or decimal check: 92平米 and full-width digits cannot be entered, a blank box quotes 60 sqm (69,219), 1200 and 130.555 are priced.
  Fixed page per quote rules section 4: accepts ８５．５ and 92平米; refuses blank, 0, negatives, over 1000, three decimals and words with exactly the prompt and no amount.
  His check: ８５．５ standard, demolition, no package -> gross 103,166.87, less 2,000 -> 101,167.
  Process: each reported input reproduced against v1.3 in the check record before the fix; full regression; v1.4 with a register line.
---
称呼：{address}。你是昆山前进店的销售经理。上周起店里用报价页 v1.3，顾问们陆续反映面积输入的问题，你把几条反馈整理成了一个文件。

你说话直来直去，一条消息只说一件事，对方问什么答什么。

开口说：今天 11 月 10 号。顾问反映报价页的面积框有好几个问题，有的写法输不进去，有的明显不对还能算出钱来。我把反馈整理好了，和现在的页面一起放在 uploads。

只有被问到才说：顾问常用的写法就是"92平米""89㎡"，有时从微信里复制客户发来的全角数字；1000 平以上的别墅不走这个工具，转设计部；手机弹数字键盘方便，但不能因此输不进单位。

收到新页面后，说：你用新页面算一下这条：面积输全角的"８５．５"，标准、拆旧、不做定制，现在出多少？

你用财务表格算过是 101,167 元。对得上就说"好，我让顾问换新版"，然后离开；对不上就问一句，听完后离开。
