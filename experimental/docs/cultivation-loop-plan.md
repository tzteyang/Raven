# 改进闭环的机制实施规划：契约、边界、Session 与反馈来源

设计依据是 [cultivation-loop-design.md](cultivation-loop-design.md)；本文只写怎么实现、按什么顺序、怎么验收。状态随实施更新，任务结束后仍有效的决策转入设计文档，本文归档。

## 1. 约束

来自根目录 `AGENTS.md`：源码、注释、测试夹具全英文，中文只在 `*.md`；测试放 `tests/test_<module>_<aspect>.py`，集成测试放 `tests/integration/test_<scope>_<kind>.py`；只用 `uv run`；提交与推送只在用户明确指示时；不提交报告资产与大文件；新领域术语要有可对照代码的定义。

来自 `experimental/AGENTS.md`：最小完整实现，不为假想需求预留；不引入可避免的技术债，暂时折中要记录原因、影响、处置条件；模块按业务责任分边界，依赖方向不倒转；不做未被要求的兼容层；重构要说明收益与验证方式；完成以证据判定。

本项目的约定：`raven/` 零侵入，确有必要的改动先与用户评审；四策略作为 Curator 一等公民的设计不做挑战。另一位开发者的四策略改造于 2026-09-29 提交、本分支 rebase 到其上之后，此前为它保留的文件名单解除，Curator 侧的改动直接在本分支完成。

## 2. 目标与非目标

目标：让闭环的输入、边界、步进与反馈来源按设计文档落地，使自动运行与 Studio 人工会话共用一条管线，记录能按标签归因。

非目标：不改四策略的生成设计，归因作为独立阶段接在它之前，生成从 select 开始；不做四策略面收口（正交，另有规划）；不改 `raven/`；不做批量挖掘外层的替代。

## 3. 模块与依赖方向

```text
experimental/
  scenario/        契约类型、可见性、目录加载、披露日程   ← 不依赖其他 experimental 包
  iteration/       协议与有界交换；管线、Session、hearing ← 管线依赖 scenario、analyst、curator
  assessor/        Assessor 协议、Standard、真人          ← 依赖 iteration 的协议与交换
  analyst/         Analyst 与反馈契约                     ← 依赖 iteration 的协议与交换、requirements、scenario
  research/        离线调研：槽位、归纳、研究、确认、打包 ← 依赖 scenario、iteration 的交换、curator 的工具声明与记录
  automation/      工作对象与交互方的模拟器、装配         ← 依赖 scenario、iteration、analyst、curator
  simulation/      旅行社与专家包实例：场景数据、尺子、价值判定 ← 依赖 automation、assessor 与以上各包
  curator/         四策略生成不变，新增 attribution/ 归因阶段
```

`automation/` 是新包，承接今天 `simulation/` 里的通用机制。依赖只能向上指：`simulation` 用 `automation`，反之不可；`scenario` 谁都不依赖。

## 4. 有实质取舍的三个决定

### 4.1 通用机制放在哪

| 方案 | 做法 | 复杂度 | 取舍 |
|---|---|---|---|
| A 新包 `automation/` | 雇佣、副本、并行、约束、交接、运行设置搬进新包 | 中 | 边界最清楚；多一个包 |
| B 并入 `iteration/` | 这些都是"跑试炼"的事 | 低 | `iteration` 会同时含管线与 Raven 具体的副本操作，两种责任混在一起 |
| C 并入 `curator/raven_adapter/` | 它们都操作 Worker | 低 | 把评测侧的东西放进 Curator 侧的包，边界反了 |

采用 A。关键假设：这些机制不含旅行社知识；若搬迁时发现某个函数带场景键，它留在 `simulation/`。

### 4.2 Curator 的执行观察给多少

| 方案 | 内容 | 取舍 |
|---|---|---|
| 全量（今天） | 本轮所有回合 | 题库结构与会话名一起过去；上下文最大 |
| 引用回合 | Analyst 在 evidence 里引用的回合，会话键换成不透明编号 | 归因所需齐全；依赖 Analyst 引用得准 |
| 不给 | 只给机制活动摘要 | Curator 无法核对机制在具体回合做了什么 |

采用引用回合。关键假设：`Requirement.evidence` 必填且落到回合，今天已如此。

### 4.3 台账怎么建

| 方案 | 做法 | 取舍 |
|---|---|---|
| 重写 `record.py` | 通用台账替换 2063 行启发式 | 收益最大；改动最大，且文件在保留名单 |
| 只加标签 | 记录写 `origin`，`record.py` 先用标签、无标签时退回启发式 | 增量可验；两套逻辑并存一段时间 |
| 新建通用台账模块 | `iteration/ledger.py` 按标签连接，`record.py` 改为消费它加旅行社标签 | 边界对；`record.py` 仍要改 |

采用第三种，分两步：先建 `ledger.py` 与标签，再让 `record.py` 消费。两套逻辑并存期记录在第 8 节。

## 5. 实施阶段与可检查交付

### 阶段一（已完成，已提交）

- `experimental/scenario/`：契约、默认可见性、加载与完备性检查；`scenarios/travel_agency/contract.json`。
- `experimental/iteration/session.py`：`Session`、`Outcome`、`StepError`。
- `tests/test_scenario_contract.py`、`tests/test_iteration_session.py`、`tests/test_simulation_scenario.py` 两条快照测试。
- `docs/rsi-iteration.md` 第 6 节。

### 阶段一点五（已完成，不碰保留文件）

隔间机制里能自负责的部分先行落地，其余记在下方"在等什么"。

- `iteration/audience.py`：字段受众声明（数据类用字段元数据，pydantic 用 `AUDIENCES` 类属性，包外类型用 `declare`）与 `project`；未声明即拒绝，裸映射在顶层被拒。
- `iteration/protocols.py`、`requirements.py`、`analyst/feedback.py` 声明受众；`iteration/declarations.py` 声明 `Execution`、`Change`、`Plan`、`StateUse`，其中 `Change.expected`/`verification` 只进记录。
- `scenario/sealed.py`：差分封印，token、长文本窗口、短文本短语三种指纹，`sealed_for(scenario, role)` 从契约推出。
- `iteration/compartment.py`：`Guard`、`GuardedProvider`（包住 `LLMProvider` 全部方法）、可 pickle 的 `GuardedFactory`、`Compartment`、`Boundaries`，记录写 `boundaries.jsonl`，策略 abort 与 warn。
- `iteration/session.py`：Analyst 与 Curator 的 provider 换成守卫版，Curator 的 feedback 先经 `admit`，分析与改造各在自己的隔间里；改造步的意外异常把记录标为 error。
- 测试 `tests/test_iteration_compartment.py` 九条。

在等什么：

| 未完成 | 等的是 |
|---|---|
| hearing 由逐字段剥离改为 `project`，`Remark` 退掉，会话键不透明、只传引用回合 | 已完成（见阶段二进展）；先验过滤等 C4 给它输入 |
| `run()` 进隔间并改写为 Session 的自动编排 | 已完成（2.1）：`run()` 是 Session 的自动编排，每步在其隔间里执行 |
| 伙伴的 provider 守卫（`GuardedFactory` 已备好） | 已完成：`hire(guard=…)`，`__main__` 从契约装配 `Boundaries` |
| `Withheld` 路径模式 | 已完成：`automation/employee.py` 的 `EVALUATION_PATHS` |
| 模拟老板不读 Curator 计划、提示词改为用自己的话说规则、`previous_expectations` 移出 Analyst 材料、history 剥 `expected` | 已完成（2.7） |
| 装配隔间与交互方、工作对象模拟器的守卫 | 已完成：模拟客人（`automation/traveller.py`）每次调用进 conversant 隔间，模拟老板（`simulation/agency.py`）每次评审进 party 隔间，都减去伙伴自己的产出；模拟入口把运行的 `Boundaries` 交给二者，进出与违规同样记进 `boundaries.jsonl`。至此每个角色的模型调用都在守卫之后 |
| 对真实一轮运行断言无违规的集成测试 | 已完成（2.4）：`tests/integration/test_iteration_boundaries_e2e.py`，2026-09-29 在 DeepSeek 上通过 |

### 阶段二（另一分支提交后，从其分支尖 rebase）

另一位开发者的四策略改造于 2026-09-29 提交，本分支随后 rebase 到其上：两个提交与阶段一点五的改动都无冲突地套用，本分支相关测试 112 项中 111 项通过；唯一失败是 `test_iteration_session.py` 的假 `improve` 不接受对方新增的 `observations` 参数。随 rebase 一起做的两处小改：假 `improve` 接受该参数；`Session._curate` 把 `observations` 经 `scope.admit` 交给 Curator，与 `run()` 保持同形。

已完成的阶段二工作（2026-09-29，rebase 之后）：

- 2.2 的 hearing 一半：`heard` 是 `project(signals, "curator")`，`Remark` 删除；`cited(sessions, feedback)` 取要求的证据或观察点名的回合，会话键换成不透明标签（按试炼名的短哈希，`hearing.opaque`）；`heard_observations` 只送这些回合，`run()` 与 `Session` 都改走它，对方新增的全量 `execution_observations` 由此退掉。测试 `tests/test_iteration_hearing.py`。
- 按出处豁免：`Sealed.without(texts)`；`Boundaries.compartment(role, spoken=…)` 给 Curator 隔间减去引用回合里工作对象的话；`Guard.check_request` 对伙伴减去 user 消息的文本。
- 伙伴守卫：`hire(guard=…)` 把 `GuardedFactory(make_lazy_provider, guard)` 作为 `provider_factory` 交给 Worker，随 spawn 进子进程；`simulation/__main__.py` 从契约推出各角色封印，装配 `Boundaries`，日志在运行目录的 `boundaries.jsonl`。
- 2.4 的路径部分：`employee.EVALUATION_PATHS` 覆盖 `iteration`、`assessor`、`analyst`、`scenario`、`simulation` 五个包与它们的测试，内容标记同步加上 `experimental.scenario`、`experimental.assessor` 及斜杠写法。

2.3 已完成（2026-09-29）：`Requirement` 加 `id`（闭环按历史顺序分配，`repeats` 时沿用）、`situation`、`grounds`（受众 party、analyst）、`materials`；`analyst.run.vet` 在提交时把反馈投影到 curator 受众后扫描（本轮条目 id、会话键、target 名、短的参考答案与备注，加运行的 Curator 封印），并要求每条要求点名本轮回合、写明情境；`Signal.attachments` 改为 `Handover(name, kind, files)`，模拟老板从契约读种类，记录按名字识别资料。长的参考文本只由运行封印负责：要求会合法复述检查项复述的规范，只有差分封印分得清。

2.9 已完成（2026-09-29）：归因是独立组件 `curator/attribution/`（设计 5.1.1、5.1.3）。`Attributor` 协议有两个实现：`ModelAttributor` 默认在 Curator 的 provider 与模型上开自己的一次对话，工具只有只读查询、原生探索、`submit_diagnosis` 与 `report_gap`，有自己的 `AttributionLimits`、可续跑的 `AttributionState`、提示词目录与身份；`SuppliedAttributor` 接收别处做出的诊断。`subjects(feedback)` 给出必须诊断的输入（要求 id、`material:<名>`、`node:<playbook>/<node>#<n>`，或 `task`），缺一即拒。每次归因写 `<worker>/attribution/<uuid>.json`；`workflow.attribute()` 只归因；生成从 select 开始，只接收 `Attributed`，`Selection.grounds` 与 `Declaration.parse_selection(value, attribution)` 让每个 target 引用诊断，`Change.treatment` 在设计提交里必填。C5 的记录侧随之完成：历史条目带 `diagnoses` 与 `treatment`，Analyst 不读 `diagnoses`；"是否守住"一位由 2.8 的台账算。测试 `tests/test_harness_curator_attribution.py`；生成、workflow、exploration、composition 的单测与 `tests/integration/test_harness_curator_*` 的脚本按"先归因、再从 select 生成"改过，单测与集成测试全部通过。

C6 已完成（同日）：`Change`、`Selection`、`Plan`、`StateUse`、`Execution` 在类型上声明受众（数据类也可用 `AUDIENCES` 类属性），`iteration/declarations.py` 退掉。

2.7、C5、2.8 的实施细化（2026-09-29，已完成，下面各条已落地；2.7 的"披露日程成为管线输入"随后完成，见 2.7 一行）。三项互相咬合：历史要表达（要求、诊断、改动、是否守住），"是否守住"要有唯一的计算规则，预测要退出所有提示词。

- 受众模块上移为 `experimental/audience.py`：Curator 的类型已在自己身上声明受众，却因依赖方向不能调用 `project`；上移后 Curator 与闭环共用一份角色与投影，`declare` 已无调用方，删除。
- 2.7：Curator 材料里的 `previous_expectations` 改为按 curator 受众投影的 `previous_plan`（不含 `expected`/`verification`）；Analyst 材料去掉 `previous_expectations`；模拟老板不再收 `reply`，提示词去掉 `curator_reply`。
- C5：历史条目改为 `iteration/history.py` 的类型（`Entry`、`Raised`、`Diagnosed`、`Revised`），字段声明受众，Curator 与 Analyst 各读自己的投影；`Revised.addresses` 取自选择的 `grounds`，为此候选带上 `selection`，激活时记到 `worker.last_selection`；`Raised.held` 在下一轮分析后由台账的规则填入。
- 2.8：`iteration/ledger.py` 给出"是否守住"的唯一规则（下一轮没有沿用它 id 的要求，且它依据的检查项与回归检查没有失败；都判未知则不下结论），以及从历史展开的台账行与按归因器身份、（状态，处置）的聚合；留出集是 `Session.trial(..., holdout=True)` 的会话，只被评价与记录，不给 Analyst、不被引用给 Curator，信号记在 `Round.holdout`。
- 验收：Analyst 与 Curator 的材料里没有 `expected`/`verification`；投影测试覆盖历史类型；台账测试覆盖守住、复发、检查项失败、无下一轮四种情形；留出会话不出现在 Analyst 与 Curator 的任何输入里。
- 同批完成：C3（`common/materials.md` 按 norm、fact、exemplar、counterexample 给处理规则，归因对资料按种类写 `placement`）；C7 的闭环一侧（缺口记为 `questions`，本轮不改造，运行继续）；`iteration/records.load` 读入归因记录并附上台账。测试 `tests/test_iteration_ledger.py`、`tests/test_iteration_session.py` 的留出集与缺口两条、`tests/test_iteration_hearing.py` 的历史投影。

2.2 剩下的，以及它暴露的：

- `run()` 里 Analyst 与 Curator 进隔间：已随 2.1 完成，`__main__` 把 `Boundaries` 交给 `run()`，Analyst 由 Session 用守卫版 provider 构造。
- 被托管的子代理（Raven-Research、Raven-PPT）作为独立产品进程用自己的 provider，未经守卫；它们的输入来自伙伴，泄露面在伙伴一侧，先记录。
- 引用回合依赖 Analyst 在 `evidence` 或 `observed` 里写回合 id：已随 2.3 完成，`analyst.run.vet` 拒绝不点名回合的要求。
- 先验过滤：C4 已给它槽位，经 `hearing.heard_prior` 过滤后进入。

对方提交对本规划的影响：

- `iteration/hearing.py` 新增 `execution_observations`，把本轮全部回合（含会话键、工作对象原话、全部记录）交给 Curator，即 4.2 里"全量"一项。2.2 的投影逻辑同样作用于它：会话键不透明、只传 Analyst 引用的回合。
- `simulation/employee.py` 新增通用入口 `hire_task`，去掉了 `Fresh`（副本每轮从本体复制，天然干净）。2.6 上提后它在 `automation/employee.py`。
- `simulation/scenario.py` 的上传改为整包复制（`SKILL.md` 原样），2.5 消费契约时沿用。
- 对方把 "preparation" 用作候选准备（`harness/preparation.py`、`StrategyPreparation.prepare`，已登记到 `CONTEXT.md`）。本规划的离线阶段改名为调研阶段 research，模块 `research/`，避免同名两义。
- 对方文档 `curator-workflow.md` 第 5 节写明"理解贯穿查询与后续阶段，并非要求额外生成一份固定格式的理解文档"，与 2.9/C1 的结构化 `Diagnosis` 方向相反。已定（2026-09-29）：对方实现时尚未考虑显式归因，2.9 按原方案在其 understand、select、design 三个阶段上加入 `Diagnosis`，并同步更正 `curator-workflow.md` 第 5 节的这句话。方案比较与产物定义见设计文档 5.1.1：用户选定独立的归因阶段（方案 B）。
- C3 到 C8 所指的文件对方都动过，但对应机制仍在：`Change.expected`/`verification` 仍是必填字段（C6）、`collect.py` 仍单列 previous expectations（C4、2.7）、`understand.md` 的 history 仍是自由文本（C5）、`report_gap` 仍无应答者（C7）。清单不变，位置以 rebase 后的文件为准。

| 编号 | 交付 | 改动 | 测试 |
|---|---|---|---|
| 2.1（已完成） | `run()` 改写为 Session 的自动编排：`Limits`、`Round`、`history_entry` 等移入 `session.py`，`run()` 只剩按 `Outcome` 取步；`run(boundaries=…)` 让 Analyst 与 Curator 进隔间，`simulation/__main__.py` 传入契约推出的 `Boundaries` | `iteration/run.py`、`iteration/session.py` | `test_iteration_run.py` 全部通过；`test_iteration_session.py` 的形状比较保留为两条路径同形的证据 |
| 2.2（已完成） | 字段受众声明与投影；隔间与守卫：`project`、`Compartment`、provider 代理、`records/boundaries.jsonl`；封印集合由契约推出；hearing 改为投影加三项逻辑（会话键不透明、只传引用回合、先验过滤） | `iteration/protocols.py`、`requirements.py`、`analyst/feedback.py`、新 `iteration/compartment.py`、`scenario/sealed.py`、`iteration/hearing.py` | 新 `tests/test_iteration_compartment.py`：所有字段有受众；投影不含他人字段；守卫拒绝未投影值与封印片段；差分封印不误报规范文本；守卫工厂可 pickle。新 `tests/test_iteration_hearing.py`（今天 hearing 的测试散在 `test_iteration_run.py` 里，随之迁入） |
| 2.3（已完成） | 带类别的交接项 `Handover(name, kind, files)`；`Requirement` 加闭环分配的 `id`、`repeats`、`situation`、按受众拆开的 `grounds` 与 `materials`；Analyst 提交时的结构检查（投影到 curator 受众后扫封印与 target 名；每条要求点名本轮回合） | `iteration/protocols.py`、`requirements.py`、`analyst/run.py`、`analyst/prompts/analyst.md`、`simulation/agency.py`、`simulation/record.py`、`iteration/session.py` | `test_analyst_run.py`：含条目 id、期望答案原文、target 名或不点名回合的要求被拒后模型重交；`test_simulation_scenario.py`：交接项带种类。契约定义见设计文档 5.1.2 |
| 2.4（已完成） | `Withheld` 路径模式；每个角色在每个隔间里的 provider 都被守卫的契约测试；对夹具运行的隔间记录做断言。契约测试没有另开文件，分在各角色所在模块的测试里：`tests/test_iteration_compartment.py`（隔间、守卫、按说话人豁免、同角色预绑定的 provider）、`tests/test_iteration_session.py`（Curator 与 Analyst 的隔间、先验扫描）、`tests/test_simulation_replicas.py`（每个演练副本在伙伴的守卫之后）、`tests/test_simulation_scenario.py`（客人与老板的隔间）、`tests/test_assessor_standard.py`（自动 Assessor 在 Analyst 的隔间里） | `automation/employee.py`（`withheld()`）、`automation/` 装配 | 集成 `tests/integration/test_iteration_boundaries_e2e.py` 用 DeepSeek 跑入职与一轮并断言无违规：2026-09-29 通过（35 分钟）；此前一次在默认的 48 次 Curator 调用下于入职暂停、没走到 Analyst，测试因此改用真实入职需要的预算，并先按运行状态失败 |
| 2.5（已完成） | `simulation/scenario.py` 消费契约：`Scenario.load` 经 `scenario.load` 读目录，`Scenario.of` 从契约构建，带上材料种类与契约本身；Agency 与模拟入口不再各读一遍 | `simulation/scenario.py`、`agency.py`、`__main__.py` | `test_simulation_scenario.py` 通过；重复 id 的用例改为先见契约的拒绝 |
| 2.6（已完成） | 通用机制上提到 `automation/`：雇佣、副本、并行演练、Curator 不能读的评测侧（`withheld` 的路径与标记同时覆盖 `automation/` 与 `research/`，搬出 `simulation/` 的代码不因此变得可读）、起点指纹与工作目录检查（`baseline`、`starting_harness`、`workplace`）、渠道上客人收到的内容、交付物读取与页图、越界检查、网关缓存断点，以及模拟客人（按题卡协议 `Card` 取人设，不再依赖旅行社的题卡类型）。按"带场景键的留在 `simulation/`"的规则留下：题卡数值的抽取规则（`cards.py` 的行程字段）、交互方视角的场景（它的题卡按这套规则抽取）、模拟老板（读 `reference.md` 的尺子，记录题卡的行程事实）与尺子本身、价值判定与记录导出。把模拟老板上提需要两处反转：尺子由实例注入（算参考值与记录抽到的事实两件事），题卡的通用抽取与行程推导拆开；下一个非旅行社的实例需要自己的老板时再做 | 新包 `automation/`；`simulation/` 的各模块与测试改为从它导入；`hire` 改收契约场景 | 现有测试只改导入与 `hire` 的参数；不新增行为 |
| 2.7（已完成） | 披露日程成为输入对象；模拟老板不再读 Curator 计划；预期字段从两侧提示词收回。日程放在 `scenario/disclosure.py`：`Disclosure.of` 把运行选的 `all`、`staged`、契约里的具名计划或显式分批变成唯一的规则（开场交什么、第 k 次评审交什么、交互方是否自选、最后一轮前交齐），分批的合法性由契约与它共用一个 `partition`；模拟老板按它交出，运行设置记下解析后的日程。三种放法比较过：放进闭环（Session 按日程代为交出）会与 Studio 里自己决定交什么的人冲突，留在模拟老板里则与契约的校验重复、Studio 用不上；所以日程归交互方，闭环只搬运交出的东西（`Signal.attachments`），不读日程 | `scenario/disclosure.py`、`scenario/contract.py`、`simulation/agency.py`、`simulation/scenario.py`、`__main__.py`、`analyst/materials.py`、`iteration/hearing.py` | 新 `tests/test_scenario_disclosure.py`；`test_simulation_scenario.py`：`Agency` 不接收 `reply`、按日程交出；`test_analyst_run.py`：材料无 `previous_expectations` |
| 2.8（已完成） | 留出集（模拟入口 `--holdout CARD...`：留出的题卡每轮演练，只由按声明检查项评分的自动 Assessor 评，老板不评、不交接，Analyst 与 Curator 看不到）；`iteration/ledger.py`；`record.py` 消费台账。设计里的 `origin` 标签落成类型化历史里的 id（要求 id、`grounds`、`addresses`、诊断的 `about`），不另设 origin 字段。`record.py` 只按这些 id 连接：要求经 `grounds` 里的 `check:<检查项 id>` 连到检查项，`case:` 记作它的案例，没有 check 依据的要求不连；改动经本轮历史条目里同一 target 的 `addresses` 找到它回应的要求，再取这些要求的检查项，只回应资料、节点或任务的改动（入职即如此）不连，没有历史条目的 curation（未安装、子 harness 自己的改动）也不连。记录新增 `requirements_ledger`（闭环自己的台账：rows、summary、holdout），transcript 加"要求台账"一节；"是否守住"只取自历史，`record.py` 不重算。原来的字符串启发式（文本里出现检查项 id、引用会话加共享引文、SOP 章节标记、整轮兜底）全部删除；资料何时交出改按信号里交接项的名字读，不再在评语里匹配 SKILL.md 的开头；`value.py` 没有归因记录时不再退回按规则 id 与章节标记判定。模拟老板的逐项判定对 Analyst 保密，要求多半只以 `assessor:agency` 为依据，显式规则下连不到检查项；为此运行结束时评价侧先读一次要求（`simulation/attribution.read_requirements`：模型把没有 check 依据的要求对到它复述的规则，结果与干预理由的归属一起记进 `attribution.json`），记录按它以 `reading` 连接，改动经 `addresses` 找到要求后同样取这些规则；闭环自己的台账仍只按 id 连接，这次阅读只服务评价侧的挖掘判定 | `scenario/contract.py`（holdout 声明）、`iteration/run.py`、新 `iteration/ledger.py`、`simulation/record.py`、`simulation/value.py`、`simulation/attribution.py` | 新 `tests/test_iteration_ledger.py`：要求到改动到下轮判定按 id 连接；`tests/test_simulation_record.py` 在无启发式下通过，其中文本点名检查项而 `grounds` 没有的要求不连；`tests/test_simulation_value.py`：没有归因记录时不计任何干预 |

| 2.9（已完成） | Curator 的显式归因作为独立组件：每条输入一条 `Diagnosis`（状态闭集八种），选择阶段每个 target 引用一条，设计阶段对点名机制说明修改、替换还是新增；`Plan.understanding` 只面向反馈者；Analyst 的归因停在行为层（`Requirement` 加 `situation`），两层归因经台账连接 | 新 `curator/attribution/`（协议、模型归因器、给定归因器、状态、提示词）、`harness/attribution.py`、`harness/artifact.py`、`harness/declaration.py`、`generation/run.py`、`generation/stages/select.py`、`design.py`、`workflow.py`、`composition/run.py` | 新 `tests/test_harness_curator_attribution.py`：覆盖与闭集、依据与处置、独立对话与模型、暂停续跑、提示词版本、缺口、给定诊断、记录与单独入口 |

顺序：2.1 与 2.2 先做（其余都建立在 Session 与隔间上），2.3 与 2.4 并行，2.5 与 2.6 并行，2.7，2.8 与 2.9 并行。2.9 触及 `curator/generation/`，rebase 后先与该区域的开发者对一次改动范围；他们当前的改动在 `implement.md` 与 `common/` 下，理解与选择阶段的文件不在其中。`Change.expected`/`verification` 的受众声明在 `curator/harness/artifact.py`，需与该区域协调。

### 阶段三

Studio 服务端接 Session：POST 路由、每个 run 目录一个会话进程、轮询 slim 记录加 pending 状态；`live.ts` 的十个动作逐个接到服务端，`useLive.ts` 的定时器换成轮询。webui 是本地排除目录，不入仓库，验收以 Studio 自己的 vitest 为准。

### 阶段四

| 编号 | 交付 | 位置 |
|---|---|---|
| 4.1（已完成） | 评价侧 `Standard`（声明、派生、沉淀三种来源）与自动 Assessor；实现说明见设计文档 5.2 | `assessor/standard.py`、`assessor/prompts/`、`iteration/session.py` 的 `assess`、模拟入口 `--standard`；测试 `tests/test_assessor_standard.py`，真实模型检查 `tests/integration/test_assessor_standard_real_llm.py`（`ASSESSOR_TEST_CONFIG`） |
| 4.2（归纳、确认与槽位驱动的研究已完成，播种题例待做） | 调研阶段：`slots.py` 槽位与缺口、`induction.py` 从范例与反例归纳规则、`inquiry.py` 用网页研究空槽并按引文核对、`researchers.py` 研究者（Claude Code、Codex 或本阶段模型）、`web.py` 经 Raven 的网页工具搜索与读页、`confirm.py` 交互方确认（往期记录的决定文件或模拟交互方）、`package.py` 写出新场景目录与 `provenance.json`，没交出的资料留作交互方持有；契约加载器认领它，评价侧只用交互方认可的资料；模型角色独立配置（`--model`、`--party-model`、`--research-model`）并记入 `--records`；实现说明见设计文档 5.3.1 与 5.3.2。播种题例是下一步，出处记为 researched | 新包 `research/`；`scenario/contract.py` 的 `Provenance` 与 `Scenario.handed`、`simulation/scenario.py` 的 `standing_norms`；测试 `tests/test_research_slots.py`、`tests/test_research_induction.py`、`tests/test_research_inquiry.py`、`tests/test_research_web.py`、`tests/test_research_package.py`，真实模型与网页检查 `tests/integration/test_research_real_llm.py`（`RESEARCH_TEST_CONFIG`、`RESEARCH_TEST_RESEARCHER`） |
| 4.3（已完成，本机部署待所有者决定） | 伙伴进程的 OS 级隔离：worker 进程以专用用户从代码镜像运行，只写运行里的区域 `employee/`；闭环记录只有 root 能读，运行目录可穿越不可列举，启动前以该用户跑探针，碰得到不该碰的就拒绝启动；方案比较见设计文档 4.2。本机已建用户 `raven-worker` 与镜像目录，确认过 worker 以该用户从镜像跑完一个 DeepSeek 回合；个人区、旧盘个人区、共享回收站里的旧运行与 `/tmp` 的权限收紧需要所有者决定，未收紧前探针拒绝隔离运行 | 新 `curator/raven_adapter/launch.py`（子进程启动器，未隔离时同样用它）、`confinement.py`（镜像、身份、环境、路径换算、交接、探针）；`worker.py` 的 `area` 与 `confinement`；`automation/employee.py` 的 `AREA`、`seal`、`unsealed`、`unseal`；模拟入口 `--isolate-as`、`--closed`；读记录的代码按新布局读 | `tests/test_harness_curator_confinement.py`；真实用户检查 `tests/integration/test_harness_curator_confinement_real_user.py`（root 且有该用户时运行） |

4.1 与 4.2 是模型参与的机制，按"用证据验证"的要求各配集成测试，用 DeepSeek 跑流程验证：4.1 的是 `tests/integration/test_assessor_standard_real_llm.py`，2026-09-29 在 DeepSeek flash 上通过；4.2 的是 `tests/integration/test_research_real_llm.py` 的两条，一条归纳与确认，一条联网研究旅行社扣下全部事实后的事实槽。

4.2 的第一次真实运行（2026-09-29，DeepSeek flash，强度 high）：内置旅行社场景去掉服务 SOP 与方案 PPT 规范交出，模拟老板知道这两份。归纳从接待话术与方案范例读出 9 条规则，两次模型调用；老板确认 4 条、修正 4 条（补上 SOP 里紧急投诉的两类情形、把章节开篇与行前清单改为可选页、把范例里的文件名改为模板编号、去掉向客人声明"与报价单一致"这一项），1 条因它的资料没提到而未决，驳回 0 条。确认与修正的进了 `induced-norms`，随方案范例在分阶段计划的第 1 步交出，未决的进 `induced-candidates`。

### 搁置待补：Curator 改造完成后立即补上

这些改动都落在 `curator/` 里，另一位开发者的改造完成并提交后，rebase 到其分支尖，按下表补齐；它们不是待议项，是已定的改动，只是时机在等。

| 编号 | 改动 | 位置 | 与哪项一起做 |
|---|---|---|---|
| C1（已完成） | 结构化诊断、选择引用诊断、设计说明修改或新增、`understanding` 只面向反馈者 | `curator/attribution/`、`curator/generation/` | 2.9 |
| C2（已完成） | 归因请求的材料里默认不放 target 目录：`ModelAttributor(catalogue=False)` 是默认，模拟入口 `--attribution-catalogue` 改为带上。依据是招聘场景上的一对 DeepSeek 运行：两者归因调用都是 18 次；不带目录时下一轮守住 6/7 条要求，还诊断出一处逻辑错误，全部评审满意后提前结束；带目录时守住 2/5 条，轮数用完。样本只有一对，换场景或换模型后应重测 | `curator/attribution/model.py`、`simulation/__main__.py` | 真实运行 |
| C3（已完成） | `materials.md` 按资料种类给处理规则：范例学形不学实，反例说明不能做什么 | `generation/prompts/common/materials.md` | 2.3 交接项带类别后 |
| C4（已完成） | 先验作为 Curator 的参考材料槽位，经 hearing 过滤后进入：`records.cultivation` 读往期运行的类型化历史与它的工作对象说过的话（留出会话除外），`hearing.heard_prior` 按 Curator 受众投影、换成不透明标签 `prior-N`，Session 把它作为反馈的 `prior` 交给每次改造；打开会话时先用本运行的 Curator 封印扫描先验的投影，只豁免原运行工作对象的话，命中即拒绝；契约的 `prior` 相对路径从场景目录读，模拟入口另有 `--prior`；归因与改造提示词说明它是别的培养的经验，只作参考 | `iteration/records.py`、`hearing.py`、`session.py`、`run.py`、`scenario/contract.py`、`simulation/__main__.py`、`attribution/prompts/`、`common/materials.md` | 2.2 |
| C5（已完成） | Curator 历史按（要求、诊断、改动、是否守住）四元组表达，类型在 `iteration/history.py`，"是否守住"由 `iteration/ledger.py` 的规则写入；预期只进记录 | `iteration/history.py`、`ledger.py`、`session.py`、hearing | 2.7、2.8 |
| C6（已完成） | `Change.expected`/`verification` 的受众声明写到类型上，`declarations.py` 里的外部声明退掉 | `curator/harness/artifact.py` | 2.2 |
| C7（闭环一侧已完成） | Curator 的 `report_gap` 有应答者：闭环已把缺口记为 `questions` 并继续运行；自动运行里的应答者是调研阶段的半在线入口，与槽位驱动的研究同做（离线的归纳与确认已完成，见 4.2） | `iteration/session.py`；`research/` | 4.2 的研究一步 |
| C8（已完成） | 非机制错误的经验回流：按 binding 的"已知坑"条目随契约给 Curator，作为事实。落在 `raven_adapter/reference/pitfalls/`：`artifact.md`（提交结构与模块交付，进四策略公共必读）与 `planning.md`（恢复时 initialize 只读、playbook-spec 合法性，进 planning.strategy 必读），经 `Target.knowledge` 从设计阶段起进入 `selected_contracts`；每条写明复发次数。能由宿主直接消除的改契约：playbook 未加载时报出 Raven 加载器或结构校验的原因（`bind._unloaded`）；`node_reasons` 的节点集合、键形式与 missing/extra 报错此前已由组合根的事实与提示词给出，不再重复成条目 | `raven_adapter/reference/pitfalls/`、`targets/`、`bind.py` | 分析任务之后 |

### 独立的分析任务（已完成，2026-09-29）

挖掘 `raven-rsi-runs/` 里现有运行的生成 trace：取 validation 与 repair 事件，按 `repair.md` 的边界类别（语法与导入、构造、方法与结果契约、状态恢复、资源与权限、观察到的行为）聚合成错误签名表，分出局部缺陷与设计错误。局部缺陷先归为参考材料或契约的缺陷去修，其余做成 C8 的条目；表里的复发次数是经验机制价值的第一个数字。

结果：373 份 curation 记录、96 个运行里，宿主校验失败 107 次，归成 33 个签名；接口陷阱 13 个（71 次），局部缺陷 15 个（25 次），宿主或环境 5 个（11 次），设计错误 0 个。最大的一类是组合根的 `node_reasons` 覆盖（35 次、24 个运行），当前代码已由事实与报错消除；其次是 artifact `values` 结构（20 次）与模块未交付（7 次）。宿主从未提供行为探针（428 条 `validation.probe` 都是 `not_supplied`），"观察到的行为"一类没有出现过。失败率明显依模型而异（组合根 `node_reasons`：glm-5.3 15/85、deepseek-flash 3/6、gpt-6-sol 1/24、opus-5.5 0/21），经验条目的收益预计集中在较弱的模型上。度量方法：以这些次数为基线，之后按同一签名、同一口径重算，按模型分开看。

### 记录在案、暂不排期

- Curator 的跨任务经验机制（泛化版；归因专属的度量与证据回流随 2.9 做，非机制错误的回流见 C8）：跨运行聚合每次 curation 的（诊断类型、表达方式、机制形状、后续守住率、成本、出处），作为注册来源供 Curator 查询，条目只由 Curator 可见的信息加守住位构成，Curator 的引用写进记录以度量经验本身的价值。依赖沉淀检查、`origin` 标签与通用台账。让 Curator 改自己的设计是第二层递归，需留出领域、混杂标签与人的验收，等第二个领域进来再议。
- 树搜索与候选择优：演练成本高，在没有归因度量前不做。

## 6. 领域术语

新术语：伙伴 partner、工作对象 conversant、交互方 party、Session、Outcome、Standard、调研阶段 research（含案例归纳 induction；不用 preparation，该词已是 Curator 侧的候选准备）、受众 audience、投影 projection、隔间 compartment、封印 sealed。定义在设计文档第 2 节与第 5 节，与代码一一对应；`CONTEXT-MAP.md` 只路由 Runtime 与 TUI 的术语，`experimental/` 的术语以设计文档为准，若要登记进 `CONTEXT-MAP.md` 需先与用户确认。

## 7. 验收矩阵

| 要求 | 检查方式 |
|---|---|
| 场景输入不超越类别 | `test_scenario_contract.py`：类别外文件被拒 |
| 检查项、判定、期望答案、尺子、人设、题库结构不到 Curator | `test_iteration_compartment.py` 字段级与投影；各角色模块测试里的隔间断言（见 2.4）；集成测试一轮真实运行无违规 |
| 评测侧目录不进快照 | `test_simulation_scenario.py` 两条快照测试 |
| Session 与 `run()` 同一实现 | 2.1 后 `run()` 调 Session，无第二套编排 |
| Assessor 不读 Curator 计划 | `Agency` 无 `reply` 参数 |
| 预期不进提示词 | Analyst 材料与 Curator history 中无 `expected`/`verification` |
| 台账与记录按 id 连接 | `test_iteration_ledger.py`、`test_simulation_record.py`：无字符串匹配路径 |
| 派生标准不单独终止运行 | `test_assessor_standard.py` |
| 全量单元测试 | `uv run --frozen --all-extras pytest tests/test_harness_curator_*.py tests/test_analyst_*.py tests/test_iteration_*.py tests/test_simulation_*.py tests/test_scenario_*.py tests/test_assessor_*.py tests/test_research_*.py -q` |
| 门禁 | `scripts/check_source_language.py`、`scripts/check_large_files.py`、ruff check/format |

## 8. 折中与处置条件

- 阶段一里 `session.py` 与 `run.py` 编排重复约百行：2.1 消除。
- 契约加载器与 `simulation/scenario.py` 各读一遍目录：已由 2.5 消除。
- 2.8 期间台账与启发式并存：已消除（2026-09-29），`record.py` 只按类型化历史的 id 连接，启发式已删，`test_simulation_record.py` 在无启发式下通过。
- 守卫的策略只做 abort 与 warn，不做剔除后继续；出现确认过的误报来源再考虑。
- 生成代码在宿主进程内的文件访问边界未解决：进程级权限方案需容器支持，静态 I/O 检查放在 Session 安装前，列为 2.4 的可选项，若做不到在设计文档第 4 节记为已知风险。

## 9. 待验证的假设

- 五类对第二个领域穷尽：阶段四前用一个非旅行社场景在纸上过一遍。
- Curator 全量观察里子 harness 上下文是否夹带交出文件以外的内容：2.2 前在真实记录上核。
- 预期字段的命中率：2.7 后在真实运行上统计，决定是否给任何角色看。
- 引用回合足够 Curator 归因：2.2 后用 s0925c 同类运行对比诊断质量。
