# 怎么做一个专家案例（给做案例的人和代理看）

目标：为一个专家岗位做一套「工作规则随题交给员工」的培养和考试材料，让 Studio 从 plain Raven 培养出一个能直接给
真实用户用的 Raven subagent。交付物里一律叫「工作规则」，不叫「公司规则」。下文的路径都相对仓库根目录。
现有 22 个案例的设计取自一份内部的专家清单文档，仓库里没有它；新案例从你自己的岗位需求出发。

## 已经做好的样板（先读它们）

- `experts/cases/refund-desk/`（1.1 网课退款客服，最简单的一个：规则 + 订单 → 一条回复）
- `experts/cases/complaint-desk/`（1.2 售后投诉：规则 + 订单 + CRM 记录 → 分段处理结果）
- `experts/cases/poster-review/`（2.1 海报审查：规则 + 成交记录 CSV + 价目表 + 词表 → 改后文案 + 修改清单）
- `experts/cases/store-ticket/`（3.1 门店客单价：规则 + 日报 CSV → 结论和原因，带按种子生成数据和陷阱校验）
- 通用评审：`experts/common/examiner.py`（读懂它怎么用 `questions.json`、`rules/`、`measure.py` 和 `scenario.json`）

## 案例目录里要有的东西

```
experts/cases/<案例名>/
  make.py          生成全部材料（只用标准库；python3 make.py 一次生成）
  check.py         独立复核：另写一遍算法，只读员工能看到的文件和题面，重算参考答案里的关键值，打印 "mismatches: none"
  measure.py       评审用的测量值（可选但通常需要）：measure(question, product) -> dict，只量不判
  live.json        Studio 配置：照抄 refund-desk/live.json，只改 root（../../../../runs/experts/<案例名>，在仓库外的工作区里）和 scenario（wkr-<案例名>）
  rules/R1.md R2.md R3.md                 三套工作规则全文（make.py 写出）
  questions.json   40 道题：[{name, group, segment, rules, text, files, reference}]
  scripts.json     40 个脚本：[{name, title, exam, steps: [{text, files}]}]，exam = group != "train"
  wkr-<案例名>/    场景包：profile.md、onboarding.md、personas/<谁>.md、scenario.json（initial: [], criteria）、contract.json
```

`files` 是 {文件名: 文本内容}，只能是文本文件（.md / .csv / .json / .txt / .html）。`files` 里一定有 `工作规则.md`
（这道题适用的那套规则全文），其余是这道题的数据。`text` 是员工收到的任务原文，要写明工作目录里有哪些文件。

## 40 道题的固定编排

- t01–t20 培养题：奇数用 R1，偶数用 R2；t01–t10 常见情况（common），t11–t20 边界情况（edge）。
- x01–x10 同规则考试：x01–x05 common、x06–x10 edge；奇数 R1、偶数 R2。group = "same"。
- y01–y10 新规则考试：全用 R3（员工从没见过）；y01–y05 common、y06–y10 edge。group = "new"。
- 题的 segment 用 "common" / "edge"；group 用 "train" / "same" / "new"。

## 三套工作规则

- R1：取文档里这个案例的公司规则和补充规则，改写成一家公司的「工作规则」。
- R2：另一家公司，规则结构相同、参数和说法不同（数值、阈值、用词、格式、段落名都可以不同），要能让「背 R1」的员工犯错。
- R3：再一家公司，只用于考试；结构相同，参数不同，并加一两处新口径（例如多一个条件、换一种算法），用来看员工有没有学会
  「按当次规则做」，而不是背了 R1/R2。
- 每套规则写成完整的 Markdown 文件，员工每道题都会拿到当套全文。

## 最要紧的经验（前面几个案例踩过的坑）

1. 评审会认真对照规则判。规则里每一条要求都必须写得能判：用闭合的词表（「不出现‘马上’‘今天’‘尽快’这几个词」），
   不要写「这类说法」「等」这种开放说法；格式要求写死（段名、顺序、表格列、单位写法）。
2. 评审要检查的每一件事，都必须写在员工拿到的工作规则里。规则没要求的，验收项也不许要求。
3. 金额、数字的写法要说清楚：例如「金额算到分」还是「保留两位小数显示」；验收项写明「数值相等就算对」还是「写法也要一致」。
4. 参考答案要给足精度：要四舍五入比对的数，参考答案给未取舍的值（4 位小数），评审才判得准。
5. 参考答案要把判卷需要的东西都写出来：正确值、怎么算的、该写什么、不该写什么、哪些题这项不适用。
6. 每题的数据和陷阱用固定种子生成（random.Random(题号)），遇到四舍五入落在正中间、并列这类不唯一的情况就换种子重试并打印。
7. 生成时用 assert 校验：答案唯一、陷阱确实有效（用错口径会得出别的结果）、数据前后一致（例如签收时间不早于送达日期）。
8. 测量值只量不判：例如字数、段名列表、表格行列、某段里出现的禁用词。句子按「。！？」切，不要按「；」切。
9. 场景包目录名 wkr-<案例名> 不能出现在改造师能读到的源码里：`raven/`、`experimental/curator/`、`tests/`、`docs/`、
   `docs-site/docs/` 和根目录的 `pyproject.toml`、`uv.lock`、`CONTEXT.md`、`CONTEXT-MAP.md`、`AGENTS.md`
   （`experimental/curator/raven_adapter/exploration.py` 的 `_SOURCE_PATHS`；`experts/` 不在其中）。用
   `grep -rl wkr-<案例名> raven experimental/curator tests docs docs-site/docs` 查一下，应该没有输出。
10. 有条件的口径一定写成「如果……就……；否则……」或「写的是 A，就……；写的是 B，就……」，两个分支都写出来。
    「数据说明里写 X 是 UTC 的，先加 8 小时」这种没有「如果」的句子，员工会读成陈述句（以为材料就是 UTC），
    saas-metric 因此整轮作废重跑。
11. 「只交这几段，前后不加别的文字」「什么不算数据问题」这类边界要写进规则原文；验收项会因为多出来的开场白、
    把正常情况报成问题而记错，规则里没写就不能判。
12. 规则写完，用「一个只读规则原文、不知道出题意图的人」的眼光逐句读一遍：每句话有没有第二种读法？有就改。
13. 一个根因只在一项里记：员工常在交付前后加开场白、核对说明。验收项要写明“前后多出来的文字只在格式项记一处，里面的数字、
    关键词、字数不在别的项重复记”，内容类各项只判交付本身（字数、句数也按交付本身算，测量值给逐行的字数句数让评审扣掉多出来的行）。
    cafe-copy 第一次没写，一段开场白连带挂了四项，整轮作废重跑。探测里加一份「正确交付 + 前后说明」的答卷，应只挂格式项一处。
14. 测量值要用真实写法自测：员工常把话术、引文放在引号里（“……？”）。数句子时，切开后不含字母或汉字的片段（例如句末的
    右引号、右括号）不算一句，否则“一句话”会被量成两句。call-debrief 因此整轮作废。measure.py 的自测里要放带引号、带括号、
    带 Markdown 标记的例子。

## 验收项（scenario.json 的 criteria）

- 4 到 5 项，每项 id 用两到三个字母前缀（例如 D-answer），一项是 red_line，其余 standard。
- 每项写清楚：判什么、以参考答案为准的是什么、什么情况记一处错、什么情况本项不适用。
- 同一处错误只记在最贴切的一项下（评审提示里已经这样要求）。

## 评审探测（必须做，做完才算完成）

写 4 份手写答卷到 `experts/cases/<案例名>/probes/probe-<案例名>.json`：一道 R1 或 R2 的边界题的正确答卷和错误答卷，一道 R3 边界题的正确
答卷和错误答卷。格式：

```json
[{"name": "t11", "label": "right", "expect": [], "answer": "……"},
 {"name": "t11", "label": "wrong", "expect": ["X-aaa", "X-bbb"], "answer": "……"}]
```

正确答卷要真的完全符合规则；错误答卷要故意犯几种典型错误，expect 写应该挂的验收项。然后运行：

```bash
tmux new-session -d -s experts-probe-<案例名> "cd <仓库根目录> && uv run python experts/common/probe.py experts/cases/<案例名> experts/cases/<案例名>/probes/probe-<案例名>.json > /tmp/probe-<案例名>.log 2>&1; echo PROBE_EXIT \$? >> /tmp/probe-<案例名>.log"
until grep -q PROBE_EXIT /tmp/probe-<案例名>.log; do sleep 5; done
```

（评审模型是案例 live.json 里 assessor 角色的模型，我们用的是 kimi-k3，一次 1 到 3 分钟。）看日志（每份答卷末尾的 `-> MATCH` 表示挂的项和 expect 一致）：正确答卷每项都 pass（不适用的项除外），错误答卷恰好挂 expect 里的项。
不符合时，先判断是规则或验收项写得不清、参考答案不全，还是答卷本身有问题，改材料后重跑，直到符合。不要改评审代码。
跑完关掉自己的 tmux 会话。

## 不许做的事

- 不改 `experts/common/`、仓库里 `experts/` 以外的代码、`secrets/`、别的案例目录；不启动 Studio；不动别人的 tmux 会话和进程。
- 不安装任何依赖；make.py / check.py / measure.py 只用 Python 标准库。
- 不打印、不读取任何 key。
- 不 git commit / push。

## 做完要报告

规则 R1/R2/R3 各自的要点和差异、题里埋了哪些陷阱、check.py 的输出、四份探测答卷的结果（每份每项 pass/fail）、
发现并修过的问题。
