# 四策略代码生成与 Target 收敛评审

Planning 更新：本文中保留 initialize/view/revise 的决定已由 [Planning 交互实施方案](planning-strategy-plan.md) 取代；当前协议为 initialize/interact，工具与跨策略联动随之迁移。

状态：入口收敛已进入代码，本文保留迁移前评审与实施依据；旧 Target 表描述被替代的设计，不是当前生成目录。现按[说明与案例入口对齐计划](curator-docs-and-scenario-alignment-plan.md)继续实施。当前接口见 [design.md](design.md) 和[候选准备](../curator/raven_adapter/reference/preparation.md)。

原评审依据：迁移前的公共策略、31 项 Target 声明、生成 schema、Raven adapter、父子 Harness 组合代码及已留存的真实输入测试。遵循 [experimental 开发准则](../AGENTS.md)。本文中的 Curator 指实验层的 Harness Curator；Raven 原生 ContextConfig 中的 curator 指上下文窗口管理组件，二者不同。

## 1. 结论与目标边界

用户要求的主链是：**LLM-based Curator 生成或修订四策略实现，由 adapter 将策略行为接入 Raven 原生 Loop。** 四策略应是语义决策的入口；Skill、Prompt、Playbook、配置和组件可以作为实现的资产、依赖或结果，但不能再成为绕过策略实现的平行定制入口。

迁移前实现允许从 31 个 Target 中选择原生配置、文件或组件，只在选中 `*.strategy` 时要求生成策略类。这是输出契约和装配机制允许的行为，不只是提示词引导不足。把提示词改成“优先写策略类”，不能建立用户要求的架构约束。

建议将可选择的语义生成 Target 收敛为四个 `*.strategy`，保留 Target/Declaration 已有的授权、schema 和阅读材料生成机制。其余 27 项退出平行的语义生成目录，分别成为策略负责的行为、策略资产、正式宿主扩展契约或宿主配置。**27 个入口退出不等于 27 项原生能力删除，也不等于原来的四组公共方法已经覆盖它们。**

重构涉及核心表达边界，规模为中等偏大；主要修改集中在实验层。原生 Loop、工具执行器、Playbook 执行器、权限、会话和模型调用不需要因此重写。复用代码较多，但生成协议、准备时序和父子组合必须一起迁移。

两点边界：

- 每次修订只修改有变化的策略，允许继续使用已安装的实现或明确的原生基线。不要求每次重写四个类，也不强迫无业务变化的策略生成样板代码。
- 代码可以读取数据、返回结构化声明、调用宿主文件与注册服务。代码优先不等于把 Skill 正文写成 Python 字符串，也不要求策略重新实现文件复制、ToolRegistry 或 MCP 客户端。

## 2. 迁移前的可核查状态

| 事实 | 代码入口 | 对评审的意义 |
|---|---|---|
| Artifact.values 接受所选 Target 的 payload，files 提供配套源码和文本；remove/remove_paths 管理撤回 | [artifact.py](../curator/harness/artifact.py)、[declaration.py](../curator/harness/declaration.py) | 生成契约从根本上允许非策略入口；文件和撤回机制本身仍有价值 |
| 目录共 31 项，实际授权再由具体 Declaration 收窄 | [targets](../curator/raven_adapter/targets/__init__.py) | 不能把“目录可选”说成每个 Worker 都有全部权限 |
| 只有被选中的四种策略实现必须继承公共协议；原生组件和资源另走契约 | [生成规则](../curator/generation/prompts/common/contracts.md) | 当前规则明确允许这些平行路径 |
| adapter 遍历 CapabilityBinding.resources 和 capability.resources，再调用 register；无自定义类时由 adapter 的 NativeCapability 承接 | [bind.py](../curator/raven_adapter/bind.py)、[capability/runtime.py](../curator/raven_adapter/capability/runtime.py) | 当前资源采用的驱动者可以是宿主读取声明，而非 Curator 生成的 Capability 代码 |
| Skill 在 build_runtime 前暂存，实际安装在原生 runtime 构造后完成 | [bind.py](../curator/raven_adapter/bind.py)、[catalog.py](../curator/raven_adapter/capability/catalog.py) | 资源准备不能塞进首次运行期 select，也不能滥用 Memory.initialize |
| prepare 名称已用于 BoundStrategy 的宿主准备过程，尚不是生成 Capability 的公共资源准备方法 | [capability/runtime.py](../curator/raven_adapter/capability/runtime.py)、[strategy.py](../curator/raven_adapter/strategy.py) | 后文提出的准备契约是新增设计，不能以现有同名 wrapper 当作已经支持 |
| 父层先 preview_nodes，再按节点需求生成子候选；parent_materials 仅直接读取 bootstrap_files/skill_files | [composition/run.py](../curator/composition/run.py)、[worker.py](../curator/raven_adapter/worker.py) | Playbook 是组合输入；目前 capability.resources 也不在该 parent_materials 提取路径里 |
| prompt.resources 加载、校验和描述 Prompt，本身不执行模型调用或决定注入位置 | [prompts.py](../curator/raven_adapter/prompts.py) | 它主要是资产索引，不能与直接生效的配置 Target 等量齐观 |

现有真实案例与代码一致：旅行专家案例选择了 capability.resources、memory.prompt 和 planning.strategy；源码生成只发生在 Planning。文件树、单文档、消息三种输入的定向 Skill 测试，将出口限定为 capability.resources/strategy，结果都选择了资源声明，没有生成 Capability 类。这证明资源机制可工作，也证明当前输出契约没有要求策略代码承担这些变更；定向测试不用于估计不限出口时的选择概率。

这些测试不证明新架构已经成立。既有联合验证记录保留在[前一版计划](strategy-interaction-plan.md#9-最终验收记录)，其中真实 Memory 测试的原始失败和回放复验仍按原记录表述。

## 3. 三种实质方案

| 方案 | 实现与理解成本 | 约束满足与主要风险 |
|---|---|---|
| A. 将全部能力展开为四策略的公共语义方法 | 调用关系直观；方法、输入和生命周期数量明显增加 | 可满足代码入口要求，但易将 Raven 配置、后台服务和插件细节塞进通用协议；不同基线成本高 |
| B. 保留语义核心，增加必要的公共方法、受保护扩展点与正式宿主契约，均归策略实现所有 | 初期要明确调用关系与准备时序；运行期接口较集中 | 推荐。代码负责规则和资源决策，adapter 负责机制；风险是把扩展契约写成无边界的万能配置口，或给所有实现强加同一内部算法 |
| C. 四个 Raven 专用生成策略直接实现原生组件协议，由 adapter 装配 | 少一层语义翻译，但每个生成实现需理解更多原生接口和生命周期 | Raven-only 条件下可行，保留代码入口；跨 Harness 复用和生成稳定性较弱。若通用协议是硬约束，则不满足该部分要求 |

推荐 B，基于当前既希望四策略语义清晰、又希望适配不同 Harness 基线的要求。如果未来只支持单一 Raven 基线且明确接受原生接口耦合，C 的相对价值会增加。A 适合愿意承担较大的统一接口、并能为每个公共操作证明跨宿主语义的情况。

不构成独立可行方案的做法：仅修改提示词；让四个空类包住原来的 31 份自动生效声明；新增 `_configure_raven(dict)` 并把原 Target 原样放进去；为此再写一套 Loop。

## 4. 公共协议与内部协议怎么划分

| 层次 | 谁依赖它 | 应承诺什么 | 示例 |
|---|---|---|---|
| 公共语义协议 | 生成策略、跨策略调用者、不同宿主 | 行为含义、状态归属、输入输出、失败与副作用 | Memory.initialize/interact/compose；Capability.register/select；Action.handle_event/handle_request |
| 正式宿主扩展契约 | 同一生成策略类与 adapter | 支持声明、调用时机、作用域、类型、授权与结果消费者；不另设平行生成 owner | 候选准备、Planning 的可委派结构导出、原生后台组件的受管依赖绑定 |
| 约定的受保护扩展点 | 策略的公共方法/可复用基类与具体生成实现 | 被哪个方法调用、可替换的子职责、输入输出、默认行为与副作用 | prepare 调用 `_prepare_skills`，handle_event 调用 `_handle_proposal`；名称仅为候选示例 |
| adapter 内部实现 | adapter 自身 | 对原生实现的转换和生命周期封装 | 将原生 HookContext 转成 ActionEvent、复制 Skill 包、构造 ToolGate |
| 生成实现的私有辅助函数 | 该实现自身 | 无框架约定，作者自由组合 | `_build_prompt`、`_load_notes`、局部内容格式化 |

**只要 adapter 会按约定调用、Curator 必须按约定实现，它就是生成侧的正式契约。** 即使不放在通用 Strategy Protocol 中、即使名字带下划线，也不能省略文档、类型、时序和测试。“内部”应指它不作为跨策略业务操作，不能指它不需要稳定定义。

此前仅将内部方法视为实现者自由拆分的 helper，遗漏了“由公共方法调用、允许具体实现覆写的受保护扩展点”。这类约定有价值，应逐项评估。当前尚无充分依据强制所有 Memory 实现使用同一串 `_xxx` 方法完成 initialize；这不排除在具备稳定复用价值时提供可选基类或局部扩展点。

公共协议和受保护扩展点是不同粒度，不必二选一。比如资源准备有独立生命周期，适合成为正式入口；该入口内部可以再委托 `_prepare_skills` 与 `_prepare_tools`。Curator 继承公共方法并实现这些受保护方法，也属于策略代码生成，前提是实际行为经该策略类产生。只在 Protocol 中列出下划线方法，不会自动产生调用链；必须有实际公共方法/基类调用它们。adapter 直接调用的下划线方法则属于上表的宿主扩展契约。

增加方法的判据：独立调用者、独立生命周期或新的可观察语义，支持增加正式入口；同一入口内稳定且可复用的子职责，支持受保护扩展点；仅是输入类型增加或局部代码较长，先扩类型或由实现自由拆分。约定扩展点时须写清副作用和覆写规则，未启用可以省略，已启用但缺失实现不能静默成功。不以旧 Target 数量决定方法数量。

准备阶段是所有宿主都会遇到的生命周期问题，至少应对生成者公开。Capability 的资源准备还直接属于其核心语义，应纳入 Capability 的正式公共能力；Raven 特有的构造参数、组件装配和配置翻译则放入宿主扩展契约。不要用“内部协议”把核心资源决策再次藏到 adapter。

## 5. 31 项 Target 逐项处置

“退出”均指退出独立生成入口。标为“缺口”或“权限收窄”的部分不能作为等价重命名实施。名称保留的四项也需要收紧 binding payload，防止业务配置继续绕过类实现。

| # | 现有 Target | 建议归属与处置 | 协议或 adapter 的必要变化 |
|---|---|---|---|
| 1 | `memory.strategy` | 保留，作为 Memory 唯一语义生成入口 | 保留 initialize/interact/compose 和按需 compact；明确其与准备阶段的区别 |
| 2 | `memory.prompt` | 退出；内容成为 Memory 所有的资产，由初始化/投影决定采用方式 | 复用 Prompt、真实来源和原生 profile 读取；需要物化原生文件时，由 Memory 的准备结果显式要求，保留基线必需内容 |
| 3 | `memory.context_config` | 退出并拆字段；上下文布局/保护/相关性归 Memory，Skill 选择归 Capability，宿主参数留宿主 | 不把整个 ContextConfig 作为 Memory 私有字典透传；见第 6 节 |
| 4 | `memory.token_config` | 退出并拆字段；上下文缩减和允许调整的优化策略归 Memory，计量、缓存机制和硬预算归宿主 | 保留 native TokenWise 实际消费者；区分策略请求、普通默认值与宿主硬限制 |
| 5 | `memory.backend_config` | 退出；Memory 选择获准的存储/检索策略 | 身份、凭据和连接生命周期由宿主提供，不由材料覆盖 |
| 6 | `memory.context_engine` | 退出整引擎平行替换口；必要的引擎委托归 Memory | **缺口**：compose/compact 不覆盖整个 ContextEngine 生命周期。确需更换引擎时，使用明确的 Memory 宿主扩展契约，验证 owns_compaction、assemble、after_turn 等职责 |
| 7 | `memory.backends` | 退出；Memory 提供或选择后端依赖 | 受管构造、start/stop、检索/存储/反馈由 adapter 对接原生；不能因它是“资源”就把信息语义搬到 Capability |
| 8 | `memory.session_observers` | 退出独立组件口；会话退休信息归 Memory 的生命周期处理 | **缺口**：原生是驻留宿主的同步、不等待、不可否决删除通知；不是普通 after_iteration，也不能直接等待 async interact 或伪造活动会话 |
| 9 | `memory.intake` | 拆为 Memory 的输入组织和 Action 的早期回复/终止 | **缺口**：一次性 initialize、保留 required 消息的 compose 不等价于每 turn 入站改写。保留原始输入，显式区分模型侧派生输入；提前回复须有真实 Action 消费点 |
| 10 | `memory.system_addendum` | 文本贡献并入 Memory.compose；终止语义归 Action | 文本部分可复用现有投影；不能遗漏原 IntakeResult.reply 的控制含义 |
| 11 | `memory.archive` | 退出；Memory 处理已完成发送的观察和记录注记 | **缺口**：需真实 sent 阶段及可检查的原生记录注记结果。它不是压缩，也不能只写策略 checkpoint 后宣称已写原生 turn record |
| 12 | `planning.strategy` | 保留，作为 Planning 唯一语义生成入口 | initialize/view/revise 的任务状态协议继续使用，另补必要的准备和投影契约 |
| 13 | `planning.advise` | 退出；建议归 Planning 的视图投影，观察归实际证据驱动的修订 | before-model 建议与 after-iteration 观察有不同时序；当前 view() 无输入，不是自动等价替换。翻译可为所属实现的方法或 helper，不能形成独立业务 owner |
| 14 | `planning.skills` | 退出并合并到 Capability 的 Skill 管理 | 当前 roles 已是 capability；消除命名与职责不一致，统一完整包、来源、版本和撤回语义 |
| 15 | `planning.playbooks` | 退出；可复用程序、节点和需求由 Planning 准备并导出 | **组合关键缺口**：父子 curation 前就要读到可检查的节点结构。不能从任意 view 或源码猜图；adapter 生成原生 Playbook，Raven 执行 |
| 16 | `planning.skill_config` | 退出；已实现的发现/检索/交付策略归 Capability，服务配置归宿主 | 去除未接线字段的行为承诺，保留 pull/push、来源、实际读取语义；不是 Planning 配置 |
| 17 | `capability.strategy` | 保留；同时负责资源准备、登记和运行期选择 | register/select 保留，新增明确的候选资源准备入口；构造器保持无外部副作用，准备与 session select 状态分开 |
| 18 | `capability.resources` | 退出；贡献类型保留，由 Capability 代码主动提交 | Skill 包引用、文本资产和注册回执仍需要；不再由 adapter 从平行业务字段自动安装 |
| 19 | `capability.select_tools` | 常规选择并入 select；动态贡献先走真实登记 | **差异**：旧口可返回完整定义甚至追加定义，新 select 只选已知名称。不能把两者说成完全等价；不保留没有实际执行能力的 schema 注入，必要的工具定义定制放入受管贡献 |
| 20 | `capability.tools` | 退出；工具通过 Capability 同一路径贡献 | **缺口**：旧工厂接收 PluginContext，新资源工厂无参数且较早构造。需显式依赖注入/延迟构造契约，继续由原生 ToolRegistry 执行 |
| 21 | `capability.tool_config` | 退出并拆字段；工具行为/选择策略归 Capability，授权配置归宿主 | 保留宿主 disabled_tools、sandbox、文件边界；策略不能借配置扩大权限 |
| 22 | `capability.mcp` | 退出；Capability 请求获准连接及其工具 | **缺口**：现有贡献仅 tool/skill。连接、异步发现、错误/就绪、凭据和关闭需受管契约；注册成功不能等同连接成功 |
| 23 | `capability.plugins` | 退出整包配置口；具体组件按责任归属 | 通用插件根目录和装载权归宿主，可暴露允许的组件选择。取消任意配置透传是**权限收窄**，不是已有公共方法全部吸收 |
| 24 | `action.strategy` | 保留，作为 Action 唯一语义生成入口 | 保留 handle_event/handle_request，按已发现的缺口补事件和效果，不按每个旧 hook 增加方法 |
| 25 | `action.config` | 退出并按字段拆回真正 owner | 当前 AgentDefaults 混合采样、上下文、重试、预算和个性化，不能整体藏进 Action.prepare；见第 6 节 |
| 26 | `action.review` | 并入 ProposalEvent 和 ActionDecision | **缺口**：当前 ActionDecision 没有原生 resample overrides；保留该功能需补有类型、受阶段和预算约束的模型参数效果 |
| 27 | `action.salvage` | 并入终止 FailureEvent 与 finish | 保留 native 重试/预算耗尽后的顺序；已由原生恢复产生回答时不能再次“救援”覆盖 |
| 28 | `action.hooks` | 退出任意原生 Hook 注入口；实际业务用途映射为明确事件/效果 | **覆盖缺口**：当前 wrapper 只有部分原生阶段，不能声称全覆盖。逐项迁移需要的行为；不暴露可任意修改的 HookContext 兜底 |
| 29 | `action.tool_gates` | 并入 Action 的 dispatch ProposalEvent | 复用现有 adapter gate；保留参数验证后、执行前、失败即拒绝的时序，不能用工具隐藏或自愿请求代替 |
| 30 | `action.services` | 退出；组件依实际语义归各 owner，生命周期留宿主 | 监控判断可归 Action，存储归 Memory，连接归 Capability。驻留 start/stop 不等于一次 turn；需要显式受管依赖，不在构造器启动 |
| 31 | `prompt.resources` | 从语义 Target 降为策略所有或共享的资产索引 | 复用 Prompt 类型、模板和校验；本来就不自动注入，不属于主要绕行问题。允许 manifest 存在，实际消费者必须可追踪到策略实现 |

## 6. 宽配置不能原封不动移进类

当前 Target 有一定字段收窄，但边界仍很宽。例如 action.config 只排除了 workspace 和两项 subagent 并发/频率字段，仍包含上下文、模型调用、恢复和个性化设置。

| 配置中的语义 | 建议 owner | adapter 的职责 |
|---|---|---|
| 主模型选择、temperature、reasoning_effort、已授权的单次生成参数 | Action 的决策策略，受宿主允许范围约束 | 映射原生参数，明确当前/下次调用生效，记录实际应用结果 |
| Memory/Planning 等策略自身辅助推理的需求 | 使用推理的策略 | 通过现有有界推理服务落实，不能让 Action 的主模型设置隐式覆盖所有辅助推理 |
| memory_window、上下文分段、历史保护、相关性、压缩、图片的上下文取舍 | Memory | 结合原生模型容量、必需来源、配对消息和图片机制验证；模型物理容量不是策略可扩大的值 |
| context.pinned_skill_ids、Skill 检索/交付、tool_result/Skill 的协同呈现 | Capability 与 Memory 按“选什么/怎么放”分工 | 只维护一份实际生效能力视图；不要两个策略互相覆盖同一设置 |
| 迭代/重试/超时的可调策略 | Action 决定获准范围内的策略；宿主提供执行机制与独立硬限制 | 通过类型化策略请求落实；明确作用域，不把原生默认值误当成不可改变的授权上限 |
| 计费/usage、provider 缓存能力、调用总预算硬限制 | 宿主；Memory 可请求允许的上下文/缓存优化方式 | 保留 Raven 计量和恢复，优化请求不能伪造 provider 支持或突破实际授权 |
| backend、检索 top_k、后端使用规则 | Memory | 选择批准的依赖；凭据、用户/agent 身份、连接和停止留宿主 |
| 工具源、MCP、Skill 索引模型与 endpoint、插件组件 | Capability 决定能力需要；宿主决定可用服务和权限 | 使用服务引用和实际发现状态，凭据不成为生成资产 |
| archive_dir、workspace、sandbox、文件根、身份、并发额度 | 宿主 | 提供具名、受限的读写和资源服务；避免交付原始配置写权限 |
| enable_personalization 与相应来源 | 宿主启用条件 + Memory 的来源使用策略 | 不作为一般 Action 参数；明确原生后台更新的资源归属 |

迁移应区分“默认配置”“策略可以调的参数”“宿主明确规定的硬限制”。移到宿主层不自动意味着参数变为不可调；如果新协议取消了旧 Target 已授权的调整能力，要把它记为权限变化，不能用职责整理掩盖。身份、插件装载和文件根等归属也应在具体基线的授权契约中明确。

ContextConfig 中的 curator_model/provider/timeout 是原生上下文管理组件的参数，不是实验 Curator 模型配置。需要由 Memory 使用的委托服务明确说明，避免同名混淆。

`SkillForgeConfig` 明确标注若干 lifecycle 字段为未接线占位；不应照抄原生宽 schema 并承诺它们能生效。这不等于所有学习/提取功能都不存在：extraction 等路径要分别查实际消费者，不能仅凭名字归类。

原生 resample 允许 temperature、max_tokens、reasoning_effort。若策略能修改 max_tokens，必须在预算/上下文投影前确定有效生成预算，或预留明确上限；否则 Memory 的“本次能放多少上下文”可能根据旧预算计算。保留这一能力比单纯给 ActionDecision 加字段更复杂。

## 7. 最小完整的协议增量

### 7.1 Capability：资源准备是明确缺口

推荐在 register/select 之外增加候选范围的准备契约，概念名可用 prepare；最终签名在实现阶段与现有 BoundStrategy.prepare 区分。它至少得到材料/资产读取能力、当前版本资源清单、候选身份和授权能力，不得到整个可变 runtime。

它负责由生成代码决定采用哪个包、把哪些材料表达成 Skill、如何修订/撤回、需要哪些工具和已授权连接，并经 register 获得实际回执。Skill 正文可以在 Curator 生成时成为配套文件，prepare 读取并采用即可，无需启动时再次请求 LLM。已有完整包可以保留引用和摘要，复制二进制/嵌套文件由宿主完成。

register 继续作为其他策略贡献交互入口的公共方法，负责接纳策略；select 只面对实际可用目录。Memory、Planning、Action 工具的处理器和状态仍留在各自 owner。跨策略必需入口被拒绝时，候选验证应失败或呈现明确未满足依赖，不能声称交互已经可用。

语义简单的采用实现可以很短；不以代码行数衡量质量。关键区别是生成代码执行了采用/修订决定，而不是系统先根据顶层 resources 自动安装，随后再调用一个无关的类。

内部的 `_prepare_tools`、`_prepare_skills` 是目前较有依据的辅助划分：输入类型、校验要求和资源处理确有差别。建议作为可选组织方式评估，不在通用 Protocol 中先强制这两个方法及顺序。复制文件、连接关闭等宿主机制不因此变成生成策略必须覆写的内部方法。

### 7.2 Planning：运行期计划与候选程序分开

保留 initialize/view/revise。为 Playbook 定义、可委派节点及 requirements 增加候选准备/导出契约，其产物必须能在子 Harness 生成前检验。

建议优先使用正式宿主扩展契约：Planning 确定流程语义，Raven adapter 编译为当前 PlaybookSpec 和节点文件。如果以后多个宿主共享相同的程序语义，再提炼通用公共类型；当前不凭假设设计通用 DAG 框架。

PlanningBinding 当前还有 tool/context/observe 翻译函数。纯翻译可以继续复用 helper，不必机械变成三个公共语义方法；但其选择与实现需由 Planning 代码所有，使用同一状态 owner。adapter 不能新增独立的业务翻译规则。

这些已有翻译是收回类内辅助方法的直接证据，例如视图渲染、观察到修订请求的转换。如果由 adapter 独立调用，它们应声明为该策略类的可选宿主方法；如果由公共方法统一调度，才是辅助公共操作的受保护方法。不能把过程导出只改名为 `_build_playbooks`，却没有准备阶段的实际调用方。

### 7.3 Memory：核心保留，补时序与结果语义

initialize/interact/compose/按需 compact 仍是合理核心。需要补的是旧功能实际发生的阶段，以及哪些结果能被宿主使用：

- 入站信息标准化可以继续采用 interact 的类型化交互，但必须明确它是否可发生在初始上下文建立之前、依赖什么最小状态、如何产生模型侧派生输入。也可先独立做无状态来源规范化；不能假装当前 interact 已覆盖此时序。
- sent 观察需要包含实际输出/发送事实及原始记录身份，记录注记需要明确的结果或受限服务。宿主按原生可达路径调用，不把未送达的草稿当成已发送事实。
- 会话退休不是普通活动 turn。保留原生不等待的语义时，由宿主管理通知投递/清理扩展，不把同步删除过程改成等待 LLM；是否需要持久投递由实际清理要求决定，不默认另建事件总线。
- 整引擎委托和后端依赖属于可选的正式宿主扩展。无此需求的 Memory 不必实现整套原生接口。

提前终止/回复仍交给 Action。Memory 可以通过明确 peer 请求提出建议，执行控制和应用结果不混入 ContextView。

Prompt 渲染、来源选择、历史缩减可作为实现内部辅助职责；目前不足以据此强制统一的 `_load_profile`/`_load_skills`/`_load_history` 初始化流水线，因为输入来源和初始内容形式并不统一。若保留引擎/后端选择等必须在 runtime 构造前生效的能力，Memory 还需要正式准备阶段入口；往会话 initialize 里增加内部方法不能弥补这个时序差异。

### 7.4 Action：保留两个语义操作，补事件与效果

handle_event/handle_request 可以继续作为主方法。此次新增需求主要位于事件与结果契约：入站阶段、原生已支持的生成参数调整，以及从旧 hooks 迁移时发现的必要阶段。

为事件列明允许的控制、可见输入和实际应用点；为控制列明作用于本次还是下次调用、是否已产生外部效果。保留 ControlReceipt 和 native gate。常驻监控需要的服务通过受管依赖接入，其决策回到 Action；不把后台 start/stop 塞进每次 handle_event。

现有事件类型为 `_handle_proposal`、`_handle_failure` 等可选受保护分派方法提供了依据；监督与主动请求也可以共用一个领域检查 helper。可以提供可复用分派实现，但没有依据要求每个 Action 都实现全套分支。候选期生效的默认策略/服务依赖仍需单独的正式准备契约，不能靠运行期 helper 提前生效。

## 8. adapter 调整与完整生命周期

1. **接收候选**：schema 只允许已授权的四策略入口、绑定元数据和配套资产；仍保留 Plan 的理由/验证、显式撤回和状态描述。生成实现有真实类型，构造器保持惰性。
2. **运行候选准备**：在隔离候选范围内，执行相应策略的准备代码，收集资源贡献、依赖请求、程序结构与必要的内容物化请求。每项带 owner、来源和候选身份；不对旧 Target 字典直接循环安装。
3. **检查与暂存**：共用注册路径处理冲突和授权，校验完整包并产生稳定版本目录。准备阶段可重复执行，验证失败不能更改活动版本或用户资源。
4. **构造原生 runtime**：按显式依赖延迟构造工具/组件，连接 MCP，绑定原生上下文、Hook、gate、Playbook。公开真实就绪状态；必需依赖失败则不能发布为完整成功候选。
5. **组合并激活**：父层准备结果先供节点和需求检查，按需生成子候选；相关材料来自已确认的资产/效果清单。保持已有整体验证和激活恢复路径。
6. **运行会话**：会话 owner 读取不可变的准备结果引用及自身 checkpoint；Memory.initialize 在真实来源齐备时调用。select、compose、handle_* 在真实阶段执行，最终请求和执行记录证明效果。
7. **更新与释放**：撤回只作用于明确 owner 的资源，保留未改策略/资产/进度；失败恢复活动版本。连接/后台服务释放由宿主管理。外部工具已经造成的效果不承诺回滚。

准备 owner 与会话 owner 生命周期不同，不能通过“恰好共享实例属性”传递资源清单。应有明确、可验证、可在重启后恢复的准备结果。现有版本目录和 checkpoint 可复用，无需默认引入新数据库。

对于输入包，准备结果必须绑定可恢复的资产版本；不能让已安装实现永久依赖一次性 uploads 目录。现有摘要与复制机制可作为基础，需补齐重建和引用持有的契约。

当前 parent_materials 通过旧 Target 名称/绑定筛选内容，需改为读取准备后的 owner 资产与必要效果快照。父层流程导出、子层需求、证据分派及恢复 fingerprint 一起调整；不让子层从父层 Python 文本中猜流程或继承无授权材料。

## 9. Curator 输出与阅读链

不必因这次调整另起一套 Artifact 容器。可以保留 values/files/remove 等运输概念，同时收紧内容：

- values 只承载四策略实现的入口、必要绑定/状态元数据；不再接受可独立生效的 resources、profile、playbook 或宽配置 payload。
- files 继续承载生成源码、模板和文本资产；完整上传包使用宿主验证过的资产引用。资产被列入包不代表自动安装、调用或注入。
- 策略方法返回的结构化贡献/请求允许是声明式数据，前提是有明确代码生产者、owner、消费者及实际应用回执。
- remove 和资产撤回明确区分“删除实现”“撤回其所有资源”“移除某一资产”“保留会话状态”。当前 remove_paths 依赖内容 Target，需同步迁移，不能直接丢弃撤回能力。

阅读链改为：**当前实际基线与授权 → 四策略语义 → 本宿主支持的准备/扩展契约 → 当前实现和已准备资源 → 实际执行及修订证据。** 保留按需查询 Raven 源码的能力，不把读取大量原生文件作为理解协议的前置条件。

生成阶段的 select/design/implement/repair 都需采用新出口；检查、Inspection、观测和修复提示同步更新。只收缩 submit schema 而保留旧阅读说明，会让 Curator 不断提交已被取消的路径。

示例应提供最小类型与生命周期用法，而非默认旅行专家完整答案。采用现成 Skill、生成新 Skill、修订已装 Skill 三类不同示例更能说明协议，也避免把单一 Raven 参考类当成所有领域的模板。

## 10. Skill 管理还有两个独立问题

第一，文件树、单文档和消息经过 Curator 时，当前已经可以产生 Skill；但普通 Worker 收到消息不自动调用 Curator。已完成的 worker_message 对照中，Worker 直接写入 home/skills，新 runtime 可以发现它。这条路径不会因为生成 schema 只剩四类就自动消失。

若坚持“受管 Skill 的持久变化都经 Curator”，还需明确区分普通工作产物、待采用素材和活动 Skill，控制受管目录与发现来源，并把能力更新请求路由给 Curator。检查配置允许的原生提取/自动安装路径是否写入同一受管范围。不能仅靠 Action 提示“不要写 skills”作为保证，也不能宣称 Python Protocol 自身是执行沙箱。

第二，旅行案例已暴露安装资源的读取缺陷：原生 restrict_to_workspace 开启、Baseline.file_roots/read_roots 为空时，bind.py 不进入追加 managed Skill 只读根的分支，read_skill 可读正文，但 read_file 读取安装包引用文件被拒绝。回退读 uploads 不是已安装包访问成功。它是当前 adapter 缺陷，应在 Skill 路径迁移时修正并验证两种权限入口。

原始 ZIP 尚无自动展开支持；Scenario.upload 也会改变 SKILL.md/frontmatter 并丢失嵌套目录。两者须在输入材料契约中明确处理或拒绝，不能由新的四策略命名自动“支持”。正文质量评估继续不在本次架构评审范围内。

## 11. 实施次序与验收

实施记录：四个 `*.strategy` 生成出口、公共候选 prepare 生命周期、角色化宿主服务、资源安装账本及相关 adapter 路径已进入实现。Capability 的 tools/skills 内部生产方法经 register 接纳，原生资源构造、连接与会话运行分开。若干定向回归通过；父子组合中访问已删除字段的迁移残留已在后续入口调整中修复，定向原生集成通过。旧旅行生成曾保存两份策略源码，随后在驱动导出时失败；新的正常部署入口已实现，但真实验证因 Research 搜索凭据缺失停在准备阶段，尚未完成 Worker 行为与 V2 验证。当前未完成项、证据与后续范围见[真实专家测试方案第 10 节](expert-package-test-plan.md#10-已有证据与开测前置项)，不计为已验收。

| 步骤 | 必要变更 | 可检查结果 |
|---|---|---|
| 1. 固定能力映射 | 根据本表定公共增量、宿主扩展、字段拆分和明确收窄项；核查旧 hook 的实际用途 | 每项旧功能有新的 owner、阶段、消费者或明确撤销理由，不能将未迁移能力静默删除 |
| 2. 先完成资源闭环 | Capability 准备/register/select、类型化依赖、资产版本、代码驱动采用和撤回 | 真实类代码决定完整包采用；无策略方法调用时不自动安装业务资源；缺陷用例可读安装后的 refs/templates |
| 3. 补齐时序与组合 | Planning 程序导出、Memory 入站/归档/退休、Action 所需事件/效果 | 父子节点生成及需求变化可运行；旧功能在相应原生时点生效，未发生的效果不被记录为成功 |
| 4. 一次收敛生成出口 | 更新 Declaration/schema、四策略 bindings、生成材料、检查/安装/Inspection/撤回路径 | 新契约拒绝独立旧 Target；不保留双轨兼容或万能配置兜底；旧资产与用户数据有明确处置 |
| 5. 独立验证与资料 | 相关回归、新契约真实生成与修订、单独需求复核 | 代码、模型实际输入、资源消费、控制回执和状态变化互相对得上 |

第 2、3 步可先在受控测试里验证新契约，最终交付不留下两套有效生成入口。当前没有历史产物兼容要求，不默认实现旧格式翻译层；保存原始证据和用户数据，对旧候选给明确诊断并重新生成。接口不兼容不等于清空合法任务进度。

验收必须覆盖：

- 文件树、材料文档、消息三种 Curator 输入；ZIP 单独报告是否支持。检查 generated code 的真实采用调用与已安装包内容，不只看类名或 register 调用次数。
- 首次构建、反馈修订、显式撤回；未修改资产和任务进度保留，失败候选不污染活动目录，重启不依赖临时源文件。
- 单策略、组合策略；Memory/Planning/Action 的请求经同一 Capability 注册，但仍调用同一活动 owner，缺失依赖和部分失败可见。
- 根与 ACP 子 Harness；流程节点/requirements 与父层资产在子生成前可见，重启和更新不丢证据或改变输入身份。
- 原生工具工厂依赖、MCP 不可用、常驻服务释放；暂存、安装、可见、授权和实际执行分别验证。
- 入站早回复、派生输入、发送后注记、会话退休、resample 参数及模型预算；各阶段不以另一个近似事件冒充。
- managed Skill 读根在显式 Baseline roots 和仅原生 restrict_to_workspace 两种情况下均正确；工具不能以临时源文件回退掩盖安装访问失败。
- 宿主原生 baseline 保持可用；新类接口没有伪造支持未实现的 SkillForge 字段，也没有重新实现 Loop 或绕过 native gate。

旧多 Target 版本的测试数不能作为本方案的完成证据。初始评审阶段只做源码和文档检查；随后实施阶段进行了上述局部验证，完整验收仍未完成。后续说明与案例入口调整的独立结果见[实施记录](curator-docs-and-scenario-alignment-plan.md#6-实施记录)，不能与本段历史证据混为一轮验证。

## 12. 不需要强行修改的部分

原生 AgentLoop、ToolRegistry、权限与 gate、Skill 包格式与发现、Playbook/DAG 执行、ACP 托管保留。现有 typed Prompt、资源摘要与完整复制、版本暂存、活动能力视图、同 owner peer 路径、checkpoint、Recorder、候选隔离和激活恢复继续复用，在明确依赖处调整。

Memory 核心、Planning.initialize/view/revise、Action 两个 handle 方法不因 Target 数量变化而整体重命名。需要改变的是它们未覆盖的真实职责及其宿主契约，而非为整齐把每个旧 Target 都变成一个新方法。

最终设计的判断标准是：一个行为能沿着“哪个策略的哪段代码作出决定 → 哪个类型化结果/请求 → adapter 在哪个原生位置应用 → 哪条证据证明效果”被追踪。方法数量少、Python 文件多或没有 JSON，都不能单独证明这个目标达成。
