# experimental：数字员工的 Worker RSI

这个目录实验一件事：让 Curator 通过多轮交互，把一个 Raven 数字员工的 Harness 改造到能满足交互方提出的核心要求，像培养一个新员工那样。

- **按资料定制**：交互方交出的资料（流程、规范、模板）被 Curator 落到 Harness 的四个策略面上，员工从第一轮起就按这些规矩工作。
- **按反馈改进**：员工工作后，交互方说出哪里不对，Curator 修订 Harness，下一轮再检验。

通用机制（Assessor、Analyst、Curator、Iteration、Counterpart）不认识任何具体场景；`simulation/` 用两个场景把这套机制跑起来：模拟旅行社（展示案例）与品牌策略师加守望（文件交付、合规事实、交给值班同事 Raven-Oncall 的持续读数），每个场景只注入自己的事实计算器。

依赖方向为 `experimental/ → raven/`，`raven/` 不引用实验层。Curator 生成的内容通过 home 文件、配置、钩子、插件贡献、ContextEngine 与 ACP 子代理接入，由真实的 Raven AgentLoop 执行。Memory 的多段消息组装也推动了一项通用 provider 修复：Responses 转换保留所有 system 文本和 developer 消息，避免上下文贡献被覆盖。连接方式和依赖的内部成员见 [design.md 第 5 节](docs/design.md#5-与-raven-的连接)。

当前 Curator 只有 `memory.strategy`、`planning.strategy`、`capability.strategy`、`action.strategy` 四个语义生成入口。每个入口绑定生成的策略类；配套源码、Skill、Prompt 和模板由类代码采用，原生配置与 Playbook 经角色所属的准备服务生效。一次修订只更新需要变化的策略。当前使用方式见 [design.md](docs/design.md) 和[候选准备契约](curator/raven_adapter/reference/preparation.md)。

宿主提供根 Harness、可用子基线及授权，Curator 决定业务分工和哪些子层需要定制；根 Agent 在运行时决定实际委派。支持子能力不要求每次请求都使用它。历史迁移依据保留在 [Target 收敛评审](docs/strategy-code-generation-review.md)；真实案例的范围与未完成验证见 [专家包测试方案](docs/expert-package-test-plan.md)。

策略可选择规则或[单步语义判断](curator/harness/reference/inference.md)：Curator 提供机制及配套提示词，运行时 Worker 模型返回有类型的判断结果，再由策略交给原生消费者。调用无工具循环、无内部修复；次数、预算与作用域由宿主限制，验证范围见[实施记录](docs/semantic-intervention-plan.md)。

## 目录

```text
experimental/
├── README.md
├── docs/                            设计文档（每个管线步骤一篇）
│
├── harness/                     L1  一个 Harness 及改进它的通用机制：不认识员工、交互方和案例
│   ├── contract/                    产物模型、Declaration、四个策略协议、commitments、inference 契约与参考页
│   ├── raven_adapter/               绑到 Raven 运行时：targets、bind、worker、inference 额度、inspection、hosting、confinement
│   ├── curator/                     生成者：workflow 入口、generation（select → design → implement → repair）、attribution、composition
│   ├── assessor/                    持有标准、测量每一轮：rubric、builder、reviewer、validation、introspect、human、dataset
│   ├── analyst/                     把 Assessor 的话整理成 Curator 的行为要求
│   ├── experience/                  受治理的经验：admission、governance、verification、repair、retrieve、store
│   ├── scenario/                    材料契约、披露日程、差分封印
│   ├── participation/               每个参与方共同遵守的东西：protocols、exchange、compartment、hearing、audience、
│   │                                requirements、allowance（token 区间）、model_calls、model_roles、channel、files、render、views
│   └── loop/                        循环本体：run、session、history、ledger、records
│
├── cultivation/                 L2  数字员工的培养：L1 的应用形态，定义反馈从交互中来
│   ├── counterpart/                 交互方协议：Owner（评审骨架、交材料）、scenario（交互方眼中的场景）、case（交付谓词）
│   ├── collector/                   专家信息收集：assess → ask → research → compose → review，专家口吻成文
│   ├── conversation.py              员工与交互方的对话回合
│   ├── employee.py                  把 worker 雇成数字员工：基线、副本、Curator 不能读的评测侧
│   └── __main__.py                  真人入口：一个人既是交互方又是对话人
│
├── simulation/                  L3  没有真人也把一次培养跑起来：测试台 + 任务包
│   ├── __main__.py, suite.py        单次运行与批量挖掘入口
│   ├── bench/                       测试台：conversant（按题卡扮演的对话人）、drills、cards、isolation、caching、
│   │                                record、value、attribution、information（模拟交互方答问）、experts、collect
│   ├── cases/                       任务包：materials、题卡、Owner 子类、参考事实
│   │   ├── travel_agency/           旅行社：owner.py、reference.py（价目与方案 PPT 的尺子）
│   │   └── brand_strategist/        品牌策略师：owner.py、experts、watch 源
│   └── showcase/s0925c/             展示案例记录
│
└── webui/                           本地网页界面：Studio 与 ribbon，读 cultivation 的记录
```

## 通用机制与场景的关系

依赖方向固定：`simulation/ → cultivation/ → harness/`，只向下，`tests/test_experimental_layers.py` 强制。`harness/` 不认识员工、交互方和案例；`cultivation/` 只定义反馈怎样从交互中来；`simulation/bench/` 用模拟的人跑 `cases/` 里的任务包，案例不反向引用测试台。

| 通用接口 | 旅行社场景的实现 |
|---|---|
| `harness.loop.run.run(worker, provider, trials, assessors, analyst=…, opening=…, boundaries=…, prior=…)` | `simulation/__main__.py` 从场景契约组装参数与隔间，默认最多 4 轮 |
| `Trial.run(worker) -> Sessions` | `simulation.bench.drills.enlist` 把题卡装成模拟对话人 `Conversant`，`grouped` 配成 `Together`，让每张题卡在员工的隔离副本上并行演练，副本每轮从本体复制，所以每次演练的子代理 home 都是干净的 |
| `assessor.role.AssessorProtocol.evaluate(sessions) -> Signal` | `cultivation.counterpart.Owner` 的案例子类（旅行社 `cases.travel_agency.owner.Agency`、品牌 `cases.brand_strategist.owner.BrandOwner`，按场景名从 `OWNERS` 选）：老板持有标准，按注入的事实评审并按披露日程交材料；并列的 `assessor.introspect.Introspection`：雇员在副本上自评每单，来源 `self`（`--no-introspection` 关闭）；可选 `assessor.standard.Assessor`；通用 Analyst 把这些整理成要求 |
| `harness.raven_adapter.worker.Worker` | `cultivation.employee.hire` 雇来的员工，带上 Curator 不能读的评测侧文件（`withheld`）；`cultivation.employee.Replica` 是每张题卡的隔离副本 |
| `harness.curator.workflow.improve(worker, provider, feedback=…)` | 不改，直接调用 |
| 入职资料 `opening` | 老板的入职对话与交出的资料 |

### Evaluation role names

`assessor.builder.RubricBuilder` constructs and revises rubric criteria;
`assessor.standard.Assessor` evaluates outputs against them. `assessor.role.AssessorProtocol`
is the shared interface for evaluation sources. `Standard` remains the rubric data type.
`assessor.reviewer.MetaReviewer` audits rubric/check defects and proposes reusable construction guidance.

Use `rubric_builder`, `assessor` and `meta_reviewer` in `--model role=value`, `--effort role=value`, and WebUI
model settings. These replace the former `critic` and `judge` keys; callers must use the new names.
New signals and assessment traces use `assessor`; builder traces and the revision section in
`standard.json` use `rubric_builder`. The record reader still displays saved runs with the former
keys, without rewriting those records. The `--standard` source selector and `standard.json` filename stay the same.

With `--standard derived sedimented`, simulation and live sessions construct gates, guardrails and quality criteria,
run the Assessor, and allow one meta-review and corrective reassessment. Explicit external conditions stay protected.
Built-in program verifiers check completed replies and readable delivered text; they establish only those properties.
Additional domain verifiers and independently calibrated restricted expressions can be supplied through the Assessor API.

`assessor.rubric.Criterion` is the shared contract for construction, assessment and review. It carries `definition`
(subject, applicability, one acceptance statement), `basis` (source references, host-bound versions and derivation),
and `assessment` (required evidence, a whole-criterion decision and necessary local checks). `origin` records entry
through declared/derived/sedimented; `kind` determines strength and `authority` protects external requirements.
LLM instructions, named verifiers and program expressions have separate typed fields. Passing local checks alone
cannot establish the full criterion; a program decision also needs independently labeled calibration bound to its
exact contract. Required evidence that is missing, truncated or based on a stale source remains unknown.

New `standard.json` records use schema 3. `parent_id` is the only stored tree relationship; each parent keeps its own
whole-condition judgment. Schema 2 semantic records resume as flat forests. Earlier records lacking semantic contracts
remain viewable but must be rebuilt from original inputs before execution.

`RubricBuilder(max_calls=4, max_nodes=16)` bounds each construction transaction, including rejected/cut response retries.
An evidenced `Change.refine` queues a local follow-up; roots and branches may have different depths. A host
`RevisionScope` limits every operation and rewritten field, regardless of the reason supplied. No new input or issue
means reuse, not another model call. Pending targets and stopping reasons are recorded and shown in the evaluation view.

Meta Reviewer issues carry an explicit `allow` list. A checker issue can authorize only assessment edits; a bounded
repair cannot request recursive expansion. Unresolved diagnoses remain pending until supported verification; changing
their wording or returning an empty next review does not close them. `Assessor(repair_suites={id: RepairSuite(id, cases)})`
accepts independently labeled `ReplayCase` tuples for a property's repair. For a relationship or removal, the suite can
name its encompassing criterion, or `None` for an explicitly verified whole-rubric property. Whole-task labels are not
accepted as substitutes for a checker-specific oracle. Missing verification leaves the repair a candidate. Exact
duplicates can be removed with a host-checked equivalent condition retained; this proves preservation, not judging accuracy.

Use `--owner-feedback silent --disclose all` for simulation comparisons where the owner's scores are measurements
only. All materials must be available at onboarding. Measurement signals remain in the record and are excluded from
Analyst input, curation, historical requirements and stopping decisions. Actual external feedback still takes precedence.

Evaluation records live in `standard.json`. By default, `evaluation-memory/` under the run holds `guidance.json` and
`replays.json`; `--evaluation-memory <directory>` (or `evaluation_memory` in live configuration) deliberately reuses
them across runs. Keep this directory outside the worker's workspace and out of its reachable tool paths. Guidance
retains cited episodes so its source survives the originating run. A shared store refuses stale writes from another
run; reopen the store before attempting further learning.

`Session.holdout` captures outcomes from fixed external rubric/dataset verifiers, with policy and execution identities.
Simulation supplies these through `--holdout`; direct Session callers must run held-out trials on isolated replicas.
The corpus keeps up to three passing and three failing outcomes. Only a comparison against independently labeled
positive and negative cases, with improvement and no regression, activates proposed guidance. Missing evidence leaves
guidance pending. Live sessions can reuse an existing corpus; they do not manufacture independent labels from human
conversation or self-assessment. At most eight active principles/procedures enter subsequent Builder instructions.

The run record distinguishes experimental installation from `promotion`: `candidate`, `rejected` or `accepted`.
`stable_revision` records the last verified version; it does not deploy or automatically roll back the live worker.
The Cultivation and Record views display the rubric, check evidence, review issues, guidance lifecycle and promotion.

Curator experience is optional. Simulation and iteration accept `--experience-memory <directory>` and
`--experience-scope <scope>`; `--experience-migrate` explicitly upgrades an older store. LiveConfig exposes the same
settings. The host-owned directory must remain outside Git and Worker writable areas. No experience directory keeps
the existing behavior. Each curation freezes stage-specific Markdown guidance and validates it again on resume and
before installation. New records and normal-task observations teach later tasks; held-out comparisons cannot train
the experience store.

Both experience loops use the shared admission and revision protocol documented in
[the governance design](docs/experience-governance-design.md), with separate [Rubric](docs/rubric-experience-plan.md)
and [Curator](docs/curator-experience-plan.md) plans. Curator method corrections remain candidates until an independent
host verifier or `CuratorExperience.verify_repair` supplies a targeted comparison; model review alone cannot adopt
them. Frozen usage, diagnoses, source withdrawals and adoption receipts remain auditable in host-owned records.
See [design](docs/evaluation-system-design.md) and [implementation evidence](docs/evaluation-system-plan.md).

## 运行

独立专家构建、离线准备与 Scenario 首轮共用同一收集流程。缺口由 LLM 根据内容判断，不再按材料类别是否存在触发。离线结果是信息快照与审核记录，不是新的场景目录；旧 `--out / --records / --without / --decisions / --from-records` 编排已移除。

```bash
# 旅行社模拟：一次运行（需要自备带 key 的配置文件）
uv run python -m experimental.simulation --config <config.json> --home <基线 home> \
  --state-dir <新的空目录> --scenario travel_agency --disclose all --rounds 4

# 离线准备：只使用指定披露计划的首轮材料，输出审核结果与记录
uv run python -m experimental.cultivation.collector --scenario <场景目录> --disclose staged \
  --output <新的准备目录> --config <config.json> --research exchange

# 或明确指定此次已交付材料；允许询问真人
uv run python -m experimental.cultivation.collector --scenario <场景目录> --release <材料名> \
  --output <新的准备目录> --config <config.json> --interactive

# Scenario 首轮可复用离线审核结果；任务、材料、环境不匹配时拒绝，需要重新评估
uv run python -m experimental.simulation --scenario <场景目录> --config <config.json> \
  --state-dir <新的运行目录> --information <准备目录/result.json>

# 留出集：这些题卡每轮演练，只由按声明检查项评分的自动 Assessor 评，Analyst 与 Curator 看不到
uv run python -m experimental.simulation --config <config.json> --state-dir <新的空目录> \
  --scenario travel_agency --holdout <题卡名>

# 老板只评不说：评审照常记进每轮记录作度量，但不进 Analyst、停止判断、历史和 Curator，
# 改进只靠雇员自评与 --standard；材料须在入职时交齐
uv run python -m experimental.simulation --config <config.json> --state-dir <新的空目录> \
  --scenario brand_strategist --disclose all --owner-feedback silent --standard derived sedimented

# 真人 CLI：真人既是对话方也是评价者
uv run python -m experimental.cultivation --help

# 从业务任务和交互材料开始；没有产品案例也能进行信息收集
uv run python -m experimental.simulation.bench.experts --config <config.json> \
  --task-file <业务任务.md> --material <交互材料目录> --output <新的运行目录> \
  --research exchange --interactive

# 可选：产品案例仅为调研提供引导，不作为本次交互输入
uv run python -m experimental.simulation.bench.experts --config <config.json> \
  --task-file <业务任务.md> --research-reference <产品案例目录> --output <新的运行目录> \
  --research exchange --research-tasks 3

# 产品包也可以明确作为交互输入：先评估已有信息与缺口，不强制抽象或重新调研
uv run python -m experimental.simulation.bench.experts --config <config.json> \
  --expert <专家包目录> --output <新的运行目录> \
  --research exchange --interactive --request-file <客户需求.md>

# 测试
uv run pytest tests/test_harness_curator_*.py tests/test_analyst_*.py tests/test_iteration_*.py tests/test_simulation_*.py \
  tests/test_scenario_*.py tests/test_assessor_*.py tests/test_research_*.py
```

首轮构建先输出 `information/` 记录：八个维度的说明、获取证据、研究任务组、候选版本、审核意见和未决问题。
只有审核接受且没有阻断问题，才将整理后的说明写入员工的 `uploads/information/` 并调用 Curator。
`--material` 和 `--expert` 的材料保留在员工上传目录，按交互输入评估与采用；`--research-reference` 的材料
只供单独的调研引导读取，不进入员工上传目录。只有实际委派调研且选择使用引导时，才执行一次有界提炼，
结果在多个研究组间复用。一个组可以关联多个信息字段，材料已充分时不启动调研。
`--interactive` 允许在终端回答信息问题，`--answers-file` 提供事先写好的答案。没有配置用户渠道时，评估环节不提出
用户问题，只有用户能定的事写成描述里的前提（`assumption`），结果仍为 `ready`；配置了渠道时宿主只问一轮，
没答到的问题同样带着前提继续，只有加上 `--wait-for-input` 才会停在 `needs_input` 等待输入。
审核未通过且修订额度用尽、或某个环节超时时为 `incomplete`，不会继续改造。
`--research exchange` 使用配置中的网页工具和独立研究对话，也可选 `claude`、`codex` 或 `none`。
主流程模型由配置文件决定，调研模型单独指定。例如，配置主流程为 DeepSeek 后，可用
`--research claude --research-model claude-sonnet-5-5 --research-effort xhigh`
运行 Claude Code 调研；`--research-effort` 不会改变主流程的推理设置。离线准备与专家构建入口
均支持这些选项，具体模型和 effort 是否可用取决于本机 CLI 与账号。
Claude Code 的预算是客户端控制值，最后一次调用可能使报告金额超过上限；运行记录保留
客户端报告的模型、耗时、金额与终止原因。这些金额不是账号账单，引用核验通过也不等于结论充分。
默认不设置美元上限；确需客户端金额控制时才传 `--research-budget`。
`--collection-timeout` 默认 3600 秒，限制一次信息收集的整个闭环。闭环由宿主按固定顺序执行：读材料、评估
（最多 4 次调用、6 次本机查询、300 秒）、提问、规划调研组（2 次调用、120 秒）、并行执行调研波、汇编描述
（3 次调用、600 秒，完整专家包的汇编一次调用可能超过 300 秒）、审核并最多修订一次
（`--submission-reserve` 默认 900 秒保留给汇编、审核和一次修订）。
每个调研组最多 `--research-window`（默认 1800 秒），且不超过保留额度之前剩下的时间；剩余窗口不足 600 秒
时跳过调研。`--research-tasks`（默认 3）限制一波里并行的组数，每组最多 `--research-questions`（默认 2）个问题，
`--research-waves`（默认 1）限制调研波数，第二波只在仍有缺口且时间允许时发生。
每组窗口里再留 150 秒给引文核验和审核，研究代理只能用其余部分。

模型只决定内容，不决定顺序：评估环节交回覆盖判断、用户问题和调研需求，规划环节交回调研组，汇编环节交回描述。
每个组执行一次调研、来源核验和逐条审核；被采纳的发现逐条进入证据并返回证据 id，被扣留的发现和综述带着理由
留在尝试记录里。是否修订由宿主规则决定：有被扣留部分、审核判为编辑式且窗口还剩 300 秒以上就不搜索改写一次，
判为需要新来源且还剩 600 秒以上就重新取证一次，否则记为缺口；不存在第二次。
宿主读不到被引页面的发现记为线索（`leads.json`），只是带地址的调研问题，不是证据。
所有提示词共用 `prompts/voice.md` 的表达标准：描述和调研交付要像资深从业者给同事的交接说明，
两个审核都把不符合这一标准列为可退回的缺陷。

未通过审核的正文保留在尝试记录中，不进入知识证据。网页截断、JSON 转义和 PDF 断词的核验处理保持；
失败原因与原始记录保持可追溯。超时或审核额度耗尽会保存 `result.json`、`snapshot.json`、`trace.json`
和各环节记录（`assessment.json`、`questions.json`、`plan-<波>.json`、`wave-<波>.json`、`proposal-<n>.json`、`review-<n>.json`），返回 `incomplete` 及 `stop_reason`，不会继续构建 Harness。
下一次可以用已有快照和聚焦字段重新评估；不自动恢复全部失败任务或重跑整套调研。

离线入口支持 `--collector claude` 或 `--collector codex`，配合 `--model <模型> --collection-effort <强度>`，
通过 Claude Code 或 Codex 的受限结构化调用驱动同一个收集流程。CLI 只选择宿主提供的工具，由宿主执行；
审核同样只提交判断。两者都用本机 CLI 的登录，不需要 Raven 配置里的 key；Codex 会在只读沙箱里运行、不加载用户配置，
收集调用不开网页搜索。默认 `--collector provider` 仍使用 Raven 配置中的模型。

一次真实模型检查只验证有界闭环：收集和审核实时运行，调研使用已有记录回放，不新增网页搜索。
整次上限 300 秒、一个研究组、无自动修订，不重复启动；输入是旧销售教练试验中已保存的
`candidate-2.json` 与 `sources-2.json`，只取其中一条职业标准发现。
默认 `RESEARCH_COLLECTION_MODE=replay` 使用固定交付；设为 `source_review` 时，研究模型只根据该发现
对应的已保存来源页面实时生成交付，修订由宿主规则决定。两种模式均使用生产收集流程，
整轮上限仍为 300 秒，不新增网页搜索。

```bash
RESEARCH_CLAUDE_CONFIG_DIR=/path/to/.claude \
RESEARCH_COLLECTION_RECORDS=/outside/repo/new-run \
RESEARCH_COLLECTION_FIXTURE=/outside/repo/retained-group \
uv run pytest tests/integration/test_research_real_llm.py -k claude_collection_closed_loop -v -s -o addopts=''
```

测试脚本只提供环境、输入与证据回放，不另写规划器、审核循环或手动决定修订路径。
结构化检查通过或按预算正确结束，不等于完整职业画像已经充分，更不等于专家工作能力得到证明。

Scenario 默认在入职前准备信息；`--information-research none` 关闭外部研究渠道，不跳过信息评估。可选 `--information-answer-material <材料名>` 让模拟交互方回答必要问题，私有资料只在回答适配器内使用。离线入口的对应选项是 `--answer-material`。内容审核不代替交互方采纳，研究结果也不自动成为评价标准。

后续信息补充可传 `--previous-information <snapshot.json>`、`--focus knowledge methods` 和
`--answers-file <带版本的答复JSON>`；已生成的 `guidance/guidance.json` 可以用 `--research-guidance` 复用。答复文件格式为 `{"version": "sha256:上一快照摘要", "answers": {"问题ID": "答复"}}`，版本不匹配时拒绝使用。独立专家入口也可用 `--information <离线result.json>` 复用匹配的已审核结果。
非关注字段及未决问题保持，输出记录本次改变的维度与上一版本。命令仍创建新运行；已有 Harness 的自动轮间
收集和暂停改造后的重启未接入。API 发布信息前会检查当前版本，防止覆盖过期输入或改写暂停改造的依据。

## 本地 Studio

`experimental/webui/` 是本地的网页界面：只读地展示记录下的运行（每轮的演练、老板的评审、Analyst 的要求、Curator 的归因与改动、交付物），给了 `--live-config` 时还能在页面上驱动一次真人参与的培养会话（`webui/live.py`，每一步调用闭环的 `Session`）。页面由 Vite 构建，入口 HTML 在构建时由 `scripts/entry.mjs` 生成，不入库。

运行查看页的 Cultivation 视图是上下布局：上方是一块闭环画布（`webui/src/loop.ts` 从对话所用的同一条时间线推出，`views/LoopMap.tsx` 用 React Flow 绘制），入职和每一轮各占一块独立的画板。入职是一条开口的线（交接 → 诊断 → 设计 → 实施）；每轮是一圈闭合轨道，上沿是演练一侧（版本 → 演练 → 评估 → 分析），下沿折回是 Curator 一侧（诊断 → 设计 → 实施）。画板标题右侧写这一轮的结果，环中间写评分，画板之间的虚线标出交给下一轮的版本。画布可以拖动、缩放（左上角按钮）；画板都放得下时整体显示，放不下时出现小地图，并跟随阅读位置平移到对应的画板。下方是完整的多轮对话。两者互相跳转：点站点让对话滚到这一步（`data-station` 标出每段对话所讲的站点）并闪一下，读到哪一站、鼠标停在哪一段，画布上对应的站点就亮起，所在画板描边。鼠标在画板上移动时，近处站点放大并朝鼠标偏移，一束光跟着鼠标；指着的站点的事实显示在画布下方。正在跑的运行由 `/api/phase`（`serve.run_phase`）标出当前站点，流向它的轨道和进入这一轮的交接线是流动的。

对话里每个渲染出来的模块都能切到它自己的原始内容：模块的标题行（或右上角）有一个“rendered / { } raw”分段开关（`views/Raw.tsx`），切到 raw 时原位显示这个模块取自记录的那几段，每段标出它在记录里的路径（`sources.ts`）。Curator 回复里，诊断取 `generated.candidate.attribution`（或归因记录），理解与设计取 `plan.understanding` / `plan.design` 的 Markdown 原文，选择理由取 `selection`，交接材料取信号附件及点到这些材料的诊断与 grounds，每项改动取 `plan.changes[i]`、`artifact.values[target]`、绑定工厂所在的生成模块源码、该模块导入的其他生成模块（折叠）和 `selection.grounds[target]`，代码层的每个绑定同上，宿主检查取 `generated.validation`，失败说明取记录的 error / missing / paused 与 `validation.errors`；owner 的交接与评语取信号（正文按 Markdown 原文），Analyst 取它的 feedback，调研阶段取调研记录。开关放在 `<summary>` 里也不会顺带展开或收起所在模块。代码块由 `views/Code.tsx` 统一绘制（highlight.js 按扩展名高亮、复制；代码不折行、带行号栏，JSON 逐行编号并自动折行），“Generated code and bindings”里的文件和绑定值也用它。

页面拿到的 run（`/api/runs/<id>`，`serve.detail`）是瘦身过的（`serve.slim`）：组合 curation 里交给 Curator 的会话副本（`composition.observations`）不下发；页面只计数的记录（各策略的调用与结果、模型输入等）只留顶层的简单字段，`action.call` 另留它回应的事件头，被裁过的回合标 `records_cut`。员工回复与工具事件、子 harness 步骤、Action 的结果与控制、回滚、playbook 进度和各类错误整条保留。回合下的 records 折叠框打开时再从 `/api/turn` 取这一回合的完整记录，逐条列出、点开看高亮 JSON。服务端按迭代记录的修改时间缓存瘦身结果，超过 64 KB 的 JSON 回答按浏览器的 `Accept-Encoding` 用 gzip 压缩。磁盘上的记录不受影响。三轮的品牌 run 由此从几百 MB 降到 20 MB 以内（gzip 后约 3–4 MB）。

```bash
cd experimental/webui && npm ci && npm run build && cd -
uv run python -m experimental.webui.serve --runs <放运行目录的目录> [--live-config <config.json>]
# 浏览器打开 http://127.0.0.1:8765 ：根路径（以及 /viewer）是运行查看页，/studio 是 Studio；默认只绑定本机
```

## 隔离运行

`--isolate-as <用户>` 让员工的进程树（shell、子 harness、Curator 安装的策略代码）以这个用户从代码镜像运行，只能写它在运行目录里的区域 `employee/`（设计文档 4.2）。前提：

1. 以 root 运行；机器上有这个用户且不是 root，例如 `useradd --system --no-create-home --shell /usr/sbin/nologin raven-worker`。
2. `--state-dir` 之上的目录对其他用户只可穿越、不可列举（0711），这些目录里不在通往运行路径上的条目对其他用户关闭；仓库、场景目录与以前的运行对其他用户关闭；系统临时目录对其他用户不可列举（1733）。
3. 镜像默认建在 `/opt/raven-worker`，与 uv 缓存同盘时硬链接，按内容摘要复用。

启动前以这个用户跑一次探针，有一条不满足就拒绝启动并列出路径；`--closed <路径>...` 追加必须关闭的路径。运行结束时运行目录关成 0700，之后的运行进不去。

```bash
uv run python -m experimental.simulation --config <config.json> --state-dir <准备好的目录下的新运行目录> \
  --scenario travel_agency --isolate-as raven-worker --closed <别处存放场景或记录的目录>
```

## 展示案例

本节是旧多 Target 版本的历史运行记录，保留原始产物与结果，不作为当前四策略生成格式示例或新版验收证据。

[`simulation/cases/s0925c/`](simulation/cases/s0925c/) 是一次自动运行的培养记录：老板只交资料、扮客人演练、说意见，Curator 在入职时凭资料生成了流程与关口，之后按意见逐轮补齐，第 3 轮全部红线通过。目录里有案例说明、系统自动导出的 transcript，以及第 1 轮和第 3 轮的方案 PPT。

Planning 的公共交互、Capability 联动、恢复和执行边界见 [Planning 实施方案](docs/planning-strategy-plan.md)，当前生成指南见 [Planning](curator/harness/reference/planning.md)。

完整生成与运行通路见 [Curator 流程说明](docs/curator-workflow.md)，其中第 3 节详细解释四策略的一等生成入口。最新真实模型结果见 [产品案例验证记录](docs/expert-package-validation.md)。
