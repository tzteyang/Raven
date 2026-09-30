# Planning 交互协议与四策略协作实施方案

状态：实现完成，针对性验证通过。真实模型专家业务验收单独记录。当前方案取代早期文档中保留 initialize/view/revise 的决定。

## 目标与边界

Planning 的运行期公共协议收敛为 initialize + interact；prepare 继续负责候选构建。Curator 通过四策略代码生成规划、信息组织、能力管理和行为控制。支持清单、部分计划、分层分解、重规划、阶段流程及原生委派；不增加独立资源或配置 Target。

本次不实现规划器内部的多轮模型搜索、不新建调度器或跨会话共享计划服务。单步推理、原生权限和执行预算继续适用。DAG 执行依赖真实的原生调度，计划中的循环不能直接作为 DAG 环。候选方案与执行方案由具体类型区分，重规划必须保留已执行事实。

## 方案比较与决定

| 方案 | 取舍 |
|---|---|
| 保留公共 view | 读取直观，但增加独立策略调用和结果一致性约定 |
| interact 内预设读取命令 | 入口统一，宿主仍需调用生成代码才能读取 |
| 操作返回计划投影 | 沿用已有 PlanReader 缓存读取方式；每次操作必须提供可恢复的投影 |

采用第三种。其前提是规划状态只通过明确操作变更；外部变化通过观察或请求输入。若未来需要脱离会话的共享规划或自主搜索，应单独评估执行与状态服务。

## 公共契约

- PlanningInitialization 提供 scope、task、restored。每个会话实例首次使用及恢复时初始化一次；恢复不清空进度。客户当前输入进入运行期交互，Curator 构建指令不作为业务任务。
- PlanningStrategy[ViewT, CommandT, ReplyT].initialize 返回 PlanningProjection[ViewT]；interact 接收 InteractionRequest[CommandT]，返回 PlanningResult[ViewT, ReplyT]。
- PlanningProjection 包含 view 和 guidance；PlanningResult 包含 reply 和 projection。业务接受或拒绝属于 ReplyT，正常拒绝可以记录阻塞。错误恢复本 owner 状态。
- 共同请求增加 query/command 模式。query 不改变持久状态或已发布投影；只读约束沿 peer 调用传播。command 可以产生合法无变化结果。
- view 是当前计划的可消费表达，允许为空或不完整；guidance 是由已提交状态产生的规划指导，None 撤回旧指导。投影须可由持久状态重建。
- 工具及 peer 返回 reply；宿主保存完整结果，向其他策略提供只读 view。成功保存后才发布投影。来源、scope 和事件身份由宿主提供，Agent 不能自称执行观察。
- 重复真实证据不能重复推进。候选方案可以作为状态保存，但是否成为执行方案由明确业务命令决定。状态恢复不等于外部动作回滚。

## 生命周期与四策略联动

1. 会话进入时建立或恢复 Planning；内存初始化标记与 checkpoint 的恢复标记分离。
2. 模型调用前，按绑定选择将当前输入和可观察事实交给同步、只读的 _observe，再由 interact 做异步判断和变更。
3. Capability.select 读取本次已提交计划，选择真实可用工具和 Skill；Planning 前置同步必须早于原生参与者的能力选择。
4. Memory 组装计划指导、有效能力与其他来源。Planning 不修改最终消息窗口。
5. 执行后的观察继续进入同一 owner。Action 在原生控制点读取计划与当前事件；计划不自动代表当前输出已获验证。
6. Planning 工具经 Capability.register 发布，引用 planning.interact；注册、安装、可见性和执行权限分别保留。无工具的 peer/观察接入也可独立选用。
7. Memory 与 Planning 的 query 共享只读传播；不允许借 peer 升级为写操作。Action 控制入口不开放为只读调用。
8. Planning.prepare 沿用 Playbook 与子节点 requirements。实际委派、子 Harness 定制和会话计划分别记录。

不规定 initialize 的下划线模板方法序列。_observe 只在选择对应宿主观察时要求实现。生成代码可以内部复用投影辅助方法，但宿主不要求公共 view/revise 或 _render_context。

## 实施范围与迁移

公共类型、Planning 协议及绑定；共同交互/peer/工具封装；Planning 运行时与前置调用；Memory 只读调用；Capability 引用解析；Curator Target、指南与生成阅读材料；现有调用方和测试。

沿用会话隔离、checkpoint、候选准备、Capability 安装、Action 控制和根子部署。当前分支内同步迁移协议，不保留旧接口别名。旧方案保留历史说明并指向本方案；当前阅读入口只呈现生效协议。失败激活仍由既有候选恢复机制处理。

## 验收

- 新建、恢复、换版和会话隔离，包含空计划与部分计划。
- query 不写状态或投影；跨 Memory 只读查询可用；嵌套写入不能升级只读约束。
- 业务拒绝可记录阻塞；非法结果、依赖失败及持久化失败不发布半成品。
- 真实原生 Loop 中同轮规划更新影响 Capability 选择和模型输入；guidance 撤回有效。
- 工具、peer、前后观察调用同一 owner，工具只返回业务答复；重复证据不会重复推进。
- 清单与依赖图两种具体表达通过相同公共协议；生成阅读路径完整，无旧签名混入。

仅运行与本次修改有关的单元及原生集成验证。真实模型案例沿用正常双层部署，结果单独记录；不将生成成功当作业务任务成功。此前旅行 run-2 已结束，客户请求执行超时，不能作为本次通过证据。

## 实施记录

- [x] 合并公共协议、跨策略联动、常见规划覆盖和执行边界。
- [x] 实现协议和运行时。
- [x] 迁移信息链与调用方。
- [x] 完成针对性验证及独立于实现过程的代码复核。


## 验证与复核记录

2026-09-29，以下命令均通过。测试使用共享项目环境，uv run --offline --no-sync；原生集成使用确定性模型响应和真实 Worker/Loop/ACP 进程，不等同于真实模型专家任务验收。

- 单元：uv run --offline --no-sync pytest tests/test_harness_curator_planning.py tests/test_harness_curator_planning_binding.py tests/test_harness_curator_interactions.py tests/test_harness_curator_capability_binding.py tests/test_harness_curator_contracts.py tests/test_harness_curator_participants.py tests/test_harness_curator_preparation.py tests/test_harness_curator_inference.py tests/test_harness_curator_composition.py tests/test_harness_curator_hosting.py -q --tb=short — 126 passed。
- 原生集成：uv run --offline --no-sync pytest -m integration tests/integration/test_harness_curator_planning_e2e.py tests/integration/test_harness_curator_strategies_e2e.py::test_four_strategy_composition_preserves_planning_and_rejects_stale_candidates -q --tb=short — 首次 4 passed、1 failed；失败为新增测试使用了不支持的画像路径。改为实际支持的 TOOLS.md 后，新增用例单独运行 1 passed。
- 补充原生接入：uv run --offline --no-sync pytest -m integration tests/integration/test_harness_curator_hosting_e2e.py::test_parent_playbook_executes_the_same_child_its_inspection_observes tests/integration/test_harness_curator_e2e.py::test_native_class_helpers_apply_to_actual_requests tests/integration/test_harness_curator_planning_e2e.py::test_current_input_updates_plan_before_capability_and_withdraws_guidance -q --tb=short — 3 passed。去重共 7 个原生集成用例通过。

复核确认：观察翻译到交互提交在同一 OperationGroup 内串行完成，避免翻译完成后被另一操作插入；查询既不能改 checkpoint，也不能替换 guidance；业务拒绝能够保存阻塞信息；失败 checkpoint 不发布投影；恢复标记与实例初始化标记分离；首轮用户输入更新先于 Capability.select；guidance=None 实际撤回旧模型输入；父 Playbook 消费的 ACP 子进程与检查结果一致。

仍有效的边界：不提供多轮内部模型搜索、跨会话共享计划事务或任意流程到 DAG 的编译；语义规划质量需通过真实任务评估。此前真实旅行 run-2 执行超时，本轮没有将它重新标为通过。

## 真实模型暴露的机制修正（已完成定向复验）

本轮三例 DeepSeek 验证见产品案例记录。效果质量先保留观察，以下机制问题先修正：

1. 投影校验使用 Python 类身份，拒绝同一 ViewT 的无新增字段投影子类。采用“验证声明类型、检查公共包裹与相同 ViewT、归一化宿主发布值”的方案；相较强迫生成代码使用同一个类名或比较完整 JSON schema，它接受合法子类型且保留领域视图类型约束。领域扩展仍放在 ViewT，公共投影仅含 view/guidance。
2. Planning 工厂补齐只读 plan 依赖，与其他消费者相同：初始化前 None，之后返回当前会话已提交视图的副本；操作中的未提交状态不外露。
3. 缺少具体方法注解时产生明确 TypeError，包含策略、方法与参数，保留类型检查，不再泄漏原始 KeyError。
4. Plan.node_reasons schema 与根生成提示明确使用 Playbook 名称/节点 ID；没有流程节点时为空映射。节点 requirements 请求子定制，实际调用独立决定。

验证优先使用最小回归及上轮原始生成代码；历史失败不覆盖为通过。更新当前指南和流程说明，运行期源码变动后不沿用旧来源身份继续生成。

本节机制修复已完成：67 项相关单元检查、2 项原生集成检查通过；上轮旅行和小红书原始 Planning 文件未改写，修复后均通过加载和初始化。详见 [真实产品验证记录第 7 节](expert-package-validation.md#7-已确认机制问题的修复与定向复验)。业务效果与完整真实模型复跑不计入本节通过范围。
