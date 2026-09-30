# Memory 策略设计与实施计划

Planning 更新：本文中保留 initialize/view/revise 的决定已由 [Planning 交互实施方案](planning-strategy-plan.md) 取代；当前协议为 initialize/interact，工具与跨策略联动随之迁移。

状态：历史设计与阶段验收记录，描述四策略入口收敛之前的协议演进，不作为当前生成接口说明。当前有效契约见 [design.md](design.md)、[候选准备](../curator/raven_adapter/reference/preparation.md)及各策略源码；本文历史测试数不证明新入口或真实案例已经验收。

本文保留 Memory 公共协议、运行时接入、Curator 信息链及与 Capability 的协作设计与实施顺序。最终接口见[公共协议](../curator/harness/strategies/memory.py)和[运行接入说明](../curator/raven_adapter/reference/memory.md)；schema 从实际类型定义导出。

设计遵循 [experimental 行为准则](../AGENTS.md)：按责任划分、选择最小完整实现、比较实质方案、只为明确需求提供兼容、用可检查的行为验收。

配套文档：[Capability 策略设计与实施方案](capability-strategy-design.md)、[Action 策略设计与实施方案](action-strategy-design.md)、[三策略联合实施标准](strategy-interaction-plan.md)。共同身份、依赖调用、统一视角优先及 V1/V2 验收以联合标准为准；能力贡献与有效能力视图的资源细节以 Capability 第 3 节为准。本文说明 Memory 如何生产和消费这些信息。

## 1. 目标、已确定约束与范围

Memory 负责初始化、维护和呈现模型上下文，并定义模型主动管理信息的交互语义。验收针对真正发给模型的请求及其状态来源。

- 公共核心为 initialize、interact、compose，保留独立 compact 用于声明由生成策略承担的压缩场景。
- 移除 experimental Memory 公共协议中的 recall、retain；查找、记录、更正等行为由具体交互协议表达，可保留为实现内部辅助函数。
- 不规定 initialize 内部必须调用哪些 _xxx 方法，不固定 profile、skills 或工作笔记的内容布局。
- 不把一份完整 Memory 示例作为 Curator 默认必读的实现答案。可复用的组件接口、真实基线和契约测试提供事实依据。
- Curator 定义和改造协议；Memory 运行时消费协议。新增、接入、修改或撤回持久 Skill 仍经过 Curator 的明确候选变更。
- 交互入口在候选构建/装配期通过 Capability.register 发布，校验与激活后调用回到同一 Harness、正确会话中的活动 Memory。
- 根与子 Harness 使用同一公共语义，允许基线输入和实现不同；不写按产品名称分支的统一拼接模板。

本轮保留 Planning 的公共语义，Action 按配套方案联合调整。不改 playbook/DAG 调度、原生记忆后端、权限机制、provider 协议，也不增加通用事件总线、独立记忆服务或任意时刻的工具热注册。

原生 MemoryBackend 的 recall、store、feedback 是独立接口，本计划不删除或改名。源码调整优先留在 experimental 适配层，保持 experimental → raven 的依赖方向。

### 1.1 两条保证性验收准则

M-V1：Curator 根据直接提供的信息与材料生成 Memory 的初始化、信息交互和上下文组织，首次真实 provider 请求体现这些决定；interact 的更新由同一 owner 接收，并影响同一 turn 后续模型输入。

M-V2：Curator 根据修正反馈或新增信息修改既有 Memory 实现。更正的旧内容退出实际请求，未被修订的事实与工作状态保留，新增内容按新规则进入上下文；重启、会话与根/子作用域仍正确。

不能仅凭模型复述 MEMORY 标签、类实现了 initialize 或状态文件非空宣称满足。断言必须检查输入材料、候选、活动 revision、真实消息与相应状态之间的关系。针对局部基线的缺口，优先调整共同来源/组装契约，再同步各适配，不让一个基线的特殊标题成为所有实现的布局规则。

## 2. 当前事实与需要改变的边界

| 当前位置 | 已有行为 | 目标变化 |
|---|---|---|
| [公共 MemoryStrategy](../curator/harness/strategies/memory.py) | recall/retain 必需，compose/compact 可选 | 明确初始化、交互和上下文生命周期 |
| [MemoryBinding](../curator/raven_adapter/memory/contracts.py) | query/context 与 composition 两条互斥路径 | 绑定新公共操作及跨策略入口，移除旧协议分支 |
| [BoundMemory](../curator/raven_adapter/memory/runtime.py) | 宿主回调触发读写，状态按 task 保留 | 连接活动实例、初始化状态、交互分派和当前上下文 |
| [MemoryContext](../curator/raven_adapter/memory/context.py) | 原生引擎先组装，生成策略处理消息投影；原 system/developer 消息整体保护 | Memory 能决定受授权初始内容的组织；宿主必需内容单独保留 |
| [共享状态包装](../curator/raven_adapter/strategy.py) | 类型检查、锁、checkpoint、失败后恢复 owned mapping | 优先复用，只扩展本轮需要的契约 |
| [装配入口](../curator/raven_adapter/bind.py) | 构造策略与 ContextEngine，注册 Planning 和 Capability 工具 | 接入共同贡献流程及 Memory 调用位置 |

不假定新增一个方法签名就能改变运行行为。尤其不能保留“system 已经封闭，只能追加文本”的路径，却宣称 Memory 已拥有初始上下文组装能力。

## 3. 公共语义与数据归属

### 3.1 四个操作

| 操作 | 调用者与输入 | 结果与状态语义 |
|---|---|---|
| initialize(initial: InitialContext) → InitializationT | 宿主在资源可用且实际作用域已知时调用；包含任务/会话身份、实际来源、消息及恢复条件 | 建立或恢复初始上下文组织和工作状态；返回可检查的初始化视图 |
| interact(request: InteractionRequest[CommandT]) → ReplyT | 模型入口、其他策略或宿主投影的事实，经共同封装进入 | 身份与来源由宿主绑定；具体命令定义信息操作，结果区别实际更新、无需修改、拒绝和失败 |
| compose(request: ContextRequest) → ContextView | 模型调用前；读取当前请求、历史、Memory 状态及有效能力视图 | 形成当前上下文投影，显式遵守必要内容与预算约束 |
| compact(request: CompactionRequest) → ContextView | 宿主在所接入的压力点提出缩减要求 | 缩减给定投影，保留任务连续性、工具配对与必要证据；不能缩减时明确失败或报告无可用动作 |

InitT、InitViewT、CommandT、ReplyT 必须是具体可校验类型，不能用任意字典替代契约。宿主共同字段和具体策略内容分开：身份、来源及权限事实由宿主提供，业务信息布局由 Curator 生成的实现决定。

运行时组件通过构造依赖绑定；需要进入模型、日志、checkpoint 或跨进程消息的数据使用可序列化表示。不能把整个 RavenRuntime 暴露为模型命令或序列化状态。

### 3.2 初始化与组装

initialize 具有真实的初始组织责任，可以复用原生组装器、资源提供者和 Prompt 模板。它不等于仅设置 ready 标志，也不把未来每次调用的 system prompt 永久冻结。

- 初始化可确定初始内容、动态来源和交互说明的组织方式。
- 当前问题、工作目录、模型绑定、技能选择等动态值按其实际生命周期读取。
- 首次模型请求必须可追溯到初始化结果；后续请求由 compose 使用最新状态生成。
- 同一作用域重复初始化必须保留有效进度。换版可显式迁移自身状态，不能用清空状态掩盖不兼容。
- 宿主提供的必需内容与可改造的 profile、技能材料分开验证；不能依赖大段字符串标题猜测其所有权。
- 对不透明的自定义基线，只使用实际开放的组装能力。缺少必要能力时报告缺口，不静默退回纯追加实现。

### 3.3 状态与交互

保留任务共享信息、会话工作状态、单次上下文投影三个生命周期。优先复用现有 memory.json 和宿主身份，不建立并行存储系统；checkpoint 中的实际组织由实现决定，作用域隔离必须可验证。

interact 是信息操作入口，Memory 保持唯一语义和状态所有者。查询是否有副作用、写入何时算成功、重复请求怎样处理，由具体命令契约明确。自动记录经宿主转换进入相同更新规则，不能让模型伪造宿主事件来源。

compose、compact 不隐式修改原始会话或保留事实。默认生成投影；需要长期保留摘要等信息时，走显式的状态更新路径。实现缓存不等于已提交记忆，失败不能留下半完成的语义更新。

工具处理器必须通过绑定分派到活动 owner，并使用宿主给出的当前作用域。禁止为工具另建 Memory、捕获错误的默认会话实例，或把 checkpoint 副本交给 Capability 自行管理。

### 3.4 压缩与恢复

compact 的独立性来自正常组装与执行中窗口缩减的不同输入及不变量。它不会取得 Loop 的调度权。

本轮先核实并明确实际接入的压力点。生成的文本压缩与原生窗口维护只能各有一个责任来源；图片处理、provider 特定恢复和重试预算默认继续委托原生行为。未接通的路径须明确标注，不能仅凭实现了 compact 就宣称全部缩减已接管。

## 4. 与 Capability 的共同设计

本节只规定 Memory 侧责任，共同资源结构、注册规则和能力视图见 [Capability 文档第 3 节](capability-strategy-design.md)。

### 4.1 Memory → Capability：注册交互贡献

从 interact 的具体类型和 Memory 绑定导出入口声明；schema 只维护一个来源。声明带行为归属及宿主可解析的处理器绑定，实际命令不预设为固定 CRUD 集合。Memory 绑定通过宿主提供的窄注册引用调用 Capability.register；这是明确的公共调用，不能只在装配代码里保留一个 Memory 特判分支。

声明在装配期可取得，不依赖当前会话已执行 initialize。宿主先创建候选作用域的注册入口，再构造惰性 owner、提取声明并登记。登记回执的 staged 只表示进入候选；校验和激活后的有效能力视图才说明入口可供模型使用。

同一贡献重复登记应幂等，冲突明确拒绝，失败不能留下部分资源。入口绑定到活动 owner 的作用域分派，不能因构造时未初始化而另建 Memory 实例。

无需为同一入口增加一个所有实现都必须覆盖的 export_tools 或 provide 方法。可以用普通构造辅助形成贡献，再交给 register；资源构造不成为新的强制内部步骤。

initialize 在资源就绪且实际作用域已知时初始化 Memory 状态。compose/interact 不注册新的持久能力，也不在运行中的 turn 修改全局工具表；协议或入口发生变化时，由 Curator 产生新候选并整体换版。

### 4.2 Capability → Memory：有效能力视图

compose 接收宿主规范化后的本次能力视图，包含实际提供的工具定义、选中技能的引用/交付方式及入口可用性。它不自行维护一份会逐渐过期的能力清单。

Capability 的候选选择不等同于最终工具表，注册回执也不等同于活动能力。原生权限、可见性和受保护委派入口等规则落实后，Memory 看到的视图应与模型实际收到的能力一致；执行权限仍由原生派发判定。

Capability 需要的任务和状态输入从既有事实或只读视图取得，不要求先执行完整 compose。其他策略合法的上下文贡献仍保留，不通过改造 Memory 把其行为复制过来。

### 4.3 Curator 的资源管理权

Memory 可记录适合沉淀为 Skill 的材料或建议。持久 Skill 的接入、生成、修改和撤回经过 Curator 的明确候选变更；普通记忆交互不直接安装或改写能力资源。

### 4.4 与 Action、Planning 的协作

Action 可读取 Memory 提供的证据，或经其具体 interact 契约请求记录、纠正信息和调整上下文需求。Memory 保留语义与状态所有权；Action 的判断、宿主实际控制与记忆写入回执分别记录，不能把某个请求直接视为执行证据。

Planning 的当前视图可成为初始化或 compose 的输入；Memory 不另行推进计划。需要计划修订时走 Planning 的公共操作。依赖使用共同的窄接口、宿主作用域与观测边界，不注入整个 owner 集合，也不在持锁状态形成互相等待的调用环。

模型请求和宿主投影的实际事件进入 interact 时保留来源区别。初始化/compose 使用其他策略的内容贡献，必须知道该内容是建议、领域事实还是宿主结果；来源变化和过期不能通过重复拼接隐藏。

## 5. 运行时方案比较与验证关口

| 方案 | 复杂度、理解与维护成本 | 风险与约束满足情况 |
|---|---|---|
| 实验适配层接入新语义，委托原生未改行为 | 中等；改动集中，可沿原生调用链追踪 | 推荐；需验证首次组装、选择后 compose 和压力处理都具有真实调用点 |
| 每类基线生成完整 ContextEngine | 生成与测试成本高；每个实现都需解释历史、资源和生命周期 | 能控制组装，但容易重复或遗漏原生行为 |
| 生成实现整体接管原生 MemoryModule | 控制面最大，阅读与维护成本最高 | 会扩大到预算、窗口维护和模型切换，超出当前必要范围 |

推荐第一种。假设是现有 ContextEngine、原生 MemoryModule 的委托接口及合法宿主调用点能承接所需行为。先用受控 provider 做小验证；若只能通过不可靠的 Hook 消息原地改写才能实现，应重新比较接入方案。

验证必须覆盖最终 provider 请求，特别是 Capability 选择之后的 compose，以及同一 turn 内 interact 后的下一次调用。不得把“下一 turn 才更新”作为未记录的降级。

2026-09-28 的仓库外小验证已证明一个可用消费位置：在原生 ActionModule.decide 的委托边界，仅为本次模型调用生成消息副本；将原生委派保护置于投影之前，投影读到的工具集合与最终 provider 请求一致。真实 Loop 中工具更新状态后，同一 turn 的第二次调用看到新投影，原生指导仍在，原始 transcript 不累加投影内容。该验证仅覆盖普通 Raven 的最终请求边界，不证明 initialize、源内容拆解、compact、ACP 产品或新公共协议已经实现。

实施时还需核对投影后的预算、TokenWise 与缓存标记是否继续对应实际请求。初始内容组织必须从明确的来源与所有权表达取得，不得因为最终投影可行就省略首次组装和不同基线的验收。

来源级探测进一步验证：相同 SegmentBuilder 包装可以在普通 Raven 与 raven-code launcher 渲染的产品基线上改变 bootstrap 来源顺序/表达，并保留 identity 和产品 profile 内容；来源文件更新反映在下一 turn 的实际 system 内容中。该实验依赖 ContextAssembler._builders/_phase_a/_phase_b，不能直接作为生成策略的公共依赖。M0 需把这些事实转成统一的来源描述与受控构造边界，明确每个来源的 owner、可改造范围、动态更新及保护要求；未知自定义引擎应报告能力缺口。完整 ACP 传输、initialize 生命周期与 Curator 驱动修订仍须后续验收。

## 6. 三层实施计划

### 第一层：协议与运行时

| 步骤 | 改动与交付 | 验收 |
|---|---|---|
| M0 | 验证实际调用点，固定输入输出、作用域、register/回执及有效视图字段 | 普通 Raven 和一个现有 ACP 产品基线都能观察首次/后续请求路径；登记与激活不混淆 |
| M1 | 修改公共 MemoryStrategy、docstring 和 MemoryBinding，更新仓库内消费者 | 新接口类型可检验；旧 recall/retain 不再是公共要求 |
| M2 | 实现初始化、初始上下文控制、逐次 compose 和声明的 compact 接入 | 首次请求及交互后的同一 turn 请求采用正确上下文 |
| M3 | 通过 Capability.register 连接 interact，复用锁、checkpoint 和观测 | 模型调用和组装共享正确 owner；登记幂等、冲突拒绝及重复/失败/恢复语义成立 |
| M4 | 验证根与子 Harness、基线差异及与原有贡献的共存 | 无错误实例共享、内容重复或基线能力遗漏 |

主要修改 [公共协议](../curator/harness/strategies/memory.py)、[绑定模型](../curator/raven_adapter/memory/contracts.py)、[运行包装](../curator/raven_adapter/memory/runtime.py)、[上下文适配](../curator/raven_adapter/memory/context.py) 和 [装配入口](../curator/raven_adapter/bind.py)。

共享 strategy.py、inference.py 按联合依赖契约扩展。Planning 现有工具和 Action.handle_request 与 Memory 一起验证 register 的通用性；Planning 保留其 initialize/view/revise 行为，Action 按配套方案实现。

### 第二层：Curator 信息组成与传递

1. 更新 memory target 的 schema、effect、state 和 knowledge，包含 interact 声明到 register 的真实调用与回执语义。沿用 Target.describe 自动展开，不手工复制第二份 schema。
2. 更新公共 Memory 说明、Raven 接入说明、上下文资源说明及涉及旧接口的生成提示词，明确初始化资源、调用时机、结果消费者和未支持路径。
3. 增加实际初始化、交互、组装与能力视图的可查询证据，关联 task/session/turn、Harness revision 和必要的状态/资源引用。复用 Recorder、Inspection 和 read_observation。
4. 从整轮 Sessions 显式传入员工执行证据，贯穿 iteration → workflow → composition → local generation；对子作用域按真实关联保留证据。不能只读取未参与试炼的主 Worker.last_execution。
5. 新证据参与生成输入身份；恢复与候选复用须核实来源仍一致。保持评价者参考答案、私有评分与执行证据的边界。
6. 修正把“未运行/状态未变”一概当作缺陷的指令，改为对照预期触发条件核查。

保留现有理解、选择、设计、实现、修复阶段，源码快照、分页查询、阶段 history 与 checkpoint 机制。只更新受影响内容和连接点，不重做阅读框架。

主要涉及 targets/memory.py、harness/reference/memory.md、harness/reference/strategy-prompts.md、raven_adapter/reference/memory.md、reference/context-and-resources.md，以及 generation/prompts 中相关段落。证据连接涉及 iteration/run.py、curator/workflow.py、composition/run.py 及必要的输入身份代码。

### 第三层：验证、资料与收尾

| 验收场景 | 必须成立的结果 |
|---|---|
| 首次初始化 | 首次真实 provider 请求体现新组织方案，保留必要基线内容 |
| M-V1 材料定制 | 用户材料、初始化组织、交互说明和实际请求存在可核对的来源关系 |
| M-V2 反馈修订 | 更正与新增输入改变指定行为；未变事实、进度及作用域保留 |
| 交互后刷新 | 工具成功处理后，同一 turn 的下一次模型输入使用新状态 |
| 多次组装 | 不重复累加交互说明或知识块，不造成工具调用/结果孤立 |
| 基线差异 | 普通 Raven 与现有 ACP 产品基线无需相同 profile 格式 |
| 能力一致性 | 提示中的入口、技能交付与有效能力视图一致 |
| 注册与生效 | staged 回执不提前暴露工具；候选激活后才进入有效视图 |
| 重复登记 | 相同 Memory 入口幂等，不产生重复工具或另一个 owner；冲突明确拒绝 |
| 运行期边界 | compose/interact 和会话初始化不修改冻结中的全局工具表 |
| 恢复与换版 | 重启、重复初始化和新协议内修订保留有效状态 |
| 作用域 | 会话与父子 Harness 不串用工作状态 |
| 失败与预算 | 非法交互、初始化失败、无法压缩不伪装成成功 |
| 信息链 | 契约、查询结果与本轮实际证据完整进入生成阶段 |
| 跨策略协作 | Action/Planning 经共同接口交互，Memory 状态与原始执行事实不被复制或混同 |
| 未选择 Memory | 原基线路径正常，其他策略行为不被改变 |
| 候选失败 | 旧产物、受管理内容和状态可以按现有机制恢复 |

优先更新现有 tests/test_harness_curator_strategies.py、test_harness_curator_contracts.py、test_harness_curator_generation.py、test_harness_curator_workflow.py、test_harness_curator_composition.py、test_iteration_run.py、test_simulation_replicas.py 和 fixtures/harness_curator。

集成验证沿用 tests/integration/test_harness_curator_prompt_e2e.py、test_harness_curator_strategies_e2e.py、test_harness_curator_composition_e2e.py 和 test_harness_curator_hosting_e2e.py。测试按风险选择，不为私有方法顺序或某个示例字段写约束。

拟执行命令；不是已经执行通过的声明：

```bash
uv run pytest tests/test_harness_curator_*.py tests/test_iteration_run.py tests/test_simulation_replicas.py -x
uv run pytest tests/integration/test_harness_curator_prompt_e2e.py tests/integration/test_harness_curator_strategies_e2e.py tests/integration/test_harness_curator_composition_e2e.py tests/integration/test_harness_curator_hosting_e2e.py -x
make check-source-language
make check-large-files
```

离线通过后，使用用户已授权的 DeepSeek 官方 V4.1-Flash 验证 M-V1/M-V2，覆盖首次生成、纠正反馈和新增输入。模型使用与证据要求遵循联合标准；API 连通性和旧接口测试不能替代新协议实际生成与执行效果。不扩展为无关业务案例挖掘。

## 7. 联合顺序、兼容与风险

实施顺序以联合标准 S0—S6 为准：共同契约与 M0 → Capability 共同资源路径 → 完整 Memory 生命周期 → Action 与跨策略协作 → 信息链 → 根/子与真实模型验证 → 与实现分开的审查。

- 不新增旧公共协议兼容层，仓库内代码、测试和材料一次同步。旧运行产物不静默转换，协议不匹配在构造/验证阶段清楚报告。
- 同一新协议内的状态保留和激活失败恢复是必要行为。存量数据若需迁移，先明确具体格式和范围；不批量改写或删除已有状态。
- 共享绑定改动可能影响其他策略，回归覆盖公共包装和默认基线。
- 初始内容重组可能破坏原有资源与插件贡献，以最终请求和基线对照验证。
- 交互入口的 schema、处理器和产物必须同版激活，避免旧 handler 连接新状态。
- 完整初始化与逐次组装的接口可行性由 M0 证据决定；未获支持时更新方案，不把遗漏隐藏到后续阶段。

完成后，将长期有效的职责、接口和运行方式转入现有设计/参考资料及必要的 CONTEXT.md 定义，更新本计划状态并归档临时结论。本文不自动成为 Curator 默认实现示例或运行契约；只有已实现的协议和接入材料进入生成说明。
