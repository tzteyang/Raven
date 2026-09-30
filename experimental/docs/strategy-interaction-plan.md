# 三策略交互契约、实施顺序与验收标准

Planning 更新：本文中保留 initialize/view/revise 的决定已由 [Planning 交互实施方案](planning-strategy-plan.md) 取代；当前协议为 initialize/interact，工具与跨策略联动随之迁移。

状态：历史设计与阶段验收记录，描述四策略入口收敛之前的协议演进，不作为当前生成接口说明。当前有效契约见 [design.md](design.md)、[候选准备](../curator/raven_adapter/reference/preparation.md)及各策略源码；本文历史测试数不证明新入口或真实案例已经验收。

架构范围更正：上述验证没有满足“四策略代码作为语义生成入口”的完整要求；当前仍允许独立资源、配置和原生组件 Target。对这些入口的逐项收敛及协议缺口见 [Target 收敛评审](strategy-code-generation-review.md)，该调整尚未实施。本计划的历史结果不作为新架构完成的证据。

本计划以用户确认的 Memory、Capability、Action 讨论为依据，遵循 [experimental 开发准则](../AGENTS.md) 和仓库根规则。它规定三者共同承担的约束与最终验收标准；各策略的具体方案分别见 [Memory](memory-strategy-plan.md)、[Capability](capability-strategy-design.md)、[Action](action-strategy-design.md)。本计划不把此前临时草稿或旧协议的测试通过当成新设计已实现。

## 1. 必须兑现的两条价值准则

V1：Curator 能把用户直接提供的信息、规范、材料和资源，转化为目标 Harness 中实际生效、来源可解释的实现与内容。

V2：Curator 能结合已安装的实现、实际执行证据、修正反馈或新增输入，修订 Harness，并使新行为生效、旧行为按意图退场、应保留的状态和资源继续存在。

这两条都是设计与实现的验收条件，必须对三个策略分别验证，再做联合验证。接口存在、构造成功、模型声称遵守、一次最终回答包含某个标签，都不足以单独证明它们成立。

| 策略 | V1 的最低行为证明 | V2 的最低行为证明 |
|---|---|---|
| Memory | 输入材料决定初始化后的真实模型上下文组织；模型交互回到同一 owner，并影响同一 turn 的后续输入 | 新材料与反馈改变相应内容或组织规则；相关旧内容退出实际请求，未被修改的事实与工作进度保留，其他会话不被覆盖 |
| Capability | Curator 分别采用完整的外来 Skill 包、根据材料生成 Skill；安装后的正文/资源确实被消费，工具确实可调用 | 修订或撤回明确作用于目标资源，旧处理器和废弃 Skill 不再作为活动能力；保留无关资源，失败激活恢复原状态 |
| Action | 任务约束生成有实际效果的事件处理和模型请求入口；在所需执行点纠正或阻止行为，指导实际送达模型 | 修正反馈与新增条件改变相应裁决和交互行为；新约束生效，仍然有效的旧约束和状态保留，控制应用结果进入证据 |

联合用例必须同时覆盖首次定制、后续纠错和补充信息。新增输入不是必须推翻旧实现的信号；合理的不变决定也需要来源和实际行为证据。缺失材料应成为明确缺口，不以编造业务事实填补。

其他验收维度：可解释的来源、作用域隔离、可恢复的激活、真实能力与说明一致、跨策略协作没有状态分叉。这些补充 V1/V2，不取代它们。

## 2. 统一视角与局部差异

遇到一个基线、某种工具或某个策略无法适配时，先检查共同契约是否缺少必要的身份、生命周期、能力表达或结果语义。能够形成共同规则的差异，先调整共同规则，再让所有相关消费者一致采用。

优先级为：共同语义与不变量 → 宿主明确提供的能力和限制 → 具体策略的领域判断。局部适配负责读取真实基线、翻译数据和应用已声明效果；它不应私藏另一个策略的业务规则。

允许局部差异，但必须满足：有实际宿主差异作为证据；通过共同能力声明可见；不会绕开公共结果或作用域规则；存在跨基线验证。不得用产品名分支、私有 callback、额外全局工具表或隐式状态副本掩盖契约缺口。

以下机制已有价值，应继续复用：Curator 的理解/选择/设计/实现/修复流程，Target 派生的阅读与 schema，原生 ToolRegistry/权限/gate，Prompt 与 SegmentBuilder，候选验证和统一激活，已有 checkpoint、Recorder、Inspection，以及 Planning 的 initialize/view/revise。

三个策略仍可独立选用。只选择 Memory 或 Action 时，共同能力登记由宿主的基础 Capability 实现承接，并委托原生选择；不强迫 Curator 顺带生成一个无业务变化的 Capability 类。没有生成 Memory 时，内容贡献使用同一输入交付契约并保留原生组装。依赖的领域操作如果不存在则明确报告，不以基础实现伪造任意 Memory/Planning 命令。单策略、两策略与三策略组合都需验证。

## 3. 共同契约

### 3.1 身份、来源与活动 owner

共同的运行信息由宿主提供：目标 Harness、revision、task/session/turn、调用或事件标识、事件阶段和可关联证据。模型命令只提供领域内容；不能自行指定可信来源、会话身份或权限事实。

工具 schema 来自真实请求类型。跨进程描述使用可解析引用，运行时由宿主定位同一 Harness、当前会话和当前版本的活动 owner。模型入口、自动观察及上下文组装不得各自构造一份 owner 或管理其 checkpoint 副本。

任务共享信息、会话状态、单次请求投影和候选资源登记具有不同生命周期。共同包装应表达这种差别，不让 Memory/Capability/Action 分别用私有全局变量解决。

### 3.2 贡献、资源与生效

Capability.register 是显式公共操作。Memory.interact、Action.handle_request 与现有 Planning 工具通过同一贡献路径发布；不存在只有 Memory 能用的私有登记分支。候选范围的注册、实际激活和运行期选择分开；详细的贡献、回执、包引用及撤回规则以 [Capability 第 3 节](capability-strategy-design.md) 为准。

Curator 是持久能力资源变更的决策者。用户上传提供待检查材料；普通策略交互可以提交材料或建议，但不能绕过 Curator 安装 Skill、替换工具或增加子 Harness。

有效能力视图必须来自本次实际生效、经过原生可见性与委派保护处理的能力。Memory.compose 和 Action 使用该视图时，不得把 staged 登记或某个中间选择结果当成最终事实。工具可见性不等于执行许可。

### 3.3 跨策略依赖与请求

依赖按实际操作声明并绑定，不注入整个运行时或任意 owner 字典。共同提供三类关系：只读视图、对所属策略公共操作的类型化请求、由宿主消费的执行控制。

- 读取的视图是副本，带适用作用域和必要版本信息；缺失与空结果不同。
- 修改通过目标 owner 的公共操作完成。Planning 拥有计划修订，Memory 拥有信息更新，Capability 拥有资源与选择语义；Action 不复制这些状态。
- 所有运行期请求受当前声明约束。宿主控制也只在明确支持的阶段和范围内应用。
- 依赖边界保留请求、结果和错误证据。异常不能成为“没有变化”的成功回执。
- 调用图和锁顺序必须可解释；不允许持有一个 owner 的锁时形成回调到自身的等待环。实施时优先采用明确、有限的依赖方向，不引入通用服务定位器或事件总线。

当前实现按 Harness 串行执行完整策略调用链，链内可顺序调用 peer；同链回调到自身及通过新 asyncio task 并行分叉会明确失败。原生 Loop、工具执行器和跨 Harness 调度仍由 Raven 负责。该边界避免两个并发入口互相持有不同 owner 锁，也保护任务共享知识的回滚范围。

单个 owner 的 checkpoint 恢复不撤销其他 owner 已成功的操作，更不撤销外部工具效果。跨策略部分失败需要逐项结果和关联标识，后续按已完成事实恢复，不能声称天然具有跨策略事务。重复交付的处理由身份和具体操作语义保证，不承诺无法证明的 exactly-once 外部执行。

### 3.4 决策、反馈与实际效果

策略返回的领域答复、模型可见指导、宿主控制请求及其实际结果分开记录。控制语言规定目标范围、适用阶段和支持条件；未知或不支持的控制明确拒绝，不能静默降级为通过。

某方法未启用、已启用但当前事件不匹配、成功处理后无需干预、业务拒绝和基础设施失败必须能够区分。声明中启用的方法必须存在真实实现和消费路径，禁止空壳通过构造核验。

同一规则可以由自愿请求和宿主检查共同使用。必须阻断的约束具有真实的执行前消费者；不能以工具隐藏、提示语或可能被忽略的 review 返回替代。

## 4. 方案比较与采用理由

| 方案 | 复杂度和可理解性 | 满足需求的程度与风险 |
|---|---|---|
| 各策略各补工具、回调和状态字段 | 局部实现快，阅读者需理解三套路径 | V1 容易演示，V2 的一致更新与跨策略作用域难保证；不采用 |
| 共同类型、声明和 owner 调用边界，加薄的宿主绑定 | 初期需要明确生命周期，之后可共用检查和证据 | 推荐；支持两条价值准则并保留领域自由，风险集中在真实消费时序 |
| 统一事件调度器接管四策略、工具和 Loop | 集中表达强，迁移与维护成本最高 | 超过现有需求且重复 Raven 调度；不采用 |

采用第二种。关键假设是 Raven 原生公开角色/ContextEngine/Hook/ToolGate 等入口足以落实行为；先以实际 provider 请求与真实工具效果证明。若某个必要路径只能靠不可靠的消息原地改写或字段伪造实现，应回到共同设计修正并重新比较，不能悄悄削减 V1/V2。

接入验证修正了两点假设：来源捕获集中使用 ContextAssembler 的内部 builder 与 scent 接缝，并为自定义引擎提供明确的 ContextSourceProvider；未提供来源的引擎保留受保护的不透明上下文。真实模型验证还发现 Responses 转换只保留最后一段 system，必须在原生通用转换器修复。依赖方向仍为 experimental → raven；没有为生成策略另建执行器。具体依赖和维护边界转入长期 design.md。

## 5. 实施阶段与可检查交付

| 阶段 | 必需交付 | 完成证据 |
|---|---|---|
| S0 现状与计划 | 三份策略方案、本共同标准、基线测试及实现边界 | 阅读入口正确；旧行为、提案与验证事实明确区分 |
| S1 共同契约与接入验证 | 身份/来源、资源贡献、有效视图、依赖调用及控制结果类型；最小实际消费者验证 | 原生根与现有 ACP 产品基线上，最终模型请求和工具执行证明调用时序 |
| S2 Capability | register/select、完整包采用/生成/修订/撤回、活动目录和各策略入口绑定 | C-V1/C-V2 及资源恢复、注册冲突、冻结期测试 |
| S3 Memory | initialize/interact/compose/compact、初始组装和逐次投影 | M-V1/M-V2；同 turn 状态刷新、原生必需内容、作用域和压力测试 |
| S4 Action | handle_event/handle_request、公共事件/决定、真实 gate/review/请求路径、跨策略协作 | A-V1/A-V2；执行前约束与实际控制效果、同 owner 和部分失败测试 |
| S5 信息链 | 新契约进入 Curator 阅读路径，执行证据贯穿更新流程 | 真实输入、生成修复、根/子证据分派和输入 fingerprint 核验 |
| S6 联合验收与审查 | 离线端到端、真实 DeepSeek 测试、独立审查轮次、长期资料 | 按第 6 节逐项收集证据，未满足项继续实施 |

各阶段可按依赖细化，但不以完成文档或单个策略替代整个目标。现有工作区中其他人的改动保留；不自动提交、推送或重写历史。创建分支前依根规则确认基线；分支确认前可完成仓库外草稿、只读核查和独立 API 探测。

## 6. 保证性验收矩阵

| 编号 | 必须证明的结果 | 主要证据 |
|---|---|---|
| M-V1 | 用户材料决定真实初始上下文组织，initialize 非空壳，interact 同 turn 生效 | 最终 provider 请求、初始化与交互记录、同 owner 状态 |
| M-V2 | 更正/新增信息替换指定内容且保留其他事实与会话隔离 | 变更前后请求、状态与 revision 对照，重启恢复 |
| C-V1 | Curator 主导采用完整 Skill 包及从材料生成 Skill，两种资源实际被使用 | Curator 提交、内容/附件摘要、发现与正文消费、实际工具调用 |
| C-V2 | 能力修订/撤回精确生效且失败可恢复 | 活动目录、文件摘要、旧能力不可用、未修改资源仍存在 |
| A-V1 | 主动请求与宿主监督共享行为规则，约束在所需位置生效 | 请求处理、gate/review、工具未执行或执行记录、交付前后可见性 |
| A-V2 | 修正/新增规则改变正确的判断且不丢失仍有效规则与状态 | 同组正反例在两个 revision 上的结果，实际纠正输入和应用回执 |
| J-OWNER | 所有策略入口绑定到正确会话与 revision 的活动 owner | 双会话、根/子、换版和重复交付测试 |
| J-FAIL | 部分失败、预算耗尽、不支持效果和拒绝具有真实结果 | 状态、资源、控制和错误记录；无伪造成功 |
| J-EVIDENCE | 试炼副本与子 Harness 的相关实际执行进入 Curator 修订材料 | Sessions 到 workflow/composition 的关联、分页查询与恢复输入身份 |
| J-BASELINE | 未选择新策略时原生行为保持；选用时遵守各基线内容结构 | 普通 Raven 与一个现有 ACP 产品，原生权限、委派保护和生命周期回归 |
| J-GENERATE | 新协议能被 Curator 在真实模型下理解、生成、修复并修订 | 完整真实生成链及独立行为断言，不只检查输出标记 |

测试断言读取系统实际输出：provider 请求、实际派发、包内容、活动实例、状态和反馈材料。断言本身不照抄生成实现的内部算法。给 Curator 的业务输入与测试预期同源，但不把完整解答实现预先塞进默认提示。

失败后先定位属于契约、绑定、生成信息或具体领域实现，再修复相应层。协议级失败不得通过调松测试或把目标缩小到现有易通过路径解决。

## 7. 验证执行与真实模型

离线验证顺序：类型与边界测试 → 原生 Loop 的受控 provider 测试 → 三策略首次生成与修订 → 根/子与基线回归 → 与实现分开的需求审查。通过后再扩大测试；没有新改动、失败或未解决风险时不重复整套运行。

真实模型使用用户明确授权的 DeepSeek 官方 API。官方模型名为 deepseek-flash，对应 V4.1-Flash，依据 [官方调用说明](https://api-docs.deepseek.com/) 与 [官方模型说明](https://api-docs.deepseek.com/quick_start/pricing/)。记录实际请求名；上游与适配器提供响应模型名时一并保留，未提供时不能推断为已核验。将 API 连通性探测与策略端到端测试分开报告。

真实测试至少分别验证三策略的 V1/V2，再跑联合修订场景；Capability 覆盖现成包与材料生成两条路径。使用有界调用、超时与明确修复次数，记录实际调用和 token 用量。联网错误、生成错误与行为不满足分别报告，不能将跳过计为通过。测试只提供必要的任务材料和项目契约；密钥从环境或仓库外受限文件加载，不进入仓库、提示词、报告或日志。

规划中的检查命令由最终改动确定，至少覆盖相关单元和真实原生 Loop 集成，并执行 make check-source-language、make check-large-files。pytest 默认可能过滤 integration 标记，需显式选择并核对 collected/passed/deselected，不能把未运行的集成测试计为通过。

## 8. 完成审计与长期资料

完成前对第 6 节每一行提供对应的文件、命令输出或执行记录，标明通过、失败、未实现或证据不足。计划中的勾选和模型自述不是完成证据。

源码、docstring、绑定 schema、生成阅读材料、测试和必要领域定义同步修改，不保留无需求的旧协议兼容层。既有新协议内的 checkpoint 保留、明确迁移和失败回滚属于正确性范围，不得以移除兼容为由清空状态。

最后将长期接口与运行说明放入现有设计和参考资料，更新三份计划与本计划的状态。明确实际支持的压力点、事件和控制范围；未实现的必要行为不能被写成可选建议后宣布完成。

## 9. 最终验收记录

2026-09-29 完成 S0–S6：公共协议、运行绑定、资源与证据链、调用方迁移、独立审查、相关回归和真实模型行为核验。长期说明已转入 design.md 与 harness/reference、raven_adapter/reference；三份策略计划保留设计取舍及实施顺序。

### 9.1 测试结果与范围

| 验证 | 结果 | 范围 |
|---|---|---|
| 相关单元回归 | 538 passed | Curator、Iteration、Analyst、Simulation 与 Responses 消息转换 |
| 原生集成回归 | 51 passed，5 个真实模型用例另行运行 | 原生 Loop、ACP 父子、code/research/oncall/design/ppt 基线、换版恢复、三策略交互 |
| 官方 DeepSeek 实测 | 原始 pytest 为 4 passed、1 failed | Capability、Action、完整 Skill 包、三策略联合用例均完成首次生成和反馈修订；Memory 失败原因见下文 |
| Memory 真实记录复验 | 8 组行为检查及修正后的 2 项断言回放通过，无新增模型调用 | 两版原始生成物、真实 provider 输入、工具交互、回答、任务/会话/版本身份 |
| 仓库检查 | 通过 | Ruff、diff whitespace、大文件、源码语言；密钥未进入仓库变更 |

Memory 的原始测试要求最终自然语言回答原样复述系统提示中的 MEMORY:amber。实际运行已将偏好改为 amber、保留随机生成的原事实，并正确作答，但回答未复述该标记。测试现改为检查实际 system 内容、同 turn 信息更新、换版后事实与回答；修正后的同一断言函数已在两版留存记录上执行。原始失败没有改记为一次全新模型测试通过。

真实用例使用 deepseek/deepseek-flash、官方 Responses 接口，以及明确限制的生成调用、查询、预检和修复预算。记录保留实际生成 trace 与 worker 执行；当前适配器未完整提供 Curator token 合计和上游响应模型身份，因此不把请求别名或估计值冒充这两项遥测。这里证明的是所列路径的可运行性，不是任意任务上的统计成功率。

### 9.2 逐项完成证据

| 标准 | 已完成的行为证据 | 可复现入口 |
|---|---|---|
| M-V1、M-V2 | 实际来源重组；initialize 结果进入 compose；交互后的同 turn 请求更新；新偏好与旧事实共存；两会话和换版恢复 | test_harness_curator_interactions.py、test_harness_curator_strategies.py、test_harness_curator_interactions_e2e.py；真实 Memory 两版及留存记录复验 |
| C-V1、C-V2 | 完整上传包经 Curator 明确采用；材料生成 Skill；正文和引用附件实际消费；工具/资源修订撤回、冲突拒绝、失败恢复 | test_harness_curator_capability_binding.py、test_harness_curator_interactions_e2e.py；真实 capability 与 skill_adoption 用例 |
| A-V1、A-V2 | dispatch 真正拒绝调用；请求与事件共享 owner；两版允许/拒绝条件改变；实际 finish、流式草稿抑制和控制回执 | test_harness_curator_interactions_e2e.py、test_harness_curator_prompt_e2e.py；真实 action 用例 |
| J-OWNER | Memory、Planning、Action 经同一 Capability 登记；实际 session/revision owner；Action 查询活跃 Memory；避免跨任务锁反转 | test_harness_curator_interactions.py、test_harness_curator_hosting_e2e.py；真实 joint 两版 |
| J-FAIL | 类型错误、只读写入、循环/并行分叉、部分成功、不支持控制、预算与取消均有明确结果 | test_harness_curator_interactions.py、test_harness_curator_strategies.py、test_analyst_activity.py |
| J-EVIDENCE | 试炼与子层完整相关条目传入生成；评测私有材料不泄漏；恢复固定已读证据并识别真实新增 turn；干预按 applied 回执计数 | test_iteration_run.py、test_harness_curator_composition.py、test_harness_curator_composition_e2e.py、test_analyst_activity.py |
| J-BASELINE | 原生权限、委派保护、产品工具、会话及生命周期保持；ACP inspect 与实际响应进程一致 | test_harness_curator_agents_e2e.py、test_harness_curator_hosting_e2e.py、test_harness_curator_deployment_e2e.py |
| J-GENERATE | 三策略分别生成/修订、完整包采用/更新、共同注册与 peer 协作；核对实际输入、工具效果及控制结果 | test_harness_curator_real_llm.py；Memory 断言修正和回放边界见 9.1 |

### 9.3 审查中完成的修正

与主体实现分开的审查和运行验证补齐了以下共同问题：

- Responses 转换保留所有 system 文本和 developer 消息，避免内容贡献被覆盖。
- ACP、Worker 和 probe 使用共同的 turn 作用域，正确转交流式与 usage sink。
- Action 要求重试后，Skill 来源仍定位到原始组装的用户消息。
- 按 Harness 串行执行策略协作链，拒绝链内循环和并行分叉；其他 owner 已完成的写入不随调用方失败回滚。
- 注册回执与真实候选目录一致；关闭后不能伪造登记成功。完整包保留二进制、目录与模式，活动发现不继续暴露退休资源。
- 子进程 PID 不参与任务执行身份；进程重启不丢弃已经固定的证据，新 turn 或更改的记录仍使恢复输入检查失败。
- Analyst 与场景记录消费真实控制回执，避免重复计算工具拒绝，或把请求和未采纳控制算成实际干预。

维护边界：ContextAssembler 的私有来源接缝集中在 context_sources.py；自定义引擎可以提供 ContextSourceProvider。完整包不接受符号链接或特殊文件。子层证据沿用 ACP 的分页、流式 delta 省略和超大条目标记截断。当前支持的压力点、事件和控制以公共类型及绑定 schema 为准，原生权限、调度、委派和外部副作用仍由 Raven 承担。

### 9.4 检查命令

以下为同一改动使用的检查范围；具体环境使用既有 uv 环境，真实测试的配置和密钥位于仓库外。

```bash
uv run pytest -n 0 tests/test_harness_curator*.py tests/test_iteration*.py tests/test_analyst*.py tests/test_simulation*.py tests/test_openai_codex_provider.py tests/test_provider_protocol.py -q
uv run pytest -n 0 -m 'integration and not real_llm' tests/integration/test_harness_curator*.py -q
CURATOR_TEST_CONFIG=<private-config.json> CURATOR_TEST_MODEL=deepseek/deepseek-flash uv run pytest -n 3 -m real_llm tests/integration/test_harness_curator_real_llm.py -q
make check-large-files check-source-language COMMIT_RANGE=HEAD
git diff --check
```

真实模型测试保持显式启用；默认跳过不计为通过。Memory 的修正断言在 assert_memory_execution 中，与保存的两版真实记录使用同一函数核验。
