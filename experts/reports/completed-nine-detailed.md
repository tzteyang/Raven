## 网课退款客服（refund-desk）

员工通道：**纯旧通道（OpenRouter）**（以当前完整有效报告中的答卷为准）。
本专家未列入这次109题恢复清单，保留既有旧通道验收；没有因事故重跑。

三版本对照：完整；培养后 revision：`098fe127cd2d9198bbc758b8c153fd22c4c4d47ca9d6045df08fedf37678f6d8`。
每次重复使用同一组 x/y 各 10 题，合计答卷数不代表独立新题。仅完整、逐项 LLM 评审齐全且无派活/证据错误的报告进入能力表。

| 版本 | 完整有效 / 发现报告 | 全对题 x（合计、每次） | 全对题 y（合计、每次） | 挂项 x（合计、每次） | 挂项 y（合计、每次） |
|---|---|---|---|---|---|
| plain | 3 / 3 | 0/30（每次 0/10, 0/10, 0/10） | 4/30（每次 1/10, 2/10, 1/10） | 40/138（每次 12/46, 11/46, 17/46） | 38/138（每次 14/46, 13/46, 11/46） |
| v0 | 3 / 3 | 15/30（每次 6/10, 5/10, 4/10） | 18/30（每次 5/10, 6/10, 7/10） | 18/138（每次 4/46, 6/46, 8/46） | 14/138（每次 6/46, 4/46, 4/46） |
| 培养后 | 3 / 3 | 30/30（每次 10/10, 10/10, 10/10） | 27/30（每次 9/10, 9/10, 9/10） | 0/138（每次 0/46, 0/46, 0/46） | 3/138（每次 1/46, 1/46, 1/46） |

员工路由分层（与判卷模型无关）：

缺少 transport 字段的旧正常答卷依据实验历史归为 legacy OpenRouter；显式但不完整的元数据归为未记录。不根据当前默认provider反推历史。

- R1：provider=`OpenRouter`；model=`z-ai/glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 180 次（其中 180 次无逐行通道字段，按旧记录归组）。

原完整运行共 9 次，其中 0 次内部混合通道。混合运行仍只计一次完整20题验收；以下是答卷层样本数，覆盖运行数不能跨路由相加成新实验。

| 路由 | 版本 | 题组 | 有效答卷次数 | 不同题号数 | 全对 / 有效答卷 | 失败项 / 适用项 | 覆盖原运行数 |
|---|---|---|---:|---:|---|---|---:|
| R1 | plain | x 同规则 | 30 | 10 | 0/30 | 40/138 | 3 |
| R1 | plain | y 新规则 | 30 | 10 | 4/30 | 38/138 | 3 |
| R1 | v0 | x 同规则 | 30 | 10 | 15/30 | 18/138 | 3 |
| R1 | v0 | y 新规则 | 30 | 10 | 18/30 | 14/138 | 3 |
| R1 | 培养后 | x 同规则 | 30 | 10 | 30/30 | 0/138 | 3 |
| R1 | 培养后 | y 新规则 | 30 | 10 | 27/30 | 3/138 | 3 |

异常记录单列（未纳入能力表，也未被程序判成规则失败）：

| 版本 | unknown 待核报告 | 派活 error 报告 | 无适用判定报告 |
|---|---|---|---|
| plain | 0 | 0 | 0 |
| v0 | 0 | 0 | 0 |
| 培养后 | 0 | 0 | 0 |

同一报告可能同时含 error 与 unknown；上表不是互斥报告数。原始报告：

- plain：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/refund-desk/accept-plain-1011-154351.json)
- plain：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/refund-desk/accept-plain-1011-160905.json)
- plain：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/refund-desk/accept-plain-1011-163427.json)
- v0：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/refund-desk/accept-v0-1011-155007.json)
- v0：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/refund-desk/accept-v0-1011-162441.json)
- v0：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/refund-desk/accept-v0-1011-164709.json)
- 培养后：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/refund-desk/accept-098fe127cd2d-1011-151939.json)
- 培养后：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/refund-desk/accept-098fe127cd2d-1011-161650.json)
- 培养后：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/refund-desk/accept-098fe127cd2d-1011-164059.json)

Studio 原 run.out 的 exam 分母会随评审来源、适用项和 unknown 变化，不能当作固定工作规则指标；以下读取当前 session 的 iteration，按 source 和题组分开。位置是记录中的 JSON 路径，不推断补考或额外轮的含义。
当前 session：`live-20261011132451-74e09a`。

| 记录位置 | 评审 source | 题组 | pass | fail | unknown | not_applicable |
|---|---|---|---|---|---|---|
| [rounds[0]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/refund-desk/runs/live-20261011132451-74e09a/iteration/3c6a82cc44d9474bbfad7167ea82c130.json) | rules-judge | x | 41 | 5 | 0 | 0 |
| [rounds[0]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/refund-desk/runs/live-20261011132451-74e09a/iteration/3c6a82cc44d9474bbfad7167ea82c130.json) | rules-judge | y | 41 | 5 | 0 | 0 |
| [rounds[1]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/refund-desk/runs/live-20261011132451-74e09a/iteration/3c6a82cc44d9474bbfad7167ea82c130.json) | assessor | 未定位 | 0 | 0 | 1 | 0 |
| [rounds[1]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/refund-desk/runs/live-20261011132451-74e09a/iteration/3c6a82cc44d9474bbfad7167ea82c130.json) | rules-judge | x | 43 | 3 | 0 | 0 |
| [rounds[1]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/refund-desk/runs/live-20261011132451-74e09a/iteration/3c6a82cc44d9474bbfad7167ea82c130.json) | rules-judge | y | 40 | 6 | 0 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/refund-desk/runs/live-20261011132451-74e09a/iteration/3c6a82cc44d9474bbfad7167ea82c130.json) | assessor | 未定位 | 0 | 0 | 1 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/refund-desk/runs/live-20261011132451-74e09a/iteration/3c6a82cc44d9474bbfad7167ea82c130.json) | rules-judge | x | 45 | 1 | 0 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/refund-desk/runs/live-20261011132451-74e09a/iteration/3c6a82cc44d9474bbfad7167ea82c130.json) | rules-judge | y | 44 | 2 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/refund-desk/runs/live-20261011132451-74e09a/iteration/3c6a82cc44d9474bbfad7167ea82c130.json) | assessor | 未定位 | 0 | 0 | 2 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/refund-desk/runs/live-20261011132451-74e09a/iteration/3c6a82cc44d9474bbfad7167ea82c130.json) | rules-judge | x | 46 | 0 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/refund-desk/runs/live-20261011132451-74e09a/iteration/3c6a82cc44d9474bbfad7167ea82c130.json) | rules-judge | y | 45 | 1 | 0 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/refund-desk/runs/live-20261011132451-74e09a/iteration/3c6a82cc44d9474bbfad7167ea82c130.json) | assessor | 未定位 | 0 | 0 | 2 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/refund-desk/runs/live-20261011132451-74e09a/iteration/3c6a82cc44d9474bbfad7167ea82c130.json) | rules-judge | x | 46 | 0 | 0 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/refund-desk/runs/live-20261011132451-74e09a/iteration/3c6a82cc44d9474bbfad7167ea82c130.json) | rules-judge | y | 45 | 1 | 0 | 0 |

导出的策略产物（文件存在不等于已证明学会；效果还需对照v0、plain及通道条件，跨通道结果仅作描述）：

- 策略文件 `refund_capability.py`（3535 字）
- 技能 `refund-single-reply`：单条退款回复的结论成稿、全篇措辞与长度核对及直接交付。（2028 字）
- 策略项 `capability.strategy`

例题取各版本第一次完整有效验收；固定 x01，并补题号最先的观察改善/退步例（若有）。这是个例展示，不能替代全表；v0及每份答卷的通道一并列出。通道不同的例题不能归因为训练作用。

### x01 · 固定题 x01；改善例（按题号第一处）

<details><summary>plain · OpenRouter / z-ai/glm-5.3-flash：挂项 2/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/refund-desk/accept-plain-1011-154351.json)

<pre>三份文件已读完。核对政策：语言考试冲刺档，购课 9-21，今天 9-24 为第 4 天（≤7 天），已听 2 节（≤3 节）→ 符合全额退款条件，应退 899.00 元；消息含“投诉”，须转人工并告知工单号短信发送。以下是回复学员的消息：

---

邓佳琪同学您好，非常抱歉给您带来不好的体验。您 9 月 21 日购买的“四六级突破营”（订单号 QH20260921X01，实付 899.00 元），在购课 7 天内且已听不超过 3 节，符合全额退款条件，应退金额 899.00 元。您提出的投诉已记录，将转人工专员处理，工单号会短信发送给您。退款到账时间为 3 到 5 个工作日。给您带来不便再次致歉。

---

说明：称呼用“同学”；已写明全额退、金额 899.00 元、转人工及工单号短信通知、到账时间“3 到 5 个工作日”；未出现“马上/今天/尽快”；正文约 140 字（不含空格换行），符合 150 字上限；投诉场景未推荐任何课程。</pre>

</details>
<details><summary>v0 · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/refund-desk/accept-v0-1011-155007.json)

<pre>同学您好！已查到您的订单（四六级突破营，9月21日购课，已听2节）。您购课在7天内且已听节数未超3节，符合全额退款条件，应退金额899.00元，将在3到5个工作日内原路到账。关于助教态度问题，我们已为您转人工处理，工单号会短信发送给您，会有专人跟进核实并回复。给您带来不便，非常抱歉！</pre>

</details>
<details><summary>培养后 · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/refund-desk/accept-098fe127cd2d-1011-151939.json)

<pre>同学您好，您购课在7天全额退期内、已听2节未超3节，可全额退款899.00元，3到5个工作日到账。关于助教态度的投诉，我们已转人工处理，工单号会短信发送给您。</pre>

</details>

## 电商售后投诉处理（complaint-desk）

员工通道：**纯旧通道（OpenRouter）**（以当前完整有效报告中的答卷为准）。
本专家未列入这次109题恢复清单，保留既有旧通道验收；没有因事故重跑。

三版本对照：完整；培养后 revision：`50bd665135f23049740c765559fe6493b827456fc2a8e5ecd51cb2f1b4bb962c`。
每次重复使用同一组 x/y 各 10 题，合计答卷数不代表独立新题。仅完整、逐项 LLM 评审齐全且无派活/证据错误的报告进入能力表。

| 版本 | 完整有效 / 发现报告 | 全对题 x（合计、每次） | 全对题 y（合计、每次） | 挂项 x（合计、每次） | 挂项 y（合计、每次） |
|---|---|---|---|---|---|
| plain | 3 / 3 | 10/30（每次 2/10, 4/10, 4/10） | 22/30（每次 9/10, 6/10, 7/10） | 23/120（每次 9/40, 6/40, 8/40） | 9/120（每次 2/40, 4/40, 3/40） |
| v0 | 3 / 3 | 9/30（每次 3/10, 3/10, 3/10） | 18/30（每次 6/10, 8/10, 4/10） | 32/120（每次 10/40, 11/40, 11/40） | 12/120（每次 4/40, 2/40, 6/40） |
| 培养后 | 3 / 3 | 27/30（每次 8/10, 9/10, 10/10） | 22/30（每次 7/10, 8/10, 7/10） | 3/120（每次 2/40, 1/40, 0/40） | 9/120（每次 3/40, 2/40, 4/40） |

员工路由分层（与判卷模型无关）：

缺少 transport 字段的旧正常答卷依据实验历史归为 legacy OpenRouter；显式但不完整的元数据归为未记录。不根据当前默认provider反推历史。

- R1：provider=`OpenRouter`；model=`z-ai/glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 180 次（其中 180 次无逐行通道字段，按旧记录归组）。

原完整运行共 9 次，其中 0 次内部混合通道。混合运行仍只计一次完整20题验收；以下是答卷层样本数，覆盖运行数不能跨路由相加成新实验。

| 路由 | 版本 | 题组 | 有效答卷次数 | 不同题号数 | 全对 / 有效答卷 | 失败项 / 适用项 | 覆盖原运行数 |
|---|---|---|---:|---:|---|---|---:|
| R1 | plain | x 同规则 | 30 | 10 | 10/30 | 23/120 | 3 |
| R1 | plain | y 新规则 | 30 | 10 | 22/30 | 9/120 | 3 |
| R1 | v0 | x 同规则 | 30 | 10 | 9/30 | 32/120 | 3 |
| R1 | v0 | y 新规则 | 30 | 10 | 18/30 | 12/120 | 3 |
| R1 | 培养后 | x 同规则 | 30 | 10 | 27/30 | 3/120 | 3 |
| R1 | 培养后 | y 新规则 | 30 | 10 | 22/30 | 9/120 | 3 |

异常记录单列（未纳入能力表，也未被程序判成规则失败）：

| 版本 | unknown 待核报告 | 派活 error 报告 | 无适用判定报告 |
|---|---|---|---|
| plain | 0 | 0 | 0 |
| v0 | 0 | 0 | 0 |
| 培养后 | 0 | 0 | 0 |

同一报告可能同时含 error 与 unknown；上表不是互斥报告数。原始报告：

- plain：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-plain-1011-154440.json)
- plain：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-plain-1011-161252.json)
- plain：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-plain-1011-164758.json)
- v0：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-v0-1011-155546.json)
- v0：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-v0-1011-163527.json)
- v0：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-v0-1011-171130.json)
- 培养后：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-50bd665135f2-1011-152216.json)
- 培养后：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-50bd665135f2-1011-162319.json)
- 培养后：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-50bd665135f2-1011-165744.json)

Studio 原 run.out 的 exam 分母会随评审来源、适用项和 unknown 变化，不能当作固定工作规则指标；以下读取当前 session 的 iteration，按 source 和题组分开。位置是记录中的 JSON 路径，不推断补考或额外轮的含义。
当前 session：`live-20261011135058-153aad`。

| 记录位置 | 评审 source | 题组 | pass | fail | unknown | not_applicable |
|---|---|---|---|---|---|---|
| [rounds[0]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/complaint-desk/runs/live-20261011135058-153aad/iteration/edf6496c13cb460bafa795f0b71caa5d.json) | rules-judge | x | 30 | 10 | 0 | 0 |
| [rounds[0]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/complaint-desk/runs/live-20261011135058-153aad/iteration/edf6496c13cb460bafa795f0b71caa5d.json) | rules-judge | y | 36 | 4 | 0 | 0 |
| [rounds[1]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/complaint-desk/runs/live-20261011135058-153aad/iteration/edf6496c13cb460bafa795f0b71caa5d.json) | rules-judge | x | 32 | 8 | 0 | 0 |
| [rounds[1]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/complaint-desk/runs/live-20261011135058-153aad/iteration/edf6496c13cb460bafa795f0b71caa5d.json) | rules-judge | y | 36 | 4 | 0 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/complaint-desk/runs/live-20261011135058-153aad/iteration/edf6496c13cb460bafa795f0b71caa5d.json) | assessor | 未定位 | 1 | 0 | 0 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/complaint-desk/runs/live-20261011135058-153aad/iteration/edf6496c13cb460bafa795f0b71caa5d.json) | rules-judge | x | 38 | 2 | 0 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/complaint-desk/runs/live-20261011135058-153aad/iteration/edf6496c13cb460bafa795f0b71caa5d.json) | rules-judge | y | 38 | 2 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/complaint-desk/runs/live-20261011135058-153aad/iteration/edf6496c13cb460bafa795f0b71caa5d.json) | assessor | y | 0 | 1 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/complaint-desk/runs/live-20261011135058-153aad/iteration/edf6496c13cb460bafa795f0b71caa5d.json) | assessor | 未定位 | 2 | 0 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/complaint-desk/runs/live-20261011135058-153aad/iteration/edf6496c13cb460bafa795f0b71caa5d.json) | rules-judge | x | 40 | 0 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/complaint-desk/runs/live-20261011135058-153aad/iteration/edf6496c13cb460bafa795f0b71caa5d.json) | rules-judge | y | 39 | 1 | 0 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/complaint-desk/runs/live-20261011135058-153aad/iteration/edf6496c13cb460bafa795f0b71caa5d.json) | assessor | x | 3 | 1 | 0 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/complaint-desk/runs/live-20261011135058-153aad/iteration/edf6496c13cb460bafa795f0b71caa5d.json) | rules-judge | x | 37 | 3 | 0 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/complaint-desk/runs/live-20261011135058-153aad/iteration/edf6496c13cb460bafa795f0b71caa5d.json) | rules-judge | y | 38 | 2 | 0 | 0 |

导出的策略产物（文件存在不等于已证明学会；效果还需对照v0、plain及通道条件，跨通道结果仅作描述）：

- 策略文件 `complaint_capability.py`（5409 字）
- 技能 `complaint-compensation`：规则补券与客户赔偿诉求并存时，分项处理并用券后余额判断权限。（1123 字）
- 技能 `complaint-counting`：依据当次规则核对本月同款同问题投诉，归并颜色、归类和去重后决定标记与通知。（936 字）
- 策略项 `capability.strategy`

例题取各版本第一次完整有效验收；固定 x01，并补题号最先的观察改善/退步例（若有）。这是个例展示，不能替代全表；v0及每份答卷的通道一并列出。通道不同的例题不能归因为训练作用。

### x01 · 固定题 x01；改善例（按题号第一处）

<details><summary>plain · OpenRouter / z-ai/glm-5.3-flash：挂项 1/4</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-plain-1011-154440.json)

<pre>## 投诉分析

- **质量问题**：客户反馈“裂缝”，按《问题分类表》归为**开裂**。签收时间 2026-09-25 20:00，现在 2026-09-27 12:00，签收后约 40 小时，**在 48 小时内**，客户可选免费换新或全额退款。
- **送货延迟**：承诺 2026-09-21，实际 2026-09-25，晚了 4 天（&gt;3 天），按规则补 **50.00 元无门槛券**，计入补偿额度。
- **补偿额度**：订单金额 3280.00 元 × 5% = 164.00 元；本订单之前已发补偿 0.00 元，可用额度 164.00 元。50.00 元券在额度内，客服可直接给，无需主管审批。
- **系统性问题判断**：同款号 QM-DT08（不看颜色后缀）同问题“开裂”，本月已有工单 T0918001（2026-09-18，QM-DT08-BK，开裂）1 起；本次为第 2 起，未达第 3 起，**暂不标“系统性问题”**。
- 客户要求的 500 元赔偿超出客服权限（164.00 元），回复中不能先答应。

## 回复草稿

邓欣您好，非常抱歉给您带来了不好的体验！关于您反馈的问题：

1. **餐桌裂缝**：您是 9 月 25 日晚签收的，在签收后 48 小时内，您可以任选其一：**免费换新**一张同款餐桌，或**全额退款** 3280.00 元。您方便的话告诉我们您倾向哪种方式，我们马上为您安排。
2. **送货延迟**：这次比承诺的 9 月 21 日晚了 4 天，我们向您致歉，并补偿 **50 元无门槛优惠券**，已同步到您的账户。
3. 关于您提到的 500 元赔偿，已记录并上报，会有专人进一步与您沟通，请您耐心等待。

再次为给您带来的不便道歉，如有其他问题随时联系我们！

## 处理方式

- 质量问题（开裂，签收后 40 小时）：向客户提供**免费换新**或**全额退款**两种方案，等客户选择后执行。
- 送货延迟 4 天：发放 **50.00 元无门槛券**，计入补偿额度（本订单累计 50.00 元 ≤ 164.00 元额度，客服权限内可直接给）。
- 500 元赔偿诉求：超出客服补偿权限，不在回复中答应，记录后上报主管审批流程。
- 未达“系统性问题”标准（同款号同问题本月第 2 起），无需通知品控。

## CRM 更新

- 新增工单：
  - 工单号：T09270XX（按当日编号规则生成）
  - 日期：2026-09-27 12:00
  - 订单号：X01-ORDER
  - 款号：QM-DT08-BK
  - 问题分类：开裂
  - 问题描述：客户说裂缝，另投诉送货延迟 4 天
  - 已发补偿：50.00 元（无门槛券）
- 系统性标记：同款号 QM-DT08 同“开裂”问题本月第 2 起，不标“系统性问题”，不通知品控。</pre>

</details>
<details><summary>v0 · OpenRouter / z-ai/glm-5.3-flash：挂项 0/4</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-v0-1011-155546.json)

<pre>## 投诉分析

- **质量问题**：客户称实木餐桌有裂缝，按《问题分类表》归为「开裂」。签收时间为 2026-09-25 20:00，现在 2026-09-27 12:00，签收后约 40 小时，在 48 小时内，客户可选免费换新或全额退款。
- **送货延迟**：承诺 2026-09-21 送达，实际 2026-09-25 送达，晚了 4 天（&gt;3 天），按规则补 50.00 元无门槛券，计入补偿额度。
- **客户索赔 500 元**：客服可直接给的补偿上限为订单金额 5%，即 3280.00 × 5% = 164.00 元；500 元超过上限，且本订单此前已发补偿 0.00 元、可用额度仅 164.00 元，回复中不能答应，需主管审批。
- **系统性问题核查**：同款号 QM-DT08（不看颜色后缀）、同问题「开裂」的本月工单：T0918001（QM-DT08-BK，开裂）共 1 起；本次投诉为第 2 起，未达第 3 起，不标「系统性问题」、不通知品控。

## 回复草稿

邓欣您好，非常抱歉给您带来不好的体验。关于餐桌出现裂缝的问题：您的订单在签收后 48 小时内，您可以选择**免费换新**或**全额退款**，您倾向哪种方式请告诉我们，我们马上为您安排。另外，本次配送比承诺的 9 月 21 日晚了 4 天，我们向您补发 50 元无门槛优惠券作为补偿。您提出的 500 元赔偿超出了客服可处理的权限，我们已记录并提交主管审批，审批结果会尽快答复您，请您耐心等待。

## 处理方式

- 质量问题（签收后 48 小时内）：向客户提供免费换新或全额退款两种方案，待客户选择后执行。
- 送货延迟 4 天：补发 50.00 元无门槛券（在 164.00 元客服可给额度内，可直接执行；本订单补偿额度剩余 164.00 − 50.00 = 114.00 元）。
- 500 元赔偿：超出客服权限，提交主管审批，未承诺、未执行。
- 系统性问题：本次为同款号同问题本月第 2 起，不触发通知品控。

## CRM 更新

- 新增工单：日期 2026-09-27 12:00，订单号 X01-ORDER，款号 QM-DT08-BK，问题分类「开裂」，问题描述「客户说裂缝」，已发补偿 0.00 元（50 元券待客户确认方案后随处理一并发放，发放后再更新）。
- 同款号同问题「开裂」本月累计 2 起（含本次），未达第 3 起，不标「系统性问题」。

说明：以上换新/退款、发券及 CRM 写入均为待执行操作，本次仅给出处理方案与记录内容，未实际执行。</pre>

</details>
<details><summary>培养后 · OpenRouter / z-ai/glm-5.3-flash：挂项 0/4</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-50bd665135f2-1011-152216.json)

<pre>## 投诉分析

- 质量问题：客户报告实木餐桌裂缝，按《问题分类表》归为“开裂”。签收时间 2026-09-25 20:00，现在 2026-09-27 12:00，已过 40 小时，在 48 小时内，按规则 1 客户可选免费换新或全额退款。
- 晚送：实际送达 2026-09-25 − 承诺 2026-09-21 = 晚 4 天，超过 3 天（不含 3 天），按规则 3 应补 50.00 元无门槛券，计入补偿额度。
- 补偿额度：订单金额 3280.00 元 × 5% = 164.00 元上限；此前已发补偿 0.00 元；本次晚送券 50.00 元计入额度，券后余额 = 164.00 − 0.00 − 50.00 = 114.00 元。
- 客户索赔 500.00 元：晚送券与该索赔是两项不同事项，券不能替代赔偿诉求。500.00 元 &gt; 164.00 元上限，也超过券后余额 114.00 元，需主管审批，回复中不先答应。
- 同款同问题计数：同款号 QM-DT08（含各颜色）本月“开裂”记录有 T0918001（2026-09-18，订单 QM0939895，QM-DT08-BK，客户说裂缝）；其余 QM-DT08 记录为异响、缺件、变形，不属同问题。本次订单 X01-ORDER 不在其中，为新增一起，合计本月第 2 起，未达第 3 起阈值，不标“系统性问题”、不通知品控。

## 回复草稿

邓欣您好，非常抱歉给您带来不好的体验。关于餐桌裂缝的问题：您的订单在签收后 48 小时内，您可以选择免费换新或全额退款，您希望用哪种方式我们都可以为您办理。关于晚送：本次送达确实比承诺日期晚了 4 天，我们将为您补发 50.00 元无门槛优惠券。关于您提出的 500 元赔偿：这一诉求超出了客服可直接处理的补偿范围，需提交主管审批，审批结果我们会尽快告知，在此之前无法向您承诺具体金额。给您带来不便再次抱歉。

## 处理方式

- 质量问题：在 48 小时内，向客户提供免费换新或全额退款两种方案，待客户选择后办理。
- 晚送补偿：符合规则 3，应补 50.00 元无门槛券，计入补偿额度（额度占用后余额 114.00 元）；该券发放需按权限执行，本单 50.00 元在 164.00 元上限内，客服可直接办理。
- 客户 500.00 元索赔：超过券后余额 114.00 元及 164.00 元上限，需提交主管审批，不先答应、不与 50.00 元券合并或替代。
- 同款同问题：本月 QM-DT08 开裂共 2 起（含本次），未达第 3 起，不安排“系统性问题”标记和品控通知。

## CRM 更新

- 为订单 X01-ORDER（款号 QM-DT08-BK）新建本月工单，问题分类“开裂”，记录客户诉求（换新/退款、500 元赔偿）及上述处理进度：换新/退款待客户选择，50.00 元券可办理，500 元索赔需提交主管审批。
- 同款同问题本月起数为 2，未达阈值，本次不做“系统性问题”标记，不通知品控。</pre>

</details>

### x03 · 退步例（按题号第一处）

<details><summary>plain · OpenRouter / z-ai/glm-5.3-flash：挂项 0/4</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-plain-1011-154440.json)

<pre>## 投诉分析

- **时效判断**：签收时间为 2026-09-23 05:00，现在为 2026-09-25 17:00，已过 **60 小时**，超过 48 小时。按规则 1，不能直接答应换新或退款，只能提交质检申请。
- **送货延迟**：承诺 2026-09-19 送达，实际 2026-09-23 送达，晚了 **4 天**（&gt;3 天），按规则 3 应补 **50.00 元无门槛券**，计入补偿额度。
- **补偿额度**：客服可直接给的补偿上限为订单金额 5% = 4599.00 × 5% = **229.95 元**。本订单之前已发补偿 0.00 元，50.00 元券在额度内，客服可直接给。客户要求的 200 元赔偿超过常规补偿口径，且质量问题已过 48 小时，不能先答应。
- **系统性问题判断**：同款号 QM-SF03（不看颜色后缀）、同问题「破损」（磕碰按《问题分类表》归为破损）本月工单已有 2 起（T0911002、T0918001），本次为第 **3** 起，按规则 4 应在 CRM 标注「系统性问题」并通知品控。

## 回复草稿

蒋悦您好，很抱歉给您带来不好的购物体验。关于沙发磕碰的问题，由于已超过签收后 48 小时，我们已为您提交质检申请，质检结果出来后会第一时间与您联系，届时根据质检结论为您安排后续处理。关于送货延迟 4 天的问题，我们向您诚挚道歉，并为您补偿 50 元无门槛优惠券，已发放到您的账户。您提到的 200 元赔偿，我们已记录您的诉求，会一并提交给主管评估，有结果会尽快答复您。感谢您的理解与耐心。

## 处理方式

1. 为订单 X03-ORDER 提交质检申请（磕碰问题，签收已超 48 小时，不承诺换新/退款）。
2. 发放 50.00 元无门槛券（晚送 4 天，规则 3），计入补偿额度；本订单累计补偿 50.00 元，未超 229.95 元上限。
3. 客户提出的 200 元赔偿诉求：记录并转主管审批，不在回复中先答应。
4. CRM 标注「系统性问题」并通知品控（QM-SF03 破损本月第 3 起）。

## CRM 更新

- 新建工单：订单 X03-ORDER，款号 QM-SF03-OK，问题分类「破损」（客户说磕碰），日期 2026-09-25 17:00，已发补偿 50.00 元。
- 标注：**系统性问题**（QM-SF03 款号「破损」本月第 3 起：T0911002、T0918001、本单），已通知品控。
- 备注：签收超 48 小时，已转质检申请；晚送 4 天补 50 元券；200 元赔偿诉求待主管审批。</pre>

</details>
<details><summary>v0 · OpenRouter / z-ai/glm-5.3-flash：挂项 1/4</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-v0-1011-155546.json)

<pre>## 投诉分析

**事实核对（依据本次订单记录与 CRM）**
- 订单 X03-ORDER，蒋悦，布艺沙发，款号 QM-SF03-OK，订单金额 4599.00 元，此前已发补偿 0.00 元。
- 承诺送达 2026-09-19，实际送达 2026-09-23，晚了 4 天（&gt;3 天，不含 3 天），触发晚送补偿。
- 签收时间 2026-09-23 05:00，现在 2026-09-25 17:00，已过 60 小时，**超过 48 小时**。
- 客户陈述“磕碰”，按《问题分类表》归入**破损**。是否属实属待核实事项，需质检确认。

**规则适用**
1. 质量问题已超签收后 48 小时：按规则 1，**不能在回复中答应换新或退款**，只提交质检申请。
2. 晚送 4 天：按规则 3，补 50.00 元无门槛券，计入补偿额度。
3. 补偿额度：4599.00 × 5% = 229.95 元，此前已发 0.00 元，剩余 229.95 元；50.00 元券在额度内，客服可直接给。客户索要的 200 元现金赔偿无规则依据，且涉及质量问题的处理须先走质检，不在回复中答应。
4. 系统性判断：按补充口径，款号看 QM-SF03（不含颜色后缀）。本月同款号同问题（破损）已有 2 起：T0911002（QM-SF03-OK，磕碰）、T0918001（QM-SF03-OK，磕碰）。本订单本月无既有工单，本次计为第 3 起 → **CRM 标“系统性问题”并通知品控**。

## 回复草稿

&gt; 蒋悦您好，很抱歉给您带来不好的体验。经核对，您的订单实际送达比承诺的 9 月 19 日晚了 4 天，按我们的售后规则，为您补发一张 50.00 元无门槛优惠券，稍后会发到您的账户。
&gt; 关于沙发磕碰的问题：由于已超过签收后 48 小时，我们无法直接为您办理退货退款，但会立即为您提交质检申请，由质检人员核实磕碰情况，核实后按质检结果为您处理。请您保留商品现状并配合质检，我们会尽快跟进并回复您。
&gt; 您提出的 200 元赔偿，目前无法直接答应，需以质检结果为准，请您理解。

## 处理方式

- 提交该订单的质量问题（破损/磕碰）质检申请（因超 48 小时，不办理换新/退款）。
- 发放 50.00 元无门槛券（晚送补偿，计入补偿额度；发放后本订单累计补偿 50.00 元，额度剩余 179.95 元）。
- 200 元赔偿诉求不答应，待质检结果后再定。
- 通知品控该款号系统性问题（见下）。

## CRM 更新

- 新增工单：订单 X03-ORDER，款号 QM-SF03-OK，问题分类：破损，问题描述：客户说磕碰，已发补偿：50.00 元。
- 该款号（QM-SF03）本月“破损”问题已达第 3 起，工单标记**“系统性问题”**，并通知品控。
- 注：以上为拟执行操作，本次未实际写入 CRM 或发放券，需按流程执行后回填。</pre>

</details>
<details><summary>培养后 · OpenRouter / z-ai/glm-5.3-flash：挂项 1/4</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-50bd665135f2-1011-152216.json)

<pre>## 投诉分析

- 质量问题：客户报告布艺沙发（款号 QM-SF03-OK，订单 X03-ORDER，订单金额 4599.00 元）有磕碰，按《问题分类表》归为“破损”。签收时间为 2026-09-23 05:00，现在 2026-09-25 17:00，已过 60 小时，超过 48 小时，按规则 1 不直接答应换新或退款，只提交质检申请。
- 晚送：实际送达 2026-09-23，承诺 2026-09-19，晚了 4 天，超过 3 天（不含 3 天），按规则 3 应补 50.00 元无门槛券，计入补偿额度。
- 独立索赔：客户另要求赔 200.00 元。补偿额度上限为订单金额 5%＝229.95 元，此前已发补偿 0.00 元，本次应计入额度的晚送券 50.00 元，券后余额＝229.95−0.00−50.00＝179.95 元。索赔 200.00 元＞179.95 元，超过客服可直接给的额度，需提交主管审批，回复中不先答应。晚送券与客户索赔金额不同且客户未同意以券替代，两项分别处理。
- 同款同问题计数：同款号按 QM-SF03（不看颜色后缀）查本月“破损”类记录：T0911002（QM-SF03-OK，磕碰）、T0918001（QM-SF03-OK，磕碰），共 2 起且订单各不相同；本次订单 X03-ORDER 不在其中，新增 1 起，合计本月第 3 起，达到规则 4 阈值。

## 回复草稿

蒋悦您好，很抱歉给您带来不好的体验。您反馈的沙发磕碰问题已收到，因签收已超过 48 小时，我们将为您提交质检申请，由质检核实后处理，暂不能直接承诺退货或退款，请您理解。关于晚送 4 天，按店铺规定可为您补 50.00 元无门槛券（需提交主管审批后发放）。您提出的 200 元赔偿诉求已记录，因超出客服可直接处理的额度，需提交主管审批，审批结果我们会另行告知，请您耐心等待。

## 处理方式

- 质量问题：需提交主管审批——提交质检申请（签收超 48 小时，不直接办理换新/退款）。
- 晚送补偿：需提交主管审批——拟补 50.00 元无门槛券，计入补偿额度（发放前不写已发）。
- 客户索赔 200.00 元：超过券后余额 179.95 元，需提交主管审批，不提前承诺赔付。
- 同款同问题本月第 3 起：按规则 4 在 CRM 标“系统性问题”并通知品控（待执行，不写已完成）。

## CRM 更新

- 新建工单：订单 X03-ORDER，款号 QM-SF03-OK，问题分类“破损”，问题描述“客户说磕碰”。
- 该订单本月无既有同问题工单，本次计为同款号同问题本月第 3 起，工单标记“系统性问题”，并通知品控。
- 记录补偿事项：晚送券 50.00 元（拟发，待审批）、客户索赔 200.00 元（待主管审批），本订单已发补偿仍为 0.00 元。</pre>

</details>

## 营销海报审查（poster-review）

员工通道：**纯旧通道（OpenRouter）**（以当前完整有效报告中的答卷为准）。
本专家未列入这次109题恢复清单，保留既有旧通道验收；没有因事故重跑。

三版本对照：完整；培养后 revision：`8ab6e08e3fe15439c773463f111f4d2dc99a54fa605ebd55abb9a5aa4f9e5b9c`。
每次重复使用同一组 x/y 各 10 题，合计答卷数不代表独立新题。仅完整、逐项 LLM 评审齐全且无派活/证据错误的报告进入能力表。

| 版本 | 完整有效 / 发现报告 | 全对题 x（合计、每次） | 全对题 y（合计、每次） | 挂项 x（合计、每次） | 挂项 y（合计、每次） |
|---|---|---|---|---|---|
| plain | 3 / 3 | 21/30（每次 8/10, 7/10, 6/10） | 16/30（每次 3/10, 7/10, 6/10） | 10/150（每次 2/50, 3/50, 5/50） | 16/150（每次 8/50, 4/50, 4/50） |
| v0 | 3 / 3 | 19/30（每次 6/10, 8/10, 5/10） | 5/30（每次 2/10, 3/10, 0/10） | 11/150（每次 4/50, 2/50, 5/50） | 32/150（每次 11/50, 7/50, 14/50） |
| 培养后 | 3 / 3 | 27/30（每次 10/10, 10/10, 7/10） | 22/30（每次 9/10, 6/10, 7/10） | 3/150（每次 0/50, 0/50, 3/50） | 8/150（每次 1/50, 4/50, 3/50） |

员工路由分层（与判卷模型无关）：

缺少 transport 字段的旧正常答卷依据实验历史归为 legacy OpenRouter；显式但不完整的元数据归为未记录。不根据当前默认provider反推历史。

- R1：provider=`OpenRouter`；model=`z-ai/glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 180 次（其中 180 次无逐行通道字段，按旧记录归组）。

原完整运行共 9 次，其中 0 次内部混合通道。混合运行仍只计一次完整20题验收；以下是答卷层样本数，覆盖运行数不能跨路由相加成新实验。

| 路由 | 版本 | 题组 | 有效答卷次数 | 不同题号数 | 全对 / 有效答卷 | 失败项 / 适用项 | 覆盖原运行数 |
|---|---|---|---:|---:|---|---|---:|
| R1 | plain | x 同规则 | 30 | 10 | 21/30 | 10/150 | 3 |
| R1 | plain | y 新规则 | 30 | 10 | 16/30 | 16/150 | 3 |
| R1 | v0 | x 同规则 | 30 | 10 | 19/30 | 11/150 | 3 |
| R1 | v0 | y 新规则 | 30 | 10 | 5/30 | 32/150 | 3 |
| R1 | 培养后 | x 同规则 | 30 | 10 | 27/30 | 3/150 | 3 |
| R1 | 培养后 | y 新规则 | 30 | 10 | 22/30 | 8/150 | 3 |

异常记录单列（未纳入能力表，也未被程序判成规则失败）：

| 版本 | unknown 待核报告 | 派活 error 报告 | 无适用判定报告 |
|---|---|---|---|
| plain | 0 | 0 | 0 |
| v0 | 0 | 0 | 0 |
| 培养后 | 0 | 0 | 0 |

同一报告可能同时含 error 与 unknown；上表不是互斥报告数。原始报告：

- plain：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-plain-1011-154727.json)
- plain：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-plain-1011-161118.json)
- plain：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-plain-1011-165018.json)
- v0：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-v0-1011-155625.json)
- v0：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-v0-1011-163615.json)
- v0：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-v0-1011-171405.json)
- 培养后：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-8ab6e08e3fe1-1011-153944.json)
- 培养后：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-8ab6e08e3fe1-1011-162355.json)
- 培养后：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-8ab6e08e3fe1-1011-170035.json)

Studio 原 run.out 的 exam 分母会随评审来源、适用项和 unknown 变化，不能当作固定工作规则指标；以下读取当前 session 的 iteration，按 source 和题组分开。位置是记录中的 JSON 路径，不推断补考或额外轮的含义。
当前 session：`live-20261011135907-d09c71`。

| 记录位置 | 评审 source | 题组 | pass | fail | unknown | not_applicable |
|---|---|---|---|---|---|---|
| [rounds[0]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/poster-review/runs/live-20261011135907-d09c71/iteration/8eb48c1ee1fb408ebd95363668bb0c65.json) | rules-judge | x | 44 | 6 | 0 | 0 |
| [rounds[0]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/poster-review/runs/live-20261011135907-d09c71/iteration/8eb48c1ee1fb408ebd95363668bb0c65.json) | rules-judge | y | 40 | 10 | 0 | 0 |
| [rounds[1]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/poster-review/runs/live-20261011135907-d09c71/iteration/8eb48c1ee1fb408ebd95363668bb0c65.json) | assessor | 未定位 | 1 | 0 | 0 | 0 |
| [rounds[1]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/poster-review/runs/live-20261011135907-d09c71/iteration/8eb48c1ee1fb408ebd95363668bb0c65.json) | rules-judge | x | 48 | 2 | 0 | 0 |
| [rounds[1]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/poster-review/runs/live-20261011135907-d09c71/iteration/8eb48c1ee1fb408ebd95363668bb0c65.json) | rules-judge | y | 43 | 7 | 0 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/poster-review/runs/live-20261011135907-d09c71/iteration/8eb48c1ee1fb408ebd95363668bb0c65.json) | assessor | 未定位 | 4 | 0 | 0 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/poster-review/runs/live-20261011135907-d09c71/iteration/8eb48c1ee1fb408ebd95363668bb0c65.json) | rules-judge | x | 43 | 7 | 0 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/poster-review/runs/live-20261011135907-d09c71/iteration/8eb48c1ee1fb408ebd95363668bb0c65.json) | rules-judge | y | 42 | 8 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/poster-review/runs/live-20261011135907-d09c71/iteration/8eb48c1ee1fb408ebd95363668bb0c65.json) | assessor | x | 0 | 1 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/poster-review/runs/live-20261011135907-d09c71/iteration/8eb48c1ee1fb408ebd95363668bb0c65.json) | assessor | y | 0 | 1 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/poster-review/runs/live-20261011135907-d09c71/iteration/8eb48c1ee1fb408ebd95363668bb0c65.json) | assessor | 未定位 | 4 | 0 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/poster-review/runs/live-20261011135907-d09c71/iteration/8eb48c1ee1fb408ebd95363668bb0c65.json) | rules-judge | x | 49 | 1 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/poster-review/runs/live-20261011135907-d09c71/iteration/8eb48c1ee1fb408ebd95363668bb0c65.json) | rules-judge | y | 46 | 4 | 0 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/poster-review/runs/live-20261011135907-d09c71/iteration/8eb48c1ee1fb408ebd95363668bb0c65.json) | assessor | x | 0 | 2 | 0 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/poster-review/runs/live-20261011135907-d09c71/iteration/8eb48c1ee1fb408ebd95363668bb0c65.json) | assessor | 未定位 | 4 | 0 | 1 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/poster-review/runs/live-20261011135907-d09c71/iteration/8eb48c1ee1fb408ebd95363668bb0c65.json) | rules-judge | x | 47 | 3 | 0 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/poster-review/runs/live-20261011135907-d09c71/iteration/8eb48c1ee1fb408ebd95363668bb0c65.json) | rules-judge | y | 49 | 1 | 0 | 0 |

导出的策略产物（文件存在不等于已证明学会；效果还需对照v0、plain及通道条件，跨通道结果仅作描述）：

- 策略文件 `poster_capability.py`（2658 字）
- 策略项 `capability.strategy`

例题取各版本第一次完整有效验收；固定 x01，并补题号最先的观察改善/退步例（若有）。这是个例展示，不能替代全表；v0及每份答卷的通道一并列出。通道不同的例题不能归因为训练作用。

### x01 · 固定题 x01

<details><summary>plain · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-plain-1011-154727.json)

<pre>规则和数据都读完了。先核算：

**年卡参考价（第 1 条）**：活动 10 月 8 日开始，前 7 天窗口为 **10 月 1 日–10 月 7 日**（不含开始当天）。窗口内年卡“成交”记录：2850、2680、2570、2470、2670、2710、2760、2940、2830、2880（退款 2850、2390 与作废 2960 已剔除）→ **最低成交价 2470 元**。海报只涉及年卡一种卡种。

**赠品价值（第 2 条）**：私教课门市价 200 元/节 × 8 节 = **1600 元**，不是 2000 元。

## 改后文案

燃点健身 5 周年庆！年卡只要 1099 元（门市价 2470 元），办卡送价值 1600 元的私教课 8 节（私教课单节门市价 200 元 × 8 节）！3 个月瘦不下来全额退款：需每月到店体测、由教练记录，并在会员小程序“售后”入口申请。10 月 8 日起开抢，活动截止日期：10 月 30 日。

## 修改清单

| 原文 | 改成 | 依据第几条 |
|---|---|---|
| 全网第一 | 删掉 | 第 5 条（极限词表含“第一”） |
| 原价 3999 元 | 门市价 2470 元 | 第 1 条（10 月 1 日–7 日年卡最低成交价 2470 元；不写“原价”） |
| 仅剩 20 个名额 | 删掉 | 第 5 条（制造紧迫感说法） |
| 价值 2000 元的私教课 8 节 | 价值 1600 元的私教课 8 节（私教课单节门市价 200 元 × 8 节） | 第 2 条（注明算法，单价按门市价表 200 元/节） |
| 3 个月瘦不下来全额退款 | 3 个月瘦不下来全额退款：需每月到店体测、由教练记录，并在会员小程序“售后”入口申请 | 第 3 条（补全两个条件后才可保留） |
| （无截止日期） | 活动截止日期：10 月 30 日 | 第 4 条 |

补充说明：退款承诺的两个条件（每月到店体测并记录、小程序“售后”入口申请）已按规则写全，故保留该句；若市场部无法落实其中任何一项，则整句应删除。</pre>

</details>
<details><summary>v0 · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-v0-1011-155625.json)

<pre>四份材料已读取完整。按工作规则核算：

**门市价计算**（规则 1：活动 10 月 8 日开始，前 7 天不含当天，即 10 月 1 日–10 月 7 日，只看“成交”状态）：
- 年卡成交记录：2850、2680、2570、2470、2670、2710、2760、2940、2830、2880（退款 2850、2390 及作废 2960 不计）→ 最低 **2470 元**
- 海报只涉及年卡，只写年卡。

**赠品**（规则 2）：私教课门市价 200 元/节 × 8 节 = 1600 元，需注明算法；原文“价值 2000 元”无依据。

## 改后文案

燃点健身 5 周年庆！年卡只要 1099 元（门市价 2470 元）！办卡送价值 1600 元的私教课（私教课单节门市价 200 元 × 8 节）。3 个月瘦不下来可申请退款：需每月到店体测、由教练记录，并在会员小程序“售后”入口申请。10 月 8 日起开抢，活动截止日期：10 月 30 日。

## 修改清单

| 原文 | 改成 | 依据 |
|---|---|---|
| 全网第一 | （删除） | 规则 5（“第一”在极限词表） |
| 原价 3999 元 | 门市价 2470 元 | 规则 1（10 月 1–7 日年卡最低成交价 2470 元，不写“原价”） |
| 仅剩 20 个名额！ | （删除） | 规则 5（“仅剩 N 份”类紧迫说法） |
| 价值 2000 元的私教课 8 节 | 价值 1600 元的私教课（私教课单节门市价 200 元 × 8 节） | 规则 2（赠品门市价表：200 元/节，须注明算法） |
| 3 个月瘦不下来全额退款 | 3 个月瘦不下来可申请退款：需每月到店体测、由教练记录，并在会员小程序“售后”入口申请 | 规则 3（只能写成有条件退款，补齐两项条件） |
| 10 月 8 日起开抢。（无截止日期） | 10 月 8 日起开抢，活动截止日期：10 月 30 日。 | 规则 4（须写截止日期，取题面 10 月 30 日） |

说明：1099 元活动价、5 周年庆、8 节私教课等业务事实题面已有，予以保留；未自行增加任何促销条件或日期。本稿依据齐全，可直接发布。</pre>

</details>
<details><summary>培养后 · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-8ab6e08e3fe1-1011-153944.json)

<pre>核算完成：窗口内年卡成交记录 10 笔，最低成交价 2470 元；赠品私教课 8 节 × 200 元/节 = 1600 元。

## 改后文案

燃点健身 5 周年庆！年卡只要 1099 元（门市价 2470 元）。办卡送价值 1600 元的私教课（私教课单节门市价 200 元 × 8 节）。3 个月瘦不下来可申请退款：需每月到店体测、由教练记录，并在会员小程序“售后”入口申请。活动 10 月 8 日开始，活动截止日期：10 月 30 日。

## 修改清单

| 原文 | 改成 | 依据第几条 |
|---|---|---|
| 全网第一 | 删除 | 依据第 5 条 |
| 年卡只要 1099 元（原价 3999 元） | 年卡只要 1099 元（门市价 2470 元） | 依据第 1 条 |
| 仅剩 20 个名额！ | 删除 | 依据第 5 条 |
| 办卡送价值 2000 元的私教课 8 节 | 办卡送价值 1600 元的私教课（私教课单节门市价 200 元 × 8 节） | 依据第 2 条 |
| 3 个月瘦不下来全额退款！ | 3 个月瘦不下来可申请退款：需每月到店体测、由教练记录，并在会员小程序“售后”入口申请。 | 依据第 3 条 |
| 10 月 8 日起开抢 | 活动 10 月 8 日开始 | 依据第 5 条 |
| （原文未写截止日期） | 活动截止日期：10 月 30 日 | 依据第 4 条 |

说明：参考价 2470 元按规则第 1 条口径核算——活动开始前 7 天（2026-10-01 至 2026-10-07，不含开始当天）年卡“成交”状态记录共 10 笔，取最低价；海报仅涉及年卡一种卡种。活动售价 1099 元按原稿保留。</pre>

</details>

### x03 · 改善例（按题号第一处）

<details><summary>plain · OpenRouter / z-ai/glm-5.3-flash：挂项 1/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-plain-1011-154727.json)

<pre>规则和资料都读完了。先核算关键数据：

**参考价核算**（活动 2026-12-20 开始，前 7 天不含当天 = 12 月 13 日至 12 月 19 日，只看“成交”状态的 20 次卡）：
- 12-13：1170；12-14：1250（1210 为退款，不计）；12-15：1160、1220、1230（1050 为退款，不计）；12-16：1360；12-17：1330；12-18：1150、1180、1300；12-19：1270
- **最低实际成交价 = 1150 元**（12 月 18 日，门店）

**赠品核算**：体测门市价 99 元/次，海报写的“价值 199 元”与价表不符，应为 99 元。

## 改后文案

「燃点健身 5 周年庆！20 次卡只要 599 元（门市价 1150 元），办卡送价值 99 元（体测门市价 99 元 × 1 次）的体测 1 次！12 月 20 日起开抢。活动截止日期：2027 年 1 月 10 日。」

## 修改清单

| 原文 | 改成 | 依据第几条 |
|---|---|---|
| 极致 | （删除） | 第 5 条（极限词表收录“极致”） |
| 20 次卡只要 599 元（原价 1680 元） | 20 次卡只要 599 元（门市价 1150 元） | 第 1 条（不写“原价”；门市价取活动开始前 7 天、不含当天的最低实际成交价，12 月 13–19 日成交记录中最低为 1150 元） |
| 办卡送价值 199 元的体测 1 次 | 办卡送价值 99 元（体测门市价 99 元 × 1 次）的体测 1 次 | 第 2 条（赠品须注明算法，单价按《赠品门市价表》体测 99 元/次） |
| （无截止日期） | 活动截止日期：2027 年 1 月 10 日 | 第 4 条 |
| 手慢无 | （删除） | 第 5 条（制造紧迫感的说法一律删掉，不换说法） |

说明：原文没有效果承诺类语句，第 3 条不涉及；海报只涉及 20 次卡一种卡种，故只写一个参考价。</pre>

</details>
<details><summary>v0 · OpenRouter / z-ai/glm-5.3-flash：挂项 1/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-v0-1011-155625.json)

<pre>四份材料已读取完毕。核对要点：

- **价格**：活动 2026-12-20 开始，前 7 天（不含当天）= 12-13 至 12-19。20 次卡“成交”记录最低价为 **1150 元**（12-18，S12180112），故写“门市价 1150 元”，不写“原价 1680 元”。
- **赠品**：体测门市价 99 元/次，海报写 199 元无依据，需按价表改并注明算法。
- **极限词/紧迫感**：“极致”（词表内）、“手慢无”（规则 5）均删。
- **截止日期**：按规则 4 补“活动截止日期：1 月 10 日”。

## 改后文案

「燃点健身 5 周年庆！20 次卡只要 599 元（门市价 1150 元）！办卡送价值 99 元（体测门市价 99 元/次 × 1 次）的体测 1 次！12 月 20 日起开抢。活动截止日期：1 月 10 日。」

## 修改清单

| 原文 | 改成 | 依据 |
|---|---|---|
| 极致 | 删除 | 规则 5（“极致”在极限词表内，不换其他说法） |
| 20 次卡只要 599 元（原价 1680 元） | 20 次卡只要 599 元（门市价 1150 元） | 规则 1：不写“原价”；门市价取活动开始前 7 天（12-13 至 12-19）20 次卡“成交”记录最低价 1150 元（退款、作废记录已剔除） |
| 办卡送价值 199 元的体测 1 次 | 办卡送价值 99 元（体测门市价 99 元/次 × 1 次）的体测 1 次 | 规则 2 + 《赠品门市价表》：体测门市价 99 元/次，须注明算法；199 元无依据 |
| 手慢无 | 删除 | 规则 5（制造紧迫感的说法一律删掉） |
| （无截止日期） | 活动截止日期：1 月 10 日 | 规则 4（题面：2027-01-10 截止） |

599 元活动价本身未改动（规则未要求核算活动价，仅规范参考价写法）。</pre>

</details>
<details><summary>培养后 · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-8ab6e08e3fe1-1011-153944.json)

<pre>核算完成：窗口内 20 次卡成交 11 笔，最低成交价 1150 元；赠品体测按门市价 99 元/次 × 1 次 = 99 元。

## 改后文案

「燃点健身 5 周年庆！20 次卡只要 599 元（门市价 1150 元），办卡送价值 99 元（体测门市价 99 元 × 1 次）的体测 1 次！12 月 20 日开始。活动截止日期：1 月 10 日。」

## 修改清单

| 原文 | 改成 | 依据第几条 |
|---|---|---|
| 极致 | （删除） | 第 5 条 |
| 原价 1680 元 | 门市价 1150 元 | 第 1 条 |
| 手慢无 | （删除） | 第 5 条 |
| 价值 199 元的体测 1 次 | 价值 99 元（体测门市价 99 元 × 1 次）的体测 1 次 | 第 2 条 |
| 12 月 20 日起开抢 | 12 月 20 日开始 | 第 5 条 |
| （原文未写截止日期） | 活动截止日期：1 月 10 日 | 第 4 条 |

说明（发布文案之外，供内部核实）：门市价 1150 元取自 2026-12-13 至 2026-12-19（不含 12-20 当天）20 次卡状态为“成交”的 11 笔记录的最低价；活动售价 599 元按原稿保留，未做核算改动。</pre>

</details>

### y02 · 退步例（按题号第一处）

<details><summary>plain · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-plain-1011-154727.json)

<pre>审查完成，共改 5 处，结果已交付《海报审查结果.md》。

**改后文案（可直接发布）：**

「蓝湾游泳 8 周年庆！季卡 599 元（门店价 1080 元）！办卡送价值 55.2 元（泳镜门市价 69 元 × 1 副 × 8 折）的泳镜 1 副！11 月 14 日起开抢，12 月 5 日截止。」

**修改要点：**
1. **「顶级」删除** — 在极限词表内（第 5 条）。
2. **「原价 1599 元」→「门店价 1080 元」** — 活动开始前 7 天（11-07~11-13）门店渠道、成交状态的季卡最低价为 1080 元（第 1 条）。
3. **「仅剩 50 份！」删除** — 制造紧迫感的说法（第 5 条）。
4. **赠品价值 100 元 → 55.2 元** — 泳镜门市价 69 元 × 1 副 × 8 折（第 2 条）。
5. **补「12 月 5 日截止」**（第 4 条）。

原文案无效果承诺类语句，第 3 条不涉及。

【交付文件 海报审查结果.md】
# 海报审查结果

## 审查结论

共改 5 处：删极限词「顶级」、价格改为按规则核算的门店价并删除「原价」、删紧迫说法「仅剩 50 份」、赠品价值按门市价 8 折重算、补写截止日期。

## 改后文案

「蓝湾游泳 8 周年庆！季卡 599 元（门店价 1080 元）！办卡送价值 55.2 元（泳镜门市价 69 元 × 1 副 × 8 折）的泳镜 1 副！11 月 14 日起开抢，12 月 5 日截止。」

## 修改清单

| 原文 | 改成 | 依据第几条 |
|---|---|---|
| 顶级 | （删除） | 第 5 条（极限词表内，删掉且不换说法） |
| 季卡只要 599 元（原价 1599 元） | 季卡 599 元（门店价 1080 元） | 第 1 条（活动开始前 7 天，即 11 月 7 日—11 月 13 日，门店渠道、状态为成交的季卡最低价为 1080 元；不写「原价」） |
| 仅剩 50 份！ | （删除） | 第 5 条（制造紧迫感的说法，删掉且不换说法） |
| 办卡送价值 100 元的泳镜 1 副 | 办卡送价值 55.2 元（泳镜门市价 69 元 × 1 副 × 8 折）的泳镜 1 副 | 第 2 条（按门市价 × 数量再打 8 折：69 × 1 × 0.8 = 55.2 元） |
| 11 月 14 日起开抢。 | 11 月 14 日起开抢，12 月 5 日截止。 | 第 4 条（必须写截止日期） |
</pre>

</details>
<details><summary>v0 · OpenRouter / z-ai/glm-5.3-flash：挂项 1/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-v0-1011-155625.json)

<pre>四份材料已读取齐全，按本次工作规则审查。

**计算口径核对**：活动 2026-11-14 开始，前 7 天窗口为 11-07 至 11-13（不含开始当天）；海报只涉及季卡一种卡种，只看状态“成交”、渠道“门店”的记录：

- 11-07 季卡 1160（成交/门店）✓
- 11-08 季卡 1080（成交/门店）✓
- 11-09 季卡 1160、1140（成交/门店）✓
- 11-10 季卡 1150（退款/线上）✗
- 11-11 季卡 1130（成交/门店）✓
- 11-12 季卡 1140、1120（成交/线上）✗
- 11-13 季卡 1120（作废/线上）✗

门店成交最低价为 **1080 元**，故写“门店价 1080 元”，不写“原价 1599 元”。

赠品泳镜 1 副：门市价 69 元 × 1 副 × 8 折 = **55.2 元**（价表中泳镜为 69 元/副，非文案所称 100 元）。

## 审查结论

共改 5 处。

## 改后文案

「蓝湾游泳 8 周年庆！季卡只要 599 元（门店价 1080 元），办卡送价值 55.2 元（泳镜门市价 69 元 × 1 副 × 8 折）的泳镜 1 副！11 月 14 日起开抢，12 月 5 日截止。」

## 修改清单

| 原文 | 改成 | 依据 |
|---|---|---|
| 顶级 | （删除） | 规则第 5 条（极限词表含“顶级”） |
| 原价 1599 元 | 门店价 1080 元 | 规则第 1 条 + 成交记录（11-07~11-13 门店成交季卡最低 1080 元） |
| 仅剩 50 份！ | （删除） | 规则第 5 条（“仅剩 N 份”属制造紧迫感，删掉不换说法） |
| 价值 100 元的泳镜 1 副 | 价值 55.2 元（泳镜门市价 69 元 × 1 副 × 8 折）的泳镜 1 副 | 规则第 2 条 + 赠品门市价表（泳镜 69 元/副） |
| 11 月 14 日起开抢。 | 11 月 14 日起开抢，12 月 5 日截止。 | 规则第 4 条（必须写截止日期，见题面 2026-12-05） |

无效果承诺类语句，规则第 3 条不涉及；599 元活动价为本次题面给定事实，予以保留。以上改稿可直接发布。</pre>

</details>
<details><summary>培养后 · OpenRouter / z-ai/glm-5.3-flash：挂项 1/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-8ab6e08e3fe1-1011-153944.json)

<pre>核算完成：季卡门店价 1080 元（11-07 至 11-13 门店成交 5 笔，最低 1080）；赠品泳镜 69 × 1 × 8 折 = 55.2 元。

## 审查结论

一共改了 6 处。

## 改后文案

「蓝湾游泳 8 周年庆！季卡只要 599 元（门店价 1080 元），办卡送价值 55.2 元（泳镜门市价 69 元 × 1 副 × 8 折）的泳镜 1 副！11 月 14 日开始，12 月 5 日截止。」

## 修改清单

| 原文 | 改成 | 依据第几条 |
|---|---|---|
| 顶级 | （删除） | 第 5 条 |
| 季卡只要 599 元（原价 1599 元） | 季卡只要 599 元（门店价 1080 元） | 第 1 条 |
| 仅剩 50 份！ | （删除） | 第 5 条 |
| 价值 100 元的泳镜 1 副 | 价值 55.2 元（泳镜门市价 69 元 × 1 副 × 8 折）的泳镜 1 副 | 第 2 条 |
| 11 月 14 日起开抢 | 11 月 14 日开始 | 第 5 条 |
| （原文未写截止日期） | 12 月 5 日截止 | 第 4 条 |

说明：活动售价 599 元按规则保留；参考价取活动开始前 7 天（11 月 7 日至 11 月 13 日）门店渠道“成交”状态季卡最低价 1080 元；赠品按门市价 69 元 × 1 副 × 8 折 = 55.2 元。</pre>

</details>

## 医疗推文合规审查（dental-post）

员工通道：**纯旧通道（OpenRouter）**（以当前完整有效报告中的答卷为准）。
本专家未列入这次109题恢复清单，保留既有旧通道验收；没有因事故重跑。

三版本对照：完整；培养后 revision：`f220b0b0f4f5667b97695557853f1811f14b2c623ea311b0235734636746d690`。
每次重复使用同一组 x/y 各 10 题，合计答卷数不代表独立新题。仅完整、逐项 LLM 评审齐全且无派活/证据错误的报告进入能力表。

| 版本 | 完整有效 / 发现报告 | 全对题 x（合计、每次） | 全对题 y（合计、每次） | 挂项 x（合计、每次） | 挂项 y（合计、每次） |
|---|---|---|---|---|---|
| plain | 3 / 3 | 4/30（每次 1/10, 1/10, 2/10） | 5/30（每次 1/10, 3/10, 1/10） | 35/150（每次 11/50, 12/50, 12/50） | 34/150（每次 14/50, 9/50, 11/50） |
| v0 | 3 / 3 | 3/30（每次 1/10, 2/10, 0/10） | 4/30（每次 2/10, 0/10, 2/10） | 39/150（每次 14/50, 10/50, 15/50） | 37/150（每次 14/50, 12/50, 11/50） |
| 培养后 | 3 / 3 | 29/30（每次 10/10, 10/10, 9/10） | 24/30（每次 9/10, 7/10, 8/10） | 1/150（每次 0/50, 0/50, 1/50） | 6/150（每次 1/50, 3/50, 2/50） |

员工路由分层（与判卷模型无关）：

缺少 transport 字段的旧正常答卷依据实验历史归为 legacy OpenRouter；显式但不完整的元数据归为未记录。不根据当前默认provider反推历史。

- R1：provider=`OpenRouter`；model=`z-ai/glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 180 次（其中 180 次无逐行通道字段，按旧记录归组）。

原完整运行共 9 次，其中 0 次内部混合通道。混合运行仍只计一次完整20题验收；以下是答卷层样本数，覆盖运行数不能跨路由相加成新实验。

| 路由 | 版本 | 题组 | 有效答卷次数 | 不同题号数 | 全对 / 有效答卷 | 失败项 / 适用项 | 覆盖原运行数 |
|---|---|---|---:|---:|---|---|---:|
| R1 | plain | x 同规则 | 30 | 10 | 4/30 | 35/150 | 3 |
| R1 | plain | y 新规则 | 30 | 10 | 5/30 | 34/150 | 3 |
| R1 | v0 | x 同规则 | 30 | 10 | 3/30 | 39/150 | 3 |
| R1 | v0 | y 新规则 | 30 | 10 | 4/30 | 37/150 | 3 |
| R1 | 培养后 | x 同规则 | 30 | 10 | 29/30 | 1/150 | 3 |
| R1 | 培养后 | y 新规则 | 30 | 10 | 24/30 | 6/150 | 3 |

异常记录单列（未纳入能力表，也未被程序判成规则失败）：

| 版本 | unknown 待核报告 | 派活 error 报告 | 无适用判定报告 |
|---|---|---|---|
| plain | 0 | 0 | 0 |
| v0 | 0 | 0 | 0 |
| 培养后 | 0 | 0 | 0 |

同一报告可能同时含 error 与 unknown；上表不是互斥报告数。原始报告：

- plain：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/accept-plain-1011-200100-f8f329e07a.json)
- plain：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/accept-plain-1011-201359-dca256619d.json)
- plain：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/accept-plain-1011-203156-f6875bff2f.json)
- v0：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/accept-v0-1011-204256-ea213aec97.json)
- v0：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/accept-v0-1011-205846-7602e6ce8b.json)
- v0：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/accept-v0-1011-211110-a7938bb60e.json)
- 培养后：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/accept-f220b0b0f4f5-1011-193059-fbbfa1ef35.json)
- 培养后：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/accept-f220b0b0f4f5-1011-194022-784477a95f.json)
- 培养后：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/accept-f220b0b0f4f5-1011-195059-be9edefd1f.json)

Studio 原 run.out 的 exam 分母会随评审来源、适用项和 unknown 变化，不能当作固定工作规则指标；以下读取当前 session 的 iteration，按 source 和题组分开。位置是记录中的 JSON 路径，不推断补考或额外轮的含义。
当前 session：`live-20261011153837-14c53a`。

| 记录位置 | 评审 source | 题组 | pass | fail | unknown | not_applicable |
|---|---|---|---|---|---|---|
| [rounds[0]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/dental-post/runs/live-20261011153837-14c53a/iteration/39526b21c95649e3928ce19a272a3aea.json) | rules-judge | x | 38 | 12 | 0 | 0 |
| [rounds[0]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/dental-post/runs/live-20261011153837-14c53a/iteration/39526b21c95649e3928ce19a272a3aea.json) | rules-judge | y | 40 | 10 | 0 | 0 |
| [rounds[1]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/dental-post/runs/live-20261011153837-14c53a/iteration/39526b21c95649e3928ce19a272a3aea.json) | assessor | 未定位 | 0 | 2 | 1 | 0 |
| [rounds[1]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/dental-post/runs/live-20261011153837-14c53a/iteration/39526b21c95649e3928ce19a272a3aea.json) | rules-judge | x | 47 | 3 | 0 | 0 |
| [rounds[1]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/dental-post/runs/live-20261011153837-14c53a/iteration/39526b21c95649e3928ce19a272a3aea.json) | rules-judge | y | 46 | 4 | 0 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/dental-post/runs/live-20261011153837-14c53a/iteration/39526b21c95649e3928ce19a272a3aea.json) | assessor | 未定位 | 0 | 1 | 2 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/dental-post/runs/live-20261011153837-14c53a/iteration/39526b21c95649e3928ce19a272a3aea.json) | rules-judge | x | 46 | 4 | 0 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/dental-post/runs/live-20261011153837-14c53a/iteration/39526b21c95649e3928ce19a272a3aea.json) | rules-judge | y | 49 | 1 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/dental-post/runs/live-20261011153837-14c53a/iteration/39526b21c95649e3928ce19a272a3aea.json) | assessor | 未定位 | 0 | 3 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/dental-post/runs/live-20261011153837-14c53a/iteration/39526b21c95649e3928ce19a272a3aea.json) | rules-judge | x | 47 | 3 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/dental-post/runs/live-20261011153837-14c53a/iteration/39526b21c95649e3928ce19a272a3aea.json) | rules-judge | y | 47 | 3 | 0 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/dental-post/runs/live-20261011153837-14c53a/iteration/39526b21c95649e3928ce19a272a3aea.json) | assessor | x | 0 | 4 | 26 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/dental-post/runs/live-20261011153837-14c53a/iteration/39526b21c95649e3928ce19a272a3aea.json) | assessor | y | 1 | 4 | 25 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/dental-post/runs/live-20261011153837-14c53a/iteration/39526b21c95649e3928ce19a272a3aea.json) | rules-judge | x | 48 | 2 | 0 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/dental-post/runs/live-20261011153837-14c53a/iteration/39526b21c95649e3928ce19a272a3aea.json) | rules-judge | y | 48 | 2 | 0 | 0 |

导出的策略产物（文件存在不等于已证明学会；效果还需对照v0、plain及通道条件，跨通道结果仅作描述）：

- 策略文件 `review_capability.py`（3883 字）
- 技能 `post-review-delivery`：取得本篇材料后，用允许字段的新句、规定结构和实际改写结果组成交付。（1217 字）
- 策略项 `capability.strategy`

例题取各版本第一次完整有效验收；固定 x01，并补题号最先的观察改善/退步例（若有）。这是个例展示，不能替代全表；v0及每份答卷的通道一并列出。通道不同的例题不能归因为训练作用。

### x01 · 固定题 x01；改善例（按题号第一处）

<details><summary>plain · OpenRouter / z-ai/glm-5.3-flash：挂项 1/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/accept-plain-1011-200100-f8f329e07a.json)

<pre>## 改后推文

【齿然口腔】主诊医生：周海涛 主任医师。种植牙相关诊疗欢迎咨询了解，点击预约！

配图：儿童诊室.jpg

医疗广告审查证明编号：（沪）医广【2026】第 02-23-311 号

## 修改说明

| 原文 | 改成 | 依据第几条 |
|---|---|---|
| 种植牙零风险 | 删除“零风险” | 第 1 条 |
| 一颗管终身 | 删除该说法 | 第 1 条 |
| 种植科周海涛主任从业 15 年 | 主诊医生：周海涛 主任医师（删去科室、从业年限，“主任”换成名册职称） | 第 2 条 |
| 成功率 99.3% | 删除该说法 | 第 2 条 |
| 种植牙特价 3980 元 | 具体费用以面诊方案为准 | 第 5 条 |
| 仅限本月 | 删除该说法 | 第 5 条 |
| 对比图_张女士.jpg | 不用 | 第 3 条 |
| 口腔扫描仪.jpg | 不用 | 第 3 条 |
| 医生合影.jpg | 不用 | 第 3 条 |
| （新增）医疗广告审查证明编号：（沪）医广【2026】第 02-23-311 号 | 加在推文末行 | 第 4 条 |

说明：发布日 2026-12-09，推广项目为种植牙，选用覆盖种植牙且在有效期（2026-02-23 至 2027-02-22）内的证明；配图仅“儿童诊室.jpg”标签为“诊所环境”，其余三张标签均不符，不能使用；“点击预约”按第 5 条保留。</pre>

</details>
<details><summary>v0 · OpenRouter / z-ai/glm-5.3-flash：挂项 2/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/accept-v0-1011-204256-ea213aec97.json)

<pre>资料齐全，按规则改稿如下。

## 改后推文

【齿然口腔】种植牙，种植科主诊医生：周海涛 主任医师。种植牙特价3980元，具体费用以面诊方案为准，点击预约！

配图：儿童诊室.jpg

医疗广告审查证明编号：（沪）医广【2026】第 02-23-311 号

## 修改说明

| 原文 | 改成 | 依据第几条 |
|---|---|---|
| 种植牙零风险 | 删去“零风险” | 第 1 条 |
| 一颗管终身 | 删去 | 第 1 条 |
| 种植科周海涛主任从业 15 年，成功率 99.3% | 种植科主诊医生：周海涛 主任医师 | 第 2 条 |
| 种植牙特价 3980 元，仅限本月 | 具体费用以面诊方案为准 | 第 5 条 |
| 对比图_张女士.jpg | 不用 | 第 3 条 |
| 口腔扫描仪.jpg | 不用 | 第 3 条 |
| 医生合影.jpg | 不用 | 第 3 条 |
| （新增）医疗广告审查证明编号：（沪）医广【2026】第 02-23-311 号 | — | 第 4 条 |

说明：发布日 2026-12-09，推广项目为种植牙，《审查证明表》中覆盖种植牙且在有效期内（2026-02-23 至 2027-02-22）的证明为（沪）医广【2026】第 02-23-311 号。配图清单中仅“儿童诊室.jpg”标签为“诊所环境”，可用；其余三张标签均非诊所环境，不使用。</pre>

</details>
<details><summary>培养后 · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/accept-f220b0b0f4f5-1011-193059-fbbfa1ef35.json)

<pre>## 改后推文

【齿然口腔】种植牙，主诊医生：周海涛 主任医师。具体费用以面诊方案为准，点击预约！

配图：儿童诊室.jpg

医疗广告审查证明编号：（沪）医广【2026】第 02-23-311 号

## 修改说明

| 原文 | 改成 | 依据第几条 |
|---|---|---|
| 种植牙零风险，一颗管终身！ | 种植牙 | 第 1 条 |
| 种植科周海涛主任从业 15 年，成功率 99.3%。 | 主诊医生：周海涛 主任医师。 | 第 2 条 |
| 种植牙特价 3980 元，仅限本月， | 具体费用以面诊方案为准， | 第 5 条 |
| 对比图_张女士.jpg | 不用 | 第 3 条 |
| 口腔扫描仪.jpg | 不用 | 第 3 条 |
| 医生合影.jpg | 不用 | 第 3 条 |
| 原无此行 | 医疗广告审查证明编号：（沪）医广【2026】第 02-23-311 号 | 第 4 条 |</pre>

</details>

## 门店客单价分析（store-ticket）

员工通道：**纯旧通道（OpenRouter）**（以当前完整有效报告中的答卷为准）。
本专家未列入这次109题恢复清单，保留既有旧通道验收；没有因事故重跑。

三版本对照：完整；培养后 revision：`a3a9e4ad8ac567a63d7d6b230064374705dfc9f5ad91e028ae15129ea2dd2f0f`。
每次重复使用同一组 x/y 各 10 题，合计答卷数不代表独立新题。仅完整、逐项 LLM 评审齐全且无派活/证据错误的报告进入能力表。

| 版本 | 完整有效 / 发现报告 | 全对题 x（合计、每次） | 全对题 y（合计、每次） | 挂项 x（合计、每次） | 挂项 y（合计、每次） |
|---|---|---|---|---|---|
| plain | 1 / 1 | 4/10（每次 4/10） | 4/10（每次 4/10） | 12/32（每次 12/32） | 8/33（每次 8/33） |
| v0 | 1 / 1 | 2/10（每次 2/10） | 4/10（每次 4/10） | 14/32（每次 14/32） | 10/33（每次 10/33） |
| 培养后 | 1 / 1 | 8/10（每次 8/10） | 5/10（每次 5/10） | 2/32（每次 2/32） | 6/33（每次 6/33） |

员工路由分层（与判卷模型无关）：

缺少 transport 字段的旧正常答卷依据实验历史归为 legacy OpenRouter；显式但不完整的元数据归为未记录。不根据当前默认provider反推历史。

- R1：provider=`OpenRouter`；model=`z-ai/glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 60 次（其中 60 次无逐行通道字段，按旧记录归组）。

原完整运行共 3 次，其中 0 次内部混合通道。混合运行仍只计一次完整20题验收；以下是答卷层样本数，覆盖运行数不能跨路由相加成新实验。

| 路由 | 版本 | 题组 | 有效答卷次数 | 不同题号数 | 全对 / 有效答卷 | 失败项 / 适用项 | 覆盖原运行数 |
|---|---|---|---:|---:|---|---|---:|
| R1 | plain | x 同规则 | 10 | 10 | 4/10 | 12/32 | 1 |
| R1 | plain | y 新规则 | 10 | 10 | 4/10 | 8/33 | 1 |
| R1 | v0 | x 同规则 | 10 | 10 | 2/10 | 14/32 | 1 |
| R1 | v0 | y 新规则 | 10 | 10 | 4/10 | 10/33 | 1 |
| R1 | 培养后 | x 同规则 | 10 | 10 | 8/10 | 2/32 | 1 |
| R1 | 培养后 | y 新规则 | 10 | 10 | 5/10 | 6/33 | 1 |

异常记录单列（未纳入能力表，也未被程序判成规则失败）：

| 版本 | unknown 待核报告 | 派活 error 报告 | 无适用判定报告 |
|---|---|---|---|
| plain | 0 | 0 | 0 |
| v0 | 0 | 0 | 0 |
| 培养后 | 0 | 0 | 0 |

同一报告可能同时含 error 与 unknown；上表不是互斥报告数。原始报告：

- plain：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/store-ticket/accept-plain-1011-164942.json)
- v0：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/store-ticket/accept-v0-1011-165131.json)
- 培养后：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/store-ticket/accept-a3a9e4ad8ac5-1011-164438.json)

Studio 原 run.out 的 exam 分母会随评审来源、适用项和 unknown 变化，不能当作固定工作规则指标；以下读取当前 session 的 iteration，按 source 和题组分开。位置是记录中的 JSON 路径，不推断补考或额外轮的含义。
当前 session：`live-20261011135231-9fb59c`。

| 记录位置 | 评审 source | 题组 | pass | fail | unknown | not_applicable |
|---|---|---|---|---|---|---|
| [rounds[0]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/store-ticket/runs/live-20261011135231-9fb59c/iteration/42aea0c25c3d40d2ab06096cc6d1cb32.json) | rules-judge | x | 17 | 15 | 0 | 0 |
| [rounds[0]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/store-ticket/runs/live-20261011135231-9fb59c/iteration/42aea0c25c3d40d2ab06096cc6d1cb32.json) | rules-judge | y | 25 | 8 | 0 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/store-ticket/runs/live-20261011135231-9fb59c/iteration/42aea0c25c3d40d2ab06096cc6d1cb32.json) | assessor | x | 0 | 2 | 0 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/store-ticket/runs/live-20261011135231-9fb59c/iteration/42aea0c25c3d40d2ab06096cc6d1cb32.json) | assessor | 未定位 | 1 | 0 | 0 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/store-ticket/runs/live-20261011135231-9fb59c/iteration/42aea0c25c3d40d2ab06096cc6d1cb32.json) | rules-judge | x | 24 | 8 | 0 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/store-ticket/runs/live-20261011135231-9fb59c/iteration/42aea0c25c3d40d2ab06096cc6d1cb32.json) | rules-judge | y | 24 | 9 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/store-ticket/runs/live-20261011135231-9fb59c/iteration/42aea0c25c3d40d2ab06096cc6d1cb32.json) | assessor | x | 0 | 1 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/store-ticket/runs/live-20261011135231-9fb59c/iteration/42aea0c25c3d40d2ab06096cc6d1cb32.json) | assessor | 未定位 | 3 | 0 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/store-ticket/runs/live-20261011135231-9fb59c/iteration/42aea0c25c3d40d2ab06096cc6d1cb32.json) | rules-judge | x | 28 | 4 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/store-ticket/runs/live-20261011135231-9fb59c/iteration/42aea0c25c3d40d2ab06096cc6d1cb32.json) | rules-judge | y | 31 | 2 | 0 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/store-ticket/runs/live-20261011135231-9fb59c/iteration/42aea0c25c3d40d2ab06096cc6d1cb32.json) | assessor | x | 0 | 1 | 0 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/store-ticket/runs/live-20261011135231-9fb59c/iteration/42aea0c25c3d40d2ab06096cc6d1cb32.json) | assessor | y | 0 | 3 | 0 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/store-ticket/runs/live-20261011135231-9fb59c/iteration/42aea0c25c3d40d2ab06096cc6d1cb32.json) | rules-judge | x | 26 | 6 | 0 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/store-ticket/runs/live-20261011135231-9fb59c/iteration/42aea0c25c3d40d2ab06096cc6d1cb32.json) | rules-judge | y | 25 | 8 | 0 | 0 |

导出的策略产物（文件存在不等于已证明学会；效果还需对照v0、plain及通道条件，跨通道结果仅作描述）：

- 策略文件 `store_capability.py`（3350 字）
- 技能 `store-result-handoff`：门店分析限定两期范围、核算对外数字及组装解释和首句时使用的正反例。（2979 字）
- 策略项 `capability.strategy`

例题取各版本第一次完整有效验收；固定 x01，并补题号最先的观察改善/退步例（若有）。这是个例展示，不能替代全表；v0及每份答卷的通道一并列出。通道不同的例题不能归因为训练作用。

### x01 · 固定题 x01；改善例（按题号第一处）

<details><summary>plain · OpenRouter / z-ai/glm-5.3-flash：挂项 2/3</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/store-ticket/accept-plain-1011-164942.json)

<pre>分析完成，按工作规则给出结论：

## 结论（7 月 vs 6 月环比）

**堂食下降最多：武侯店，客单价 18.49 元 → 16.13 元，下降 12.8%**
**外卖下降最多：双流店，客单价 27.16 元 → 22.73 元，下降 16.3%**

（其余门店堂食降幅均在 1.9% 以内、外卖在 2.0% 以内；所有门店两个月都有数据，无因新店缺基期被剔除的情况。）

## 原因分析（仅写数据可见的）

**武侯店·堂食：优惠金额大幅投放是主因**
- 优惠金额占比从 4.2% 升到 16.4%（优惠金额月合计约 6,168 元 → 24,644 元，约 4 倍）。7 月 1 日起几乎每天优惠金额都在 600–1,000 元量级（如 7/1 优惠 797.31 元、实收 4,102.59 元），而 6 月单日多在 160–270 元。
- 团购订单占比基本持平（4.8% → 4.7%），有效订单数还略有增长（7,596 → 7,798 单），说明不是客流或团购结构问题，就是让利拉低了单均实收。
- 待确认：这批优惠是总部统一活动还是门店自行投放、是否包含核销口径异常。

**双流店·外卖：整体单均实收下降，非优惠或团购结构所致**
- 优惠金额占比持平（6.2% → 6.2%），排除优惠加码因素。
- 团购订单占比从 12.6% 骤降到 1.1%（月团购单约 706 单 → 61 单），但拆开看：6 月团购单客单价 27.25 元、非团购单 27.14 元；7 月两者分别为 22.74 元和 22.73 元——团购单和非团购单客单价几乎一样，且同步下降，说明团购占比变化不是客单价下降的原因。
- 有效订单数反而略增（5,612 → 5,799 单），即订单没少、每单收的钱少了。
- 待确认：每单金额整体下移的具体原因（如套餐结构调整、满减门槛变化、客单结构向低价单品迁移）在日报字段中看不到，需结合菜单/活动明细核实。

**另需提醒的数据异常（建议先核实再下经营结论）**：太古里店 7 月数据明显异常——堂食订单量翻倍（4,707 → 10,573 单）而外卖订单骤减（2,953 → 649 单，日均仅约 20 单），疑似两渠道数据串行或上报口径变化，本报告排名未受影响（太古里两项均为上升），但建议核对原始数据。</pre>

</details>
<details><summary>v0 · OpenRouter / z-ai/glm-5.3-flash：挂项 2/3</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/store-ticket/accept-v0-1011-165131.json)

<pre>**结论（7月 vs 6月，环比，堂食/外卖分开）：**

- **堂食下降最多：武侯店**，客单价从 18.49 元降到 16.13 元，**下降 12.8%**
- **外卖下降最多：双流店**，客单价从 27.16 元降到 22.73 元，**下降 16.3%**

（其余门店堂食降幅均在 1.9% 以内、外卖在 2.0% 以内，多数门店客单价持平或微升；所有门店两个月均有数据，无因基期缺数据被剔除的门店。）

**原因（数据可见）：**

1. **武侯店（堂食）**：优惠力度大幅加码。优惠金额占比从 6 月的 4.2% 升到 7 月的 **16.4%**（6 月日均优惠约 200 元，7 月多天达 700–1000 元），是客单价被拉低的最直接因素；团购订单占比基本持平（4.78%→4.74%），不是原因。
2. **双流店（外卖）**：高客单的团购订单占比从 6 月的 **12.6% 骤降到 7 月的 1.1%**（6 月日均团购单约 22 单，7 月多数天只有 1–3 单），团购单占比大幅萎缩拉低了整体客单价；优惠金额占比基本持平（6.2%→6.2%），不是原因。

**待确认**：武侯店 7 月优惠金额为何集中放大（新活动/大额券），双流店外卖团购单为何断崖式减少（团购套餐下架或渠道投放变化）——需向门店或平台侧核实。</pre>

</details>
<details><summary>培养后 · OpenRouter / z-ai/glm-5.3-flash：挂项 0/3</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/store-ticket/accept-a3a9e4ad8ac5-1011-164438.json)

<pre>2026 年 7 月环比 6 月，客单价下降最多的是：外卖渠道双流店，客单价从 27.16 元降至 22.73 元，降幅 16.3%；堂食渠道武侯店，客单价从 18.49 元降至 16.13 元，降幅 12.8%。

原因（数据中可见的变化）：

- **外卖双流店**：团购订单占比从 6 月的 12.6% 降到 7 月的 1.1%（团购订单 706 单→61 单），而优惠金额占比基本持平（6.1%→6.2%）、有效订单数还略有增加（5612→5799 单）。客单下降与团购订单占比大幅回落同步发生；团购订单本身客单高低及其对整体客单的作用机制，日报缺少同口径的团购订单金额，无法直接验证，待确认。
- **堂食武侯店**：优惠金额占比从 6 月的 4.2% 升到 7 月的 16.3%（优惠金额约 5,943 元→约 20,660 元），团购订单占比基本持平（4.8%→4.7%）、有效订单数略增（7596→7798 单）。客单下降与优惠力度明显加大同步发生；该优惠活动属于什么性质、为何集中投放，日报无相关信息，待确认。

口径说明：客单价 =（实收金额 − 退款金额）÷ 有效订单数，有效订单数 = 订单数 − 零元单数 − 全额退款单数；本期为 2026-07-01 至 07-31（744 条记录），基期为 2026-06-01 至 06-30（720 条记录），两期均为 12 家门店，无重复行、无基期缺失门店，全部门店参与排名。</pre>

</details>

### x02 · 退步例（按题号第一处）

<details><summary>plain · OpenRouter / z-ai/glm-5.3-flash：挂项 0/3</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/store-ticket/accept-plain-1011-164942.json)

<pre>**结论：8 月客单价下降最多的是陆家嘴店，客单价从 32.22 元降到 26.87 元，下降 5.35 元，降幅 16.60%**（环比 7 月；外卖+堂食合并口径，客单价=实收金额÷(订单数−零元单数)）。

**原因（有数据依据）：**
- **团购订单占比断崖式下滑**：团购订单占比从 7 月的 12.07% 降到 8 月的 0.96%（团购订单约从 1,445 单降到约 117 单）。7 月陆家嘴店团购占比是全门店最高（第二名中山公园店仅 6.43%），8 月团购套餐基本停售，客单价随之回落——这是最主要原因。
- 其他因素基本排除：外卖订单占比 29.29%→29.44%（基本持平），优惠金额占比 6.03%→5.62%（反而略降），订单量 11,976→12,168（还略增），说明不是客流或渠道结构问题，就是团购拉低客单价的效应消失。

**其余门店**：降幅第二的中山公园店仅降 0.82 元（2.49%），其余门店降幅都在 1.3% 以内，多数门店客单价环比持平或微升，无异常。

（推测）陆家嘴店 8 月团购活动到期或主动下架了团购套餐；若 9 月继续，客单价将维持在 27 元左右，若恢复团购则会回到 32 元水平但单均收入未必更高，建议结合毛利评估团购套餐是否恢复。</pre>

</details>
<details><summary>v0 · OpenRouter / z-ai/glm-5.3-flash：挂项 1/3</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/store-ticket/accept-v0-1011-165131.json)

<pre>**结论：8 月客单价下降最多的是陆家嘴店，客单价从 32.22 元降到 26.87 元，下降 5.35 元，降幅 16.60%。**（其余门店降幅均在 2.5% 以内，另有 6 家门店环比微升。）

**原因分析（按工作规则口径：外卖+堂食合并、退款不扣减、去重后计算）：**

| 指标 | 7 月 | 8 月 | 变化 |
|---|---|---|---|
| 有效订单数（订单数−零元单数） | 11,976 | 12,168 | +192 |
| 实收金额 | 385,886.28 元 | 326,986.94 元 | −58,899.34 元 |
| 客单价 | 32.22 元 | 26.87 元 | −5.35 元（−16.60%） |
| 团购订单占比 | 12.07%（1,446 单） | 0.96%（117 单） | −11.11 个百分点 |
| 外卖订单占比 | 29.29% | 29.44% | 基本持平 |
| 优惠金额占比 | 6.03% | 5.62% | 基本持平 |

**主要原因：团购订单占比断崖式下滑。** 7 月团购核销订单 1,446 单（占有效订单 12.07%），8 月骤降至 117 单（0.96%），减少了 1,329 单。团购到店核销通常对应整单消费（客单价高于散单），这部分高客单订单大量流失，而总订单数基本持平（说明散单补上了缺口），拉低了整体客单价。（推测：可能是 7 月有团购活动到期或平台套餐下架，8 月未续。）

外卖占比、优惠金额占比均基本持平，可排除这两个因素；订单量还在微增，也不是客流问题。

**补充说明：** 本次数据覆盖 2026 年 7–8 月、12 家门店，无基期缺失的新店；数据中未发现同店同日同渠道重复行。</pre>

</details>
<details><summary>培养后 · OpenRouter / z-ai/glm-5.3-flash：挂项 1/3</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/store-ticket/accept-a3a9e4ad8ac5-1011-164438.json)

<pre>2026 年 8 月客单价环比下降最多的是陆家嘴店，客单价从 7 月的 32.22 元降至 8 月的 26.87 元，下降 5.35 元、降幅 16.60%。

原因（外卖＋堂食合并口径，2026 年 7—8 月，12 家门店中 11 家可比）：
- 陆家嘴店团购订单占比从 7 月的 12.07%（1,445 单）骤降至 8 月的 0.96%（117 单），团购订单减少约 1,328 单，是两期之间最突出的结构性变化。若团购订单客单价高于其他订单，其占比大幅下降可能拉低整体客单价；日报缺少团购订单的同口径分组金额，该价值假设及作用机制无法直接验证（推测）。
- 优惠金额占比从 6.03% 微降至 5.62%，变化方向与客单价下降相反，不构成下降原因。
- 其余门店客单价基本稳定或小幅上升（如莘庄店 +1.75%、五角场店 +1.52%），陆家嘴店的降幅远超第二名中山公园店（下降 0.82 元、2.49%）。

口径说明：客单价 = 实收金额 ÷（订单数 − 零元单数），退款不扣减；两期数据各 744 行、无重复行，7 月、8 月均为 12 家门店，全部有基期数据，无门店因缺基期被排除。</pre>

</details>

## 会议待办整理（meeting-actions）

员工通道：**纯旧通道（OpenRouter）**（以当前完整有效报告中的答卷为准）。
本专家未列入这次109题恢复清单，保留既有旧通道验收；没有因事故重跑。

三版本对照：完整；培养后 revision：`51921603a07c003f1c971093525834122bee4a91ccd405f8acde5e2223376efa`。
每次重复使用同一组 x/y 各 10 题，合计答卷数不代表独立新题。仅完整、逐项 LLM 评审齐全且无派活/证据错误的报告进入能力表。

| 版本 | 完整有效 / 发现报告 | 全对题 x（合计、每次） | 全对题 y（合计、每次） | 挂项 x（合计、每次） | 挂项 y（合计、每次） |
|---|---|---|---|---|---|
| plain | 3 / 3 | 28/30（每次 10/10, 9/10, 9/10） | 26/30（每次 7/10, 10/10, 9/10） | 2/150（每次 0/50, 1/50, 1/50） | 6/150（每次 4/50, 0/50, 2/50） |
| v0 | 3 / 3 | 27/30（每次 10/10, 9/10, 8/10） | 23/30（每次 8/10, 6/10, 9/10） | 3/150（每次 0/50, 1/50, 2/50） | 9/150（每次 3/50, 4/50, 2/50） |
| 培养后 | 3 / 3 | 29/30（每次 10/10, 10/10, 9/10） | 26/30（每次 8/10, 9/10, 9/10） | 1/150（每次 0/50, 0/50, 1/50） | 4/150（每次 2/50, 1/50, 1/50） |

员工路由分层（与判卷模型无关）：

缺少 transport 字段的旧正常答卷依据实验历史归为 legacy OpenRouter；显式但不完整的元数据归为未记录。不根据当前默认provider反推历史。

- R1：provider=`OpenRouter`；model=`z-ai/glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 180 次（其中 180 次无逐行通道字段，按旧记录归组）。

原完整运行共 9 次，其中 0 次内部混合通道。混合运行仍只计一次完整20题验收；以下是答卷层样本数，覆盖运行数不能跨路由相加成新实验。

| 路由 | 版本 | 题组 | 有效答卷次数 | 不同题号数 | 全对 / 有效答卷 | 失败项 / 适用项 | 覆盖原运行数 |
|---|---|---|---:|---:|---|---|---:|
| R1 | plain | x 同规则 | 30 | 10 | 28/30 | 2/150 | 3 |
| R1 | plain | y 新规则 | 30 | 10 | 26/30 | 6/150 | 3 |
| R1 | v0 | x 同规则 | 30 | 10 | 27/30 | 3/150 | 3 |
| R1 | v0 | y 新规则 | 30 | 10 | 23/30 | 9/150 | 3 |
| R1 | 培养后 | x 同规则 | 30 | 10 | 29/30 | 1/150 | 3 |
| R1 | 培养后 | y 新规则 | 30 | 10 | 26/30 | 4/150 | 3 |

异常记录单列（未纳入能力表，也未被程序判成规则失败）：

| 版本 | unknown 待核报告 | 派活 error 报告 | 无适用判定报告 |
|---|---|---|---|
| plain | 0 | 0 | 0 |
| v0 | 0 | 0 | 0 |
| 培养后 | 0 | 0 | 0 |

同一报告可能同时含 error 与 unknown；上表不是互斥报告数。原始报告：

- plain：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-plain-1011-195712-f8f329e07a.json)
- plain：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-plain-1011-200713-dca256619d.json)
- plain：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-plain-1011-201632-f6875bff2f.json)
- v0：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-v0-1011-203049-ea213aec97.json)
- v0：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-v0-1011-203944-7602e6ce8b.json)
- v0：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-v0-1011-205005-a7938bb60e.json)
- 培养后：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-51921603a07c-1011-193059-ba62ea87d9.json)
- 培养后：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-51921603a07c-1011-193822-1c3c5611f2.json)
- 培养后：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-51921603a07c-1011-194734-3261e8ba25.json)

Studio 原 run.out 的 exam 分母会随评审来源、适用项和 unknown 变化，不能当作固定工作规则指标；以下读取当前 session 的 iteration，按 source 和题组分开。位置是记录中的 JSON 路径，不推断补考或额外轮的含义。
当前 session：`live-20261011155829-a4cb4c`。

| 记录位置 | 评审 source | 题组 | pass | fail | unknown | not_applicable |
|---|---|---|---|---|---|---|
| [rounds[0]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/meeting-actions/runs/live-20261011155829-a4cb4c/iteration/af9fb873ac9e4ab091afa6d828d5e1d5.json) | rules-judge | x | 49 | 1 | 0 | 0 |
| [rounds[0]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/meeting-actions/runs/live-20261011155829-a4cb4c/iteration/af9fb873ac9e4ab091afa6d828d5e1d5.json) | rules-judge | y | 50 | 0 | 0 | 0 |
| [rounds[1]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/meeting-actions/runs/live-20261011155829-a4cb4c/iteration/af9fb873ac9e4ab091afa6d828d5e1d5.json) | rules-judge | x | 49 | 1 | 0 | 0 |
| [rounds[1]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/meeting-actions/runs/live-20261011155829-a4cb4c/iteration/af9fb873ac9e4ab091afa6d828d5e1d5.json) | rules-judge | y | 48 | 2 | 0 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/meeting-actions/runs/live-20261011155829-a4cb4c/iteration/af9fb873ac9e4ab091afa6d828d5e1d5.json) | rules-judge | x | 50 | 0 | 0 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/meeting-actions/runs/live-20261011155829-a4cb4c/iteration/af9fb873ac9e4ab091afa6d828d5e1d5.json) | rules-judge | y | 47 | 3 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/meeting-actions/runs/live-20261011155829-a4cb4c/iteration/af9fb873ac9e4ab091afa6d828d5e1d5.json) | assessor | 未定位 | 0 | 0 | 1 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/meeting-actions/runs/live-20261011155829-a4cb4c/iteration/af9fb873ac9e4ab091afa6d828d5e1d5.json) | rules-judge | x | 49 | 1 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/meeting-actions/runs/live-20261011155829-a4cb4c/iteration/af9fb873ac9e4ab091afa6d828d5e1d5.json) | rules-judge | y | 47 | 3 | 0 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/meeting-actions/runs/live-20261011155829-a4cb4c/iteration/af9fb873ac9e4ab091afa6d828d5e1d5.json) | assessor | 未定位 | 0 | 0 | 1 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/meeting-actions/runs/live-20261011155829-a4cb4c/iteration/af9fb873ac9e4ab091afa6d828d5e1d5.json) | rules-judge | x | 49 | 1 | 0 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/meeting-actions/runs/live-20261011155829-a4cb4c/iteration/af9fb873ac9e4ab091afa6d828d5e1d5.json) | rules-judge | y | 49 | 1 | 0 | 0 |

导出的策略产物（文件存在不等于已证明学会；效果还需对照v0、plain及通道条件，跨通道结果仅作描述）：

- 策略文件 `meeting_capability.py`（3767 字）
- 技能 `meeting-workday-counting`：按本场起算规则和公司日历类型换算 N 个工作日内；含调休上班计入与排除的对照（1043 字）
- 策略项 `capability.strategy`

例题取各版本第一次完整有效验收；固定 x01，并补题号最先的观察改善/退步例（若有）。这是个例展示，不能替代全表；v0及每份答卷的通道一并列出。通道不同的例题不能归因为训练作用。

### x01 · 固定题 x01

<details><summary>plain · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-plain-1011-195712-f8f329e07a.json)

<pre>## 待办

| 负责人 | 事项 | 截止日期 |
|---|---|---|
| 郑宇 | 后台权限配置 | 2026-11-18 |
| 何静 | 日志告警 | 2026-11-30 |
| 孙婷 | 数据看板 | 2026-11-20 |
| 王磊 | 活动页 | 待定 |
| 刘洋 | 接口文档 | 2026-11-24 |

## 待认领

| 事项 | 截止日期 |
|---|---|
| 需求文档 | 2026-11-20 |</pre>

</details>
<details><summary>v0 · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-v0-1011-203049-ea213aec97.json)

<pre>## 待办

| 负责人 | 事项 | 截止日期 |
|---|---|---|
| 郑宇 | 后台权限配置 | 2026-11-18 |
| 何静 | 日志告警 | 2026-11-30 |
| 孙婷 | 数据看板 | 2026-11-20 |
| 王磊 | 活动页 | 待定 |
| 刘洋 | 接口文档 | 2026-11-24 |

## 待认领

| 事项 | 截止日期 |
|---|---|
| 需求文档 | 2026-11-20 |</pre>

</details>
<details><summary>培养后 · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-51921603a07c-1011-193059-ba62ea87d9.json)

<pre>## 待办

| 负责人 | 事项 | 截止日期 |
|---|---|---|
| 郑宇 | 后台权限配置 | 2026-11-18 |
| 何静 | 日志告警 | 2026-11-30 |
| 孙婷 | 数据看板 | 2026-11-20 |
| 王磊 | 活动页 | 待定 |
| 刘洋 | 接口文档 | 2026-11-24 |

## 待认领

| 事项 | 截止日期 |
|---|---|
| 需求文档 | 2026-11-20 |</pre>

</details>

### y06 · 改善例（按题号第一处）

<details><summary>plain · OpenRouter / z-ai/glm-5.3-flash：挂项 1/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-plain-1011-195712-f8f329e07a.json)

<pre>## 待办事项

| 事项 | 负责人 | 协作人 | 截止日期 |
|---|---|---|---|
| 退费名单 | 唐瑶 | 无 | 2026/09/30 |
| 新教师培训 | 许诺 | 无 | 2026/10/08 |
| 试听课 | 曹阳 | 陈思 | 2026/10/10 |
| 新学期课表 | 许诺 | 无 | 2026/10/08 |
| 直播课课件 | 待认领 | 无 | 2026/09/30 |

## 待确认事项

| 事项 | 要确认什么 |
|---|---|
| 直播课课件 | 负责人 |</pre>

</details>
<details><summary>v0 · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-v0-1011-203049-ea213aec97.json)

<pre>## 待办事项

| 事项 | 负责人 | 协作人 | 截止日期 |
|---|---|---|---|
| 退费名单 | 唐瑶 | 无 | 2026/09/30 |
| 新教师培训 | 许诺 | 无 | 2026/10/08 |
| 试听课 | 曹阳 | 陈思 | 2026/10/12 |
| 新学期课表 | 许诺 | 无 | 2026/10/08 |
| 直播课课件 | 待认领 | 无 | 2026/09/30 |

## 待确认事项

| 事项 | 要确认什么 |
|---|---|
| 直播课课件 | 负责人 |</pre>

</details>
<details><summary>培养后 · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-51921603a07c-1011-193059-ba62ea87d9.json)

<pre>## 待办事项

| 事项 | 负责人 | 协作人 | 截止日期 |
|---|---|---|---|
| 退费名单 | 唐瑶 | 无 | 2026/09/30 |
| 新教师培训 | 许诺 | 无 | 2026/10/08 |
| 试听课 | 曹阳 | 陈思 | 2026/10/12 |
| 新学期课表 | 许诺 | 无 | 2026/10/08 |
| 直播课课件 | 待认领 | 无 | 2026/09/30 |

## 待确认事项

| 事项 | 要确认什么 |
|---|---|
| 直播课课件 | 负责人 |</pre>

</details>

### y10 · 退步例（按题号第一处）

<details><summary>plain · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-plain-1011-195712-f8f329e07a.json)

<pre>## 待办事项

| 事项 | 负责人 | 协作人 | 截止日期 |
|---|---|---|---|
| 补家访记录 | 王芳（市场专员） | 无 | 2026/09/28 |
| 直播课课件 | 杨光 | 无 | 2026/09/21 |
| 出学情报告 | 唐瑶 | 无 | 待定 |
| 出期中试卷 | 待认领 | 无 | 2026/09/28 |
| 排课系统的 bug | 韩雪 | 无 | 2026/09/22 |
| 核对退费名单 | 杨光 | 唐瑶 | 2026/09/23 |
| 新学期课表 | 陈思 | 无 | 2026/09/21 |

## 待确认事项

| 事项 | 要确认什么 |
|---|---|
| 出学情报告 | 截止日期 |
| 出期中试卷 | 负责人 |</pre>

</details>
<details><summary>v0 · OpenRouter / z-ai/glm-5.3-flash：挂项 1/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-v0-1011-203049-ea213aec97.json)

<pre>## 待办事项

| 事项 | 负责人 | 协作人 | 截止日期 |
|---|---|---|---|
| 补家访记录 | 王芳（市场部） | 无 | 2026/09/28 |
| 交直播课课件 | 杨光 | 无 | 2026/09/21 |
| 出学情报告 | 唐瑶 | 无 | 待定 |
| 出期中试卷 | 待认领 | 无 | 2026/09/28 |
| 处理排课系统的 bug | 韩雪 | 无 | 2026/09/22 |
| 核对退费名单 | 杨光 | 唐瑶 | 2026/09/23 |
| 交新学期课表 | 陈思 | 无 | 2026/09/21 |

## 待确认事项

| 事项 | 要确认什么 |
|---|---|
| 出学情报告 | 截止日期 |
| 出期中试卷 | 负责人 |</pre>

</details>
<details><summary>培养后 · OpenRouter / z-ai/glm-5.3-flash：挂项 1/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-51921603a07c-1011-193059-ba62ea87d9.json)

<pre>## 待办事项

| 事项 | 负责人 | 协作人 | 截止日期 |
|---|---|---|---|
| 补家访记录 | 王芳（市场部） | 无 | 2026/09/28 |
| 直播课课件 | 杨光 | 无 | 2026/09/21 |
| 出学情报告 | 唐瑶 | 无 | 待定 |
| 出期中试卷 | 待认领 | 无 | 2026/09/28 |
| 排课系统的 bug | 韩雪 | 无 | 2026/09/22 |
| 核对退费名单 | 杨光 | 唐瑶 | 2026/09/23 |
| 新学期课表 | 陈思 | 无 | 2026/09/21 |

## 待确认事项

| 事项 | 要确认什么 |
|---|---|
| 出学情报告 | 截止日期 |
| 出期中试卷 | 负责人 |</pre>

</details>

## 电商标题和卖点（taobao-title）

员工通道：**纯旧通道（OpenRouter）**（以当前完整有效报告中的答卷为准）。
本专家未列入这次109题恢复清单，保留既有旧通道验收；没有因事故重跑。

三版本对照：完整；培养后 revision：`42a572b356cde6fccb635c6c0e1d7d12418af4930985a75f8727c45b57edb624`。
每次重复使用同一组 x/y 各 10 题，合计答卷数不代表独立新题。仅完整、逐项 LLM 评审齐全且无派活/证据错误的报告进入能力表。

| 版本 | 完整有效 / 发现报告 | 全对题 x（合计、每次） | 全对题 y（合计、每次） | 挂项 x（合计、每次） | 挂项 y（合计、每次） |
|---|---|---|---|---|---|
| plain | 3 / 3 | 22/30（每次 7/10, 7/10, 8/10） | 22/30（每次 8/10, 7/10, 7/10） | 11/120（每次 4/40, 4/40, 3/40） | 9/120（每次 2/40, 3/40, 4/40） |
| v0 | 3 / 3 | 23/30（每次 6/10, 8/10, 9/10） | 21/30（每次 7/10, 8/10, 6/10） | 9/120（每次 5/40, 3/40, 1/40） | 10/120（每次 3/40, 2/40, 5/40） |
| 培养后 | 3 / 3 | 26/30（每次 9/10, 7/10, 10/10） | 27/30（每次 10/10, 7/10, 10/10） | 4/120（每次 1/40, 3/40, 0/40） | 3/120（每次 0/40, 3/40, 0/40） |

员工路由分层（与判卷模型无关）：

缺少 transport 字段的旧正常答卷依据实验历史归为 legacy OpenRouter；显式但不完整的元数据归为未记录。不根据当前默认provider反推历史。

- R1：provider=`OpenRouter`；model=`z-ai/glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 180 次（其中 180 次无逐行通道字段，按旧记录归组）。

原完整运行共 9 次，其中 0 次内部混合通道。混合运行仍只计一次完整20题验收；以下是答卷层样本数，覆盖运行数不能跨路由相加成新实验。

| 路由 | 版本 | 题组 | 有效答卷次数 | 不同题号数 | 全对 / 有效答卷 | 失败项 / 适用项 | 覆盖原运行数 |
|---|---|---|---:|---:|---|---|---:|
| R1 | plain | x 同规则 | 30 | 10 | 22/30 | 11/120 | 3 |
| R1 | plain | y 新规则 | 30 | 10 | 22/30 | 9/120 | 3 |
| R1 | v0 | x 同规则 | 30 | 10 | 23/30 | 9/120 | 3 |
| R1 | v0 | y 新规则 | 30 | 10 | 21/30 | 10/120 | 3 |
| R1 | 培养后 | x 同规则 | 30 | 10 | 26/30 | 4/120 | 3 |
| R1 | 培养后 | y 新规则 | 30 | 10 | 27/30 | 3/120 | 3 |

异常记录单列（未纳入能力表，也未被程序判成规则失败）：

| 版本 | unknown 待核报告 | 派活 error 报告 | 无适用判定报告 |
|---|---|---|---|
| plain | 0 | 0 | 0 |
| v0 | 0 | 0 | 0 |
| 培养后 | 0 | 0 | 0 |

同一报告可能同时含 error 与 unknown；上表不是互斥报告数。原始报告：

- plain：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-plain-1011-200925-f8f329e07a.json)
- plain：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-plain-1011-202036-dca256619d.json)
- plain：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-plain-1011-203617-f6875bff2f.json)
- v0：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-v0-1011-204607-ea213aec97.json)
- v0：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-v0-1011-205848-7602e6ce8b.json)
- v0：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-v0-1011-211012-a7938bb60e.json)
- 培养后：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-42a572b356cd-1011-193059-2e6383eeab.json)
- 培养后：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-42a572b356cd-1011-194024-bcc1869a26.json)
- 培养后：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-42a572b356cd-1011-195438-c893324f03.json)

Studio 原 run.out 的 exam 分母会随评审来源、适用项和 unknown 变化，不能当作固定工作规则指标；以下读取当前 session 的 iteration，按 source 和题组分开。位置是记录中的 JSON 路径，不推断补考或额外轮的含义。
当前 session：`live-20261011162336-b947f2`。

| 记录位置 | 评审 source | 题组 | pass | fail | unknown | not_applicable |
|---|---|---|---|---|---|---|
| [rounds[0]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/taobao-title/runs/live-20261011162336-b947f2/iteration/d56408f0eb5b4c8e98f524f6eb5d0075.json) | rules-judge | x | 38 | 2 | 0 | 0 |
| [rounds[0]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/taobao-title/runs/live-20261011162336-b947f2/iteration/d56408f0eb5b4c8e98f524f6eb5d0075.json) | rules-judge | y | 37 | 3 | 0 | 0 |
| [rounds[1]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/taobao-title/runs/live-20261011162336-b947f2/iteration/d56408f0eb5b4c8e98f524f6eb5d0075.json) | rules-judge | x | 31 | 9 | 0 | 0 |
| [rounds[1]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/taobao-title/runs/live-20261011162336-b947f2/iteration/d56408f0eb5b4c8e98f524f6eb5d0075.json) | rules-judge | y | 37 | 3 | 0 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/taobao-title/runs/live-20261011162336-b947f2/iteration/d56408f0eb5b4c8e98f524f6eb5d0075.json) | rules-judge | x | 35 | 5 | 0 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/taobao-title/runs/live-20261011162336-b947f2/iteration/d56408f0eb5b4c8e98f524f6eb5d0075.json) | rules-judge | y | 37 | 3 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/taobao-title/runs/live-20261011162336-b947f2/iteration/d56408f0eb5b4c8e98f524f6eb5d0075.json) | assessor | x | 0 | 0 | 20 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/taobao-title/runs/live-20261011162336-b947f2/iteration/d56408f0eb5b4c8e98f524f6eb5d0075.json) | assessor | y | 0 | 0 | 20 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/taobao-title/runs/live-20261011162336-b947f2/iteration/d56408f0eb5b4c8e98f524f6eb5d0075.json) | rules-judge | x | 37 | 3 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/taobao-title/runs/live-20261011162336-b947f2/iteration/d56408f0eb5b4c8e98f524f6eb5d0075.json) | rules-judge | y | 36 | 4 | 0 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/taobao-title/runs/live-20261011162336-b947f2/iteration/d56408f0eb5b4c8e98f524f6eb5d0075.json) | assessor | x | 0 | 0 | 20 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/taobao-title/runs/live-20261011162336-b947f2/iteration/d56408f0eb5b4c8e98f524f6eb5d0075.json) | assessor | y | 0 | 0 | 20 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/taobao-title/runs/live-20261011162336-b947f2/iteration/d56408f0eb5b4c8e98f524f6eb5d0075.json) | rules-judge | x | 38 | 2 | 0 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/taobao-title/runs/live-20261011162336-b947f2/iteration/d56408f0eb5b4c8e98f524f6eb5d0075.json) | rules-judge | y | 38 | 2 | 0 | 0 |

导出的策略产物（文件存在不等于已证明学会；效果还需对照v0、plain及通道条件，跨通道结果仅作描述）：

- 策略文件 `listing_capability.py`（2350 字）
- 策略项 `capability.strategy`

例题取各版本第一次完整有效验收；固定 x01，并补题号最先的观察改善/退步例（若有）。这是个例展示，不能替代全表；v0及每份答卷的通道一并列出。通道不同的例题不能归因为训练作用。

### x01 · 固定题 x01

<details><summary>plain · OpenRouter / z-ai/glm-5.3-flash：挂项 0/4</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-plain-1011-200925-f8f329e07a.json)

<pre>## 标题
禾木电炖锅1.5L隔水炖白陶瓷内胆玻璃炖盅3档豆沙粉

## 卖点
1. 1.5L容量，炖汤炖粥分量刚刚好
2. 300W功率，小火慢炖更入味
3. 白陶瓷内胆，细腻易清洗
4. 12小时预约，睡前备好食材早上开吃
5. 玻璃小炖盅3个，一锅多盅全家分食</pre>

</details>
<details><summary>v0 · OpenRouter / z-ai/glm-5.3-flash：挂项 0/4</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-v0-1011-204607-ea213aec97.json)

<pre>## 标题
禾木电炖锅1.5L白陶瓷内胆隔水炖12小时预约3档火力豆沙粉炖盅

## 卖点
1. 容量1.5L，小家庭炖汤炖粥刚刚好
2. 功率300W，小火慢炖省电安心
3. 白陶瓷内胆，炖煮不串味好清洗
4. 隔水炖设计，受热均匀不易糊底
5. 12小时预约，睡前备好早上就能喝</pre>

</details>
<details><summary>培养后 · OpenRouter / z-ai/glm-5.3-flash：挂项 0/4</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-42a572b356cd-1011-193059-2e6383eeab.json)

<pre>## 标题
禾木电炖锅1.5L白陶瓷内胆隔水炖12小时预约300W豆沙粉

## 卖点
1. 容量1.5L，小份炖煮刚刚好
2. 功率300W，文火慢炖入味足
3. 白陶瓷内胆，细腻易洁不串味
4. 隔水炖法，受热均匀不糊底
5. 玻璃小炖盅3个，一锅多盅同炖</pre>

</details>

### x04 · 改善例（按题号第一处）

<details><summary>plain · OpenRouter / z-ai/glm-5.3-flash：挂项 2/4</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-plain-1011-200925-f8f329e07a.json)

<pre>## 商品名称
澄悦声波电动牙刷成人磁吸充电IPX7防水38000次/分钟软毛

## 商品卖点
卖点一：38000次/分钟高频声波振动，清洁更彻底
卖点二：IPX7防水等级，安心水洗好打理
卖点三：30天持久续航，出差旅行无忧</pre>

</details>
<details><summary>v0 · OpenRouter / z-ai/glm-5.3-flash：挂项 2/4</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-v0-1011-204607-ea213aec97.json)

<pre>## 商品名称
澄悦声波电动牙刷成人款 IPX7防水 38000次/分钟振动 30天续航

## 商品卖点
卖点一：振动频率38000次/分钟，深层清洁
卖点二：磁吸充电，30天长续航
卖点三：IPX7防水，全身安心使用</pre>

</details>
<details><summary>培养后 · OpenRouter / z-ai/glm-5.3-flash：挂项 0/4</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-42a572b356cd-1011-193059-2e6383eeab.json)

<pre>## 商品名称
澄悦声波电动牙刷 成人 IPX7防水 38000次/分钟 磁吸充电

## 商品卖点
卖点一：振动频率38000次/分钟
卖点二：续航30天
卖点三：IPX7防水</pre>

</details>

### x10 · 退步例（按题号第一处）

<details><summary>plain · OpenRouter / z-ai/glm-5.3-flash：挂项 0/4</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-plain-1011-200925-f8f329e07a.json)

<pre>## 商品名称
澄悦卷发棒28mm大卷陶瓷懒人卷发器5档210℃30秒速热

## 商品卖点
卖点一：陶瓷釉涂层，顺滑好打理
卖点二：5档温控，随心调节
卖点三：30秒速热，出门前快速卷好</pre>

</details>
<details><summary>v0 · OpenRouter / z-ai/glm-5.3-flash：挂项 1/4</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-v0-1011-204607-ea213aec97.json)

<pre>## 商品名称
卷发棒28mm大卷陶瓷懒人卷发器210℃5档30秒速热360°旋转

## 商品卖点
卖点一：210℃高温，轻松卷出自然大卷
卖点二：5档温度可调，满足不同卷度需求
卖点三：60分钟自动断电，使用安心</pre>

</details>
<details><summary>培养后 · OpenRouter / z-ai/glm-5.3-flash：挂项 1/4</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-42a572b356cd-1011-193059-2e6383eeab.json)

<pre>材料已读齐，规则明确：标题 40–50 字符（汉字 2、空格 0、其余 1），6 个必含词各出现一次，标题数字须来自参数值，禁用词含“最”“专业级”，品牌名单含杜邦/DuPont（涂层参数值需删品牌后使用），功能词仅“自动断电”在参数表中有依据。已按要求核对最终整行长度（50 字符）、必含词、禁词与品牌。

## 商品名称
澄悦卷发棒28mm大卷陶瓷釉懒人卷发器210℃30秒速热360°

## 商品卖点
卖点一：温度210℃
卖点二：温度档位5档
卖点三：60分钟自动断电</pre>

</details>

## 销售通话复盘（call-debrief）

员工通道：**纯旧通道（OpenRouter）**（以当前完整有效报告中的答卷为准）。
本专家未列入这次109题恢复清单，保留既有旧通道验收；没有因事故重跑。

三版本对照：完整；培养后 revision：`483e4e1633b13b448b16ffd2194ec85edc2b9c48e4055326af165cc56a02e078`。
每次重复使用同一组 x/y 各 10 题，合计答卷数不代表独立新题。仅完整、逐项 LLM 评审齐全且无派活/证据错误的报告进入能力表。

| 版本 | 完整有效 / 发现报告 | 全对题 x（合计、每次） | 全对题 y（合计、每次） | 挂项 x（合计、每次） | 挂项 y（合计、每次） |
|---|---|---|---|---|---|
| plain | 3 / 3 | 13/30（每次 5/10, 4/10, 4/10） | 9/30（每次 3/10, 1/10, 5/10） | 21/150（每次 6/50, 9/50, 6/50） | 27/150（每次 11/50, 10/50, 6/50） |
| v0 | 3 / 3 | 17/30（每次 5/10, 5/10, 7/10） | 20/30（每次 8/10, 6/10, 6/10） | 13/150（每次 5/50, 5/50, 3/50） | 14/150（每次 2/50, 5/50, 7/50） |
| 培养后 | 3 / 3 | 20/30（每次 7/10, 7/10, 6/10） | 17/30（每次 5/10, 6/10, 6/10） | 11/150（每次 4/50, 3/50, 4/50） | 14/150（每次 5/50, 4/50, 5/50） |

员工路由分层（与判卷模型无关）：

缺少 transport 字段的旧正常答卷依据实验历史归为 legacy OpenRouter；显式但不完整的元数据归为未记录。不根据当前默认provider反推历史。

- R1：provider=`OpenRouter`；model=`z-ai/glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 180 次（其中 180 次无逐行通道字段，按旧记录归组）。

原完整运行共 9 次，其中 0 次内部混合通道。混合运行仍只计一次完整20题验收；以下是答卷层样本数，覆盖运行数不能跨路由相加成新实验。

| 路由 | 版本 | 题组 | 有效答卷次数 | 不同题号数 | 全对 / 有效答卷 | 失败项 / 适用项 | 覆盖原运行数 |
|---|---|---|---:|---:|---|---|---:|
| R1 | plain | x 同规则 | 30 | 10 | 13/30 | 21/150 | 3 |
| R1 | plain | y 新规则 | 30 | 10 | 9/30 | 27/150 | 3 |
| R1 | v0 | x 同规则 | 30 | 10 | 17/30 | 13/150 | 3 |
| R1 | v0 | y 新规则 | 30 | 10 | 20/30 | 14/150 | 3 |
| R1 | 培养后 | x 同规则 | 30 | 10 | 20/30 | 11/150 | 3 |
| R1 | 培养后 | y 新规则 | 30 | 10 | 17/30 | 14/150 | 3 |

异常记录单列（未纳入能力表，也未被程序判成规则失败）：

| 版本 | unknown 待核报告 | 派活 error 报告 | 无适用判定报告 |
|---|---|---|---|
| plain | 0 | 0 | 0 |
| v0 | 0 | 0 | 0 |
| 培养后 | 0 | 0 | 0 |

同一报告可能同时含 error 与 unknown；上表不是互斥报告数。原始报告：

- plain：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-plain-1011-200027-f8f329e07a.json)
- plain：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-plain-1011-201304-dca256619d.json)
- plain：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-plain-1011-202508-f6875bff2f.json)
- v0：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-v0-1011-204026-ea213aec97.json)
- v0：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-v0-1011-205156-7602e6ce8b.json)
- v0：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-v0-1011-210144-a7938bb60e.json)
- 培养后：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-483e4e1633b1-1011-193059-ce20ddb647.json)
- 培养后：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-483e4e1633b1-1011-194011-1a9190f826.json)
- 培养后：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-483e4e1633b1-1011-195155-72e6b263f0.json)

Studio 原 run.out 的 exam 分母会随评审来源、适用项和 unknown 变化，不能当作固定工作规则指标；以下读取当前 session 的 iteration，按 source 和题组分开。位置是记录中的 JSON 路径，不推断补考或额外轮的含义。
当前 session：`live-20261011160338-48a052`。

| 记录位置 | 评审 source | 题组 | pass | fail | unknown | not_applicable |
|---|---|---|---|---|---|---|
| [rounds[0]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/call-debrief/runs/live-20261011160338-48a052/iteration/ba7f3d558f1c4ec7bc70826a132e2ebb.json) | rules-judge | x | 45 | 5 | 0 | 0 |
| [rounds[0]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/call-debrief/runs/live-20261011160338-48a052/iteration/ba7f3d558f1c4ec7bc70826a132e2ebb.json) | rules-judge | y | 49 | 1 | 0 | 0 |
| [rounds[1]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/call-debrief/runs/live-20261011160338-48a052/iteration/ba7f3d558f1c4ec7bc70826a132e2ebb.json) | assessor | 未定位 | 0 | 0 | 1 | 0 |
| [rounds[1]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/call-debrief/runs/live-20261011160338-48a052/iteration/ba7f3d558f1c4ec7bc70826a132e2ebb.json) | rules-judge | x | 49 | 1 | 0 | 0 |
| [rounds[1]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/call-debrief/runs/live-20261011160338-48a052/iteration/ba7f3d558f1c4ec7bc70826a132e2ebb.json) | rules-judge | y | 47 | 3 | 0 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/call-debrief/runs/live-20261011160338-48a052/iteration/ba7f3d558f1c4ec7bc70826a132e2ebb.json) | assessor | 未定位 | 0 | 0 | 1 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/call-debrief/runs/live-20261011160338-48a052/iteration/ba7f3d558f1c4ec7bc70826a132e2ebb.json) | rules-judge | x | 47 | 3 | 0 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/call-debrief/runs/live-20261011160338-48a052/iteration/ba7f3d558f1c4ec7bc70826a132e2ebb.json) | rules-judge | y | 44 | 6 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/call-debrief/runs/live-20261011160338-48a052/iteration/ba7f3d558f1c4ec7bc70826a132e2ebb.json) | assessor | 未定位 | 1 | 0 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/call-debrief/runs/live-20261011160338-48a052/iteration/ba7f3d558f1c4ec7bc70826a132e2ebb.json) | rules-judge | x | 46 | 4 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/call-debrief/runs/live-20261011160338-48a052/iteration/ba7f3d558f1c4ec7bc70826a132e2ebb.json) | rules-judge | y | 49 | 1 | 0 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/call-debrief/runs/live-20261011160338-48a052/iteration/ba7f3d558f1c4ec7bc70826a132e2ebb.json) | assessor | 未定位 | 0 | 0 | 1 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/call-debrief/runs/live-20261011160338-48a052/iteration/ba7f3d558f1c4ec7bc70826a132e2ebb.json) | rules-judge | x | 47 | 3 | 0 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/call-debrief/runs/live-20261011160338-48a052/iteration/ba7f3d558f1c4ec7bc70826a132e2ebb.json) | rules-judge | y | 48 | 2 | 0 | 0 |

导出的策略产物（文件存在不等于已证明学会；效果还需对照v0、plain及通道条件，跨通道结果仅作描述）：

- 策略文件 `call_debrief_capability.py`（2263 字）
- 策略项 `capability.strategy`

例题取各版本第一次完整有效验收；固定 x01，并补题号最先的观察改善/退步例（若有）。这是个例展示，不能替代全表；v0及每份答卷的通道一并列出。通道不同的例题不能归因为训练作用。

### x01 · 固定题 x01

<details><summary>plain · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-plain-1011-200027-f8f329e07a.json)

<pre>## 改进点
开场第一句“胡总您好，我是智排科技的李然，想跟您聊聊贵司排班的事”只说明了来意，没有同时说明这次通话大概多久。

## 建议话术
“胡总您好，我是智排科技的李然，想跟您聊聊门店排班的事，大概占用您十分钟，您现在方便吗？”

## 给主管的风险
- 答应赠送：客户提出价格异议后，销售承诺“签约的话首年再送您三个月”，赠送需主管审批，销售不能当场答应。

## 跟进邮件
胡总您好，感谢您抽出时间沟通。很高兴您将与财务总监在9月23日（周三）一起听取我们的方案，我会提前准备好材料，届时准时参加。如时间或安排有调整，请随时告诉我。祝生意兴隆！智排科技 李然</pre>

</details>
<details><summary>v0 · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-v0-1011-204026-ea213aec97.json)

<pre>## 改进点
开场第一句“胡总您好，我是智排科技的李然，想跟您聊聊贵司排班的事”只说了来意，没有说明这次通话大概多久。

## 建议话术
“胡总您好，我是智排科技的李然，想跟您聊聊贵司店长排班的事，大概占用您十分钟，方便吗？”

## 给主管的风险
销售未经审批当场答应客户“签约的话首年再送您三个月”（赠送）。

## 跟进邮件
胡总您好，感谢您今天的时间。按约定，9月23日（周三）我会把排班方案准备好，供您和财务总监一起评估。如时间有调整，请您定一个方便的时间，我们随时配合。</pre>

</details>
<details><summary>培养后 · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-483e4e1633b1-1011-193059-ce20ddb647.json)

<pre>## 改进点
销售开场第一句“胡总您好，我是智排科技的李然，想跟您聊聊贵司排班的事”只说明了来意，没有同时说明这次通话大概多久。

## 建议话术
胡总您好，我是智排科技的李然，想和您聊聊贵司门店排班的事。这次通话大概需要十分钟，您现在方便吗？

## 给主管的风险
销售答应客户“签约的话首年再送您三个月”，属于赠送，价目表注明折扣和赠送需销售主管审批，销售不能当场答应。

## 跟进邮件
胡总您好，感谢您今天的时间。您提到店长每周排班耗时且容易出错，我们会在9月23日（周三）准备好方案，与您和财务总监一起沟通。如有其他想了解的内容，欢迎随时联系。智排科技 李然</pre>

</details>

### x02 · 改善例（按题号第一处）

<details><summary>plain · OpenRouter / z-ai/glm-5.3-flash：挂项 2/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-plain-1011-200027-f8f329e07a.json)

<pre>已完成并交付《复盘与跟进邮件.md》。要点：

- **改进点**：开场——第一句只报姓名，没说来意和通话时长（下一步承诺已约定 2026-11-18 听方案，价格异议也按标准动作先问了预算，故按优先级取开场）。
- **需主管确认的承诺**：销售答应“两周上线”，属上线时长类。
- **跟进邮件**：约 70 字，写明 2026-11-18 的下一步，未提价格/竞品，署名“客流通 陈晨”。

【交付文件 复盘与跟进邮件.md】
## 本次最该改的一点
开场第一句&quot;孙总您好，我是客流通的陈晨&quot;只自报了姓名，没有同时说明来意和这次通话大概多久。

## 建议这样说
&quot;孙总您好，我是客流通的陈晨，想跟您聊聊咱们会员复购的提升方案，大概占用您五分钟，方便吗？&quot;

## 需主管确认的承诺
上线时长：答应客户两周上线。

## 跟进邮件
孙总您好，感谢今天的沟通。您约好 2026-11-18 与老板一起听取我们的方案，我会提前准备好，届时为您详细讲解。期待合作。客流通 陈晨</pre>

</details>
<details><summary>v0 · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-v0-1011-204026-ea213aec97.json)

<pre>## 本次最该改的一点

开场第一句“孙总您好，我是客流通的陈晨”只报了身份，没有同时说明来意和这次通话大概多久，不符合开场要求。

## 建议这样说

“孙总您好，我是客流通的陈晨，想跟您聊聊咱们会员复购的提升方案，大概占用您五分钟，方便吗？”

## 需主管确认的承诺

- 上线时长：销售答应客户“两周就能上线”。

## 跟进邮件

孙总您好，感谢您的时间。按约定，我会在2026-11-18准备好方案，供您和老板一起听取。如时间需调整，请您定一个方便的时间。
客流通 陈晨</pre>

</details>
<details><summary>培养后 · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-483e4e1633b1-1011-193059-ce20ddb647.json)

<pre>## 本次最该改的一点

开场第一句“孙总您好，我是客流通的陈晨。”只报了公司和姓名，没有同时说明来意和这次通话大概多久。

## 建议这样说

“孙总您好，我是客流通的陈晨，想和您聊聊怎么提升会员复购，大概占用您五分钟，方便吗？”

## 需主管确认的承诺

销售答应客户“两周就能上线”（上线时长承诺）。

## 跟进邮件

孙总您好：
感谢您今天的时间。按约定，我将于2026-11-18把会员营销方案准备好，供您和老板一起了解，标准版两周即可上线。如有其他需要补充的信息，请随时告知。
客流通 陈晨</pre>

</details>

### x05 · 退步例（按题号第一处）

<details><summary>plain · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-plain-1011-200027-f8f329e07a.json)

<pre>## 改进点
通话结束时客户说“内部再商量商量，回头联系你”，李然只回“好的，等您消息”，没有追问并当场约定具体哪天、做什么的下一步。

## 建议话术
“王总，那咱们别等回头，就定这周五下午，我把两家新店的排班方案带过来给您过一遍，您看行吗？”

## 给主管的风险
- 李然答应客户签约首年赠送三个月（赠送需主管审批，销售不能当场答应）。
- 李然承诺两周即可上线（上线时长承诺）。

## 跟进邮件
王总您好，感谢今天的沟通。您提到店长每周排班耗时且易出错，这正是我们门店排班系统要解决的问题。请您定一个方便的时间，我们再就两家新店的排班安排做一次详细沟通。期待您的回复。

智排科技 李然</pre>

</details>
<details><summary>v0 · OpenRouter / z-ai/glm-5.3-flash：挂项 1/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-v0-1011-204026-ea213aec97.json)

<pre>## 改进点
客户说“内部再商量商量，回头联系你”时，李然只回“好的，等您消息”，没有追问并当场约定具体哪天、做什么的下一步。

## 建议话术
“王总，要不这样，您和内部商量后，这周五前给我个答复？我周四先把一份适合两家新店的方案发您，您带着讨论更省事。”

## 给主管的风险
- 李然答应客户“两周就能上线”（上线时长承诺）。
- 李然答应客户“签约首年再送三个月”（赠送承诺）。

## 跟进邮件
王总您好，感谢今天沟通。您提到店长排班耗时易错，我们的门店排班系统可针对性解决。您方便时定一个时间，我们再确认下一步安排，期待您的回复。</pre>

</details>
<details><summary>培养后 · OpenRouter / z-ai/glm-5.3-flash：挂项 1/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-483e4e1633b1-1011-193059-ce20ddb647.json)

<pre>已完成并交付《复盘与跟进邮件.md》。要点：价格异议环节处理正确（按标准动作询问了对比对象和报价内容），改进点为通话结束未约定具体下一步；风险两项——承诺上线两周、承诺首年赠送三个月（均需主管审批）；跟进邮件因客户未答应具体日期，按要求写“请您定一个方便的时间”。

【交付文件 复盘与跟进邮件.md】
## 改进点

通话结束时客户说&quot;我们内部再商量商量，回头联系你&quot;，李然没有追问并约定具体哪天、做什么的下一步，只回复&quot;好的，等您消息&quot;。

## 建议话术

王总，您内部商量后，我们约在本周五下午三点电话沟通，确定是否推进，可以吗？如果这个时间不方便，请您定一个本周内方便的时间，我随时配合。

## 给主管的风险

- 李然向客户承诺上线时长为两周（&quot;两周就能上线，没问题&quot;），上线时长承诺未经主管审批确认。
- 李然向客户承诺签约首年赠送三个月（&quot;签约的话首年我再送您三个月&quot;），赠送需销售主管审批，销售不能当场答应。

## 跟进邮件

王总您好，感谢今天的沟通。您提到将内部商量排班系统事宜，方便时请您定一个方便的时间，我们再电话确认下一步安排。期待您的回复。

智排科技 李然
</pre>

</details>

## 竞品对比表（compete-table）

员工通道：**纯旧通道（OpenRouter）**（以当前完整有效报告中的答卷为准）。
本专家未列入这次109题恢复清单，保留既有旧通道验收；没有因事故重跑。

三版本对照：完整；培养后 revision：`0150fa86cde9f76b036450fa70805618763e99bd4c3b4240f5b540542b282b5d`。
每次重复使用同一组 x/y 各 10 题，合计答卷数不代表独立新题。仅完整、逐项 LLM 评审齐全且无派活/证据错误的报告进入能力表。

| 版本 | 完整有效 / 发现报告 | 全对题 x（合计、每次） | 全对题 y（合计、每次） | 挂项 x（合计、每次） | 挂项 y（合计、每次） |
|---|---|---|---|---|---|
| plain | 3 / 3 | 4/30（每次 2/10, 1/10, 1/10） | 2/30（每次 0/10, 2/10, 0/10） | 28/150（每次 8/50, 10/50, 10/50） | 39/150（每次 17/50, 9/50, 13/50） |
| v0 | 3 / 3 | 28/30（每次 10/10, 9/10, 9/10） | 16/30（每次 6/10, 7/10, 3/10） | 2/150（每次 0/50, 1/50, 1/50） | 15/150（每次 4/50, 4/50, 7/50） |
| 培养后 | 3 / 3 | 25/30（每次 8/10, 8/10, 9/10） | 21/30（每次 8/10, 7/10, 6/10） | 5/150（每次 2/50, 2/50, 1/50） | 14/150（每次 2/50, 5/50, 7/50） |

员工路由分层（与判卷模型无关）：

缺少 transport 字段的旧正常答卷依据实验历史归为 legacy OpenRouter；显式但不完整的元数据归为未记录。不根据当前默认provider反推历史。

- R1：provider=`OpenRouter`；model=`z-ai/glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 180 次（其中 180 次无逐行通道字段，按旧记录归组）。

原完整运行共 9 次，其中 0 次内部混合通道。混合运行仍只计一次完整20题验收；以下是答卷层样本数，覆盖运行数不能跨路由相加成新实验。

| 路由 | 版本 | 题组 | 有效答卷次数 | 不同题号数 | 全对 / 有效答卷 | 失败项 / 适用项 | 覆盖原运行数 |
|---|---|---|---:|---:|---|---|---:|
| R1 | plain | x 同规则 | 30 | 10 | 4/30 | 28/150 | 3 |
| R1 | plain | y 新规则 | 30 | 10 | 2/30 | 39/150 | 3 |
| R1 | v0 | x 同规则 | 30 | 10 | 28/30 | 2/150 | 3 |
| R1 | v0 | y 新规则 | 30 | 10 | 16/30 | 15/150 | 3 |
| R1 | 培养后 | x 同规则 | 30 | 10 | 25/30 | 5/150 | 3 |
| R1 | 培养后 | y 新规则 | 30 | 10 | 21/30 | 14/150 | 3 |

异常记录单列（未纳入能力表，也未被程序判成规则失败）：

| 版本 | unknown 待核报告 | 派活 error 报告 | 无适用判定报告 |
|---|---|---|---|
| plain | 0 | 0 | 0 |
| v0 | 0 | 0 | 0 |
| 培养后 | 0 | 0 | 0 |

同一报告可能同时含 error 与 unknown；上表不是互斥报告数。原始报告：

- plain：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-plain-1011-154248.json)
- plain：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-plain-1011-160901.json)
- plain：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-plain-1011-163249.json)
- v0：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-v0-1011-155054.json)
- v0：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-v0-1011-162418.json)
- v0：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-v0-1011-164759.json)
- 培养后：[第 1 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-0150fa86cde9-1011-152100.json)
- 培养后：[第 2 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-0150fa86cde9-1011-161604.json)
- 培养后：[第 3 次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-0150fa86cde9-1011-163919.json)

Studio 原 run.out 的 exam 分母会随评审来源、适用项和 unknown 变化，不能当作固定工作规则指标；以下读取当前 session 的 iteration，按 source 和题组分开。位置是记录中的 JSON 路径，不推断补考或额外轮的含义。
当前 session：`live-20261011132451-42b3d5`。

| 记录位置 | 评审 source | 题组 | pass | fail | unknown | not_applicable |
|---|---|---|---|---|---|---|
| [rounds[0]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/compete-table/runs/live-20261011132451-42b3d5/iteration/0ff79422ce734041a6994448605bb155.json) | rules-judge | x | 50 | 0 | 0 | 0 |
| [rounds[0]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/compete-table/runs/live-20261011132451-42b3d5/iteration/0ff79422ce734041a6994448605bb155.json) | rules-judge | y | 46 | 4 | 0 | 0 |
| [rounds[1]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/compete-table/runs/live-20261011132451-42b3d5/iteration/0ff79422ce734041a6994448605bb155.json) | rules-judge | x | 48 | 2 | 0 | 0 |
| [rounds[1]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/compete-table/runs/live-20261011132451-42b3d5/iteration/0ff79422ce734041a6994448605bb155.json) | rules-judge | y | 45 | 5 | 0 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/compete-table/runs/live-20261011132451-42b3d5/iteration/0ff79422ce734041a6994448605bb155.json) | rules-judge | x | 47 | 3 | 0 | 0 |
| [rounds[2]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/compete-table/runs/live-20261011132451-42b3d5/iteration/0ff79422ce734041a6994448605bb155.json) | rules-judge | y | 45 | 5 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/compete-table/runs/live-20261011132451-42b3d5/iteration/0ff79422ce734041a6994448605bb155.json) | rules-judge | x | 49 | 1 | 0 | 0 |
| [rounds[3]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/compete-table/runs/live-20261011132451-42b3d5/iteration/0ff79422ce734041a6994448605bb155.json) | rules-judge | y | 46 | 4 | 0 | 0 |
| [rounds[4]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/compete-table/runs/live-20261011132451-42b3d5/iteration/0ff79422ce734041a6994448605bb155.json) | rules-judge | x | 48 | 2 | 0 | 0 |
| [rounds[4]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/compete-table/runs/live-20261011132451-42b3d5/iteration/0ff79422ce734041a6994448605bb155.json) | rules-judge | y | 48 | 2 | 0 | 0 |
| [rounds[5]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/compete-table/runs/live-20261011132451-42b3d5/iteration/0ff79422ce734041a6994448605bb155.json) | assessor | y | 0 | 1 | 0 | 0 |
| [rounds[5]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/compete-table/runs/live-20261011132451-42b3d5/iteration/0ff79422ce734041a6994448605bb155.json) | assessor | 未定位 | 0 | 0 | 1 | 0 |
| [rounds[5]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/compete-table/runs/live-20261011132451-42b3d5/iteration/0ff79422ce734041a6994448605bb155.json) | rules-judge | x | 49 | 1 | 0 | 0 |
| [rounds[5]](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/compete-table/runs/live-20261011132451-42b3d5/iteration/0ff79422ce734041a6994448605bb155.json) | rules-judge | y | 45 | 5 | 0 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/compete-table/runs/live-20261011132451-42b3d5/iteration/0ff79422ce734041a6994448605bb155.json) | assessor | 未定位 | 0 | 0 | 2 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/compete-table/runs/live-20261011132451-42b3d5/iteration/0ff79422ce734041a6994448605bb155.json) | rules-judge | x | 50 | 0 | 0 | 0 |
| [pending](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/compete-table/runs/live-20261011132451-42b3d5/iteration/0ff79422ce734041a6994448605bb155.json) | rules-judge | y | 41 | 9 | 0 | 0 |

导出的策略产物（文件存在不等于已证明学会；效果还需对照v0、plain及通道条件，跨通道结果仅作描述）：

- 策略文件 `capability_impl.py`（3316 字）
- 技能 `comparison-state-fidelity`：依据当次竞品功能资料保真填表，并按当次定义选择与表格一致的定位项。（1079 字）
- 策略项 `capability.strategy`

例题取各版本第一次完整有效验收；固定 x01，并补题号最先的观察改善/退步例（若有）。这是个例展示，不能替代全表；v0及每份答卷的通道一并列出。通道不同的例题不能归因为训练作用。

### x01 · 固定题 x01；改善例（按题号第一处）

<details><summary>plain · OpenRouter / z-ai/glm-5.3-flash：挂项 1/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-plain-1011-154248.json)

<pre>定位语：云笺是唯一支持开放 API 的产品。

| 功能 | 云笺 | 砚池 | 编鹿 | 落笔 | 简页 |
|---|---|---|---|---|---|
| 实时协作 | 有 | 有 | 有 | 有 | 有 |
| 离线编辑 | 有 | 有 | 无 | 部分 | 无 |
| 版本历史 | 有 | 有 | 有 | 未知 | 有 |
| 表格公式 | 部分 | 有 | 部分 | 有 | 有 |
| 审批流 | 有 | 部分 | 有 | 无 | 有 |
| 开放 API | 有 | 无 | 部分 | 无 | 部分 |
| 权限与审计 | 有 | 有 | 未知 | 部分 | 有 |
| 年付价（元/人/月） | 24.0 | 24.8 | 27.0 | 27.0 | 29.4 |

说明（供你核对，不进投标文件）：14 人团队不影响计价（各家均按人计费、无团队档位）；折算口径为云笺 30×0.8=24.0，砚池 31×0.8=24.8，编鹿 27.0（不打折），落笔 36×0.75=27.0，简页 42×0.7=29.4；本表未涉及外币，汇率表未用到。</pre>

</details>
<details><summary>v0 · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-v0-1011-155054.json)

<pre>定位语：在开放 API 方面，云笺支持开放 API，其余对比产品均不支持或仅部分支持。

| 功能 | 云笺 | 砚池 | 编鹿 | 落笔 | 简页 |
|---|---|---|---|---|---|
| 实时协作 | 有 | 有 | 有 | 有 | 有 |
| 离线编辑 | 有 | 有 | 无 | 部分 | 无 |
| 版本历史 | 有 | 有 | 有 | 未知 | 有 |
| 表格公式 | 部分 | 有 | 部分 | 有 | 有 |
| 审批流 | 有 | 部分 | 有 | 无 | 有 |
| 开放 API | 有 | 无 | 部分 | 无 | 部分 |
| 权限与审计 | 有 | 有 | 未知 | 部分 | 有 |
| 年付价（元/人/月） | 24.0 | 24.8 | 27.0 | 27.0 | 29.4 |</pre>

</details>
<details><summary>培养后 · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-0150fa86cde9-1011-152100.json)

<pre>定位语：云笺支持开放 API，各竞品仅部分支持或未提供。

| 功能 | 云笺 | 砚池 | 编鹿 | 落笔 | 简页 |
|---|---|---|---|---|---|
| 实时协作 | 有 | 有 | 有 | 有 | 有 |
| 离线编辑 | 有 | 有 | 无 | 部分 | 无 |
| 版本历史 | 有 | 有 | 有 | 未知 | 有 |
| 表格公式 | 部分 | 有 | 部分 | 有 | 有 |
| 审批流 | 有 | 部分 | 有 | 无 | 有 |
| 开放 API | 有 | 无 | 部分 | 无 | 部分 |
| 权限与审计 | 有 | 有 | 未知 | 部分 | 有 |
| 年付价（元/人/月） | 24.0 | 24.8 | 27.0 | 27.0 | 29.4 |</pre>

</details>

### x10 · 退步例（按题号第一处）

<details><summary>plain · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-plain-1011-154248.json)

<pre>| 产品 | 看板 | 甘特图 | 工时统计 | 自动化规则 | 开放 API | 私有部署 | 权限与审计 | 价格（元/人/月） |
|---|---|---|---|---|---|---|---|---|
| 简舟 | 支持 | 支持 | 支持 | 部分支持 | 支持 | 支持 | 支持 | 26 |
| Milepost | 支持 | 支持 | 支持 | 支持 | 支持 | 不支持 | 支持 | 23 |
| Ganttery | 支持 | 部分支持 | 支持 | 未公开 | 支持 | 不支持 | 部分支持 | 28 |
| 石阶 | 支持 | 不支持 | 未公开 | 部分支持 | 部分支持 | 部分支持 | 支持 | 28 |
| 天梯 | 支持 | 不支持 | 支持 | 支持 | 不支持 | 不支持 | 未公开 | 36 |

一句话卖点：简舟支持私有部署。</pre>

</details>
<details><summary>v0 · OpenRouter / z-ai/glm-5.3-flash：挂项 0/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-v0-1011-155054.json)

<pre>| 产品 | 看板 | 甘特图 | 工时统计 | 自动化规则 | 开放 API | 私有部署 | 权限与审计 | 折算价（元/人/月） |
|---|---|---|---|---|---|---|---|---|
| 简舟 | 支持 | 支持 | 支持 | 部分支持 | 支持 | 支持 | 支持 | 26 |
| Milepost | 支持 | 支持 | 支持 | 支持 | 支持 | 不支持 | 支持 | 23 |
| Ganttery | 支持 | 部分支持 | 支持 | 未公开 | 支持 | 不支持 | 部分支持 | 28 |
| 石阶 | 支持 | 不支持 | 未公开 | 部分支持 | 部分支持 | 部分支持 | 支持 | 28 |
| 天梯 | 支持 | 不支持 | 支持 | 支持 | 不支持 | 不支持 | 未公开 | 36 |

一句话卖点：简舟支持私有部署。</pre>

</details>
<details><summary>培养后 · OpenRouter / z-ai/glm-5.3-flash：挂项 1/5</summary>

[完整答卷和逐项模型判定](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-0150fa86cde9-1011-152100.json)

<pre>表格与折算价已按 10 人团队核对完毕。

| 产品 | 看板 | 甘特图 | 工时统计 | 自动化规则 | 开放 API | 私有部署 | 权限与审计 | 价格（元/人/月） |
|---|---|---|---|---|---|---|---|---|
| 简舟 | 支持 | 支持 | 支持 | 部分支持 | 支持 | 支持 | 支持 | 26 |
| Milepost | 支持 | 支持 | 支持 | 支持 | 支持 | 不支持 | 支持 | 23 |
| Ganttery | 支持 | 部分支持 | 支持 | 未公开 | 支持 | 不支持 | 部分支持 | 28 |
| 石阶 | 支持 | 不支持 | 未公开 | 部分支持 | 部分支持 | 部分支持 | 支持 | 28 |
| 天梯 | 支持 | 不支持 | 支持 | 支持 | 不支持 | 不支持 | 未公开 | 36 |

一句话卖点：简舟支持私有部署，其他产品不支持或仅部分支持。</pre>

</details>

