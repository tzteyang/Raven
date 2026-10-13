# Raven 专家：验收收尾与实测记录

生成时间：2026-10-12T03:04:26.366581+00:00。
共 22 个专家；用户确认验收 22 个，训练证据完整 22 个，导出核对通过 22 个，收尾完成 22 个。
已保存有效完整实测报告 166 份；具备原计划三版本实测报告的专家 14 个。

用户确认以各专家的 acceptance_source=user、确认原文和当前导出revision绑定记录为依据。该确认不代表所有模型评审项通过；历史复测计划已结束，未满足原计划次数的部分不再执行。

实测只计 reports_of 严格核验后的完整20题和逐项LLM判定，用户确认及 control.complete 不增加实测报告或更改分数。训练状态依据当前日志末次完成标记与deployment revision；导出再核对payload、来源会话和ACP入口。

每个结果格按“同规则x / 新规则y”排列：全对=整题全对/有效答卷，挂项=失败criterion/适用criterion。同一组x/y各10题被重复使用，30份答卷不是30道新题。混合run仍只算一次完整验收，路由分层见各专家证据。

额度事故使13个专家进入109题恢复，后续派活改用新通道；相同宣称模型名不证明provider等价。下表及分组统计都是描述性观察，特别是混合路由不能解释为纯训练因果增益；9个原已完成专家保留旧通道结果。

| 领域 | 专家 | 训练 | 导出 | 用户确认验收 | 已保存实测 P/V/T报告数 | plain：全对/挂项 x / y | v0：全对/挂项 x / y | trained：全对/挂项 x / y | 路由 | 证据 |
|---|---|---|---|---|---|---|---|---|---|---|
| 客服与投诉 | 1.1 网课退款客服 | 完整 | 完整 | 已确认 | 3/3/3 | 全对 0/30 / 4/30<br>挂项 40/138 / 38/138 | 全对 15/30 / 18/30<br>挂项 18/138 / 14/138 | 全对 30/30 / 27/30<br>挂项 0/138 / 3/138 | 纯旧通道（OpenRouter） | [记录](#evidence-refund-desk) |
| 客服与投诉 | 1.2 电商售后投诉处理 | 完整 | 完整 | 已确认 | 3/3/3 | 全对 10/30 / 22/30<br>挂项 23/120 / 9/120 | 全对 9/30 / 18/30<br>挂项 32/120 / 12/120 | 全对 27/30 / 22/30<br>挂项 3/120 / 9/120 | 纯旧通道（OpenRouter） | [记录](#evidence-complaint-desk) |
| 营销文案合规 | 2.1 营销海报审查 | 完整 | 完整 | 已确认 | 3/3/3 | 全对 21/30 / 16/30<br>挂项 10/150 / 16/150 | 全对 19/30 / 5/30<br>挂项 11/150 / 32/150 | 全对 27/30 / 22/30<br>挂项 3/150 / 8/150 | 纯旧通道（OpenRouter） | [记录](#evidence-poster-review) |
| 营销文案合规 | 2.2 医疗推文合规审查 | 完整 | 完整 | 已确认 | 3/3/3 | 全对 4/30 / 5/30<br>挂项 35/150 / 34/150 | 全对 3/30 / 4/30<br>挂项 39/150 / 37/150 | 全对 29/30 / 24/30<br>挂项 1/150 / 6/150 | 纯旧通道（OpenRouter） | [记录](#evidence-dental-post) |
| 数据问答 | 3.1 门店客单价分析 | 完整 | 完整 | 已确认 | 1/1/1 | 全对 4/10 / 4/10<br>挂项 12/32 / 8/33 | 全对 2/10 / 4/10<br>挂项 14/32 / 10/33 | 全对 8/10 / 5/10<br>挂项 2/32 / 6/33 | 纯旧通道（OpenRouter） | [记录](#evidence-store-ticket) |
| 数据问答 | 3.2 SaaS 指标取数 | 完整 | 完整 | 已确认 | 3/3/3 | 全对 21/30 / 24/30<br>挂项 15/120 / 8/120 | 全对 9/30 / 5/30<br>挂项 30/120 / 34/120 | 全对 26/30 / 23/30<br>挂项 4/120 / 7/120 | 混合通道 | [记录](#evidence-saas-metric) |
| 办公汇报 | 4.1 会议待办整理 | 完整 | 完整 | 已确认 | 3/3/3 | 全对 28/30 / 26/30<br>挂项 2/150 / 6/150 | 全对 27/30 / 23/30<br>挂项 3/150 / 9/150 | 全对 29/30 / 26/30<br>挂项 1/150 / 4/150 | 纯旧通道（OpenRouter） | [记录](#evidence-meeting-actions) |
| 办公汇报 | 4.2 运营周报 | 完整 | 完整 | 已确认 | 3/3/3 | 全对 0/30 / 0/30<br>挂项 39/120 / 32/120 | 全对 0/30 / 3/30<br>挂项 36/120 / 28/120 | 全对 25/30 / 13/30<br>挂项 5/120 / 17/120 | 混合通道 | [记录](#evidence-weekly-report) |
| 品牌内容 | 5.1 咖啡新品文案 | 完整 | 完整 | 已确认 | 3/1/3 | 全对 3/30 / 1/30<br>挂项 27/150 / 30/150 | 全对 6/10 / 7/10<br>挂项 6/50 / 3/50 | 全对 30/30 / 27/30<br>挂项 0/150 / 3/150 | 混合通道 | [记录](#evidence-cafe-copy) |
| 品牌内容 | 5.2 小红书种草笔记 | 完整 | 完整 | 已确认 | 3/3/2 | 全对 29/30 / 21/30<br>挂项 1/150 / 9/150 | 全对 20/30 / 20/30<br>挂项 13/150 / 25/150 | 全对 11/20 / 7/20<br>挂项 12/100 / 34/100 | 混合通道 | [记录](#evidence-xhs-note) |
| 电商文案 | 6.1 电商标题和卖点 | 完整 | 完整 | 已确认 | 3/3/3 | 全对 22/30 / 22/30<br>挂项 11/120 / 9/120 | 全对 23/30 / 21/30<br>挂项 9/120 / 10/120 | 全对 26/30 / 27/30<br>挂项 4/120 / 3/120 | 纯旧通道（OpenRouter） | [记录](#evidence-taobao-title) |
| 电商文案 | 6.2 亚马逊英文 Listing | 完整 | 完整 | 已确认 | 2/2/2 | 全对 10/20 / 11/20<br>挂项 14/100 / 10/100 | 全对 10/20 / 10/20<br>挂项 13/100 / 12/100 | 全对 11/20 / 16/20<br>挂项 9/100 / 5/100 | 混合通道 | [记录](#evidence-amazon-listing) |
| 招聘求职 | 7.1 简历初筛 | 完整 | 完整 | 已确认 | 3/3/3 | 全对 4/30 / 13/30<br>挂项 45/150 / 27/150 | 全对 5/30 / 4/30<br>挂项 42/150 / 35/150 | 全对 16/30 / 12/30<br>挂项 20/150 / 32/150 | 混合通道 | [记录](#evidence-resume-screen) |
| 招聘求职 | 7.2 简历优化 | 完整 | 完整 | 已确认 | 3/1/3 | 全对 13/30 / 20/30<br>挂项 21/150 / 13/150 | 全对 9/10 / 8/10<br>挂项 3/50 / 6/50 | 全对 29/30 / 27/30<br>挂项 1/150 / 3/150 | 混合通道 | [记录](#evidence-resume-rewrite) |
| 合同审阅 | 8.1 合同留痕审稿 | 完整 | 完整 | 已确认 | 2/1/3 | 全对 12/20 / 14/20<br>挂项 12/80 / 17/80 | 全对 7/10 / 6/10<br>挂项 4/40 / 7/40 | 全对 18/30 / 20/30<br>挂项 30/120 / 24/120 | 混合通道 | [记录](#evidence-contract-review) |
| 合同审阅 | 8.2 采购合同风险清单 | 完整 | 完整 | 已确认 | 2/2/2 | 全对 12/20 / 12/20<br>挂项 9/100 / 9/100 | 全对 15/20 / 8/20<br>挂项 5/100 / 15/99 | 全对 14/20 / 9/20<br>挂项 8/100 / 12/100 | 混合通道 | [记录](#evidence-contract-sheet) |
| 网页与小工具 | 9.1 品牌落地页 | 完整 | 完整 | 已确认 | 2/1/2 | 全对 5/20 / 3/20<br>挂项 16/96 / 22/88 | 全对 1/10 / 2/10<br>挂项 11/50 / 13/50 | 全对 11/20 / 18/20<br>挂项 11/100 / 3/100 | 混合通道 | [记录](#evidence-landing-page) |
| 网页与小工具 | 9.2 预约交互页面 | 完整 | 完整 | 已确认 | 1/0/0 | 全对 9/10 / 4/10<br>挂项 1/50 / 6/46 | 无有效完整报告 | 无有效完整报告 | 混合通道 | [记录](#evidence-booking-page) |
| 销售话术 | 10.1 销售通话复盘 | 完整 | 完整 | 已确认 | 3/3/3 | 全对 13/30 / 9/30<br>挂项 21/150 / 27/150 | 全对 17/30 / 20/30<br>挂项 13/150 / 14/150 | 全对 20/30 / 17/30<br>挂项 11/150 / 14/150 | 纯旧通道（OpenRouter） | [记录](#evidence-call-debrief) |
| 销售话术 | 10.2 需求追问清单 | 完整 | 完整 | 已确认 | 3/3/3 | 全对 15/30 / 13/30<br>挂项 17/150 / 22/150 | 全对 22/30 / 12/30<br>挂项 12/150 / 23/150 | 全对 27/30 / 20/30<br>挂项 3/150 / 15/150 | 混合通道 | [记录](#evidence-discovery-coach) |
| 产品市场 | 11.1 竞品对比表 | 完整 | 完整 | 已确认 | 3/3/3 | 全对 4/30 / 2/30<br>挂项 28/150 / 39/150 | 全对 28/30 / 16/30<br>挂项 2/150 / 15/150 | 全对 25/30 / 21/30<br>挂项 5/150 / 14/150 | 纯旧通道（OpenRouter） | [记录](#evidence-compete-table) |
| 产品市场 | 11.2 评价周报 | 完整 | 完整 | 已确认 | 3/3/3 | 全对 0/30 / 0/30<br>挂项 48/120 / 58/120 | 全对 5/30 / 5/30<br>挂项 35/120 / 57/120 | 全对 20/30 / 16/30<br>挂项 10/120 / 19/120 | 混合通道 | [记录](#evidence-review-digest) |

## 描述性变化：统计对象是专家

按整题全对率（不是挂项数）分改善/持平/退步；使用精确分数比较。每一阶段只纳入两端版本满足历史实测条件、且训练/导出已核实的专家。历史条件为门店客单价每版本1份有效完整报告、其余每版本3份；这只是保留原统计口径，用户确认不作为实测证据。联合组汇总该专家x+y的20题，不把专家变成题目计数；x、y、联合三行不能相加。各阶段按实际参与版本的通道构成继续分层。

| 阶段 | 题组 | 通道层 | 本层专家数 | 改善 | 持平 | 退步 | 本阶段未纳入专家数 |
|---|---|---|---:|---:|---:|---:|---:|
| plain→v0 | x 同规则 | 纯旧通道（OpenRouter） | 9 | 4 | 0 | 5 | 7 |
| plain→v0 | x 同规则 | 混合通道 | 6 | 3 | 1 | 2 | 7 |
| plain→v0 | y 新规则 | 纯旧通道（OpenRouter） | 9 | 3 | 1 | 5 | 7 |
| plain→v0 | y 新规则 | 混合通道 | 6 | 2 | 0 | 4 | 7 |
| plain→v0 | x+y 联合 | 纯旧通道（OpenRouter） | 9 | 3 | 1 | 5 | 7 |
| plain→v0 | x+y 联合 | 混合通道 | 6 | 3 | 0 | 3 | 7 |
| v0→trained | x 同规则 | 纯旧通道（OpenRouter） | 9 | 8 | 0 | 1 | 8 |
| v0→trained | x 同规则 | 混合通道 | 5 | 5 | 0 | 0 | 8 |
| v0→trained | y 新规则 | 纯旧通道（OpenRouter） | 9 | 8 | 0 | 1 | 8 |
| v0→trained | y 新规则 | 混合通道 | 5 | 5 | 0 | 0 | 8 |
| v0→trained | x+y 联合 | 纯旧通道（OpenRouter） | 9 | 8 | 1 | 0 | 8 |
| v0→trained | x+y 联合 | 混合通道 | 5 | 5 | 0 | 0 | 8 |

同一阶段未纳入数在通道层之间重复展示，不跨行累加；仅说明实测证据范围，不产生后续任务。分组名单：

- plain→v0 · 联合 · 纯旧通道（OpenRouter）：改善：[网课退款客服](#evidence-refund-desk)、[销售通话复盘](#evidence-call-debrief)、[竞品对比表](#evidence-compete-table)；持平：[电商标题和卖点](#evidence-taobao-title)；退步：[电商售后投诉处理](#evidence-complaint-desk)、[营销海报审查](#evidence-poster-review)、[医疗推文合规审查](#evidence-dental-post)、[门店客单价分析](#evidence-store-ticket)、[会议待办整理](#evidence-meeting-actions)。
- plain→v0 · 联合 · 混合通道：改善：[运营周报](#evidence-weekly-report)、[需求追问清单](#evidence-discovery-coach)、[评价周报](#evidence-review-digest)；持平：无；退步：[SaaS 指标取数](#evidence-saas-metric)、[小红书种草笔记](#evidence-xhs-note)、[简历初筛](#evidence-resume-screen)。
- v0→trained · 联合 · 纯旧通道（OpenRouter）：改善：[网课退款客服](#evidence-refund-desk)、[电商售后投诉处理](#evidence-complaint-desk)、[营销海报审查](#evidence-poster-review)、[医疗推文合规审查](#evidence-dental-post)、[门店客单价分析](#evidence-store-ticket)、[会议待办整理](#evidence-meeting-actions)、[电商标题和卖点](#evidence-taobao-title)、[竞品对比表](#evidence-compete-table)；持平：[销售通话复盘](#evidence-call-debrief)；退步：无。
- v0→trained · 联合 · 混合通道：改善：[SaaS 指标取数](#evidence-saas-metric)、[运营周报](#evidence-weekly-report)、[简历初筛](#evidence-resume-screen)、[需求追问清单](#evidence-discovery-coach)、[评价周报](#evidence-review-digest)；持平：无；退步：无。

## 逐专家证据与排除明细

原始报告链接保留答卷、逐项LLM判定和transport元数据；不合格报告列出具体原因，不静默丢弃。本总表不读数百MB的完整Studio迭代轨迹；逐轮source/unknown轨迹仍可用 scorecard.py 单专家输出。

<a id="evidence-refund-desk"></a>
### 1.1 网课退款客服

训练：当前日志以训练完成结束，末次考试revision与当前deployment一致；[run.out](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/refund-desk/run.out)。
导出：导出payload与当前deployment一致，ACP入口已启用；[harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-refund-desk/harness.json)；[deployment](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/refund-desk/runs/live-20261011132451-74e09a/deployment.json)。
完整revision：`098fe127cd2d9198bbc758b8c153fd22c4c4d47ca9d6045df08fedf37678f6d8`。
用户确认验收：现在就当做全都通过验收了；时间 2026-10-12T03:02:03.061562+00:00；[确认记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/control/refund-desk.json)。
[v0与训练后策略正文对照](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/learned-artifacts-20261011.md#refund-desk)。
员工通道：**纯旧通道（OpenRouter）**（以当前完整有效报告中的答卷为准）。
本专家未列入这次109题恢复清单，保留既有旧通道验收；没有因事故重跑。

- 原版：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-plain-1011-154351.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/refund-desk/accept-plain-1011-154351.json)
  - [有效 2 · accept-plain-1011-160905.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/refund-desk/accept-plain-1011-160905.json)
  - [有效 3 · accept-plain-1011-163427.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/refund-desk/accept-plain-1011-163427.json)
- 初始配置：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-v0-1011-155007.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/refund-desk/accept-v0-1011-155007.json)
  - [有效 2 · accept-v0-1011-162441.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/refund-desk/accept-v0-1011-162441.json)
  - [有效 3 · accept-v0-1011-164709.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/refund-desk/accept-v0-1011-164709.json)
- 训练后：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-098fe127cd2d-1011-151939.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/refund-desk/accept-098fe127cd2d-1011-151939.json)
  - [有效 2 · accept-098fe127cd2d-1011-161650.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/refund-desk/accept-098fe127cd2d-1011-161650.json)
  - [有效 3 · accept-098fe127cd2d-1011-164059.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/refund-desk/accept-098fe127cd2d-1011-164059.json)

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
| R1 | trained | x 同规则 | 30 | 10 | 30/30 | 0/138 | 3 |
| R1 | trained | y 新规则 | 30 | 10 | 27/30 | 3/138 | 3 |

<a id="evidence-complaint-desk"></a>
### 1.2 电商售后投诉处理

训练：当前日志以训练完成结束，末次考试revision与当前deployment一致；[run.out](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/run.out)。
导出：导出payload与当前deployment一致，ACP入口已启用；[harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-complaint-desk/harness.json)；[deployment](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/complaint-desk/runs/live-20261011135058-153aad/deployment.json)。
完整revision：`50bd665135f23049740c765559fe6493b827456fc2a8e5ecd51cb2f1b4bb962c`。
用户确认验收：现在就当做全都通过验收了；时间 2026-10-12T03:02:03.061562+00:00；[确认记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/control/complaint-desk.json)。
[v0与训练后策略正文对照](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/learned-artifacts-20261011.md#complaint-desk)。
员工通道：**纯旧通道（OpenRouter）**（以当前完整有效报告中的答卷为准）。
本专家未列入这次109题恢复清单，保留既有旧通道验收；没有因事故重跑。

- 原版：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-plain-1011-154440.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-plain-1011-154440.json)
  - [有效 2 · accept-plain-1011-161252.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-plain-1011-161252.json)
  - [有效 3 · accept-plain-1011-164758.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-plain-1011-164758.json)
- 初始配置：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-v0-1011-155546.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-v0-1011-155546.json)
  - [有效 2 · accept-v0-1011-163527.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-v0-1011-163527.json)
  - [有效 3 · accept-v0-1011-171130.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-v0-1011-171130.json)
- 训练后：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-50bd665135f2-1011-152216.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-50bd665135f2-1011-152216.json)
  - [有效 2 · accept-50bd665135f2-1011-162319.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-50bd665135f2-1011-162319.json)
  - [有效 3 · accept-50bd665135f2-1011-165744.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/complaint-desk/accept-50bd665135f2-1011-165744.json)

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
| R1 | trained | x 同规则 | 30 | 10 | 27/30 | 3/120 | 3 |
| R1 | trained | y 新规则 | 30 | 10 | 22/30 | 9/120 | 3 |

<a id="evidence-poster-review"></a>
### 2.1 营销海报审查

训练：当前日志以训练完成结束，末次考试revision与当前deployment一致；[run.out](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/run.out)。
导出：导出payload与当前deployment一致，ACP入口已启用；[harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-poster-review/harness.json)；[deployment](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/poster-review/runs/live-20261011135907-d09c71/deployment.json)。
完整revision：`8ab6e08e3fe15439c773463f111f4d2dc99a54fa605ebd55abb9a5aa4f9e5b9c`。
用户确认验收：现在就当做全都通过验收了；时间 2026-10-12T03:02:03.061562+00:00；[确认记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/control/poster-review.json)。
[v0与训练后策略正文对照](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/learned-artifacts-20261011.md#poster-review)。
员工通道：**纯旧通道（OpenRouter）**（以当前完整有效报告中的答卷为准）。
本专家未列入这次109题恢复清单，保留既有旧通道验收；没有因事故重跑。

- 原版：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-plain-1011-154727.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-plain-1011-154727.json)
  - [有效 2 · accept-plain-1011-161118.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-plain-1011-161118.json)
  - [有效 3 · accept-plain-1011-165018.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-plain-1011-165018.json)
- 初始配置：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-v0-1011-155625.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-v0-1011-155625.json)
  - [有效 2 · accept-v0-1011-163615.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-v0-1011-163615.json)
  - [有效 3 · accept-v0-1011-171405.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-v0-1011-171405.json)
- 训练后：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-8ab6e08e3fe1-1011-153944.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-8ab6e08e3fe1-1011-153944.json)
  - [有效 2 · accept-8ab6e08e3fe1-1011-162355.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-8ab6e08e3fe1-1011-162355.json)
  - [有效 3 · accept-8ab6e08e3fe1-1011-170035.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/poster-review/accept-8ab6e08e3fe1-1011-170035.json)

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
| R1 | trained | x 同规则 | 30 | 10 | 27/30 | 3/150 | 3 |
| R1 | trained | y 新规则 | 30 | 10 | 22/30 | 8/150 | 3 |

<a id="evidence-dental-post"></a>
### 2.2 医疗推文合规审查

训练：当前日志以训练完成结束，末次考试revision与当前deployment一致；[run.out](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/run.out)。
导出：导出payload与当前deployment一致，ACP入口已启用；[harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-dental-post/harness.json)；[deployment](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/dental-post/runs/live-20261011153837-14c53a/deployment.json)。
完整revision：`f220b0b0f4f5667b97695557853f1811f14b2c623ea311b0235734636746d690`。
用户确认验收：现在就当做全都通过验收了；时间 2026-10-12T03:02:03.061562+00:00；[确认记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/control/dental-post.json)。
[v0与训练后策略正文对照](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/learned-artifacts-20261011.md#dental-post)。
员工通道：**纯旧通道（OpenRouter）**（以当前完整有效报告中的答卷为准）。
本专家未列入这次109题恢复清单，保留既有旧通道验收；没有因事故重跑。

- 原版：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-plain-1011-200100-f8f329e07a.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/accept-plain-1011-200100-f8f329e07a.json)
  - [有效 2 · accept-plain-1011-201359-dca256619d.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/accept-plain-1011-201359-dca256619d.json)
  - [有效 3 · accept-plain-1011-203156-f6875bff2f.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/accept-plain-1011-203156-f6875bff2f.json)
- 初始配置：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-v0-1011-204256-ea213aec97.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/accept-v0-1011-204256-ea213aec97.json)
  - [有效 2 · accept-v0-1011-205846-7602e6ce8b.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/accept-v0-1011-205846-7602e6ce8b.json)
  - [有效 3 · accept-v0-1011-211110-a7938bb60e.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/accept-v0-1011-211110-a7938bb60e.json)
- 训练后：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-f220b0b0f4f5-1011-193059-fbbfa1ef35.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/accept-f220b0b0f4f5-1011-193059-fbbfa1ef35.json)
  - [有效 2 · accept-f220b0b0f4f5-1011-194022-784477a95f.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/accept-f220b0b0f4f5-1011-194022-784477a95f.json)
  - [有效 3 · accept-f220b0b0f4f5-1011-195059-be9edefd1f.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/accept-f220b0b0f4f5-1011-195059-be9edefd1f.json)

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
| R1 | trained | x 同规则 | 30 | 10 | 29/30 | 1/150 | 3 |
| R1 | trained | y 新规则 | 30 | 10 | 24/30 | 6/150 | 3 |

<a id="evidence-store-ticket"></a>
### 3.1 门店客单价分析

训练：当前日志以训练完成结束，末次考试revision与当前deployment一致；[run.out](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/store-ticket/run.out)。
导出：导出payload与当前deployment一致，ACP入口已启用；[harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-store-ticket/harness.json)；[deployment](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/store-ticket/runs/live-20261011135231-9fb59c/deployment.json)。
完整revision：`a3a9e4ad8ac567a63d7d6b230064374705dfc9f5ad91e028ae15129ea2dd2f0f`。
用户确认验收：现在就当做全都通过验收了；时间 2026-10-12T03:02:03.061562+00:00；[确认记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/control/store-ticket.json)。
[v0与训练后策略正文对照](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/learned-artifacts-20261011.md#store-ticket)。
员工通道：**纯旧通道（OpenRouter）**（以当前完整有效报告中的答卷为准）。
本专家未列入这次109题恢复清单，保留既有旧通道验收；没有因事故重跑。

- 原版：已保存 1 份有效完整报告；排除 0 份。
  - [有效 1 · accept-plain-1011-164942.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/store-ticket/accept-plain-1011-164942.json)
- 初始配置：已保存 1 份有效完整报告；排除 0 份。
  - [有效 1 · accept-v0-1011-165131.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/store-ticket/accept-v0-1011-165131.json)
- 训练后：已保存 1 份有效完整报告；排除 0 份。
  - [有效 1 · accept-a3a9e4ad8ac5-1011-164438.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/store-ticket/accept-a3a9e4ad8ac5-1011-164438.json)

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
| R1 | trained | x 同规则 | 10 | 10 | 8/10 | 2/32 | 1 |
| R1 | trained | y 新规则 | 10 | 10 | 5/10 | 6/33 | 1 |

<a id="evidence-saas-metric"></a>
### 3.2 SaaS 指标取数

训练：当前日志以训练完成结束，末次考试revision与当前deployment一致；[run.out](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/saas-metric/run.out)。
导出：导出payload与当前deployment一致，ACP入口已启用；[harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-saas-metric/harness.json)；[deployment](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/saas-metric/runs/live-20261011152837-4591ec/deployment.json)。
完整revision：`1aa568cda685d9831ccac53cf8e51ff0bca68390262b8e67ec66915b113eed22`。
用户确认验收：现在就当做全都通过验收了；时间 2026-10-12T03:02:03.061562+00:00；[确认记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/control/saas-metric.json)。
[v0与训练后策略正文对照](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/learned-artifacts-20261011.md#saas-metric)。
员工通道：**混合通道**（以当前完整有效报告中的答卷为准）。
本专家进入额度事故恢复：1 次运行的 2 道派活纳入重做清单；全批共 109 道。清单不按分数选择，原答卷与模型判定留档，正常条目保持不变。见[执行记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/quota-recovery-executed.json)。
恢复后的后续派活改经兼容适配器与排队网关。原通道为 OpenRouter / z-ai/glm-5.3-flash；新通道为 custom gateway / glm-5.3-flash，客户端仍使用 z-ai/glm-5.3-flash 别名。只验证了相同宣称模型名及SSE/工具协议，未独立验证两个provider等价。因此本专家的版本比较是描述性结果，不能把通道变化后的差异归为纯训练因果增益。
主表合并结果只作描述；不同provider或通道未明时，不能当作同条件训练对照。下方按路由分层仍是不同题号/运行构成的观察子样本，不单独证明因果增益。

- 原版：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-plain-1011-201316-f8f329e07a.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/saas-metric/accept-plain-1011-201316-f8f329e07a.json)
  - [有效 2 · accept-plain-1011-203154-dca256619d.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/saas-metric/accept-plain-1011-203154-dca256619d.json)
  - [有效 3 · accept-plain-1011-204233-f6875bff2f.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/saas-metric/accept-plain-1011-204233-f6875bff2f.json)
- 初始配置：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-v0-1011-205654-ea213aec97.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/saas-metric/accept-v0-1011-205654-ea213aec97.json)
  - [有效 2 · accept-v0-1011-210816-7602e6ce8b.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/saas-metric/accept-v0-1011-210816-7602e6ce8b.json)
  - [有效 3 · accept-v0-1011-213040-a7938bb60e.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/saas-metric/accept-v0-1011-213040-a7938bb60e.json)
- 训练后：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-1aa568cda685-1011-193100-ed23860e9a.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/saas-metric/accept-1aa568cda685-1011-193100-ed23860e9a.json)
  - [有效 2 · accept-1aa568cda685-1011-194305-097694a163.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/saas-metric/accept-1aa568cda685-1011-194305-097694a163.json)
  - [有效 3 · accept-1aa568cda685-1011-195420-c9738c0c83.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/saas-metric/accept-1aa568cda685-1011-195420-c9738c0c83.json)

员工路由分层（与判卷模型无关）：

缺少 transport 字段的旧正常答卷依据实验历史归为 legacy OpenRouter；显式但不完整的元数据归为未记录。不根据当前默认provider反推历史。

- R1：provider=`OpenRouter`；model=`z-ai/glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 178 次（其中 178 次无逐行通道字段，按旧记录归组）。
- R2：provider=`custom gateway`；model=`glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 2 次（其中 0 次无逐行通道字段，按旧记录归组）。

原完整运行共 9 次，其中 1 次内部混合通道。混合运行仍只计一次完整20题验收；以下是答卷层样本数，覆盖运行数不能跨路由相加成新实验。

| 路由 | 版本 | 题组 | 有效答卷次数 | 不同题号数 | 全对 / 有效答卷 | 失败项 / 适用项 | 覆盖原运行数 |
|---|---|---|---:|---:|---|---|---:|
| R1 | plain | x 同规则 | 30 | 10 | 21/30 | 15/120 | 3 |
| R1 | plain | y 新规则 | 30 | 10 | 24/30 | 8/120 | 3 |
| R1 | v0 | x 同规则 | 30 | 10 | 9/30 | 30/120 | 3 |
| R1 | v0 | y 新规则 | 28 | 10 | 5/28 | 32/112 | 3 |
| R2 | v0 | y 新规则 | 2 | 2 | 0/2 | 2/8 | 1 |
| R1 | trained | x 同规则 | 30 | 10 | 26/30 | 4/120 | 3 |
| R1 | trained | y 新规则 | 30 | 10 | 23/30 | 7/120 | 3 |

混合运行的答卷构成（不增加完整运行次数）：

- v0 [accept-v0-1011-213040-a7938bb60e.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/saas-metric/accept-v0-1011-213040-a7938bb60e.json)：R1=18题、R2=2题。

<a id="evidence-meeting-actions"></a>
### 4.1 会议待办整理

训练：当前日志以训练完成结束，末次考试revision与当前deployment一致；[run.out](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/run.out)。
导出：导出payload与当前deployment一致，ACP入口已启用；[harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-meeting-actions/harness.json)；[deployment](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/meeting-actions/runs/live-20261011155829-a4cb4c/deployment.json)。
完整revision：`51921603a07c003f1c971093525834122bee4a91ccd405f8acde5e2223376efa`。
用户确认验收：现在就当做全都通过验收了；时间 2026-10-12T03:02:03.061562+00:00；[确认记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/control/meeting-actions.json)。
[v0与训练后策略正文对照](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/learned-artifacts-20261011.md#meeting-actions)。
员工通道：**纯旧通道（OpenRouter）**（以当前完整有效报告中的答卷为准）。
本专家未列入这次109题恢复清单，保留既有旧通道验收；没有因事故重跑。

- 原版：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-plain-1011-195712-f8f329e07a.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-plain-1011-195712-f8f329e07a.json)
  - [有效 2 · accept-plain-1011-200713-dca256619d.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-plain-1011-200713-dca256619d.json)
  - [有效 3 · accept-plain-1011-201632-f6875bff2f.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-plain-1011-201632-f6875bff2f.json)
- 初始配置：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-v0-1011-203049-ea213aec97.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-v0-1011-203049-ea213aec97.json)
  - [有效 2 · accept-v0-1011-203944-7602e6ce8b.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-v0-1011-203944-7602e6ce8b.json)
  - [有效 3 · accept-v0-1011-205005-a7938bb60e.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-v0-1011-205005-a7938bb60e.json)
- 训练后：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-51921603a07c-1011-193059-ba62ea87d9.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-51921603a07c-1011-193059-ba62ea87d9.json)
  - [有效 2 · accept-51921603a07c-1011-193822-1c3c5611f2.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-51921603a07c-1011-193822-1c3c5611f2.json)
  - [有效 3 · accept-51921603a07c-1011-194734-3261e8ba25.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-51921603a07c-1011-194734-3261e8ba25.json)

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
| R1 | trained | x 同规则 | 30 | 10 | 29/30 | 1/150 | 3 |
| R1 | trained | y 新规则 | 30 | 10 | 26/30 | 4/150 | 3 |

<a id="evidence-weekly-report"></a>
### 4.2 运营周报

训练：当前日志以训练完成结束，末次考试revision与当前deployment一致；[run.out](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/weekly-report/run.out)。
导出：导出payload与当前deployment一致，ACP入口已启用；[harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-weekly-report/harness.json)；[deployment](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/weekly-report/runs/live-20261011151931-f8c538/deployment.json)。
完整revision：`899b5d2ca3130d17123acee354140f6759ae788ce3a58b6cfc1e0dcff2d1768b`。
用户确认验收：现在就当做全都通过验收了；时间 2026-10-12T03:02:03.061562+00:00；[确认记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/control/weekly-report.json)。
[v0与训练后策略正文对照](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/learned-artifacts-20261011.md#weekly-report)。
员工通道：**混合通道**（以当前完整有效报告中的答卷为准）。
本专家进入额度事故恢复：1 次运行的 3 道派活纳入重做清单；全批共 109 道。清单不按分数选择，原答卷与模型判定留档，正常条目保持不变。见[执行记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/quota-recovery-executed.json)。
恢复后的后续派活改经兼容适配器与排队网关。原通道为 OpenRouter / z-ai/glm-5.3-flash；新通道为 custom gateway / glm-5.3-flash，客户端仍使用 z-ai/glm-5.3-flash 别名。只验证了相同宣称模型名及SSE/工具协议，未独立验证两个provider等价。因此本专家的版本比较是描述性结果，不能把通道变化后的差异归为纯训练因果增益。
主表合并结果只作描述；不同provider或通道未明时，不能当作同条件训练对照。下方按路由分层仍是不同题号/运行构成的观察子样本，不单独证明因果增益。

- 原版：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-plain-1011-200821-f8f329e07a.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/weekly-report/accept-plain-1011-200821-f8f329e07a.json)
  - [有效 2 · accept-plain-1011-202455-dca256619d.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/weekly-report/accept-plain-1011-202455-dca256619d.json)
  - [有效 3 · accept-plain-1011-204345-f6875bff2f.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/weekly-report/accept-plain-1011-204345-f6875bff2f.json)
- 初始配置：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-v0-1011-205953-ea213aec97.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/weekly-report/accept-v0-1011-205953-ea213aec97.json)
  - [有效 2 · accept-v0-1011-211733-7602e6ce8b.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/weekly-report/accept-v0-1011-211733-7602e6ce8b.json)
  - [有效 3 · accept-v0-1011-213240-a7938bb60e.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/weekly-report/accept-v0-1011-213240-a7938bb60e.json)
- 训练后：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-899b5d2ca313-1011-193059-958a05a7c3.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/weekly-report/accept-899b5d2ca313-1011-193059-958a05a7c3.json)
  - [有效 2 · accept-899b5d2ca313-1011-194236-6a39d5d3b4.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/weekly-report/accept-899b5d2ca313-1011-194236-6a39d5d3b4.json)
  - [有效 3 · accept-899b5d2ca313-1011-195505-a78c4f88cd.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/weekly-report/accept-899b5d2ca313-1011-195505-a78c4f88cd.json)

员工路由分层（与判卷模型无关）：

缺少 transport 字段的旧正常答卷依据实验历史归为 legacy OpenRouter；显式但不完整的元数据归为未记录。不根据当前默认provider反推历史。

- R1：provider=`OpenRouter`；model=`z-ai/glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 177 次（其中 177 次无逐行通道字段，按旧记录归组）。
- R2：provider=`custom gateway`；model=`glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 3 次（其中 0 次无逐行通道字段，按旧记录归组）。

原完整运行共 9 次，其中 1 次内部混合通道。混合运行仍只计一次完整20题验收；以下是答卷层样本数，覆盖运行数不能跨路由相加成新实验。

| 路由 | 版本 | 题组 | 有效答卷次数 | 不同题号数 | 全对 / 有效答卷 | 失败项 / 适用项 | 覆盖原运行数 |
|---|---|---|---:|---:|---|---|---:|
| R1 | plain | x 同规则 | 30 | 10 | 0/30 | 39/120 | 3 |
| R1 | plain | y 新规则 | 30 | 10 | 0/30 | 32/120 | 3 |
| R1 | v0 | x 同规则 | 30 | 10 | 0/30 | 36/120 | 3 |
| R1 | v0 | y 新规则 | 27 | 10 | 2/27 | 26/108 | 3 |
| R2 | v0 | y 新规则 | 3 | 3 | 1/3 | 2/12 | 1 |
| R1 | trained | x 同规则 | 30 | 10 | 25/30 | 5/120 | 3 |
| R1 | trained | y 新规则 | 30 | 10 | 13/30 | 17/120 | 3 |

混合运行的答卷构成（不增加完整运行次数）：

- v0 [accept-v0-1011-213240-a7938bb60e.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/weekly-report/accept-v0-1011-213240-a7938bb60e.json)：R1=17题、R2=3题。

<a id="evidence-cafe-copy"></a>
### 5.1 咖啡新品文案

训练：当前日志以训练完成结束，末次考试revision与当前deployment一致；[run.out](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/cafe-copy/run.out)。
导出：导出payload与当前deployment一致，ACP入口已启用；[harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-cafe-copy/harness.json)；[deployment](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/cafe-copy/runs/live-20261011160340-e4168d/deployment.json)。
完整revision：`64aecc43de91a4bb7355ad4b7af4c1896724031570d4ac41999c05b55526f121`。
用户确认验收：现在就当做全都通过验收了；时间 2026-10-12T03:02:03.061562+00:00；[确认记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/control/cafe-copy.json)。
[v0与训练后策略正文对照](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/learned-artifacts-20261011.md#cafe-copy)。
员工通道：**混合通道**（以当前完整有效报告中的答卷为准）。
本专家进入额度事故恢复：1 次运行的 1 道派活纳入重做清单；全批共 109 道。清单不按分数选择，原答卷与模型判定留档，正常条目保持不变。见[执行记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/quota-recovery-executed.json)。
恢复后的后续派活改经兼容适配器与排队网关。原通道为 OpenRouter / z-ai/glm-5.3-flash；新通道为 custom gateway / glm-5.3-flash，客户端仍使用 z-ai/glm-5.3-flash 别名。只验证了相同宣称模型名及SSE/工具协议，未独立验证两个provider等价。因此本专家的版本比较是描述性结果，不能把通道变化后的差异归为纯训练因果增益。
主表合并结果只作描述；不同provider或通道未明时，不能当作同条件训练对照。下方按路由分层仍是不同题号/运行构成的观察子样本，不单独证明因果增益。

- 原版：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-plain-1011-201846-f8f329e07a.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/cafe-copy/accept-plain-1011-201846-f8f329e07a.json)
  - [有效 2 · accept-plain-1011-204018-dca256619d.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/cafe-copy/accept-plain-1011-204018-dca256619d.json)
  - [有效 3 · accept-plain-1011-205948-f6875bff2f.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/cafe-copy/accept-plain-1011-205948-f6875bff2f.json)
- 初始配置：已保存 1 份有效完整报告；排除 0 份。
  - [有效 1 · accept-v0-1011-212314-ea213aec97.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/cafe-copy/accept-v0-1011-212314-ea213aec97.json)
- 训练后：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-64aecc43de91-1011-193059-81ef42434b.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/cafe-copy/accept-64aecc43de91-1011-193059-81ef42434b.json)
  - [有效 2 · accept-64aecc43de91-1011-194631-cfff7521b8.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/cafe-copy/accept-64aecc43de91-1011-194631-cfff7521b8.json)
  - [有效 3 · accept-64aecc43de91-1011-200142-fbafaf4b7f.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/cafe-copy/accept-64aecc43de91-1011-200142-fbafaf4b7f.json)

员工路由分层（与判卷模型无关）：

缺少 transport 字段的旧正常答卷依据实验历史归为 legacy OpenRouter；显式但不完整的元数据归为未记录。不根据当前默认provider反推历史。

- R1：provider=`OpenRouter`；model=`z-ai/glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 139 次（其中 139 次无逐行通道字段，按旧记录归组）。
- R2：provider=`custom gateway`；model=`glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 1 次（其中 0 次无逐行通道字段，按旧记录归组）。

原完整运行共 7 次，其中 1 次内部混合通道。混合运行仍只计一次完整20题验收；以下是答卷层样本数，覆盖运行数不能跨路由相加成新实验。

| 路由 | 版本 | 题组 | 有效答卷次数 | 不同题号数 | 全对 / 有效答卷 | 失败项 / 适用项 | 覆盖原运行数 |
|---|---|---|---:|---:|---|---|---:|
| R1 | plain | x 同规则 | 30 | 10 | 3/30 | 27/150 | 3 |
| R1 | plain | y 新规则 | 30 | 10 | 1/30 | 30/150 | 3 |
| R1 | v0 | x 同规则 | 10 | 10 | 6/10 | 6/50 | 1 |
| R1 | v0 | y 新规则 | 9 | 9 | 6/9 | 3/45 | 1 |
| R2 | v0 | y 新规则 | 1 | 1 | 1/1 | 0/5 | 1 |
| R1 | trained | x 同规则 | 30 | 10 | 30/30 | 0/150 | 3 |
| R1 | trained | y 新规则 | 30 | 10 | 27/30 | 3/150 | 3 |

混合运行的答卷构成（不增加完整运行次数）：

- v0 [accept-v0-1011-212314-ea213aec97.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/cafe-copy/accept-v0-1011-212314-ea213aec97.json)：R1=19题、R2=1题。

<a id="evidence-xhs-note"></a>
### 5.2 小红书种草笔记

训练：当前日志以训练完成结束，末次考试revision与当前deployment一致；[run.out](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/xhs-note/run.out)。
导出：导出payload与当前deployment一致，ACP入口已启用；[harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-xhs-note/harness.json)；[deployment](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/xhs-note/runs/live-20261011193431-1a5645/deployment.json)。
完整revision：`f2d14854e9a6092aca20a5059eaad1915d11ca70ab9ddcfb7e7b937e831a2dc1`。
用户确认验收：现在就当做全都通过验收了；时间 2026-10-12T03:02:03.061562+00:00；[确认记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/control/xhs-note.json)。
[v0与训练后策略正文对照](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/learned-artifacts-20261011.md#xhs-note)。
员工通道：**混合通道**（以当前完整有效报告中的答卷为准）。
本专家进入额度事故恢复：3 次运行的 14 道派活纳入重做清单；全批共 109 道。清单不按分数选择，原答卷与模型判定留档，正常条目保持不变。见[执行记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/quota-recovery-executed.json)。
恢复后的后续派活改经兼容适配器与排队网关。原通道为 OpenRouter / z-ai/glm-5.3-flash；新通道为 custom gateway / glm-5.3-flash，客户端仍使用 z-ai/glm-5.3-flash 别名。只验证了相同宣称模型名及SSE/工具协议，未独立验证两个provider等价。因此本专家的版本比较是描述性结果，不能把通道变化后的差异归为纯训练因果增益。
主表合并结果只作描述；不同provider或通道未明时，不能当作同条件训练对照。下方按路由分层仍是不同题号/运行构成的观察子样本，不单独证明因果增益。

- 原版：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-plain-1011-211522-f8f329e07a.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/xhs-note/accept-plain-1011-211522-f8f329e07a.json)
  - [有效 2 · accept-plain-1011-213216-dca256619d.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/xhs-note/accept-plain-1011-213216-dca256619d.json)
  - [有效 3 · accept-plain-1011-214043-f6875bff2f.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/xhs-note/accept-plain-1011-214043-f6875bff2f.json)
- 初始配置：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-v0-1011-211522-ea213aec97.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/xhs-note/accept-v0-1011-211522-ea213aec97.json)
  - [有效 2 · accept-v0-1011-213031-7602e6ce8b.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/xhs-note/accept-v0-1011-213031-7602e6ce8b.json)
  - [有效 3 · accept-v0-1011-214113-a7938bb60e.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/xhs-note/accept-v0-1011-214113-a7938bb60e.json)
- 训练后：已保存 2 份有效完整报告；排除 0 份。
  - [有效 1 · accept-f2d14854e9a6-1011-210720-943cd919bc.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/xhs-note/accept-f2d14854e9a6-1011-210720-943cd919bc.json)
  - [有效 2 · accept-f2d14854e9a6-1011-213154-9aa3b708e8.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/xhs-note/accept-f2d14854e9a6-1011-213154-9aa3b708e8.json)

员工路由分层（与判卷模型无关）：

缺少 transport 字段的旧正常答卷依据实验历史归为 legacy OpenRouter；显式但不完整的元数据归为未记录。不根据当前默认provider反推历史。

- R1：provider=`OpenRouter`；model=`z-ai/glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 112 次（其中 112 次无逐行通道字段，按旧记录归组）。
- R2：provider=`custom gateway`；model=`glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 48 次（其中 0 次无逐行通道字段，按旧记录归组）。

原完整运行共 8 次，其中 3 次内部混合通道。混合运行仍只计一次完整20题验收；以下是答卷层样本数，覆盖运行数不能跨路由相加成新实验。

| 路由 | 版本 | 题组 | 有效答卷次数 | 不同题号数 | 全对 / 有效答卷 | 失败项 / 适用项 | 覆盖原运行数 |
|---|---|---|---:|---:|---|---|---:|
| R1 | plain | x 同规则 | 26 | 10 | 25/26 | 1/130 | 3 |
| R1 | plain | y 新规则 | 20 | 10 | 11/20 | 9/100 | 2 |
| R2 | plain | x 同规则 | 4 | 4 | 4/4 | 0/20 | 1 |
| R2 | plain | y 新规则 | 10 | 10 | 10/10 | 0/50 | 1 |
| R1 | v0 | x 同规则 | 21 | 10 | 13/21 | 8/105 | 3 |
| R1 | v0 | y 新规则 | 20 | 10 | 16/20 | 4/100 | 2 |
| R2 | v0 | x 同规则 | 9 | 9 | 7/9 | 5/45 | 1 |
| R2 | v0 | y 新规则 | 10 | 10 | 4/10 | 21/50 | 1 |
| R1 | trained | x 同规则 | 15 | 10 | 8/15 | 7/75 | 2 |
| R1 | trained | y 新规则 | 10 | 10 | 5/10 | 5/50 | 1 |
| R2 | trained | x 同规则 | 5 | 5 | 3/5 | 5/25 | 1 |
| R2 | trained | y 新规则 | 10 | 10 | 2/10 | 29/50 | 1 |

混合运行的答卷构成（不增加完整运行次数）：

- plain [accept-plain-1011-214043-f6875bff2f.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/xhs-note/accept-plain-1011-214043-f6875bff2f.json)：R1=6题、R2=14题。
- v0 [accept-v0-1011-214113-a7938bb60e.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/xhs-note/accept-v0-1011-214113-a7938bb60e.json)：R1=1题、R2=19题。
- trained [accept-f2d14854e9a6-1011-213154-9aa3b708e8.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/xhs-note/accept-f2d14854e9a6-1011-213154-9aa3b708e8.json)：R1=5题、R2=15题。

<a id="evidence-taobao-title"></a>
### 6.1 电商标题和卖点

训练：当前日志以训练完成结束，末次考试revision与当前deployment一致；[run.out](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/run.out)。
导出：导出payload与当前deployment一致，ACP入口已启用；[harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-taobao-title/harness.json)；[deployment](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/taobao-title/runs/live-20261011162336-b947f2/deployment.json)。
完整revision：`42a572b356cde6fccb635c6c0e1d7d12418af4930985a75f8727c45b57edb624`。
用户确认验收：现在就当做全都通过验收了；时间 2026-10-12T03:02:03.061562+00:00；[确认记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/control/taobao-title.json)。
[v0与训练后策略正文对照](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/learned-artifacts-20261011.md#taobao-title)。
员工通道：**纯旧通道（OpenRouter）**（以当前完整有效报告中的答卷为准）。
本专家未列入这次109题恢复清单，保留既有旧通道验收；没有因事故重跑。

- 原版：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-plain-1011-200925-f8f329e07a.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-plain-1011-200925-f8f329e07a.json)
  - [有效 2 · accept-plain-1011-202036-dca256619d.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-plain-1011-202036-dca256619d.json)
  - [有效 3 · accept-plain-1011-203617-f6875bff2f.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-plain-1011-203617-f6875bff2f.json)
- 初始配置：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-v0-1011-204607-ea213aec97.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-v0-1011-204607-ea213aec97.json)
  - [有效 2 · accept-v0-1011-205848-7602e6ce8b.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-v0-1011-205848-7602e6ce8b.json)
  - [有效 3 · accept-v0-1011-211012-a7938bb60e.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-v0-1011-211012-a7938bb60e.json)
- 训练后：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-42a572b356cd-1011-193059-2e6383eeab.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-42a572b356cd-1011-193059-2e6383eeab.json)
  - [有效 2 · accept-42a572b356cd-1011-194024-bcc1869a26.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-42a572b356cd-1011-194024-bcc1869a26.json)
  - [有效 3 · accept-42a572b356cd-1011-195438-c893324f03.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-42a572b356cd-1011-195438-c893324f03.json)

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
| R1 | trained | x 同规则 | 30 | 10 | 26/30 | 4/120 | 3 |
| R1 | trained | y 新规则 | 30 | 10 | 27/30 | 3/120 | 3 |

<a id="evidence-amazon-listing"></a>
### 6.2 亚马逊英文 Listing

训练：当前日志以训练完成结束，末次考试revision与当前deployment一致；[run.out](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/amazon-listing/run.out)。
导出：导出payload与当前deployment一致，ACP入口已启用；[harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-amazon-listing/harness.json)；[deployment](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/amazon-listing/runs/live-20261011193431-d719da/deployment.json)。
完整revision：`a6acd033c4b60c4fb2b8d440834ae6be99f294a6243db02e14e0aa72d19f456a`。
用户确认验收：现在就当做全都通过验收了；时间 2026-10-12T03:02:03.061562+00:00；[确认记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/control/amazon-listing.json)。
[v0与训练后策略正文对照](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/learned-artifacts-20261011.md#amazon-listing)。
员工通道：**混合通道**（以当前完整有效报告中的答卷为准）。
本专家进入额度事故恢复：3 次运行的 16 道派活纳入重做清单；全批共 109 道。清单不按分数选择，原答卷与模型判定留档，正常条目保持不变。见[执行记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/quota-recovery-executed.json)。
恢复后的后续派活改经兼容适配器与排队网关。原通道为 OpenRouter / z-ai/glm-5.3-flash；新通道为 custom gateway / glm-5.3-flash，客户端仍使用 z-ai/glm-5.3-flash 别名。只验证了相同宣称模型名及SSE/工具协议，未独立验证两个provider等价。因此本专家的版本比较是描述性结果，不能把通道变化后的差异归为纯训练因果增益。
主表合并结果只作描述；不同provider或通道未明时，不能当作同条件训练对照。下方按路由分层仍是不同题号/运行构成的观察子样本，不单独证明因果增益。

- 原版：已保存 2 份有效完整报告；排除 0 份。
  - [有效 1 · accept-plain-1011-211522-f8f329e07a.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/amazon-listing/accept-plain-1011-211522-f8f329e07a.json)
  - [有效 2 · accept-plain-1011-213229-dca256619d.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/amazon-listing/accept-plain-1011-213229-dca256619d.json)
- 初始配置：已保存 2 份有效完整报告；排除 0 份。
  - [有效 1 · accept-v0-1011-211522-ea213aec97.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/amazon-listing/accept-v0-1011-211522-ea213aec97.json)
  - [有效 2 · accept-v0-1011-213327-7602e6ce8b.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/amazon-listing/accept-v0-1011-213327-7602e6ce8b.json)
- 训练后：已保存 2 份有效完整报告；排除 0 份。
  - [有效 1 · accept-a6acd033c4b6-1011-211357-dc700d5059.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/amazon-listing/accept-a6acd033c4b6-1011-211357-dc700d5059.json)
  - [有效 2 · accept-a6acd033c4b6-1011-213720-1dab029156.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/amazon-listing/accept-a6acd033c4b6-1011-213720-1dab029156.json)

员工路由分层（与判卷模型无关）：

缺少 transport 字段的旧正常答卷依据实验历史归为 legacy OpenRouter；显式但不完整的元数据归为未记录。不根据当前默认provider反推历史。

- R1：provider=`OpenRouter`；model=`z-ai/glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 89 次（其中 89 次无逐行通道字段，按旧记录归组）。
- R2：provider=`custom gateway`；model=`glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 31 次（其中 0 次无逐行通道字段，按旧记录归组）。

原完整运行共 6 次，其中 3 次内部混合通道。混合运行仍只计一次完整20题验收；以下是答卷层样本数，覆盖运行数不能跨路由相加成新实验。

| 路由 | 版本 | 题组 | 有效答卷次数 | 不同题号数 | 全对 / 有效答卷 | 失败项 / 适用项 | 覆盖原运行数 |
|---|---|---|---:|---:|---|---|---:|
| R1 | plain | x 同规则 | 20 | 10 | 10/20 | 14/100 | 2 |
| R1 | plain | y 新规则 | 12 | 10 | 5/12 | 8/60 | 2 |
| R2 | plain | y 新规则 | 8 | 8 | 6/8 | 2/40 | 1 |
| R1 | v0 | x 同规则 | 20 | 10 | 10/20 | 13/100 | 2 |
| R1 | v0 | y 新规则 | 11 | 10 | 3/11 | 10/55 | 2 |
| R2 | v0 | y 新规则 | 9 | 9 | 7/9 | 2/45 | 1 |
| R1 | trained | x 同规则 | 16 | 10 | 8/16 | 8/80 | 2 |
| R1 | trained | y 新规则 | 10 | 10 | 8/10 | 2/50 | 1 |
| R2 | trained | x 同规则 | 4 | 4 | 3/4 | 1/20 | 1 |
| R2 | trained | y 新规则 | 10 | 10 | 8/10 | 3/50 | 1 |

混合运行的答卷构成（不增加完整运行次数）：

- plain [accept-plain-1011-213229-dca256619d.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/amazon-listing/accept-plain-1011-213229-dca256619d.json)：R1=12题、R2=8题。
- v0 [accept-v0-1011-213327-7602e6ce8b.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/amazon-listing/accept-v0-1011-213327-7602e6ce8b.json)：R1=11题、R2=9题。
- trained [accept-a6acd033c4b6-1011-213720-1dab029156.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/amazon-listing/accept-a6acd033c4b6-1011-213720-1dab029156.json)：R1=6题、R2=14题。

<a id="evidence-resume-screen"></a>
### 7.1 简历初筛

训练：当前日志以训练完成结束，末次考试revision与当前deployment一致；[run.out](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-screen/run.out)。
导出：导出payload与当前deployment一致，ACP入口已启用；[harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-resume-screen/harness.json)；[deployment](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/resume-screen/runs/live-20261011161416-a19861/deployment.json)。
完整revision：`44acc1a3668801fb5fcef9c089dfaa8fc0dab5e88670eb7d3c515d901e5c74c8`。
用户确认验收：现在就当做全都通过验收了；时间 2026-10-12T03:02:03.061562+00:00；[确认记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/control/resume-screen.json)。
[v0与训练后策略正文对照](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/learned-artifacts-20261011.md#resume-screen)。
员工通道：**混合通道**（以当前完整有效报告中的答卷为准）。
本专家进入额度事故恢复：3 次运行的 17 道派活纳入重做清单；全批共 109 道。清单不按分数选择，原答卷与模型判定留档，正常条目保持不变。见[执行记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/quota-recovery-executed.json)。
恢复后的后续派活改经兼容适配器与排队网关。原通道为 OpenRouter / z-ai/glm-5.3-flash；新通道为 custom gateway / glm-5.3-flash，客户端仍使用 z-ai/glm-5.3-flash 别名。只验证了相同宣称模型名及SSE/工具协议，未独立验证两个provider等价。因此本专家的版本比较是描述性结果，不能把通道变化后的差异归为纯训练因果增益。
主表合并结果只作描述；不同provider或通道未明时，不能当作同条件训练对照。下方按路由分层仍是不同题号/运行构成的观察子样本，不单独证明因果增益。

- 原版：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-plain-1011-211522-f8f329e07a.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-screen/accept-plain-1011-211522-f8f329e07a.json)
  - [有效 2 · accept-plain-1011-213558-dca256619d.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-screen/accept-plain-1011-213558-dca256619d.json)
  - [有效 3 · accept-plain-1011-233154-f6875bff2f.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-screen/accept-plain-1011-233154-f6875bff2f.json)
- 初始配置：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-v0-1011-211522-ea213aec97.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-screen/accept-v0-1011-211522-ea213aec97.json)
  - [有效 2 · accept-v0-1011-212908-7602e6ce8b.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-screen/accept-v0-1011-212908-7602e6ce8b.json)
  - [有效 3 · accept-v0-1011-213944-a7938bb60e.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-screen/accept-v0-1011-213944-a7938bb60e.json)
- 训练后：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-44acc1a36688-1011-205656-bf13ad7705.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-screen/accept-44acc1a36688-1011-205656-bf13ad7705.json)
  - [有效 2 · accept-44acc1a36688-1011-212302-c4decbcaa6.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-screen/accept-44acc1a36688-1011-212302-c4decbcaa6.json)
  - [有效 3 · accept-44acc1a36688-1011-213709-0f0697b053.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-screen/accept-44acc1a36688-1011-213709-0f0697b053.json)

员工路由分层（与判卷模型无关）：

缺少 transport 字段的旧正常答卷依据实验历史归为 legacy OpenRouter；显式但不完整的元数据归为未记录。不根据当前默认provider反推历史。

- R1：provider=`OpenRouter`；model=`z-ai/glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 123 次（其中 123 次无逐行通道字段，按旧记录归组）。
- R2：provider=`custom gateway`；model=`glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 57 次（其中 0 次无逐行通道字段，按旧记录归组）。

原完整运行共 9 次，其中 3 次内部混合通道。混合运行仍只计一次完整20题验收；以下是答卷层样本数，覆盖运行数不能跨路由相加成新实验。

| 路由 | 版本 | 题组 | 有效答卷次数 | 不同题号数 | 全对 / 有效答卷 | 失败项 / 适用项 | 覆盖原运行数 |
|---|---|---|---:|---:|---|---|---:|
| R1 | plain | x 同规则 | 20 | 10 | 0/20 | 39/100 | 2 |
| R1 | plain | y 新规则 | 10 | 10 | 1/10 | 17/50 | 1 |
| R2 | plain | y 新规则 | 20 | 10 | 12/20 | 10/100 | 2 |
| R2 | plain | x 同规则 | 10 | 10 | 4/10 | 6/50 | 1 |
| R1 | v0 | x 同规则 | 25 | 10 | 1/25 | 41/125 | 3 |
| R1 | v0 | y 新规则 | 20 | 10 | 3/20 | 22/100 | 2 |
| R2 | v0 | x 同规则 | 5 | 5 | 4/5 | 1/25 | 1 |
| R2 | v0 | y 新规则 | 10 | 10 | 1/10 | 13/50 | 1 |
| R1 | trained | x 同规则 | 28 | 10 | 15/28 | 16/140 | 3 |
| R1 | trained | y 新规则 | 20 | 10 | 9/20 | 13/100 | 2 |
| R2 | trained | x 同规则 | 2 | 2 | 1/2 | 4/10 | 1 |
| R2 | trained | y 新规则 | 10 | 10 | 3/10 | 19/50 | 1 |

混合运行的答卷构成（不增加完整运行次数）：

- plain [accept-plain-1011-213558-dca256619d.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-screen/accept-plain-1011-213558-dca256619d.json)：R1=10题、R2=10题。
- v0 [accept-v0-1011-213944-a7938bb60e.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-screen/accept-v0-1011-213944-a7938bb60e.json)：R1=5题、R2=15题。
- trained [accept-44acc1a36688-1011-213709-0f0697b053.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-screen/accept-44acc1a36688-1011-213709-0f0697b053.json)：R1=8题、R2=12题。

<a id="evidence-resume-rewrite"></a>
### 7.2 简历优化

训练：当前日志以训练完成结束，末次考试revision与当前deployment一致；[run.out](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-rewrite/run.out)。
导出：导出payload与当前deployment一致，ACP入口已启用；[harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-resume-rewrite/harness.json)；[deployment](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/resume-rewrite/runs/live-20261011193431-ad7a1c/deployment.json)。
完整revision：`0b2cb375ce0497a85f50ba59ee94115d5cd5f1f92cd02777bd48cd07c84ff855`。
用户确认验收：现在就当做全都通过验收了；时间 2026-10-12T03:02:03.061562+00:00；[确认记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/control/resume-rewrite.json)。
[v0与训练后策略正文对照](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/learned-artifacts-20261011.md#resume-rewrite)。
员工通道：**混合通道**（以当前完整有效报告中的答卷为准）。
本专家进入额度事故恢复：1 次运行的 2 道派活纳入重做清单；全批共 109 道。清单不按分数选择，原答卷与模型判定留档，正常条目保持不变。见[执行记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/quota-recovery-executed.json)。
恢复后的后续派活改经兼容适配器与排队网关。原通道为 OpenRouter / z-ai/glm-5.3-flash；新通道为 custom gateway / glm-5.3-flash，客户端仍使用 z-ai/glm-5.3-flash 别名。只验证了相同宣称模型名及SSE/工具协议，未独立验证两个provider等价。因此本专家的版本比较是描述性结果，不能把通道变化后的差异归为纯训练因果增益。
主表合并结果只作描述；不同provider或通道未明时，不能当作同条件训练对照。下方按路由分层仍是不同题号/运行构成的观察子样本，不单独证明因果增益。

- 原版：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-plain-1011-210456-f8f329e07a.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-rewrite/accept-plain-1011-210456-f8f329e07a.json)
  - [有效 2 · accept-plain-1011-212255-dca256619d.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-rewrite/accept-plain-1011-212255-dca256619d.json)
  - [有效 3 · accept-plain-1011-213153-f6875bff2f.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-rewrite/accept-plain-1011-213153-f6875bff2f.json)
- 初始配置：已保存 1 份有效完整报告；排除 0 份。
  - [有效 1 · accept-v0-1011-214135-ea213aec97.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-rewrite/accept-v0-1011-214135-ea213aec97.json)
- 训练后：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-0b2cb375ce04-1011-203328-0ec12afbd5.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-rewrite/accept-0b2cb375ce04-1011-203328-0ec12afbd5.json)
  - [有效 2 · accept-0b2cb375ce04-1011-204204-8f5c591f11.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-rewrite/accept-0b2cb375ce04-1011-204204-8f5c591f11.json)
  - [有效 3 · accept-0b2cb375ce04-1011-205526-be6896c4e4.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-rewrite/accept-0b2cb375ce04-1011-205526-be6896c4e4.json)

员工路由分层（与判卷模型无关）：

缺少 transport 字段的旧正常答卷依据实验历史归为 legacy OpenRouter；显式但不完整的元数据归为未记录。不根据当前默认provider反推历史。

- R1：provider=`OpenRouter`；model=`z-ai/glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 121 次（其中 121 次无逐行通道字段，按旧记录归组）。
- R2：provider=`custom gateway`；model=`glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 19 次（其中 0 次无逐行通道字段，按旧记录归组）。

原完整运行共 7 次，其中 1 次内部混合通道。混合运行仍只计一次完整20题验收；以下是答卷层样本数，覆盖运行数不能跨路由相加成新实验。

| 路由 | 版本 | 题组 | 有效答卷次数 | 不同题号数 | 全对 / 有效答卷 | 失败项 / 适用项 | 覆盖原运行数 |
|---|---|---|---:|---:|---|---|---:|
| R1 | plain | x 同规则 | 30 | 10 | 13/30 | 21/150 | 3 |
| R1 | plain | y 新规则 | 30 | 10 | 20/30 | 13/150 | 3 |
| R1 | v0 | x 同规则 | 1 | 1 | 1/1 | 0/5 | 1 |
| R2 | v0 | x 同规则 | 9 | 9 | 8/9 | 3/45 | 1 |
| R2 | v0 | y 新规则 | 10 | 10 | 8/10 | 6/50 | 1 |
| R1 | trained | x 同规则 | 30 | 10 | 29/30 | 1/150 | 3 |
| R1 | trained | y 新规则 | 30 | 10 | 27/30 | 3/150 | 3 |

混合运行的答卷构成（不增加完整运行次数）：

- v0 [accept-v0-1011-214135-ea213aec97.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-rewrite/accept-v0-1011-214135-ea213aec97.json)：R1=1题、R2=19题。

<a id="evidence-contract-review"></a>
### 8.1 合同留痕审稿

训练：当前日志以训练完成结束，末次考试revision与当前deployment一致；[run.out](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-review/run.out)。
导出：导出payload与当前deployment一致，ACP入口已启用；[harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-contract-review/harness.json)；[deployment](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/contract-review/runs/live-20261011162704-4d72c3/deployment.json)。
完整revision：`cd2deb00398e0be79b5b037a9f60414d96e086e7dfae6ebb5235218d1cfd9b20`。
用户确认验收：现在就当做全都通过验收了；时间 2026-10-12T03:02:03.061562+00:00；[确认记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/control/contract-review.json)。
[v0与训练后策略正文对照](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/learned-artifacts-20261011.md#contract-review)。
员工通道：**混合通道**（以当前完整有效报告中的答卷为准）。
本专家进入额度事故恢复：2 次运行的 8 道派活纳入重做清单；全批共 109 道。清单不按分数选择，原答卷与模型判定留档，正常条目保持不变。见[执行记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/quota-recovery-executed.json)。
恢复后的后续派活改经兼容适配器与排队网关。原通道为 OpenRouter / z-ai/glm-5.3-flash；新通道为 custom gateway / glm-5.3-flash，客户端仍使用 z-ai/glm-5.3-flash 别名。只验证了相同宣称模型名及SSE/工具协议，未独立验证两个provider等价。因此本专家的版本比较是描述性结果，不能把通道变化后的差异归为纯训练因果增益。
主表合并结果只作描述；不同provider或通道未明时，不能当作同条件训练对照。下方按路由分层仍是不同题号/运行构成的观察子样本，不单独证明因果增益。

- 原版：已保存 2 份有效完整报告；排除 0 份。
  - [有效 1 · accept-plain-1011-205857-f8f329e07a.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-review/accept-plain-1011-205857-f8f329e07a.json)
  - [有效 2 · accept-plain-1011-212700-dca256619d.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-review/accept-plain-1011-212700-dca256619d.json)
- 初始配置：已保存 1 份有效完整报告；排除 0 份。
  - [有效 1 · accept-v0-1011-205857-ea213aec97.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-review/accept-v0-1011-205857-ea213aec97.json)
- 训练后：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-cd2deb00398e-1011-193104-1405c15990.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-review/accept-cd2deb00398e-1011-193104-1405c15990.json)
  - [有效 2 · accept-cd2deb00398e-1011-200633-f7fe903a07.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-review/accept-cd2deb00398e-1011-200633-f7fe903a07.json)
  - [有效 3 · accept-cd2deb00398e-1011-204240-3174ead248.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-review/accept-cd2deb00398e-1011-204240-3174ead248.json)

员工路由分层（与判卷模型无关）：

缺少 transport 字段的旧正常答卷依据实验历史归为 legacy OpenRouter；显式但不完整的元数据归为未记录。不根据当前默认provider反推历史。

- R1：provider=`OpenRouter`；model=`z-ai/glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 114 次（其中 114 次无逐行通道字段，按旧记录归组）。
- R2：provider=`custom gateway`；model=`glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 6 次（其中 0 次无逐行通道字段，按旧记录归组）。

原完整运行共 6 次，其中 1 次内部混合通道。混合运行仍只计一次完整20题验收；以下是答卷层样本数，覆盖运行数不能跨路由相加成新实验。

| 路由 | 版本 | 题组 | 有效答卷次数 | 不同题号数 | 全对 / 有效答卷 | 失败项 / 适用项 | 覆盖原运行数 |
|---|---|---|---:|---:|---|---|---:|
| R1 | plain | x 同规则 | 20 | 10 | 12/20 | 12/80 | 2 |
| R1 | plain | y 新规则 | 14 | 10 | 9/14 | 14/56 | 2 |
| R2 | plain | y 新规则 | 6 | 6 | 5/6 | 3/24 | 1 |
| R1 | v0 | x 同规则 | 10 | 10 | 7/10 | 4/40 | 1 |
| R1 | v0 | y 新规则 | 10 | 10 | 6/10 | 7/40 | 1 |
| R1 | trained | x 同规则 | 30 | 10 | 18/30 | 30/120 | 3 |
| R1 | trained | y 新规则 | 30 | 10 | 20/30 | 24/120 | 3 |

混合运行的答卷构成（不增加完整运行次数）：

- plain [accept-plain-1011-212700-dca256619d.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-review/accept-plain-1011-212700-dca256619d.json)：R1=14题、R2=6题。

<a id="evidence-contract-sheet"></a>
### 8.2 采购合同风险清单

训练：当前日志以训练完成结束，末次考试revision与当前deployment一致；[run.out](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-sheet/run.out)。
导出：导出payload与当前deployment一致，ACP入口已启用；[harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-contract-sheet/harness.json)；[deployment](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/contract-sheet/runs/live-20261011193431-d8ab30/deployment.json)。
完整revision：`0f2eaf8f25a48dc634b866a9f0b667f82dc07bf8d4e1829a9753b9b3c1511b4f`。
用户确认验收：现在就当做全都通过验收了；时间 2026-10-12T03:02:03.061562+00:00；[确认记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/control/contract-sheet.json)。
[v0与训练后策略正文对照](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/learned-artifacts-20261011.md#contract-sheet)。
员工通道：**混合通道**（以当前完整有效报告中的答卷为准）。
本专家进入额度事故恢复：3 次运行的 11 道派活纳入重做清单；全批共 109 道。清单不按分数选择，原答卷与模型判定留档，正常条目保持不变。见[执行记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/quota-recovery-executed.json)。
恢复后的后续派活改经兼容适配器与排队网关。原通道为 OpenRouter / z-ai/glm-5.3-flash；新通道为 custom gateway / glm-5.3-flash，客户端仍使用 z-ai/glm-5.3-flash 别名。只验证了相同宣称模型名及SSE/工具协议，未独立验证两个provider等价。因此本专家的版本比较是描述性结果，不能把通道变化后的差异归为纯训练因果增益。
主表合并结果只作描述；不同provider或通道未明时，不能当作同条件训练对照。下方按路由分层仍是不同题号/运行构成的观察子样本，不单独证明因果增益。

- 原版：已保存 2 份有效完整报告；排除 0 份。
  - [有效 1 · accept-plain-1011-205857-f8f329e07a.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-sheet/accept-plain-1011-205857-f8f329e07a.json)
  - [有效 2 · accept-plain-1011-212120-dca256619d.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-sheet/accept-plain-1011-212120-dca256619d.json)
- 初始配置：已保存 2 份有效完整报告；排除 0 份。
  - [有效 1 · accept-v0-1011-205857-ea213aec97.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-sheet/accept-v0-1011-205857-ea213aec97.json)
  - [有效 2 · accept-v0-1011-212409-7602e6ce8b.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-sheet/accept-v0-1011-212409-7602e6ce8b.json)
- 训练后：已保存 2 份有效完整报告；排除 0 份。
  - [有效 1 · accept-0f2eaf8f25a4-1011-205153-d4a6cd4bc9.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-sheet/accept-0f2eaf8f25a4-1011-205153-d4a6cd4bc9.json)
  - [有效 2 · accept-0f2eaf8f25a4-1011-212517-7bd1a34afa.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-sheet/accept-0f2eaf8f25a4-1011-212517-7bd1a34afa.json)

员工路由分层（与判卷模型无关）：

缺少 transport 字段的旧正常答卷依据实验历史归为 legacy OpenRouter；显式但不完整的元数据归为未记录。不根据当前默认provider反推历史。

- R1：provider=`OpenRouter`；model=`z-ai/glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 114 次（其中 114 次无逐行通道字段，按旧记录归组）。
- R2：provider=`custom gateway`；model=`glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 6 次（其中 0 次无逐行通道字段，按旧记录归组）。

原完整运行共 6 次，其中 2 次内部混合通道。混合运行仍只计一次完整20题验收；以下是答卷层样本数，覆盖运行数不能跨路由相加成新实验。

| 路由 | 版本 | 题组 | 有效答卷次数 | 不同题号数 | 全对 / 有效答卷 | 失败项 / 适用项 | 覆盖原运行数 |
|---|---|---|---:|---:|---|---|---:|
| R1 | plain | x 同规则 | 20 | 10 | 12/20 | 9/100 | 2 |
| R1 | plain | y 新规则 | 20 | 10 | 12/20 | 9/100 | 2 |
| R1 | v0 | x 同规则 | 20 | 10 | 15/20 | 5/100 | 2 |
| R1 | v0 | y 新规则 | 18 | 10 | 8/18 | 11/90 | 2 |
| R2 | v0 | y 新规则 | 2 | 2 | 0/2 | 4/9 | 1 |
| R1 | trained | x 同规则 | 20 | 10 | 14/20 | 8/100 | 2 |
| R1 | trained | y 新规则 | 16 | 10 | 7/16 | 10/80 | 2 |
| R2 | trained | y 新规则 | 4 | 4 | 2/4 | 2/20 | 1 |

混合运行的答卷构成（不增加完整运行次数）：

- v0 [accept-v0-1011-212409-7602e6ce8b.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-sheet/accept-v0-1011-212409-7602e6ce8b.json)：R1=18题、R2=2题。
- trained [accept-0f2eaf8f25a4-1011-212517-7bd1a34afa.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-sheet/accept-0f2eaf8f25a4-1011-212517-7bd1a34afa.json)：R1=16题、R2=4题。

<a id="evidence-landing-page"></a>
### 9.1 品牌落地页

训练：当前日志以训练完成结束，末次考试revision与当前deployment一致；[run.out](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/landing-page/run.out)。
导出：导出payload与当前deployment一致，ACP入口已启用；[harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-landing-page/harness.json)；[deployment](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/landing-page/runs/live-20261011193431-036e91/deployment.json)。
完整revision：`d1d627d32b2699c768c45a8edc4f4cbd6f0d877eb9e290f7f2cbf1386354fb73`。
用户确认验收：现在就当做全都通过验收了；时间 2026-10-12T03:02:03.061562+00:00；[确认记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/control/landing-page.json)。
[v0与训练后策略正文对照](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/learned-artifacts-20261011.md#landing-page)。
员工通道：**混合通道**（以当前完整有效报告中的答卷为准）。
本专家进入额度事故恢复：4 次运行的 14 道派活纳入重做清单；全批共 109 道。清单不按分数选择，原答卷与模型判定留档，正常条目保持不变。见[执行记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/quota-recovery-executed.json)。
恢复后的后续派活改经兼容适配器与排队网关。原通道为 OpenRouter / z-ai/glm-5.3-flash；新通道为 custom gateway / glm-5.3-flash，客户端仍使用 z-ai/glm-5.3-flash 别名。只验证了相同宣称模型名及SSE/工具协议，未独立验证两个provider等价。因此本专家的版本比较是描述性结果，不能把通道变化后的差异归为纯训练因果增益。
主表合并结果只作描述；不同provider或通道未明时，不能当作同条件训练对照。下方按路由分层仍是不同题号/运行构成的观察子样本，不单独证明因果增益。

- 原版：已保存 2 份有效完整报告；排除 0 份。
  - [有效 1 · accept-plain-1011-211522-f8f329e07a.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/landing-page/accept-plain-1011-211522-f8f329e07a.json)
  - [有效 2 · accept-plain-1011-213716-dca256619d.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/landing-page/accept-plain-1011-213716-dca256619d.json)
- 初始配置：已保存 1 份有效完整报告；排除 0 份。
  - [有效 1 · accept-v0-1011-211522-ea213aec97.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/landing-page/accept-v0-1011-211522-ea213aec97.json)
- 训练后：已保存 2 份有效完整报告；排除 0 份。
  - [有效 1 · accept-d1d627d32b26-1011-204356-ffb2f7329c.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/landing-page/accept-d1d627d32b26-1011-204356-ffb2f7329c.json)
  - [有效 2 · accept-d1d627d32b26-1011-211414-2c687feb68.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/landing-page/accept-d1d627d32b26-1011-211414-2c687feb68.json)

员工路由分层（与判卷模型无关）：

缺少 transport 字段的旧正常答卷依据实验历史归为 legacy OpenRouter；显式但不完整的元数据归为未记录。不根据当前默认provider反推历史。

- R1：provider=`OpenRouter`；model=`z-ai/glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 84 次（其中 84 次无逐行通道字段，按旧记录归组）。
- R2：provider=`custom gateway`；model=`glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 16 次（其中 0 次无逐行通道字段，按旧记录归组）。

原完整运行共 5 次，其中 2 次内部混合通道。混合运行仍只计一次完整20题验收；以下是答卷层样本数，覆盖运行数不能跨路由相加成新实验。

| 路由 | 版本 | 题组 | 有效答卷次数 | 不同题号数 | 全对 / 有效答卷 | 失败项 / 适用项 | 覆盖原运行数 |
|---|---|---|---:|---:|---|---|---:|
| R1 | plain | x 同规则 | 16 | 10 | 3/16 | 14/80 | 2 |
| R1 | plain | y 新规则 | 10 | 10 | 1/10 | 11/50 | 1 |
| R2 | plain | x 同规则 | 4 | 4 | 2/4 | 2/16 | 1 |
| R2 | plain | y 新规则 | 10 | 10 | 2/10 | 11/38 | 1 |
| R1 | v0 | x 同规则 | 10 | 10 | 1/10 | 11/50 | 1 |
| R1 | v0 | y 新规则 | 8 | 8 | 1/8 | 10/40 | 1 |
| R2 | v0 | y 新规则 | 2 | 2 | 1/2 | 3/10 | 1 |
| R1 | trained | x 同规则 | 20 | 10 | 11/20 | 11/100 | 2 |
| R1 | trained | y 新规则 | 20 | 10 | 18/20 | 3/100 | 2 |

混合运行的答卷构成（不增加完整运行次数）：

- plain [accept-plain-1011-213716-dca256619d.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/landing-page/accept-plain-1011-213716-dca256619d.json)：R1=6题、R2=14题。
- v0 [accept-v0-1011-211522-ea213aec97.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/landing-page/accept-v0-1011-211522-ea213aec97.json)：R1=18题、R2=2题。

<a id="evidence-booking-page"></a>
### 9.2 预约交互页面

训练：当前日志以训练完成结束，末次考试revision与当前deployment一致；[run.out](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/booking-page/run.out)。
导出：导出payload与当前deployment一致，ACP入口已启用；[harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-booking-page/harness.json)；[deployment](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/booking-page/runs/live-20261011193431-2c14a0/deployment.json)。
完整revision：`8f4bd586e294e7cd57c6f56d09427c1a4af1cf4fe1d0f58e7ccfbf81439bed96`。
用户确认验收：现在就当做全都通过验收了；时间 2026-10-12T03:02:03.061562+00:00；[确认记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/control/booking-page.json)。
[v0与训练后策略正文对照](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/learned-artifacts-20261011.md#booking-page)。
员工通道：**混合通道**（以当前完整有效报告中的答卷为准）。
本专家进入额度事故恢复：4 次运行的 15 道派活纳入重做清单；全批共 109 道。清单不按分数选择，原答卷与模型判定留档，正常条目保持不变。见[执行记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/quota-recovery-executed.json)。
恢复后的后续派活改经兼容适配器与排队网关。原通道为 OpenRouter / z-ai/glm-5.3-flash；新通道为 custom gateway / glm-5.3-flash，客户端仍使用 z-ai/glm-5.3-flash 别名。只验证了相同宣称模型名及SSE/工具协议，未独立验证两个provider等价。因此本专家的版本比较是描述性结果，不能把通道变化后的差异归为纯训练因果增益。
主表合并结果只作描述；不同provider或通道未明时，不能当作同条件训练对照。下方按路由分层仍是不同题号/运行构成的观察子样本，不单独证明因果增益。

- 原版：已保存 1 份有效完整报告；排除 0 份。
  - [有效 1 · accept-plain-1011-212811-f8f329e07a.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/booking-page/accept-plain-1011-212811-f8f329e07a.json)
- 初始配置：已保存 0 份有效完整报告；排除 0 份。
- 训练后：已保存 0 份有效完整报告；排除 0 份。

员工路由分层（与判卷模型无关）：

缺少 transport 字段的旧正常答卷依据实验历史归为 legacy OpenRouter；显式但不完整的元数据归为未记录。不根据当前默认provider反推历史。

- R1：provider=`OpenRouter`；model=`z-ai/glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 17 次（其中 17 次无逐行通道字段，按旧记录归组）。
- R2：provider=`custom gateway`；model=`glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 3 次（其中 0 次无逐行通道字段，按旧记录归组）。

原完整运行共 1 次，其中 1 次内部混合通道。混合运行仍只计一次完整20题验收；以下是答卷层样本数，覆盖运行数不能跨路由相加成新实验。

| 路由 | 版本 | 题组 | 有效答卷次数 | 不同题号数 | 全对 / 有效答卷 | 失败项 / 适用项 | 覆盖原运行数 |
|---|---|---|---:|---:|---|---|---:|
| R1 | plain | x 同规则 | 10 | 10 | 9/10 | 1/50 | 1 |
| R1 | plain | y 新规则 | 7 | 7 | 4/7 | 3/35 | 1 |
| R2 | plain | y 新规则 | 3 | 3 | 0/3 | 3/11 | 1 |

混合运行的答卷构成（不增加完整运行次数）：

- plain [accept-plain-1011-212811-f8f329e07a.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/booking-page/accept-plain-1011-212811-f8f329e07a.json)：R1=17题、R2=3题。

<a id="evidence-call-debrief"></a>
### 10.1 销售通话复盘

训练：当前日志以训练完成结束，末次考试revision与当前deployment一致；[run.out](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/run.out)。
导出：导出payload与当前deployment一致，ACP入口已启用；[harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-call-debrief/harness.json)；[deployment](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/call-debrief/runs/live-20261011160338-48a052/deployment.json)。
完整revision：`483e4e1633b13b448b16ffd2194ec85edc2b9c48e4055326af165cc56a02e078`。
用户确认验收：现在就当做全都通过验收了；时间 2026-10-12T03:02:03.061562+00:00；[确认记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/control/call-debrief.json)。
[v0与训练后策略正文对照](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/learned-artifacts-20261011.md#call-debrief)。
员工通道：**纯旧通道（OpenRouter）**（以当前完整有效报告中的答卷为准）。
本专家未列入这次109题恢复清单，保留既有旧通道验收；没有因事故重跑。

- 原版：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-plain-1011-200027-f8f329e07a.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-plain-1011-200027-f8f329e07a.json)
  - [有效 2 · accept-plain-1011-201304-dca256619d.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-plain-1011-201304-dca256619d.json)
  - [有效 3 · accept-plain-1011-202508-f6875bff2f.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-plain-1011-202508-f6875bff2f.json)
- 初始配置：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-v0-1011-204026-ea213aec97.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-v0-1011-204026-ea213aec97.json)
  - [有效 2 · accept-v0-1011-205156-7602e6ce8b.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-v0-1011-205156-7602e6ce8b.json)
  - [有效 3 · accept-v0-1011-210144-a7938bb60e.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-v0-1011-210144-a7938bb60e.json)
- 训练后：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-483e4e1633b1-1011-193059-ce20ddb647.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-483e4e1633b1-1011-193059-ce20ddb647.json)
  - [有效 2 · accept-483e4e1633b1-1011-194011-1a9190f826.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-483e4e1633b1-1011-194011-1a9190f826.json)
  - [有效 3 · accept-483e4e1633b1-1011-195155-72e6b263f0.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-483e4e1633b1-1011-195155-72e6b263f0.json)

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
| R1 | trained | x 同规则 | 30 | 10 | 20/30 | 11/150 | 3 |
| R1 | trained | y 新规则 | 30 | 10 | 17/30 | 14/150 | 3 |

<a id="evidence-discovery-coach"></a>
### 10.2 需求追问清单

训练：当前日志以训练完成结束，末次考试revision与当前deployment一致；[run.out](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/discovery-coach/run.out)。
导出：导出payload与当前deployment一致，ACP入口已启用；[harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-discovery-coach/harness.json)；[deployment](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/discovery-coach/runs/live-20261011160722-9dae58/deployment.json)。
完整revision：`3c458a40c006f74c02e50b5fbf478408a4ec8ed00602a5d7bf2de9e67c2c25ef`。
用户确认验收：现在就当做全都通过验收了；时间 2026-10-12T03:02:03.061562+00:00；[确认记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/control/discovery-coach.json)。
[v0与训练后策略正文对照](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/learned-artifacts-20261011.md#discovery-coach)。
员工通道：**混合通道**（以当前完整有效报告中的答卷为准）。
本专家进入额度事故恢复：1 次运行的 4 道派活纳入重做清单；全批共 109 道。清单不按分数选择，原答卷与模型判定留档，正常条目保持不变。见[执行记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/quota-recovery-executed.json)。
恢复后的后续派活改经兼容适配器与排队网关。原通道为 OpenRouter / z-ai/glm-5.3-flash；新通道为 custom gateway / glm-5.3-flash，客户端仍使用 z-ai/glm-5.3-flash 别名。只验证了相同宣称模型名及SSE/工具协议，未独立验证两个provider等价。因此本专家的版本比较是描述性结果，不能把通道变化后的差异归为纯训练因果增益。
主表合并结果只作描述；不同provider或通道未明时，不能当作同条件训练对照。下方按路由分层仍是不同题号/运行构成的观察子样本，不单独证明因果增益。

- 原版：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-plain-1011-201449-f8f329e07a.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/discovery-coach/accept-plain-1011-201449-f8f329e07a.json)
  - [有效 2 · accept-plain-1011-203517-dca256619d.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/discovery-coach/accept-plain-1011-203517-dca256619d.json)
  - [有效 3 · accept-plain-1011-205152-f6875bff2f.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/discovery-coach/accept-plain-1011-205152-f6875bff2f.json)
- 初始配置：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-v0-1011-210811-ea213aec97.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/discovery-coach/accept-v0-1011-210811-ea213aec97.json)
  - [有效 2 · accept-v0-1011-212551-7602e6ce8b.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/discovery-coach/accept-v0-1011-212551-7602e6ce8b.json)
  - [有效 3 · accept-v0-1011-214059-a7938bb60e.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/discovery-coach/accept-v0-1011-214059-a7938bb60e.json)
- 训练后：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-3c458a40c006-1011-193059-07d1691456.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/discovery-coach/accept-3c458a40c006-1011-193059-07d1691456.json)
  - [有效 2 · accept-3c458a40c006-1011-194650-521f1d8ec4.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/discovery-coach/accept-3c458a40c006-1011-194650-521f1d8ec4.json)
  - [有效 3 · accept-3c458a40c006-1011-195855-3778445461.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/discovery-coach/accept-3c458a40c006-1011-195855-3778445461.json)

员工路由分层（与判卷模型无关）：

缺少 transport 字段的旧正常答卷依据实验历史归为 legacy OpenRouter；显式但不完整的元数据归为未记录。不根据当前默认provider反推历史。

- R1：provider=`OpenRouter`；model=`z-ai/glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 163 次（其中 163 次无逐行通道字段，按旧记录归组）。
- R2：provider=`custom gateway`；model=`glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 17 次（其中 0 次无逐行通道字段，按旧记录归组）。

原完整运行共 9 次，其中 1 次内部混合通道。混合运行仍只计一次完整20题验收；以下是答卷层样本数，覆盖运行数不能跨路由相加成新实验。

| 路由 | 版本 | 题组 | 有效答卷次数 | 不同题号数 | 全对 / 有效答卷 | 失败项 / 适用项 | 覆盖原运行数 |
|---|---|---|---:|---:|---|---|---:|
| R1 | plain | x 同规则 | 30 | 10 | 15/30 | 17/150 | 3 |
| R1 | plain | y 新规则 | 30 | 10 | 13/30 | 22/150 | 3 |
| R1 | v0 | x 同规则 | 23 | 10 | 17/23 | 8/115 | 3 |
| R1 | v0 | y 新规则 | 20 | 10 | 6/20 | 19/100 | 2 |
| R2 | v0 | x 同规则 | 7 | 7 | 5/7 | 4/35 | 1 |
| R2 | v0 | y 新规则 | 10 | 10 | 6/10 | 4/50 | 1 |
| R1 | trained | x 同规则 | 30 | 10 | 27/30 | 3/150 | 3 |
| R1 | trained | y 新规则 | 30 | 10 | 20/30 | 15/150 | 3 |

混合运行的答卷构成（不增加完整运行次数）：

- v0 [accept-v0-1011-214059-a7938bb60e.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/discovery-coach/accept-v0-1011-214059-a7938bb60e.json)：R1=3题、R2=17题。

<a id="evidence-compete-table"></a>
### 11.1 竞品对比表

训练：当前日志以训练完成结束，末次考试revision与当前deployment一致；[run.out](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/run.out)。
导出：导出payload与当前deployment一致，ACP入口已启用；[harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-compete-table/harness.json)；[deployment](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/compete-table/runs/live-20261011132451-42b3d5/deployment.json)。
完整revision：`0150fa86cde9f76b036450fa70805618763e99bd4c3b4240f5b540542b282b5d`。
用户确认验收：现在就当做全都通过验收了；时间 2026-10-12T03:02:03.061562+00:00；[确认记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/control/compete-table.json)。
[v0与训练后策略正文对照](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/learned-artifacts-20261011.md#compete-table)。
员工通道：**纯旧通道（OpenRouter）**（以当前完整有效报告中的答卷为准）。
本专家未列入这次109题恢复清单，保留既有旧通道验收；没有因事故重跑。

- 原版：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-plain-1011-154248.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-plain-1011-154248.json)
  - [有效 2 · accept-plain-1011-160901.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-plain-1011-160901.json)
  - [有效 3 · accept-plain-1011-163249.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-plain-1011-163249.json)
- 初始配置：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-v0-1011-155054.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-v0-1011-155054.json)
  - [有效 2 · accept-v0-1011-162418.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-v0-1011-162418.json)
  - [有效 3 · accept-v0-1011-164759.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-v0-1011-164759.json)
- 训练后：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-0150fa86cde9-1011-152100.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-0150fa86cde9-1011-152100.json)
  - [有效 2 · accept-0150fa86cde9-1011-161604.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-0150fa86cde9-1011-161604.json)
  - [有效 3 · accept-0150fa86cde9-1011-163919.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-0150fa86cde9-1011-163919.json)

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
| R1 | trained | x 同规则 | 30 | 10 | 25/30 | 5/150 | 3 |
| R1 | trained | y 新规则 | 30 | 10 | 21/30 | 14/150 | 3 |

<a id="evidence-review-digest"></a>
### 11.2 评价周报

训练：当前日志以训练完成结束，末次考试revision与当前deployment一致；[run.out](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/review-digest/run.out)。
导出：导出payload与当前deployment一致，ACP入口已启用；[harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-review-digest/harness.json)；[deployment](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/review-digest/runs/live-20261011152930-9869d9/deployment.json)。
完整revision：`a7c5b576db31ebae1eee2975bc18a9f58cba679636d807ec8a10fc957f5d26c3`。
用户确认验收：现在就当做全都通过验收了；时间 2026-10-12T03:02:03.061562+00:00；[确认记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/control/review-digest.json)。
[v0与训练后策略正文对照](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/learned-artifacts-20261011.md#review-digest)。
员工通道：**混合通道**（以当前完整有效报告中的答卷为准）。
本专家进入额度事故恢复：2 次运行的 2 道派活纳入重做清单；全批共 109 道。清单不按分数选择，原答卷与模型判定留档，正常条目保持不变。见[执行记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/quota-recovery-executed.json)。
恢复后的后续派活改经兼容适配器与排队网关。原通道为 OpenRouter / z-ai/glm-5.3-flash；新通道为 custom gateway / glm-5.3-flash，客户端仍使用 z-ai/glm-5.3-flash 别名。只验证了相同宣称模型名及SSE/工具协议，未独立验证两个provider等价。因此本专家的版本比较是描述性结果，不能把通道变化后的差异归为纯训练因果增益。
主表合并结果只作描述；不同provider或通道未明时，不能当作同条件训练对照。下方按路由分层仍是不同题号/运行构成的观察子样本，不单独证明因果增益。

- 原版：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-plain-1011-201109-f8f329e07a.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/review-digest/accept-plain-1011-201109-f8f329e07a.json)
  - [有效 2 · accept-plain-1011-203123-dca256619d.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/review-digest/accept-plain-1011-203123-dca256619d.json)
  - [有效 3 · accept-plain-1011-204913-f6875bff2f.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/review-digest/accept-plain-1011-204913-f6875bff2f.json)
- 初始配置：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-v0-1011-210651-ea213aec97.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/review-digest/accept-v0-1011-210651-ea213aec97.json)
  - [有效 2 · accept-v0-1011-212800-7602e6ce8b.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/review-digest/accept-v0-1011-212800-7602e6ce8b.json)
  - [有效 3 · accept-v0-1011-214524-a7938bb60e.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/review-digest/accept-v0-1011-214524-a7938bb60e.json)
- 训练后：已保存 3 份有效完整报告；排除 0 份。
  - [有效 1 · accept-a7c5b576db31-1011-193059-c91d5340c1.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/review-digest/accept-a7c5b576db31-1011-193059-c91d5340c1.json)
  - [有效 2 · accept-a7c5b576db31-1011-194312-f4b5de3d70.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/review-digest/accept-a7c5b576db31-1011-194312-f4b5de3d70.json)
  - [有效 3 · accept-a7c5b576db31-1011-195700-840e70dbd3.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/review-digest/accept-a7c5b576db31-1011-195700-840e70dbd3.json)

员工路由分层（与判卷模型无关）：

缺少 transport 字段的旧正常答卷依据实验历史归为 legacy OpenRouter；显式但不完整的元数据归为未记录。不根据当前默认provider反推历史。

- R1：provider=`OpenRouter`；model=`z-ai/glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 159 次（其中 159 次无逐行通道字段，按旧记录归组）。
- R2：provider=`custom gateway`；model=`glm-5.3-flash`；client_alias=`z-ai/glm-5.3-flash`；有效答卷 21 次（其中 0 次无逐行通道字段，按旧记录归组）。

原完整运行共 9 次，其中 1 次内部混合通道。混合运行仍只计一次完整20题验收；以下是答卷层样本数，覆盖运行数不能跨路由相加成新实验。

| 路由 | 版本 | 题组 | 有效答卷次数 | 不同题号数 | 全对 / 有效答卷 | 失败项 / 适用项 | 覆盖原运行数 |
|---|---|---|---:|---:|---|---|---:|
| R1 | plain | x 同规则 | 30 | 10 | 0/30 | 48/120 | 3 |
| R1 | plain | y 新规则 | 30 | 10 | 0/30 | 58/120 | 3 |
| R1 | v0 | x 同规则 | 20 | 10 | 0/20 | 27/80 | 2 |
| R1 | v0 | y 新规则 | 19 | 10 | 0/19 | 40/76 | 2 |
| R2 | v0 | y 新规则 | 11 | 10 | 5/11 | 17/44 | 2 |
| R2 | v0 | x 同规则 | 10 | 10 | 5/10 | 8/40 | 1 |
| R1 | trained | x 同规则 | 30 | 10 | 20/30 | 10/120 | 3 |
| R1 | trained | y 新规则 | 30 | 10 | 16/30 | 19/120 | 3 |

混合运行的答卷构成（不增加完整运行次数）：

- v0 [accept-v0-1011-212800-7602e6ce8b.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/review-digest/accept-v0-1011-212800-7602e6ce8b.json)：R1=19题、R2=1题。
