# Capability 策略设计与实施方案

Planning 更新：本文中保留 initialize/view/revise 的决定已由 [Planning 交互实施方案](planning-strategy-plan.md) 取代；当前协议为 initialize/interact，工具与跨策略联动随之迁移。

状态：历史设计与阶段验收记录，描述四策略入口收敛之前的协议演进，不作为当前生成接口说明。当前有效契约见 [design.md](design.md)、[候选准备](../curator/raven_adapter/reference/preparation.md)及各策略源码；本文历史测试数不证明新入口或真实案例已经验收。

本文从 Curator 生成、管理和操作 Harness 能力资源的需求出发，设计 tools、skills 与跨策略交互入口的共同边界。它与 [Memory 设计与实施计划](memory-strategy-plan.md)、[Action 设计与实施方案](action-strategy-design.md) 联合实施。跨策略身份、依赖与验收以 [联合标准](strategy-interaction-plan.md) 为准；本文件第 3 节是贡献、回执和有效能力视图的资源契约说明来源。

本文保留方案取舍与实施顺序。最终接口见[公共协议](../curator/harness/strategies/capability.py)、[资源类型](../curator/harness/resources.py)和[运行接入说明](../curator/raven_adapter/reference/capability.md)，公开 schema 从类型定义导出。

## 1. 目标与保留范围

Curator 是能力资源变更的决策者和操作者。用户上传只使资源成为待检查的输入，不直接使它成为员工的能力。宿主执行校验、复制、注册和激活，并把实际结果交还 Curator。

需要完整支持三类需求：

1. 用户提供现成 Skill 包，由 Curator 检查并显式发起采用，纳入目标 Harness。
2. Curator 根据任务、反馈和已提供材料生成或修改 Skill、工具及相关使用知识。
3. Memory、Planning、Action 等策略贡献模型交互入口，由共同能力路径接入，调用回到各自的活动 owner。

目标公共核心按 register/select 设计：register 显式登记能力贡献，select 根据当前需求选择已生效能力。登记与运行时选择有不同生命周期，也不为了模仿 Memory 而增加同名 initialize/interact。

不再预先要求保留 provide。若它只有“构造一批资源，再逐项注册”的作用，就作为可选构造辅助，退出必需公共协议。只有 C0 验证发现不能被 register 或普通构造函数覆盖的独立调用者和语义时，才重新评审其公共地位；不保留空方法或旧接口兼容壳。

保留 Raven 的 ToolRegistry、技能发现与读取、权限/gate、MCP 和子代理调度。保留 Curator 的候选生成、校验和安装流程，不建立旁路资源管理员或第二套执行注册表。任意时刻热注册、通用远程包市场和新子代理部署不属于本轮。

### 1.1 两条保证性验收准则

C-V1：用户提供现成 Skill 包或可结构化的材料后，Curator 能显式决定采用或生成，通过候选安装到目标 Harness。完整包及生成内容实际可读，声明工具实际可调用；资源来源和对任务的使用路径可核查。

C-V2：Curator 接受纠正反馈或新材料后，精确更新、补充或撤回指定能力；活动资源集合体现新意图，不残留旧 Skill 或错误 handler，无关资源和状态保留，激活失败恢复原状态。

首次定制和持续修订都要覆盖现成包、材料生成及跨策略入口。仅有资源列表、登记成功或模型自述已读 Skill 不足以验收。遇到某类包或策略贡献无法表达时，先调整共同贡献/来源/生命周期契约，再同步各消费者，避免局部专用入口积累。

## 2. 当前事实与实质缺口

| 现有能力 | 当前支持 | 需要处理的缺口 |
|---|---|---|
| [CapabilityStrategy](../curator/harness/strategies/capability.py) | provide 构造资源，select 做需求相关选择 | 未明确跨策略贡献的公共接入 |
| [CapabilityResources](../curator/raven_adapter/capability/contracts.py) | 原生 Tool 对象与文本技能文件映射 | 缺少现成包引用、完整配套资源及采用关系 |
| [工具绑定](../curator/raven_adapter/capability/runtime.py) | 校验、重名检查、注册、选择及指导文本 | 其他策略入口目前各自接到装配代码 |
| [planning.skills / skill_config](../curator/raven_adapter/targets/planning.py) | Curator 可生成文本 Skill，或配置已有技能源 | 可组合实现部分采用行为，但没有统一的包采用契约 |
| [候选产物](../curator/harness/artifact.py) | 支持 target 和受管理路径撤回 | provide 的专用技能源没有完整的期望集合对齐 |
| Skill 选择 | 原生系统有发现、依赖、目录和正文消费机制 | 生成策略的 selection 主要映射工具名称或指导字符串 |

已核查的生命周期问题：stage_skills 向固定的 capability-skills 目录写本次文件，未移除本次不再提供的文件；Worker 的 assembly 目录跨运行代复用。用现有物化函数和新的原生 SkillRegistry 复现：第一版提供 alpha/beta，第二版仅提供 alpha，第二次仍发现 beta。该证据限定在这条物化/发现路径，不代表全部激活回滚情形已经测试。

这与 planning.skills 的显式 remove_paths 不是同一问题。现有内容归属和失败恢复机制应复用，不能把所有资源入口一并重写。

## 3. 跨策略共同契约

本节供 Memory 与 Action 文档引用，并遵守联合标准的共同身份和依赖边界。实现后把长期稳定部分转入公共与 Raven 接入参考资料，不维护相互冲突的平行说明。

### 3.1 责任与唯一所有者

| 主体 | 拥有的责任 | 不承担的责任 |
|---|---|---|
| Curator | 识别资源、判断采用/生成/修订/撤回，提交候选并读取结果 | 不把员工运行时的普通记忆交互自动升级为资源安装 |
| Memory | 交互命令语义、信息状态、上下文组织 | 不复制能力注册表或直接改造持久 Skill |
| Planning | 任务计划及其既有交互语义 | 不把计划状态复制给 Capability |
| Action | 宿主事件判断、agent 行为请求及控制意图 | 不复制其他策略状态、不绕过 Curator 改造持久能力 |
| Capability | 通过 register 接收能力贡献，组织候选能力集合并进行运行时选择，表达工具/技能消费关系 | 不重写其他策略的业务处理 |
| 宿主 | 验证身份与声明、绑定活动 owner、物化、注册、权限、激活及观测 | 不代替 Curator 决定新增或改写什么能力 |

### 3.2 公共 register 与能力贡献

register 是 Capability 对外公开的操作，不只是一句由私有装配分支实现的“支持贡献”。能力贡献是它接收的可检查声明，表示“这个 owner 向模型提供什么入口或使用资源”。登记本身不执行工具或 Skill，也不扩大权限。

目标协议形状如下。类型名为设计名，字段在 C0 固定；方法映射和真实调用必须一起验证：

```python
def register(contribution: CapabilityContribution) -> RegistrationReceipt:
    ...

async def select(request: SelectionRequest) -> CapabilitySelection:
    ...
```

Memory、Planning、Action 的绑定及 Curator 生成的装配代码通过宿主提供的窄注册引用使用该入口，不需要持有整个生成的 Capability 对象。注册的通用检查和底层安装复用宿主机制；策略实现可以委托这些组件，不重复实现 ToolRegistry。

只选择 Memory、Planning 或 Action 的改造时，宿主的基础 Capability 实现仍提供同一 register 入口并委托原生选择，不要求额外生成一个空 Capability 策略。它仅承接已授权候选及绑定声明的资源，不自行替 Curator 采用上传 Skill。生成 Capability 被选中时，也使用相同的登记语义和检查，不能形成另一条资源安装路径。

注册状态属于当前候选及目标 Harness 的资源集合，不写入会话级选择 checkpoint。select 读取活动能力目录和需求，不能通过选择操作改变已经批准的资源配置。

声明至少要能解析资源身份、所属 Harness/owner、工具 schema 与说明或技能包引用、生命周期和必要依赖。处理器绑定由宿主解析到活动 owner；跨进程/持久化声明使用可解析引用，不序列化任意对象。

- 工具 schema 从其真实类型/契约导出，不手工维护第二份。
- Memory 入口由 interact 的具体类型和绑定导出；Planning 接入已有工具，不改其 initialize/view/revise 语义。
- Action 入口由 handle_request 的具体命令类型和绑定导出；模型参数不能选择可信宿主事件或控制应用状态。
- 工具通过宿主分派取得当前作用域，不能捕获默认会话，也不能另造一个 Memory/Planning 实例。
- 所有贡献者遵守同一作用域分派，包括 Action；其工具请求、事件判断和 gate 必须使用正确版本的活动 owner。
- 工具与 Skill 保持不同类型：前者有可执行处理器，后者有内容、引用资源及使用条件。不会把 Skill 简化成工具名称。
- 贡献声明在装配期可获取，避免必须等会话初始化后才能确定工具集合。
- 完全相同的贡献重复登记返回同一身份和 unchanged，不重复安装。相同身份但 owner、内容或 schema 冲突时明确拒绝，不用后写覆盖前写解决。
- 未知 owner、错误 handler、缺依赖明确拒绝；宿主错误显式失败，不伪装成一次成功登记。
- 更新和撤回与拥有它的候选同版生效；不遗留指向旧实例的处理器。

RegistrationReceipt 至少说明贡献身份、owner、目标作用域及 staged、unchanged 或 rejected 状态，拒绝时提供原因。staged 只表示当前候选已接收贡献，不表示员工已能调用；校验、安装和激活结果另行记录，有效能力视图反映真正生效的资源。

register 接收 Curator 当前候选或已批准策略声明范围内的贡献。显式修订同名资源必须关联 Curator 的变更意图，不能靠重复 register 暗中替换；撤回继续使用候选的明确资源变更表达，不额外开放员工运行期的全局 unregister。

公开的注册表达与内部的声明式候选可以并存：多次 register 构成同一个可检查的候选资源集合，最终仍走统一验证与激活。该集合是构建产物，不是另一套独立的运行时执行注册表。

### 3.3 有效能力视图

SelectionRequest 包含当前需求、目标作用域及活动能力目录，覆盖 tools、skills 和已支持的子代理引用。不能只传工具名称而让策略猜测可用技能源；也不能把 staged 的候选回执当成活动目录。

CapabilitySelection 明确给出工具选择、技能引用及交付方式、不可用结果或委托原生选择。结果经宿主落实实际可用性、可见性与受保护入口等规则后，形成提供给本次 Memory.compose 的有效能力视图。

视图至少应让消费者判断：

- 实际提供给模型的工具定义及对应入口身份；
- 本次选中的技能、来源/版本引用，以及目录展示、正文供给或按需读取方式；
- 哪些交互入口此时可用，哪些资源缺失及其原因；
- 该视图对应哪个 Harness revision、作用域和模型调用。

视图不暴露可变注册表或其他策略的 checkpoint，也不把“在工具列表中”表述成“无需执行权限检查”。

对于能力选择，未知资源、不可用资源、明确空选择和委托原生选择必须可区分。工具定义与实际注册处理器必须一致；技能选择必须有实际消费者，不能只在返回值中列出一个名字。

Memory 根据同一份有效视图生成说明，避免提示与模型实际入口不一致。静态协议说明和动态可用性可以分开呈现，但不得宣称已撤回或当前不可用的入口能够调用。

### 3.4 装配和执行时序

```text
Curator 检查输入、基线及反馈，生成联合候选
  -> 宿主创建候选作用域的注册入口
  -> 构造惰性 owner，读取类型与能力贡献声明
  -> 对自有资源和其他策略贡献逐项调用 register
  -> 取得登记回执，与保留的基线能力形成候选资源集合
  -> 宿主检查完整候选并在隔离副本绑定工具/技能源
  -> 校验通过后统一安装和激活
  -> 在实际作用域初始化 Memory 等策略
  -> 根据当前任务和只读状态进行 Capability 选择
  -> 宿主提供有效能力视图
  -> Memory.compose 形成模型输入
  -> 模型调用工具，派发回对应 owner
  -> 下一次选择与组装使用更新后的状态
```

这是外部协作顺序，不是强制的策略内部 _xxx 模板。初始化输入不假定统一 profile 布局；Capability 所需事实不依赖先运行完整 compose，避免循环等待。

原生根委派保护会补回部分工具定义，其他原生规则也影响可见性；这些效果必须计入最终视图。联合小验证以 provider 实际请求为准，不把中间 selection 当作最终状态。

原生 turn_scope 冻结普通工具新增的可见性。register 当前只用于允许构建候选的阶段和装配期；激活后关闭该候选的写入口。对活动集合或已经关闭的候选发起注册应明确拒绝，不静默延迟，也不偷偷修改冻结中的全局工具表。运行期新增/撤回若成为明确需求，再定义生效边界。

### 3.5 Curator 修改权与工作模型操作

工作模型调用 Memory/Planning 工具，通过相应 owner 更新工作状态；Action 请求可以提出声明允许的协作和控制，实际结果由对应 owner 或宿主返回。这些普通交互不授予持久能力变更权。需要把内容沉淀为 Skill 时，可输出材料或建议，由 Curator 经明确资源变更处理。

既有原生技能发现、已授权的读取及选择照常工作；本约定针对本次新增的持久资源变更路径。不能把“模型读取一个已经批准的技能”误当作每次都需要重新 curation。

## 4. Skill 的两条 Curator 操作路径

### 4.1 采用用户提供的现成包

上传接收阶段将包放入输入区，保留文件结构，形成有身份和摘要的来源；暂存不等于把目录加入员工的技能源。

Curator 使用检查入口读取包清单、SKILL.md、适用条件及必要引用，决定采用到根或某个 child Harness，并明确与同名已有包的关系。它通过候选中的类型化资源操作发起采用，包引用进入 register 的贡献输入，宿主校验、物化并报告结果。

采用需要保留相对路径、嵌套资源及二进制附件。使用受约束的包/文件引用，让宿主复制实际内容；不让模型重写二进制，不把临时 exploration 路径当成永久资源位置。

原样采用和基于原包生成修订有不同来源关系，应可区分。未知包、内容摘要变更、目标越界或冲突不得静默选一个版本安装。安装不会执行 Skill 附带脚本；实际使用仍走原生工具与权限。

### 4.2 根据材料生成或修订 Skill

Curator 判断哪些输入适合形成可重复使用的技能，生成入口说明和必要配套文件，并关联真实材料依据。缺失的业务事实不能补成貌似合理的内容。

文本作者产物继续使用现有文件能力；已有配套资源通过受检查引用纳入。无需为每个独立文本 Skill 生成一份 Capability Python 类；独立技能和策略配套技能均形成贡献并经过 register。资源构造可以使用普通函数或可选辅助，不要求先实现 provide。

两种来源汇合为同一套安装、发现、检查和激活流程。候选表达和结果至少能说明：来源、目标 Harness、操作对象、采用/生成/更新/撤回意图、最终受管理资源及可用状态。

### 4.3 资源管理与持久化边界

复用 Artifact/Candidate、声明检查和部署激活。补充包级引用与来源信息，不把 Artifact.files 无差别扩展成任意二进制传输协议，也不新建远程资源平台。

资源身份至少关联 owner、目标作用域和内容身份。内容与来源进入候选验证及恢复身份，防止查询时看到的包与安装时的包不同。

新的完整资源集合与候选省略 target 要区分：未选择或未提交的既有 target 按原规则保留；显式提交完整集合或撤回操作时，当前发现集合必须与该决定一致。

候选物化在隔离目录中完成，引用检查和 Skill 发现验证通过后才切换活动资源。旧资源在仍被活动运行或回滚引用时不能被提前删除。具体目录布局沿用已有产物身份机制，不引入平行版本服务。

同名包的覆盖、外部编辑的归属及撤回恢复遵循已存在的内容所有权规则；新增包级操作补足这些规则，不绕开它们。

## 5. tools、skills 与 subagents 的支持边界

| 类别 | 本轮完整支持的目标 | 保留的原生责任 |
|---|---|---|
| tools | 提供或引用受支持入口、贡献其他策略工具、schema/handler 校验、可见性选择、换版与撤回一致性 | 实际注册、权限/gate、执行调度和工具事件 |
| skills | Curator 采用/生成/修订/撤回；完整包资源；发现、可用性、选择与实际读取/呈现 | 本地目录发现、依赖检查、原生技能读取与既有路由能力 |
| subagents | 暴露现有注册项的真实能力与使用约束，必要时选择/引用 | 部署、ACP、实例与 DAG 调度；受管理 child 不获得第三层委派 |

Capability 选择技能时可以显式委托原生路由，也可以选择已知资源；避免 Capability 与原生路由各自独立决定并重复注入。Memory 组织已决定交付的内容，不再保留另一份技能选择策略。

不能把“支持 subagents”解释为 Capability 可自行创建任意子代理或替换受保护的委派入口。本轮不重构既有子代理注册机制。

## 6. 方案比较

### 6.1 跨策略接入

| 方案 | 复杂度与可理解性 | 风险、成本与适用范围 |
|---|---|---|
| 装配期 register，逐项回执，候选统一生效 | 操作明确，符合现有注册入口的表达；通过窄注册引用减少对象依赖 | 推荐；需定义候选作用域、幂等、冲突及激活边界 |
| provide 接收全部输入并批量返回资源清单 | 纯数据流容易整体检查，适合天然的批量构造 | 可行；本轮不作为默认公共表达，不要求所有贡献者组装完整批量结果 |
| 常驻能力管理服务，运行期任意注册/撤回 | 生命周期最复杂 | 适合确有热插拔需求的系统；当前没有足够需求承担成本 |

选择第一种。这里比较的是公共调用形式与生效时机，不能把 register 等同于随时修改活动注册表；register 的内部结果仍是声明式候选。若以后必须在正在执行的 turn 中添加全新入口，再重新评审热注册机制。

注册式对人和 Curator 提供了清楚的逐项动作及错误定位，但“LLM 更习惯或更可靠”仍是待验证假设。可以用相同任务和材料对比生成完整性、接口误用、修复次数与调用成本，不以接口风格偏好代替功能验收，也不为此新增大型评测平台。

### 6.2 Skill 包接入

| 方案 | 优点 | 代价与决定 |
|---|---|---|
| Curator 将所有输入重写成文本文件 | 可复用现有文本产物 | 无法可靠保留完整包与二进制，不能覆盖现成 Skill 采用需求 |
| 采用包引用与生成文件两种来源，统一候选安装 | 保留来源和结构，复用现有激活流程 | 推荐；增加必要的包级资源契约和检查 |
| 直接把上传目录变成可用技能源 | 路径短，可用于既有调用方配置 | 自动绕过 Curator 决策时不满足本需求；只有 Curator 显式批准且生命周期受控时才是有效采用方式 |

## 7. 实施步骤

| 阶段 | 改动 | 交付与验收 |
|---|---|---|
| C0 共同边界 | 与 Memory M0、Action A0 一起固定 register/select、贡献、回执、有效视图、scope 路由及调用时序；审查 provide 是否存在独立语义 | 类型与真实调用一致；有最小 provider 证据；无必要时移除 provide 的必需公共地位 |
| C1 生命周期修复 | 修复当前 provide 技能源的残留，并使新注册集合、物化和发现结果一致 | 第二版撤回的旧技能不再从当前源暴露，失败可恢复 |
| C2 Curator 包操作 | 将来源引用、采用/生成/更新/撤回表达接入候选 register 流程 | 两条 Skill 路径都经过 Curator，回执与最终安装状态可区分 |
| C3 跨策略注册 | 将 Memory.interact、Action.handle_request 和现有 Planning 工具接入公开 register | 正确活动实例、命令 schema、幂等登记、冲突拒绝、同版更新 |
| C4 选择与呈现 | 固定 SelectionRequest/CapabilitySelection 的实际消费者，接入 Memory.compose | 读取活动目录；工具/技能与最终请求或读取证据一致 |
| C5 信息与验证 | 同步说明、检查、阶段传递和回归 | Curator 看得到资源操作及其结果；默认路径保留 |

C0 是联合前置；C1 可作为独立缺陷修复审查。C2/C3/C4 在共同契约固定后推进，各阶段提交可审查差异与证据；计划不构成自动 commit/push 授权。

### 7.1 预计文件范围

- [公共 CapabilityStrategy](../curator/harness/strategies/capability.py)、capability/contracts.py、capability/runtime.py：表达 register/select、贡献/回执和选择契约，接入候选作用域与生命周期；provide 仅在独立语义得到证实时保留为公共操作。
- [targets/capability.py](../curator/raven_adapter/targets/capability.py)、必要的 targets/planning.py、harness/artifact.py、materialize.py：补足 Skill 来源/操作契约；不为名称整齐而重命名 planning.skills。
- [bind.py](../curator/raven_adapter/bind.py)、必要的 deployment.py/worker.py：统一绑定入口，处理隔离物化、激活与恢复。
- Memory/Action binding 和 Planning 现有工具包装：接入共同贡献与依赖边界，业务逻辑仍由原 owner 实现。
- Inspection、Recorder 及生成材料：增加实际资源身份、来源、可用性、变更结果和共同调用契约。

不要求上述文件全部修改。每个改动必须对应真实生产者、消费者或验收条件；无需变化的源文件保留。

### 7.2 Curator 信息链

保留概览、target 选择、契约展开、源码查询、阶段 history、检查和 repair。更新相关 target 的 schema/effect/state/knowledge，向 Curator 提供 register/select 的完整调用契约、Skill 包清单与来源查询、支持的资源操作及结果。

Curator 的候选操作入口和生成装配代码使用的 register 遵循同一贡献语义。只在允许构建候选的阶段暴露注册动作；理解与初选阶段保持相应只读边界。回执与错误进入阶段 history，后续阶段可以据此继续、纠正或撤回本次候选变更，不能直接更改活动员工。

Curator 必须能分别看到“已提交”“已物化/注册”“实际可用”“被读取或调用”的证据。文本 Skill 的事实依据、包来源与实际运行记录保持可追踪，不能通过评测参考答案补写技能内容。

候选资源来源与代码一并校验和关联身份；暂停恢复不能悄悄换包。相关包引用不得指向销毁后的检查目录。

本计划与完整测试示例不作为 Curator 默认生成答案；运行材料只描述已实现契约、真实基线及可复用组件。

## 8. 验证矩阵与完成条件

| 场景 | 验收条件 |
|---|---|
| 现成 Skill 采用 | 从输入暂存开始，经 Curator 显式候选进入指定 Harness；无自动旁路安装 |
| C-V1 首次定制 | 现成包与材料生成都具有来源、候选和实际消费证据 |
| C-V2 持续修订 | 更正和新增输入精确更新活动资源，保留无关内容；显式撤回与省略不同 |
| 完整包 | 入口、嵌套引用、脚本和二进制资源内容及相对关系保留；安装不执行脚本 |
| 从材料生成 | 生成内容有来源依据，安装后可发现并能读取 |
| 更新与撤回 | 新资源集合与原生发现一致，省略 target 和显式撤回语义可区分 |
| 外部编辑 | 已有内容所有权规则保持，不静默覆盖 |
| 逐项注册 | 注册回执可查询；完成登记不提前修改活动员工或宣称能力可用 |
| 重复与冲突 | 相同贡献幂等；身份/schema/owner 冲突明确拒绝，失败不留下部分登记 |
| 关闭候选 | 已激活或关闭的候选不接受新的注册；不修改冻结中的全局工具集合 |
| 跨策略工具 | Memory、Planning、Action 使用公开 register，schema 与 handler 属于同一版本 |
| 状态作用域 | 工具回到当前活动 owner；会话与根/子之间无状态分叉 |
| 选择 | 未知、不可用、空选择和委托原生有明确结果 |
| 上下文一致性 | 有效工具表与交互说明一致；Skill 选择具有实际消费证据 |
| 权限与边界 | 注册不扩大执行权限；原生委派保护与 leaf 限制保持 |
| 失败恢复 | 包无效、来源变更、安装或激活失败不留下半套活动资源 |
| 原生基线 | 不选择生成 Capability 时，工具和技能默认行为正常 |
| 独立策略选择 | 单独生成 Memory/Action/Planning 时仍通过共同 register 提供入口，不强迫生成无业务变化的 Capability 类 |

优先更新现有 tests/test_harness_curator_strategies.py、test_harness_curator_contracts.py、test_harness_curator_content.py、test_harness_curator_raven.py、test_harness_curator_deployment.py、test_harness_curator_generation.py，以及 fixtures/harness_curator。

集成验证使用既有 test_harness_curator_e2e.py、test_harness_curator_strategies_e2e.py、test_harness_curator_composition_e2e.py 和 test_harness_curator_hosting_e2e.py。增加两个具有不同交互语义的最小测试 fixture 检查贡献契约，不把其中一个完整实现变成所有生成策略必须模仿的结构。

拟执行命令；不是已经完成的检查：

```bash
uv run pytest tests/test_harness_curator_*.py -x
uv run pytest tests/integration/test_harness_curator_e2e.py tests/integration/test_harness_curator_strategies_e2e.py tests/integration/test_harness_curator_composition_e2e.py tests/integration/test_harness_curator_hosting_e2e.py -x
make check-source-language
make check-large-files
```

离线通过后，使用用户已授权的 DeepSeek 官方 V4.1-Flash 验证 C-V1/C-V2，覆盖 Curator 采用现成 Skill、从材料生成 Skill 以及后续修订。模型使用遵循联合标准，报告操作链与真实消费证据，区分未运行、构造成功与任务效果。

## 9. 兼容、审查与收尾

不为旧实验接口增加无需求的兼容层。仓库内实现、调用方、测试与生成材料同次更新。现有原生接口和有效基线保留；新协议内换版与回滚必须完整。

资源清理只针对本轮管理且确认不再引用的内容。既有状态/包需要迁移时先明确范围，不做无差别目录清理。对具名目标的当前能力事实和拟变更分开记录，避免把计划当作实际安装证明。

与实现分开的审查重点：Curator 是否仍是必经决策者；register 是否为实际可调用的公共入口；是否把 staged 错当作可用；Skill 包是否真正保留；贡献是否回到正确实例；选择是否真正生效；撤回与恢复是否一致；是否无必要地保留 provide 或重写原生机制。

完成后更新现有设计、公共/宿主参考说明和必要的 CONTEXT.md 定义，保留明确的阅读入口，将本方案状态更新或归档。未解决的限制以实际影响和后续处理条件记录，不用笼统的“以后重构”代替验收。
