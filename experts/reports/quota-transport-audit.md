# 额度与传输故障：验收数据审计

稳定快照：2026-10-11T21:54:01.734061+00:00。完整机器可读清单见 [quota-transport-audit.json](./quota-transport-audit.json)。本审计只读扫描，没有修改答卷、模型判定、题库、harness或运行状态，也没有调用模型。

## 结论

22个专家中，**13个专家的29次验收运行有基础设施故障或中断证据，涉及109道派活**。另9个已完成专家没有命中本次故障条件，保留既有成果。109是需要统一恢复的派活次数，不是专家数，也不是规则能力失败数。

- 72题出现精确的协议错误消息，被保存为普通答案，原 `error` 全部为 null：30题是上游key/额度上限，42题是本地实验费用上限。
- 20题已经保存显式ACP timeout等传输错误；单列基础设施失败，不能仅凭发生时间归因于上游403。
- 17题在终止时仍为 `dispatching`，没有落盘的完成答卷；单列中断派活，不能当作全对或规则失败。
- 这些条目当时为86题 scored、6题 judging、17题 dispatching。是否重做完全依据传输证据/检查点状态，不依据已判分数。
- 6份已经发布的完整报告受到污染（12题精确额度错误、2题显式timeout），其余被列条目仍在partial中。4份污染报告能通过当时的结构校验，因为字段齐全且 `error=null`；另外2份本已因显式timeout被排除。

扫描范围为149份 `cases/*/accept-*.json` 与133份 `cases/*/accept-runs/*/partial.json`；排除superseded和子集诊断。各文件按路径/大小/mtime_ns/SHA-256登记；扫描结束再次核对时没有文件变化。相同派活在final和partial中的重复记录按 case/run/question合并，不重复计数。

## 终止与错误识别

主线程报告的上游故障开始时间为2026-10-11 21:42:45 UTC。本次读取的[控制记录](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/control/suspensions/openrouter-limit.json)显示尝试SIGSTOP于2026-10-11T21:46:07.656982+00:00，随后终端作业控制使暂停不稳定，限定实验进程树于2026-10-11T21:51:28.533297+00:00终止；应采用这份记录的精确时间，不能把最初暂停当成稳定快照。

精确额度判定仅检查真实回复字段：`answer/result/collected` 的 reply/product 首个非空行，或 full_reply 的最后一个非空行；发布报告使用同样规则。要求行首为完整运行时前缀 `turn_failed APIError: litellm.APIError: APIError: OpenrouterException -`，且同一行含明确quota/key限额、精确的 `Experiment cost ceiling reached`，或HTTP402/403。全文普通提到HTTP错误、题面、评审理由和附件内容不用于触发。full_reply允许错误前存在进度文字。

在这些已知响应中，首行错误后即使附有已生成的HTML/Word，也仍属于这次派活被基础设施中断，不能因为残留文件拿到高分便例外保留。检测器以7个离线断言验证正例、402分支和普通任务谈错误/引用/附件的排除；没有调用API。

## 已发布、应暂停纳入能力统计的报告

| 专家/版本 | 完整报告 | 精确额度题 | 显式传输错误题 | 原结构校验会纳入？ |
|---|---|---|---|---|
| 预约交互页面 / plain | [accept-plain-1011-212811-f8f329e07a.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/booking-page/accept-plain-1011-212811-f8f329e07a.json) | y08、y09、y10 | — | 会 |
| 采购合同风险清单 / trained | [accept-0f2eaf8f25a4-1011-212517-7bd1a34afa.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-sheet/accept-0f2eaf8f25a4-1011-212517-7bd1a34afa.json) | y07、y08、y09 | y10 | 不会，已识别显式error |
| 采购合同风险清单 / v0 | [accept-v0-1011-212409-7602e6ce8b.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-sheet/accept-v0-1011-212409-7602e6ce8b.json) | y09 | y10 | 不会，已识别显式error |
| 品牌落地页 / v0 | [accept-v0-1011-211522-ea213aec97.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/landing-page/accept-v0-1011-211522-ea213aec97.json) | y09、y10 | — | 会 |
| 评价周报 / v0 | [accept-v0-1011-212800-7602e6ce8b.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/review-digest/accept-v0-1011-212800-7602e6ce8b.json) | y10 | — | 会 |
| SaaS 指标取数 / v0 | [accept-v0-1011-213040-a7938bb60e.json](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/saas-metric/accept-v0-1011-213040-a7938bb60e.json) | y09、y10 | — | 会 |

原始答卷及模型criteria判定应完整保留为事故证据。移出统计范围是把基础设施失败与能力评估分开，不是把模型的fail改成pass。

## 对“已完成专家”的影响

- 原来稳定完成且本次没有命中故障的9个：退款客服、投诉处理、海报审查、门店客单价、竞品表、医疗推文审查、会议待办、销售通话复盘、电商标题。门店是各版本1次，其余8个是各版本3次；这些成果无需重训或重跑。
- SaaS指标取数在 `10-11 21:46:22` 的流水日志写了complete，但v0第3次的y09/y10实际是费用/额度故障消息。剔除这份报告后是plain/v0/trained=3/2/3，必须恢复验收，不能保留“3次都完成”。
- 落地页原有唯一v0完整报告含y09/y10错误，剔除后plain/v0/trained=1/0/2；连“每版本至少1次齐全”都应撤回。评价周报的v0也从2次降为1次。
- 运营周报本次v0第3次仍有y08额度错误、y09显式timeout、y10中断派活，未形成新完整报告；不能把它和SaaS一起称为已完成。采购合同的两个含timeout报告本已不合格，仍须把其中精确quota问题一并纳入恢复。

若采用“每版本至少1份有效报告”的最低对照口径，此快照从19个降到18个；若采用“每版本3份”的口径，从9个降到8个。业务上已完成的9个稳定旧专家包含门店的1次对照，不能拿上述3次口径的8个来覆盖它的历史完成状态。

| 受影响专家 | 有问题run数 | 精确额度题 | 显式传输题 | 未决dispatch题 | 已发布污染报告 | 剔除后有效P/V/T次数 |
|---|---:|---:|---:|---:|---:|---|
| 亚马逊英文 Listing | 3 | 13 | 3 | 0 | 0 | 1/1/1 |
| 预约交互页面 | 4 | 12 | 2 | 1 | 1 | 0/0/0 |
| 咖啡新品文案 | 1 | 0 | 0 | 1 | 0 | 3/0/3 |
| 合同留痕审稿 | 2 | 4 | 2 | 2 | 0 | 1/1/3 |
| 采购合同风险清单 | 3 | 7 | 3 | 1 | 2 | 2/1/1 |
| 需求追问清单 | 1 | 3 | 1 | 0 | 0 | 3/2/3 |
| 品牌落地页 | 4 | 9 | 2 | 3 | 1 | 1/0/2 |
| 简历优化 | 1 | 1 | 0 | 1 | 0 | 3/0/3 |
| 简历初筛 | 3 | 11 | 3 | 3 | 0 | 1/2/2 |
| 评价周报 | 2 | 1 | 0 | 1 | 1 | 3/1/3 |
| SaaS 指标取数 | 1 | 2 | 0 | 0 | 1 | 3/2/3 |
| 运营周报 | 1 | 1 | 1 | 1 | 0 | 3/2/3 |
| 小红书种草笔记 | 3 | 8 | 3 | 3 | 0 | 2/2/1 |

## 按同一条件恢复的完整清单

下表每题附保存时stage。Q=精确额度/费用上限协议消息；E=已有显式传输error；I=终止时未决派活。每个run的checkpoint链接包含原答卷、模型判定和事件；JSON另列每条匹配字段、完整错误首行、发布路径及事件时间。

| 专家 / run | 已发布 | Q：精确额度题(stage) | E：传输题(stage) | I：中断题(stage) |
|---|---|---|---|---|
| amazon-listing<br>[parallel-v1-a6acd033c4b6-2](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/amazon-listing/accept-runs/parallel-v1-a6acd033c4b6-2/partial.json) | 否 | x07(scored)、x08(scored)、x09(scored)、y01(judging) | x10(scored) | — |
| amazon-listing<br>[parallel-v1-plain-2](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/amazon-listing/accept-runs/parallel-v1-plain-2/partial.json) | 否 | y03(scored)、y04(scored)、y05(scored)、y07(judging) | y06(scored) | — |
| amazon-listing<br>[parallel-v1-v0-2](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/amazon-listing/accept-runs/parallel-v1-v0-2/partial.json) | 否 | y02(scored)、y03(scored)、y04(scored)、y05(scored)、y07(judging) | y06(scored) | — |
| booking-page<br>[parallel-v1-8f4bd586e294-1](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/booking-page/accept-runs/parallel-v1-8f4bd586e294-1/partial.json) | 否 | x10(scored)、y01(scored)、y02(scored) | y03(judging) | — |
| booking-page<br>[parallel-v1-plain-1](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/booking-page/accept-runs/parallel-v1-plain-1/partial.json) | 是 | y08(scored)、y09(scored)、y10(scored) | — | — |
| booking-page<br>[parallel-v1-plain-2](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/booking-page/accept-runs/parallel-v1-plain-2/partial.json) | 否 | x01(scored)、x02(scored) | — | x03(dispatching) |
| booking-page<br>[parallel-v1-v0-1](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/booking-page/accept-runs/parallel-v1-v0-1/partial.json) | 否 | x09(scored)、x10(scored)、y01(scored)、y03(judging) | y02(scored) | — |
| cafe-copy<br>[parallel-v1-v0-1](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/cafe-copy/accept-runs/parallel-v1-v0-1/partial.json) | 否 | — | — | y10(dispatching) |
| contract-review<br>[parallel-v1-plain-2](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-review/accept-runs/parallel-v1-plain-2/partial.json) | 否 | y05(scored) | y06(scored) | y07(dispatching) |
| contract-review<br>[parallel-v1-v0-2](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-review/accept-runs/parallel-v1-v0-2/partial.json) | 否 | x10(scored)、y01(scored)、y02(scored) | y03(scored) | y04(dispatching) |
| contract-sheet<br>[parallel-v1-0f2eaf8f25a4-2](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-sheet/accept-runs/parallel-v1-0f2eaf8f25a4-2/partial.json) | 是 | y07(scored)、y08(scored)、y09(scored) | y10(scored) | — |
| contract-sheet<br>[parallel-v1-plain-3](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-sheet/accept-runs/parallel-v1-plain-3/partial.json) | 否 | x02(scored)、x03(scored)、x04(scored) | x05(scored) | x06(dispatching) |
| contract-sheet<br>[parallel-v1-v0-2](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-sheet/accept-runs/parallel-v1-v0-2/partial.json) | 是 | y09(scored) | y10(scored) | — |
| discovery-coach<br>[parallel-v1-v0-3](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/discovery-coach/accept-runs/parallel-v1-v0-3/partial.json) | 否 | x04(scored)、x05(scored)、x06(scored) | x07(judging) | — |
| landing-page<br>[parallel-v1-d1d627d32b26-3](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/landing-page/accept-runs/parallel-v1-d1d627d32b26-3/partial.json) | 否 | x04(scored)、x05(scored)、x06(scored)、x07(scored)、x09(scored) | x08(scored) | x10(dispatching) |
| landing-page<br>[parallel-v1-plain-2](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/landing-page/accept-runs/parallel-v1-plain-2/partial.json) | 否 | x07(scored)、x09(scored) | x08(scored) | x10(dispatching) |
| landing-page<br>[parallel-v1-v0-1](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/landing-page/accept-runs/parallel-v1-v0-1/partial.json) | 是 | y09(scored)、y10(scored) | — | — |
| landing-page<br>[parallel-v1-v0-2](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/landing-page/accept-runs/parallel-v1-v0-2/partial.json) | 否 | — | — | x01(dispatching) |
| resume-rewrite<br>[parallel-v1-v0-1](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-rewrite/accept-runs/parallel-v1-v0-1/partial.json) | 否 | x02(scored) | — | x03(dispatching) |
| resume-screen<br>[parallel-v1-44acc1a36688-3](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-screen/accept-runs/parallel-v1-44acc1a36688-3/partial.json) | 否 | x09(scored)、x10(scored)、y01(scored)、y03(scored) | y02(scored) | y04(dispatching) |
| resume-screen<br>[parallel-v1-plain-2](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-screen/accept-runs/parallel-v1-plain-2/partial.json) | 否 | y01(scored)、y02(scored)、y03(scored) | y04(scored) | y05(dispatching) |
| resume-screen<br>[parallel-v1-v0-3](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/resume-screen/accept-runs/parallel-v1-v0-3/partial.json) | 否 | x06(scored)、x07(scored)、x08(scored)、x10(scored) | x09(scored) | y01(dispatching) |
| review-digest<br>[parallel-v1-v0-2](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/review-digest/accept-runs/parallel-v1-v0-2/partial.json) | 是 | y10(scored) | — | — |
| review-digest<br>[parallel-v1-v0-3](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/review-digest/accept-runs/parallel-v1-v0-3/partial.json) | 否 | — | — | x01(dispatching) |
| saas-metric<br>[parallel-v1-v0-3](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/saas-metric/accept-runs/parallel-v1-v0-3/partial.json) | 是 | y09(scored)、y10(scored) | — | — |
| weekly-report<br>[parallel-v1-v0-3](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/weekly-report/accept-runs/parallel-v1-v0-3/partial.json) | 否 | y08(scored) | y09(scored) | y10(dispatching) |
| xhs-note<br>[parallel-v1-f2d14854e9a6-2](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/xhs-note/accept-runs/parallel-v1-f2d14854e9a6-2/partial.json) | 否 | x06(scored)、x07(scored)、x09(scored) | x08(scored) | x10(dispatching) |
| xhs-note<br>[parallel-v1-plain-3](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/xhs-note/accept-runs/parallel-v1-plain-3/partial.json) | 否 | x07(scored)、x08(scored)、x09(scored) | x10(scored) | y01(dispatching) |
| xhs-note<br>[parallel-v1-v0-3](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/xhs-note/accept-runs/parallel-v1-v0-3/partial.json) | 否 | x02(scored)、x03(scored) | x04(scored) | x05(dispatching) |

## 恢复建议与保留边界

1. 对每个受影响run保留完整事故副本，包括partial、streams、judge事件、原final及原始模型verdict；将这6份污染final移到该run的事故目录，使现有glob不再把它们计为能力报告。不要删除原判定或改写分数。
2. 按机器清单中全部109题统一恢复：精确quota、显式transport error、终止时dispatching三种条件均与成绩无关。使用新的ACP会话和workspace；原题库、随题材料、harness、模型alias、judge及计分标准不变，追加route-change、incident与supersedes元数据。不能只挑失败多的题，不能因已有文件或偶然通过就豁免同类故障。
3. 未命中条件且已有正常answered/judging答卷时复用该答卷续判；正常scored保持原文与verdict不变。当前列出的运行没有额外正常答卷停在answered/judging，但恢复逻辑仍应遵循这一边界。尚未派出的题按原序继续。修复前后核对所有未重做条目的摘要，防止恢复过程扩大样本改动。
4. 暂不把含故障的run计为完成；修复后仅当同一原run的20题均完整且有逐项LLM判定时再形成完整报告，并保留事故attempt与恢复attempt的可追溯关联。服务异常统计继续保留，不因为重做成功而消失。
5. 评估备用通道的成功状态与原通道成本分开。上游HTTP403后的本地预算预留被保留，所以账面25/28之类数字不能视为已花费用或剩余真实额度。本审计没有进行账本费用对账，也没有自行调用备用通道；该通道的协议验证由主线程其他任务负责。

