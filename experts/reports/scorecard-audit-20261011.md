# 最终成绩汇总审查（2026-10-11）

这是审查与修复记录，不是最终成绩单。初始只读审查从 19:50 UTC 开始；新专家初始结果固定取 19:30 批次的第一次完整验收，后续复测仍在到达。随后获授权修正成绩汇总代码并补离线测试；没有重跑员工、评审或实验，没有改训练输入、规则或模型判定。

## 结论与完成口径

当时完成 plain / v0 / 培养后三版本宿主对照的仍是 **5 个专家**，不是 14 个或 22 个。新验收的 10 个专家中，9 个已有培养后第一次完整结果；合同留痕审稿仍只有进行中的检查点。新 10 个均尚无完整 plain、v0 验收，因此不能据培养后成绩宣称训练有提升。

“完整专家”应以一个专家的三版本对照齐全计数；训练完成、导出成功、单版本验收完成、三版本对照完成分别报告。已完成的 5 个无需因为总目标为 22 个而重训。重复次数另列：旧 5 个中门店客单价每版本 1 次，其余每版本 3 次；若最终要求统一 3 次，门店仍欠复测，但其三版本对照已经存在。

本次逐项结构复核的旧 39 份和新 9 份初次完整验收，每份均覆盖既定 x01–x10、y01–y10；每道题均有全套 criteria 的模型 verdict，`failed`、`judged` 与保存的 verdict 一致，未发现 dispatch error 或 `loose` 引用异常。这里只验证记录完整性与计算一致性，不以程序替代模型判卷。原始记录见文末源文件索引。

## 汇总修复与验证

已修改 [scorecard.py](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/common/scorecard.py)：严格验证完整 20 题与逐项 LLM verdict；派活 error、证据 unknown 和全不适用报告留在异常表，不进入能力分母；按每次真实分母及合计输出；Studio 从当前 session 的 iteration 按 source/组别分列 pass、fail、unknown、not_applicable；例题固定 x01，并展示题号最先的改善和退步例（若有）及 v0；产物栏改称“导出的策略产物”。

对外可复用纯函数为 `report_issues(rows, questions, criteria) -> list[str]`，空列表才表示完整有效报告；`case_spec(case: Path)` 读取题库和 criteria；`reports_of(case, tag)` 返回 `(admitted, excluded)` 并保留原文件路径；`studio_exams(case)` 返回当前 session 的结构化来源统计；`tally` 保留原四个键，并增加异常计数。

[test_scorecard.py](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/common/test_scorecard.py) 的 10 个离线回归测试全部通过。复现命令：`uv run --no-sync --project Raven-port python -m unittest discover -s experts/common -p test_scorecard.py -v`。覆盖带 hash 命名、部分/重复/缺判定报告排除、错误/unknown/不适用分离、每次分母变化、固定/改善/退步例题、当前 session 来源和 unknown 保留、缓存更新，以及员工通道分层。

后续为减少大型 iteration 文件的重复解析，`studio_exams` 增加最多 64 条路径版本的 LRU 缓存，键为绝对路径、mtime_ns、size；只缓存提取后的计数，不持有完整 JSON。离线验证不变记录不重读、同大小文件时间变化后重读、同时间文件大小变化后重读、session 切换，以及调用者修改返回值不会污染缓存。公开函数签名未变。

额度事故恢复后又增加 `route_summary(reports_by_version)`、`route_context(case, summary)` 与 `route_table(summary)`。每专家先说明完整有效答卷使用纯旧通道、纯新通道、混合通道或尚未记录；按 provider/model/client_alias × 版本 × x/y 分列有效答卷、不同题号数、全对及失败项。混合run仍只计一次完整20题，层内覆盖运行数不能相加成更多实验。没有逐行transport的历史正常答卷归为legacy OpenRouter，不从当前默认设置反推；显式缺损元数据则单列未知。

受[109题恢复执行记录](./quota-recovery-executed.json)影响的13个专家同时说明通道由OpenRouter切到custom gateway，仅模型宣称名称与SSE/工具协议经过验证，provider等价性未独立验证。因此后续三版本比较只作描述，不把通道变化混称为纯训练因果增益；9个既有完成专家保留旧通道结果，不重跑。新增测试验证20题混合运行不被拆成两次完整实验、旧/新/未知元数据分离、不同since时间不人为分路由，以及恢复说明不会给旧答卷贴新通道标签。

另只读运行当前全部 22 个专家的 `card()`，全部成功；扫描时已有的 60 份完整验收报告均通过严格结构校验。旧 5 个专家的三版本全部汇总数值与下表一致，没有重跑或改写旧成绩。SaaS 的 `rounds[1]` 现在明确显示 rules-judge x=2/40、y=2/40，以及 assessor 的 y=1 fail、未定位=1 unknown。

下面保留审查时的实质问题与证据；代码问题描述的是修复前行为，代码链接目前指向已经修复的文件。输入版本身份交叉核验、完整元数据冻结和更完整的最终总表仍是后续建议，本补丁没有改运行中的实验。

## 修复前会实质影响结论的问题

1. **Studio 轨迹混合两类判定，并隐藏 unknown，已经在现有数据中发生。** [scorecard.py](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/common/scorecard.py) 只读取日志里的 `exam=失败/已判`，没有来源、unknown、不适用、题组或轮次元数据。实际 [SaaS iteration](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/saas-metric/runs/live-20261011152837-4591ec/iteration/020e327334c7427c9ea24cb474066d4b.json) 的第二份 holdout（`rounds[1].holdout_signals`）是工作规则 `rules-judge` 的 4 fail / 80，加上通用 `assessor` 的 1 fail、1 unknown；[日志:17](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/saas-metric/run.out:17) 只显示 5/81。分母生成逻辑明确只计 pass/fail，unknown 被排除，见 [session_host.py:597](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/Raven-port/experimental/webui/session_host.py:597)。因此不能把 19/80 → 5/81 当作同一固定指标。最终主表使用宿主固定工作规则 criteria；Studio 附表按 source 分列 pass、fail、unknown、not_applicable，并区分 x/y。

2. **并排例题只挑最好看的改善，已经遗漏真实回退。** [pair()（修复前）](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/common/scorecard.py) 只选 plain 挂项最多且培养后零挂项的题，并且 [card()（修复前）](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/common/scorecard.py) 只用双方第一次验收、不展示 v0。竞品表首轮实际还有 x10 从 plain 全过变为培养后 C-layout 失败（[plain](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-plain-1011-154248.json)、[培养后](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/compete-table/accept-0150fa86cde9-1011-152100.json)），当前函数只展示改善的 y03。建议完整提供 20 题三版本浏览；正文例题明确标“最大改善示例”，同时列最大回退或无改善示例，展示各次判定，不能用一个示例概括总效果。

3. **dispatch error 与模型性能没有分栏。** [tally()（修复前）](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/common/scorecard.py) 会把错误题算入整题全对分母，也会累计这些题的挂项；表格却不显示错误数。新 [accept.py:276](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/common/accept.py:276) 正确保留派活异常，并交模型评审实际收到的产出，这不能被解释为规则能力下降。建议保留全部派活记录，另列派活成功/总数及错误类型；性能汇总只对完整收到且完成模型评审的答卷计算，缺失单列 unknown。可以另外给“端到端全对/总派活”，但必须明确它包括服务可用性。现已核验的完整结果没有此类错误，这一项是后续汇总必须防住的问题。

4. **空判定会被当作全对，缺少汇总端完整性校验。** `tally` 仅判断 `failed=[]`、`error` 为空；纯内存调用 `tally([{"group":"same","failed":[],"judged":[],"verdicts":[],"error":null}])` 的 `same_ok` 是 `[1,1]`。`pair` 甚至不检查 error，故 `failed=[]` 的派活错误行也能成为“培养后全过”示例。新发布端 [accept.py:181](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/common/accept.py:181) 已逐项检查、只发布完整 20 题，但汇总端仍会盲读旧文件或外来的同名 JSON。建议进入成绩表前验证确切题号、题组、criteria 唯一性和完整性、verdict/汇总一致性；缺少证据是 unknown，不是 pass，`applicable=false` 也不是 unknown。当前记录未发现空判定，不应把潜在漏洞写成当前成绩造假。

5. **重复结果的分母与版本元数据不稳健。** [cell()（修复前）](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/common/scorecard.py) 取各次分子均值，却固定使用第一次的分母；只要评审适用项有变化，这个均值分数就不代表实际合并比率。建议同时展示每次 `分子/分母`、合计 `Σ分子/Σ分母`、整题全对率的运行范围。新 [accept.py:118](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/common/accept.py:118) 已在检查点保存题库/规则/criteria/measure、harness、入口哈希与评审模型，而 `scorecard` 只根据短 revision 文件名归组。应绑定检查点身份，按同一冻结输入和模型合并；旧记录没有这些元数据时标“旧记录，来源未冻结”，不要补写推测的哈希。此次各专家宿主验收的组内适用项分母一致，未出现这项数值误差。

6. **“同题重复”与“新增样本”、“初始改造”与“训练增益”需要明确区分。** 每次都是相同 20 题，重复 3 次的 30 个 x 答卷仍只有 10 道独立 x 题，不能说测试了 30 道新题。最终必须保留 plain、v0、trained 三列；trained−plain 是全流程变化，trained−v0 才是此设计下的训练阶段变化，仍不是因果实验结论。旧竞品表同规则从 v0 的 28/30 降到 trained 的 25/30，投诉新规则 plain 与 trained 都是 22/30，见下面事实表。

7. **日志链和策略文件名不能直接证明“每轮都学会”。** [Studio 输出（修复前）](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/common/scorecard.py) 没有带 session、round、revision，也可能把重启、补考、额外轮合成一条线。同一 SaaS revision `1aa568cda685` 在 [run.out:41](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/saas-metric/run.out:41) 和 [run.out:51](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/saas-metric/run.out:51) 的 0/83 与 3/83 是同版本不同运行，不能说模型发生了一次回退。[learned()（修复前）](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/common/scorecard.py) 仅列当前 artifact.files 的名称、说明和字数，没有与 v0 比较，也不覆盖 artifact.values。该段宜改名“导出的策略产物”，具体学会什么要由 v0→trained 的内容变化与答卷证据支持。

## 新文件命名检查

新名字 `accept-51921603a07c-1011-193059-ba62ea87d9.json` 能被 `runs_of(case, "51921603a07c")` 正常读到；`glob("accept-{tag}-*.json")` 不要求固定连字符数量。[发布命名](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/common/accept.py:165) 与 [读取逻辑](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/common/scorecard.py) 兼容。实际只读调用 `card("meeting-actions")` 正确显示了当时两份带 hash 的培养后完整验收，plain/v0 均为 0 次。检查点 `accept-runs/*/partial.json` 和子集 `subset.json` 不在这个 glob 中，不会误入成绩表。

但文件时间是新运行创建时间，不一定是完成时间；跨年按 MMDD 排序也不等于真正先后。最终应使用检查点 `created`/`complete` 事件时间，不从文件名推断结束时间。

## 五个旧专家的事实

表内为“同规则整题全对 / 新规则整题全对”；这里的 30 是同一组 10 题重复 3 次产生的答卷数，不是 30 道不同题。分母 10 的门店仅 1 次。各次原始文件在后面的完整索引，亦与 [18:44 已发布快照](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/reports/status-20261011-184453.md) 一致。

| 专家 | 每版本次数 | plain | v0 | 培养后 | 允许作出的结论 |
|---|---:|---|---|---|---|
| 退款客服 | 3 | 0/30；4/30 | 15/30；18/30 | 30/30；27/30 | 两组均提升，培养后三次分别为 x=10/10、y=9/10；仍有稳定剩余错误。 |
| 竞品对比表 | 3 | 4/30；2/30 | 28/30；16/30 | 25/30；21/30 | 初始改造收益显著；训练阶段同规则下降，新规则增加。 |
| 门店客单价 | 1 | 4/10；4/10 | 2/10；4/10 | 8/10；5/10 | 首次宿主对照改善，新规则仍只全对一半；不足以谈复测稳定性。 |
| 投诉处理 | 3 | 10/30；22/30 | 9/30；18/30 | 27/30；22/30 | 同规则改善；新规则相对 plain 无净提升。 |
| 海报审查 | 3 | 21/30；16/30 | 19/30；5/30 | 27/30；22/30 | 两组相对 plain 改善；培养后 x 各次 10/10、10/10、7/10，y 各次 9/10、6/10、7/10，不能称稳定全对。 |

门店 Studio 最后两版从 7/69 到 18/69 的实际版本变化仍应如实展示；最终导出的就是后者，没有按考试成绩择优替换。证据为 [run.out:57](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/store-ticket/run.out:57)、[run.out:69](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/store-ticket/run.out:69) 与 [最终宿主验收](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/store-ticket/accept-a3a9e4ad8ac5-1011-164438.json)。

## 新 10 个专家的初次验收

下表只描述培养后版本，不计算提升。x/y 各 10 题；“挂项”是有至少一处违规的 criterion 数量，不是错误处数。初次完成的 9 个均有逐项 LLM verdict、无派活错误、无引用异常。

| 专家 | x 全对 | y 全对 | x 挂项 | y 挂项 | 初次结果原文件 |
|---|---:|---:|---:|---:|---|
| 医疗推文审查 | 10/10 | 9/10 | 0/50 | 1/50 | [dental-post](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/accept-f220b0b0f4f5-1011-193059-fbbfa1ef35.json) |
| SaaS 指标取数 | 10/10 | 6/10 | 0/40 | 4/40 | [saas-metric](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/saas-metric/accept-1aa568cda685-1011-193100-ed23860e9a.json) |
| 会议待办 | 10/10 | 8/10 | 0/50 | 2/50 | [meeting-actions](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-51921603a07c-1011-193059-ba62ea87d9.json) |
| 运营周报 | 7/10 | 4/10 | 3/40 | 6/40 | [weekly-report](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/weekly-report/accept-899b5d2ca313-1011-193059-958a05a7c3.json) |
| 咖啡新品文案 | 10/10 | 9/10 | 0/50 | 1/50 | [cafe-copy](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/cafe-copy/accept-64aecc43de91-1011-193059-81ef42434b.json) |
| 电商标题 | 9/10 | 10/10 | 1/40 | 0/40 | [taobao-title](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/taobao-title/accept-42a572b356cd-1011-193059-2e6383eeab.json) |
| 合同留痕审稿 | — | — | — | — | [仍进行中的检查点](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/contract-review/accept-runs/parallel-v1-cd2deb00398e-1/partial.json)，不把部分题的成绩当作整次结果 |
| 销售通话复盘 | 7/10 | 5/10 | 4/50 | 5/50 | [call-debrief](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/call-debrief/accept-483e4e1633b1-1011-193059-ce20ddb647.json) |
| 需求追问 | 9/10 | 7/10 | 1/50 | 6/50 | [discovery-coach](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/discovery-coach/accept-3c458a40c006-1011-193059-07d1691456.json) |
| 评价周报 | 6/10 | 5/10 | 4/40 | 7/40 | [review-digest](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/review-digest/accept-a7c5b576db31-1011-193059-c91d5340c1.json) |

复测已经说明单次成绩会变化：医疗推文的第二次 y 从 9/10 变为 7/10（[第二次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/dental-post/accept-f220b0b0f4f5-1011-194022-784477a95f.json)）；会议待办的第二次 y 从 8/10 变为 9/10（[第二次](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-51921603a07c-1011-193822-1c3c5611f2.json)）。两者都是同 revision 的重复运行，不是又一轮训练改变了能力。

## 建议最终交付结构

总览只写“22 个目标中，三版本完整 X 个、单版本验收中 Y 个、训练中 Z 个、错误待恢复 W 个”，每个专家只能落在一个进度格；不要用运行次数、题数或 criteria 数替代专家数。另行展示三个独立布尔项：训练完成、导出完成、对照完成。

主表每专家一行：`专家｜三版本完整性｜各版本运行次数 P/V/T｜plain x/y全对｜v0 x/y全对｜trained x/y全对｜trained−plain｜trained−v0｜派活/评审异常｜原始记录`。单元格给合计和每次范围，明示“同 20 题复测”。未完成的格写“待齐”而不是 0 分。

每专家附表每版本每题组一行：`版本/完整revision｜组｜独立题数｜重复数｜派活成功/尝试｜LLM评审齐全答卷数｜unknown｜全对/有效答卷｜失败criteria/适用criteria｜不适用数｜loose引用异常数`。错误处数可另列，但不能与失败 criteria 数互换。

元数据保存：完整 revision、训练 session/轮次与初始 curation 标识、输入和产物哈希、员工/评审模型及 effort、报告时间、run_id、开始/完成时间、每个原始报告和检查点路径、重启/恢复事件；缺失元数据明确写未记录。新检查点已有多数身份字段，例如 [会议待办检查点](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/experts/cases/meeting-actions/accept-runs/parallel-v1-51921603a07c-1/partial.json)。

## 旧专家源文件索引

以下为完整的三版本输入清单，均相对于本报告目录；没有纳入 `superseded/` 旧产物。`P`=plain，`V`=v0，`T`=培养后。

- 退款客服：P [1](../cases/refund-desk/accept-plain-1011-154351.json)、[2](../cases/refund-desk/accept-plain-1011-160905.json)、[3](../cases/refund-desk/accept-plain-1011-163427.json)；V [1](../cases/refund-desk/accept-v0-1011-155007.json)、[2](../cases/refund-desk/accept-v0-1011-162441.json)、[3](../cases/refund-desk/accept-v0-1011-164709.json)；T [1](../cases/refund-desk/accept-098fe127cd2d-1011-151939.json)、[2](../cases/refund-desk/accept-098fe127cd2d-1011-161650.json)、[3](../cases/refund-desk/accept-098fe127cd2d-1011-164059.json)。
- 竞品对比表：P [1](../cases/compete-table/accept-plain-1011-154248.json)、[2](../cases/compete-table/accept-plain-1011-160901.json)、[3](../cases/compete-table/accept-plain-1011-163249.json)；V [1](../cases/compete-table/accept-v0-1011-155054.json)、[2](../cases/compete-table/accept-v0-1011-162418.json)、[3](../cases/compete-table/accept-v0-1011-164759.json)；T [1](../cases/compete-table/accept-0150fa86cde9-1011-152100.json)、[2](../cases/compete-table/accept-0150fa86cde9-1011-161604.json)、[3](../cases/compete-table/accept-0150fa86cde9-1011-163919.json)。
- 门店客单价：P [1](../cases/store-ticket/accept-plain-1011-164942.json)；V [1](../cases/store-ticket/accept-v0-1011-165131.json)；T [1](../cases/store-ticket/accept-a3a9e4ad8ac5-1011-164438.json)。
- 投诉处理：P [1](../cases/complaint-desk/accept-plain-1011-154440.json)、[2](../cases/complaint-desk/accept-plain-1011-161252.json)、[3](../cases/complaint-desk/accept-plain-1011-164758.json)；V [1](../cases/complaint-desk/accept-v0-1011-155546.json)、[2](../cases/complaint-desk/accept-v0-1011-163527.json)、[3](../cases/complaint-desk/accept-v0-1011-171130.json)；T [1](../cases/complaint-desk/accept-50bd665135f2-1011-152216.json)、[2](../cases/complaint-desk/accept-50bd665135f2-1011-162319.json)、[3](../cases/complaint-desk/accept-50bd665135f2-1011-165744.json)。
- 海报审查：P [1](../cases/poster-review/accept-plain-1011-154727.json)、[2](../cases/poster-review/accept-plain-1011-161118.json)、[3](../cases/poster-review/accept-plain-1011-165018.json)；V [1](../cases/poster-review/accept-v0-1011-155625.json)、[2](../cases/poster-review/accept-v0-1011-163615.json)、[3](../cases/poster-review/accept-v0-1011-171405.json)；T [1](../cases/poster-review/accept-8ab6e08e3fe1-1011-153944.json)、[2](../cases/poster-review/accept-8ab6e08e3fe1-1011-162355.json)、[3](../cases/poster-review/accept-8ab6e08e3fe1-1011-170035.json)。
