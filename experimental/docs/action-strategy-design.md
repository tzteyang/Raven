# Action 策略设计与实施方案

状态：历史设计与阶段验收记录，描述四策略入口收敛之前的协议演进，不作为当前生成接口说明。当前有效契约见 [design.md](design.md)、[候选准备](../curator/raven_adapter/reference/preparation.md)及各策略源码；本文历史测试数不证明新入口或真实案例已经验收。

本文与 [Memory 计划](memory-strategy-plan.md)、[Capability 方案](capability-strategy-design.md) 联合实施，遵循 [experimental 开发准则](../AGENTS.md)。跨策略共同语义、两条价值准则和完成审计以 [联合实施标准](strategy-interaction-plan.md) 为准。

本文保留方案取舍与实施顺序。最终接口见[公共协议](../curator/harness/strategies/action.py)、[事件和控制类型](../curator/harness/action.py)及[运行接入说明](../curator/raven_adapter/reference/action.md)。

## 1. 职责、目标与非目标

Action 依据行为请求与执行事实，决定行为怎样推进，并表达判断依据、给调用者的反馈及需要宿主落实的控制。它具有两个主要入口：harness 主动交付事件，agent 主动提交请求。发起方式与 model_input/model_decision/tool_interaction/execution_control 的作用位置是不同维度，保留现有通道描述。

公共主要操作使用 handle_event、handle_request。它们不是两个任意字典入口：公共类型还规定事件语义、来源、状态归属、控制范围及实际应用结果。Curator 定义领域规则和任务相关请求，不必重新发明待执行/已执行、拒绝/失败或登记/生效等共同概念。

V1：从直接输入的行为规范、材料或资源，生成实际生效的监督和主动请求机制。V2：根据实际执行、纠正反馈或新增输入，修订这些机制，保留仍然适用的规则和状态。两者必须通过实际行为验证。

Action 可以与 Memory、Planning、Capability 协作，但不天然高于其他策略。各状态仍由其 owner 维护；原生权限与 Loop 执行由宿主负责。保留 Raven 的执行、工具、权限、Hook、ToolGate、checkpoint、验证与激活机制。任意热注册、新子代理调度、跨策略分布式事务和通用事件总线不属于本方案。

## 2. 当前事实及需要调整之处

| 位置 | 已有行为 | 对目标的限制 |
|---|---|---|
| [ActionStrategy](../curator/harness/strategies/action.py) | assess/recover，guide 可选 | 按评估行为、失败场景和指导输出混合分组；没有 agent 请求的显式入口 |
| [ActionBinding](../curator/raven_adapter/action/contracts.py) | 翻译 StepView、领域决定和终局回复 | 事件来源、支持效果与请求工具尚无共同表达 |
| [BoundAction](../curator/raven_adapter/action/runtime.py) | Participant.review、system_addendum、salvage | 主要覆盖宿主回调，不能仅凭返回决定证明实际效果 |
| [Action targets](../curator/raven_adapter/targets/action.py) | review/hooks/tool_gates/services 已可生成 | 实现手段存在，但与单一策略 owner 的协作仍需明确绑定 |
| [PlanReader](../curator/raven_adapter/planning/contracts.py) | 按会话读取实际计划副本 | 是有效的只读协作入口；不可复制计划状态，也不等于已有任意跨策略修改能力 |
| [原生 review 合成](../../raven/agent/harness/participants.py) | 首个非接受裁决起作用，参与者异常按无意见处理 | 不适合作为必须阻止执行的唯一机制 |
| [原生回退应用](../../raven/agent/loop/turn_path.py) | 回退受预算约束，不撤销已发生的外部效果 | 需要区分要求重试与真实应用结果 |
| [ToolGate](../../raven/contracts/tool_gate.py) | 逐调用拒绝，异常也拒绝当前调用 | 可以承担强制检查，但不等于结束整轮或授予权限 |

这些是当前行为事实，不全部属于缺陷。改动应让生成策略按真实目标选择合适消费者，并共用规则与状态；无需重写所有原生扩展点。

## 3. 公共协议与细粒度语义

### 3.1 两个主要操作

目标形状如下，类型名用于设计说明，实施前固定具体字段：

```python
async def handle_event(self, event: ActionEvent) -> ActionDecision:
    ...

async def handle_request(self, request: ActionInteraction[CommandT]) -> ActionResponse[ReplyT]:
    ...
```

handle_event 处理宿主交付的观察和执行事件；handle_request 处理 agent 经已注册入口提出的领域请求。两者都可以产生控制意图，也可以只提供反馈或决定无需干预。请求处理不自动取得比事件处理更高的权限。

实际请求类型 ActionInteraction 继承共同 InteractionRequest，并增加宿主支持的控制集合；它与 Raven 原生用于模型推理调用的 ActionRequest 不同。具体事件、决定和回执定义见 harness/action.py，生成材料应交付这些实际类型。

公共面提供两侧，但具体绑定可以只启用所需的一侧。已启用的方法必须具有真实实现、具体可校验类型和消费路径。未启用、事件不匹配、处理成功无干预、业务拒绝和运行失败分别表达，不能通过空方法或模糊 None 混同。

旧 assess/recover/guide 不保留无需求的兼容入口。恢复与指导能力由新事件/请求和结果表达。不要规定实现内部必须调用 _assess/_recover/_guide；同一规则可以委托既有组件，也可以由生成实现组织。

构造与恢复沿用显式资源绑定和 checkpoint。当前不预设 initialize、view 等新方法；若接入验证发现存在不能由现有生命周期承担的独立准备或只读消费需求，应修改公共协议并同步所有消费者，而非私藏在首个事件中。方法数量不能成为排除必要行为的理由。

### 3.2 宿主事件

公共事件采用可校验的类型与明确区分字段，避免自由字符串和 Any 数据袋。事件携带共同身份、来源、关联行为/请求、证据及当前宿主支持的效果范围。领域材料允许具体扩展，但不可改写宿主事实。

| 事件族 | 关键事实 | 语义限制 |
|---|---|---|
| 行为提案 | 模型提出的待执行调用或待交付内容 | 尚无该行为的执行结果；不能把提案视为证据 |
| 执行结果 | 成功、失败、拒绝、跳过或尚不能确定的真实结果 | 必须关联实际调用；不能追溯性地阻止已经发生的效果 |
| 进展观察 | 当前目标、行动条件、可用预算和实际进展 | 无需干预是合法结果；观察不等于失败 |
| 执行受阻/终止 | 正常路径受阻，或宿主进入特定终止路径 | 明确仍可恢复还是仅允许终局答复 |
| 控制应用结果 | 先前控制被采纳、拒绝或不支持 | 请求次数不等于已应用次数；不能自动递归触发无限控制链 |

事件族是共同语义，不是对 Raven Hook 的逐项复制，也不表示所有宿主都提供全部事件。绑定必须列出实际覆盖、可能被提前退出跳过的情况和交付保证。没有真实来源的事件不得伪造。

### 3.3 agent 请求

公共封装提供宿主绑定的身份和关联信息；模型工具参数只包含 CommandT 规定的领域内容。Curator 可定义交付检查、阻塞报告、约束查询等命令，不强制通用 CRUD 或固定工具名称。

请求入口经 Capability.register 发布，schema 来自实际请求类型；handler 由作用域分派定位到活动 Action owner。Capability 不解释 Action 命令，Action 也不另建执行注册表。

请求中的“已完成”“已测试”是模型声明，直到有实际证据才可作为执行事实。agent 可选择不调用自检入口，因此必须的检查仍需宿主执行路径承担。

### 3.4 结果与控制语言

ActionDecision/ActionResponse 的共同结构区分领域答复、诊断依据、模型可见指导和控制意图。控制至少明确目标对象、目标范围和适用条件；选择互斥的终结控制，不能返回同时继续与结束的矛盾结果。

第一批控制类别由已验证消费者决定，包括无干预、指导、拒绝待执行行为、修订提案/请求恢复以及结束当前支持范围。不是每种事件都允许全部控制。阶段不支持、目标过期或预算不允许时应有明确结果，不静默按接受处理。

“无干预”不扩大原生权限；“拒绝调用”不自动阻断全部兄弟调用；“终止当前 turn”不等于整个任务成功。工具结果、批次阻断与 turn 控制的原生区别必须在适配中保留。

语义决定与实际应用回执分开。回执说明控制身份、目标、应用状态和原因；状态需要区分 requested/applied/rejected/unsupported。返回 requested 不能向模型宣称效果已发生。终局之后不能保证再次调用策略时，以宿主记录为真实来源，供 Inspection 和后续 Curator 修订读取，不虚构补发事件。

### 3.5 状态、重复与失败

保留按 session 的 Action checkpoint；任务和 revision 由宿主绑定。工具请求、事件判断与逐调用 gate 使用同一活动 owner 的规则，不能构造互不相干的监督实例和交互实例。

事件、请求和效果具有可关联标识，重复交付不应重复提交同一语义更新。记录已观察、已请求和已应用时机，不能在控制尚未落实时把状态推进到“已经完成”。失败恢复仅覆盖 owned mapping，外部作用不随之回滚。

严格检查路径不能依赖 Participant 吞异常的默认行为。按支持声明选择 ToolGate 或已证明的强制消费者；故障有可观察的拒绝/停止结果。自愿指导则允许明确表达缺失、不适用或失败，但不得伪装成判断通过。

## 4. 跨策略协作

共同身份、生命周期与调用边界见 [联合标准第 3 节](strategy-interaction-plan.md)。本节规定 Action 的具体使用。

| 关系 | Action 可以做什么 | 状态与决策归属 |
|---|---|---|
| Memory | 读取证据，提交记录或上下文调整需求 | Memory.interact 决定如何更新，compose 决定实际输入；Action 不改写其 checkpoint |
| Planning | 读取当前计划和条件，提出修订请求 | 复用已有 PlanReader；需要修改时经 Planning.revise，不能另存并推进一份计划 |
| Capability | 读取有效能力，表达行动需要，注册自己的请求入口 | register/select 及资源生命周期由 Capability 契约承担；持久资源变更仍由 Curator 决定 |
| 宿主 | 提出受支持的拒绝、修订和终止要求 | 原生执行器、权限及组合规则决定实际后果 |

只读访问、目标 owner 的公共修改操作和宿主控制分开。采用具体、窄的依赖声明，不暴露任意反射式 call(strategy, method, kwargs)。同一组件可以承担多个策略角色，但不能借此绕过类型、作用域和实际效果记录。

跨策略顺序与失败不被隐去：例如 Memory 已记录事实而 Planning 修订失败，Action 的失败不能声称两者均已回滚。记录各项结果，下一次基于真实状态继续。对可能回调自身的依赖在绑定/调用边界拒绝或显式安排，避免 owner 锁形成等待环。

运行中的 Action 不直接生成、采用或撤回持久 Skill。它可以把材料和建议交给 Curator，随后走候选注册、校验和统一激活。Action 对其他策略没有隐含优先级；不兼容决定按宿主明确的组合规则处理，并留下结果。

## 5. Raven 接入与真实消费者

### 5.1 事件路径

- 模型决策前的实际情境可成为进展观察，指导由模型输入消费者落实。与 Memory.compose 配合，验证最终 provider 请求，不只检查 addendum 返回值。
- 未执行工具批次和待交付文本可以成为提案事件。原生 review 仍支持接受、有限重采样和结束；必须解释预算耗尽时的结果。
- 强制的逐调用规则接入 ToolGate，并调用同一 owner 的规则。验证原生权限仍先按自己的顺序处理，不新增旁路执行。
- 正常迭代结果与失败路径按真实可达性投影；终局 salvage 只能消费当前路径支持的结果。provider 错误、批次 abort 和提前退出不能被误报成正常 after_iteration。
- 对用户可见输出有检查要求时，核实流式草稿何时被释放、文件/工具效果何时发生。输出已交付之后的判断不能计为执行前检查。

### 5.2 请求与控制应用

请求工具通过共同注册进入原生工具路径，使用当前作用域的 Action owner。回复经原生工具结果返回模型；其携带的控制意图只在已验证的消费点生效。

接入验证必须证明同一模型响应中多个工具调用时的语义：某个请求是否阻断后续调用、是否等到批次完成再应用、是否仍有下一次模型调用。不能用“下一轮再处理”掩盖要求立即阻断的约束。

需要待应用控制状态时，由共同的 turn/调用关联结构保存，并明确过期、取消、换版与失败规则；不使用某个 handler 私有的永久队列。实际应用结果进入 Recorder，并在可达时作为后续事件输入。

### 5.3 阅读与生成信息链

更新 action target 的公共协议、binding schema、支持事件、控制范围、依赖与参考材料，沿用 Target.describe 的实际源展开。保持 Curator 当前阶段、查询、history 和修复流程。

Curator 应能从输入中回答：规则来源是什么；修改哪种行为；由哪个事件/请求触发；依赖哪些真实证据；在哪个消费者生效；失败和预算耗尽时发生什么；更新后保留什么。无需要求它默认阅读一份完整参考实现。

实际记录关联请求/事件、策略结果、原生应用与后续行为。修订读取相关会话、试炼副本和子 Harness 的证据，不只使用主 Worker.last_execution。对“机制未运行”的判断必须核对预期触发条件，不能把未触发一概视为缺陷。

## 6. 方案比较与实施顺序

| 方案 | 收益与成本 | 结论 |
|---|---|---|
| 各场景生成原生 review/gate/tool，并显式组合领域委托 | 可使用全部现有能力，但 Curator 每次都要正确连接来源、状态与控制消费者 | 可行，生成与修订成本较高，不作为最终公共面 |
| 公共事件/请求与结果契约，共同 owner 绑定到原生消费者 | 入口清楚，共同规则可检查；需要完成真实消费者与跨策略绑定 | 推荐，符合两条价值准则 |
| 生成策略全面接管原生 Action 角色及逐调用调度策略 | 控制集中，能统一所有决策和派发，但迁移与验证范围显著增加 | 可行，当前没有足够需求承担这部分原生替换成本 |

推荐方案不依赖固定的私有模板步骤。公共语义若不能承接已确认需求，应在共同层调整，再同步各绑定；不靠某个 Action 特判绕开。

| 阶段 | 实施内容 | 验收关口 |
|---|---|---|
| A0 | 核实所有事件来源、请求工具及效果消费者；固定类型和支持矩阵 | 真实 Loop 上证明提案/结果/终局区别、执行前约束和请求控制时机 |
| A1 | 修改公共协议、docstring、ActionBinding、类型校验与启用声明 | 已启用方法无空壳；非法来源、结果和不支持效果可检查 |
| A2 | 接入 handle_event，复用原生 review/gate/终局路径 | 实际模型指导、工具阻断、有限修订和终局结果正确 |
| A3 | 经 Capability.register 发布 handle_request | schema、处理器、活动 owner、回执和冻结期一致 |
| A4 | 接入声明的 Memory/Planning/Capability 协作 | 正确作用域、唯一状态 owner、部分失败、无回调死锁 |
| A5 | 更新 Curator 阅读材料、Inspection 和修订证据 | 原始输入与反馈都能生成正确候选，真实结果进入下一次修订 |
| A6 | 根/子、基线、回归与真实模型验证，独立审查 | V1/V2 及第 7 节全部有直接证据 |

主要改动集中于公共 Action、raven_adapter/action、targets/action、共同绑定/资源/观测边界及相关参考资料。原生实现继续委托；必要的统一适配改动不得散落为多个策略自己的后门。

## 7. 行为验收与反例

| 场景 | 必须观察到的结果 |
|---|---|
| A-V1 首次定制 | 输入的行为条件进入生成规则，真实违规提案被纠正或阻止，合法提案可以执行 |
| 主动请求 | agent 请求经过实际工具，处理回到正确 owner，答复与实际控制不混淆 |
| 自愿入口遗漏 | 模型不调用自检工具时，必须的约束仍在执行前成立 |
| 指导与纠正 | 指导或 correction 实际进入后续 provider 请求，诊断 reason 不冒充已注入内容 |
| 强制检查失败 | 依赖失败或处理异常不能默默放行本应受保护的调用 |
| 控制限制 | 不支持的效果、预算耗尽、终局重试请求都有明确真实结果 |
| 执行证据 | 模型声明、工具提案、工具拒绝和实际成功分别处理 |
| A-V2 修正反馈 | 相同正反例在改版前后体现指定变化，未被修改的约束继续成立 |
| A-V2 新增输入 | 增加条件时保留既有有效行为，依赖缺失有明确反馈 |
| 跨策略 | 计划修订、信息更新和能力读取各归其 owner；可解释部分失败，无状态副本 |
| 同一批工具 | 请求导致的批次/turn 控制与声明一致，没有先产生外部效果再声称阻断 |
| 会话与父子 | 两会话、根/子和换版不串用 handler、状态或控制待办 |
| 激活失败 | 恢复旧候选、受管理内容和自身状态，不伪造回滚外部效果 |
| 未选择 Action | 原有原生行为与其他策略保持可用 |

优先修改已有 tests/test_harness_curator_strategies.py、test_harness_curator_contracts.py、test_harness_curator_participants.py、test_harness_curator_generation.py、test_harness_curator_workflow.py，以及 fixtures/harness_curator。集成验证沿用 tests/integration/test_harness_curator_strategies_e2e.py、test_harness_curator_prompt_e2e.py、test_harness_curator_composition_e2e.py、test_harness_curator_hosting_e2e.py 和 test_harness_curator_real_llm.py。

真实模型验收使用授权的 DeepSeek V4.1-Flash，并遵守 [联合验证标准](strategy-interaction-plan.md)。首次生成、修正反馈和新增输入都需要实际执行断言；不能仅用 ACTION:cobalt 等标签变化代替行为裁决正确性。

完成后更新长期设计与参考资料，清除旧公共方法要求，同步仓库内调用者和测试。旧产物遇到不匹配协议应在验证阶段清楚失败；新协议内的状态保留、明确迁移和激活恢复继续保证。单独安排一次脱离实现思路的需求审查，逐项核对 V1/V2 和共同约束。
