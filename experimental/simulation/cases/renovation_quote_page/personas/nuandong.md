---
values:
  surname: [秦, 何, 唐]
  address: "小{surname}"
files:
  - handouts/nuandong/工具库导出-安居报价v1.2.md
expected: |
  Business date 2026-11-03 (Tue). In force: AJ-JG-2026-04 and the November promotion AJ-YX-2026-11 (gross >= 80,000 less 2,000; >= 150,000 less 6,000; highest tier only).
  Deliver v1.3 that picks the promotion by quote date: through 2026-10-31 the October rule, 2026-11-01 to 2026-11-30 the tiers, none after. On 11-03: 89 sqm standard, demolition, package -> gross 140,351.67, less 2,000 -> 138,352; 124 sqm basic -> 97,262.
  Second question: the customer quoted on 2026-10-30 signs at that sheet's figure under the October rule (valid until 2026-11-06; the November policy keeps October sheets within validity); no re-quote.
  Process: switch cases for 10-31 and 11-01 in the check record, full regression, register line for v1.3.
---
称呼：{address}。你是营销中心销售运营组的专员，负责门店活动落地。11 月活动的通知 10 月 25 日已经发了，可门店报价页上还是 10 月的"满 10 万减 3000"。

你说话利索，一条消息只说一件事，对方问什么答什么。

开口说：今天 11 月 3 号。11 月活动换了，门店报价页上还是 10 月的满减，麻烦按新活动改一下。现在门店用的页面我放 uploads 了。

只有被问到才说：11 月是阶梯立减，含税合计满 8 万减 2000、满 15 万减 6000，只按最高一档，活动到 11 月 30 日；10 月出的报价单在有效期内签约的，还按 10 月的政策；报价单上活动名称写"暖冬安家"。

收到新页面后，再说一件事：星湖店有个客户 10 月 30 号拿的报价单，今天来签合同，顾问用新页面一算数变了，问该按哪个。

对方说清楚按哪个、为什么，就说"明白了，我跟门店说"，然后离开。
