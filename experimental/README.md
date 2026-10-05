# experimental：数字员工的 Worker RSI

这个目录实验一件事：让 Curator 通过多轮交互，把一个 Raven 数字员工的 Harness 改造到能满足交互方提出的核心要求，像培养一个新员工那样。

- **按资料定制**：交互方交出的资料（流程、规范、模板）被 Curator 落到 Harness 的四个策略面上，员工从第一轮起就按这些规矩工作。
- **按反馈改进**：员工工作后，交互方说出哪里不对，Curator 修订 Harness，下一轮再检验。

通用机制（Assessor、Analyst、Curator、Iteration）不认识任何具体场景；`simulation/` 用一个模拟旅行社把这套机制跑起来，并留下一个展示案例。

依赖方向为 `experimental/ → raven/`，`raven/` 不引用实验层。Curator 生成的内容通过 home 文件、配置、钩子、插件贡献、ContextEngine 与 ACP 子代理接入，由真实的 Raven AgentLoop 执行。Memory 的多段消息组装也推动了一项通用 provider 修复：Responses 转换保留所有 system 文本和 developer 消息，避免上下文贡献被覆盖。连接方式和依赖的内部成员见 [design.md 第 5 节](docs/design.md#5-与-raven-的连接)。

当前 Curator 只有 `memory.strategy`、`planning.strategy`、`capability.strategy`、`action.strategy` 四个语义生成入口。每个入口绑定生成的策略类；配套源码、Skill、Prompt 和模板由类代码采用，原生配置与 Playbook 经角色所属的准备服务生效。一次修订只更新需要变化的策略。当前使用方式见 [design.md](docs/design.md) 和[候选准备契约](curator/raven_adapter/reference/preparation.md)。

宿主提供根 Harness、可用子基线及授权，Curator 决定业务分工和哪些子层需要定制；根 Agent 在运行时决定实际委派。支持子能力不要求每次请求都使用它。历史迁移依据保留在 [Target 收敛评审](docs/strategy-code-generation-review.md)；真实案例的范围与未完成验证见 [专家包测试方案](docs/expert-package-test-plan.md)。

策略可选择规则或[单步语义判断](curator/harness/reference/inference.md)：Curator 提供机制及配套提示词，运行时 Worker 模型返回有类型的判断结果，再由策略交给原生消费者。调用无工具循环、无内部修复；次数、预算与作用域由宿主限制，验证范围见[实施记录](docs/semantic-intervention-plan.md)。

## 目录

```text
experimental/
├── README.md
├── requirements.py              # 行为要求 Requirement：Analyst、模拟评审与 playbook 节点要求共用
├── audience.py                  # 字段受众：每个字段哪些角色能读，project 按角色投影
├── docs/
│   ├── design.md                # Curator 怎样生成与管理 harness-of-harnesses
│   ├── rsi-iteration.md         # Harness 怎样在多轮反馈中迭代改进
│   ├── cultivation-loop-design.md  # 改进闭环的角色、边界、归因、台账与标准
│   └── cultivation-loop-plan.md    # 闭环机制的实施规划与进度
│
├── scenario/                    # 【通用】场景契约：闭集的输入类别与各角色的可见性
│   ├── contract.py              #   类别、默认可见性、资料出处（provenance.json）、目录加载与完备性检查
│   ├── disclosure.py            #   披露日程：开场与每次评审交出什么
│   └── sealed.py                #   差分封印：从契约推出每个角色不能看到的内容
│
├── research/                    # 【通用】Curator 前共享的信息收集、审核与版本化交付
│   ├── information.py           #   八个专家维度、证据、资源、未决问题及内容版本
│   ├── collection.py            #   agent 自主收集：原生工具、研究委派、询问用户；独立审核与有界修正
│   ├── guidance.py              #   仅调研需要时，从可选产品案例提炼研究问题与分组线索
│   ├── curator.py               #   Raven exploration 适配；审核通过后向 Curator 交付
│   ├── scenario.py              #   已交付材料投影、首轮准备与离线结果复用
│   ├── inquiry.py               #   研究结果与原文引用核验
│   ├── researchers.py           #   研究 agent 或独立模型交换
│   └── prompts/                 #   收集、引导、研究与审核提示词
│
├── curator/                     # 【通用】读取、生成、校验、安装 Harness
│   ├── workflow.py              #   入口 improve / propose / attribute
│   ├── attribution/             #   机制归因：每条输入一条诊断，自己的对话、预算、检查点与记录
│   ├── composition/             #   两层组合：根候选 → 各子候选 → 整体校验与一次生效
│   ├── generation/              #   分阶段生成
│   │   ├── stages/              #     select → design → implement → repair（从归因结果开始）
│   │   ├── prompts/             #     各阶段提示词
│   │   └── context/             #     生成材料的组装与只读查询
│   ├── harness/                 #   产物模型、target 声明、四个公共策略协议与参考材料
│   └── raven_adapter/           #   与 Raven 运行时的连接层
│       ├── targets/             #     四个策略面在 Raven 上的扩展点声明
│       ├── bind.py, strategy.py #     把生成的策略与组件绑定到原生扩展点
│       ├── worker.py            #     被培养的 worker：装载、执行、安装
│       ├── deployment.py, hosting/  # 子 Harness 的部署与 ACP 托管
│       ├── inspection/          #     从实际运行时读出当前 Harness
│       ├── observe.py           #     机制每次决定写成观测记录
│       ├── exploration.py       #     生成期间 Curator 的只读探索空间
│       ├── planning/, action/, capability/, memory/  # 各策略面的运行时绑定
│       ├── baselines/           #     专家与朴素 Raven 基线的准备
│       └── reference/           #     给 Curator 读的宿主参考材料
│
├── assessor/                    # 【通用】持有标准、测量每一轮的角色
│   ├── role.py                  #   Assessor 协议
│   ├── human.py                 #   真人：既对话又评价
│   ├── dataset.py               #   数据集：既供样例又打分
│   ├── standard.py              #   评价侧 Standard（声明、派生、沉淀）与按它判定的自动 Assessor
│   └── prompts/                 #   自动 Assessor 的判定与派生提示词
│
├── analyst/                     # 【通用】把 Assessor 的话整理成 Curator 的行为要求
│   ├── run.py                   #   一次有界的模型交换，产出 Feedback
│   ├── feedback.py              #   Feedback：决定 + 行为要求
│   ├── materials.py             #   材料组装与 read_records 查询
│   ├── activity.py              #   机制活动：装上的机制本轮实际做了什么
│   ├── role.py                  #   Analyst：读一轮的信号与记录，写出要求
│   └── prompts/
│
├── iteration/                   # 【通用】多轮闭环
│   ├── run.py                   #   入职 curation → 每轮：试炼 → 评价 → 分析 → 修订（Session 的自动编排）
│   ├── session.py               #   可分步的 Session：每一步返回 Outcome，Studio 与 run() 共用
│   ├── protocols.py             #   Trial 协议，Signal 与交接项 Handover
│   ├── hearing.py               #   Curator 听到什么：按受众投影的信号、引用回合、历史与先验
│   ├── compartment.py           #   隔间与守卫：模型角色的每次请求按封印扫描，记入 boundaries.jsonl
│   ├── history.py, ledger.py    #   类型化历史（要求、诊断、改动、是否守住）与唯一的"守住"规则
│   ├── conversation.py          #   对话型 Trial
│   ├── exchange.py              #   各模型角色共用的有界结构化提交
│   ├── __main__.py              #   真人 CLI
│   └── records.py               #   按轮读取一次运行的记录
│
├── automation/                  # 【通用】自动培养的装配：不含任何场景的领域知识
│   ├── employee.py              #   数字员工：雇佣、每张题卡一个隔离副本、并行演练、Curator 不能读的评测侧、起点指纹
│   ├── traveller.py, prompts/   #   模拟客人：按题卡扮演，读到的只有渠道上发出的内容
│   ├── channel.py, files.py, render.py  # 客人实际看到的内容、交付物读取与页图
│   ├── isolation.py             #   越界检查：运行结束后扫描每次工具调用的路径
│   └── caching.py               #   网关模型的提示词缓存断点
│
└── simulation/                  # 【实例】旅行社场景（真实专家包也用这个入口）
    ├── __main__.py, suite.py    #   单次运行与批量挖掘入口
    ├── scenarios/travel_agency/ #   场景数据：岗位说明、资料、评审标准、客人画像
    ├── scenario.py, cards.py    #   交互方视角的场景，题卡数值的抽取规则（含行程字段）
    ├── agency.py, prompts/      #   模拟老板：演练后评审，决定交出哪些资料
    ├── reference.py             #   价目计算器与方案 PPT 的结构事实（老板评审时的尺子）
    ├── record.py                #   把一次运行导出成培养记录 transcript
    ├── value.py, attribution.py #   价值判定、要求与干预对应的规则
    └── cases/s0925c/            #   展示案例
```

## 通用机制与场景的关系

依赖方向固定：`simulation/` 引用通用层，通用层不引用 `simulation/`。

| 通用接口 | 旅行社场景的实现 |
|---|---|
| `iteration.run.run(worker, provider, trials, assessors, analyst=…, opening=…, boundaries=…, prior=…)` | `simulation/__main__.py` 从场景契约组装参数与隔间，默认最多 4 轮 |
| `Trial.run(worker) -> Sessions` | 通用的 `iteration.conversation.Conversation` 配模拟客人 `Traveller`；`Together` 让每张题卡在员工的隔离副本上并行演练，副本每轮从本体复制，所以每次演练的子代理 home 都是干净的 |
| `assessor.role.Assessor.evaluate(sessions) -> Signal` | `agency.Agency`：老板持有标准，说出评审意见并按披露日程交材料；可选并列的 `assessor.standard.StandardAssessor`；通用 Analyst 把原话整理成要求 |
| `curator.raven_adapter.worker.Worker` | `automation.employee.hire` 雇来的员工，带上 Curator 不能读的评测侧文件（`withheld`）；`automation.employee.Replica` 是每张题卡的隔离副本 |
| `curator.workflow.improve(worker, provider, feedback=…)` | 不改，直接调用 |
| 入职资料 `opening` | 老板的入职对话与交出的资料 |

## 运行

独立专家构建、离线准备与 Scenario 首轮共用同一收集流程。缺口由 LLM 根据内容判断，不再按材料类别是否存在触发。离线结果是信息快照与审核记录，不是新的场景目录；旧 `--out / --records / --without / --decisions / --from-records` 编排已移除。

```bash
# 旅行社模拟：一次运行（需要自备带 key 的配置文件）
uv run python -m experimental.simulation --config <config.json> --home <基线 home> \
  --state-dir <新的空目录> --scenario travel_agency --chain documents --rounds 4

# 离线准备：只使用指定披露计划的首轮材料，输出审核结果与记录
uv run python -m experimental.research --scenario <场景目录> --disclose staged \
  --output <新的准备目录> --config <config.json> --research exchange

# 或明确指定此次已交付材料；允许询问真人
uv run python -m experimental.research --scenario <场景目录> --release <材料名> \
  --output <新的准备目录> --config <config.json> --interactive

# Scenario 首轮可复用离线审核结果；任务、材料、环境不匹配时拒绝，需要重新评估
uv run python -m experimental.simulation --scenario <场景目录> --config <config.json> \
  --state-dir <新的运行目录> --information <准备目录/result.json>

# 留出集：这些题卡每轮演练，只由按声明检查项评分的自动 Assessor 评，Analyst 与 Curator 看不到
uv run python -m experimental.simulation --config <config.json> --state-dir <新的空目录> \
  --scenario travel_agency --holdout <题卡名>

# 真人 CLI：真人既是对话方也是评价者
uv run python -m experimental.iteration --help

# 从业务任务和交互材料开始；没有产品案例也能进行信息收集
uv run python -m experimental.simulation.experts --config <config.json> \
  --task-file <业务任务.md> --material <交互材料目录> --output <新的运行目录> \
  --research exchange --interactive

# 可选：产品案例仅为调研提供引导，不作为本次交互输入
uv run python -m experimental.simulation.experts --config <config.json> \
  --task-file <业务任务.md> --research-reference <产品案例目录> --output <新的运行目录> \
  --research exchange --research-tasks 3

# 产品包也可以明确作为交互输入：先评估已有信息与缺口，不强制抽象或重新调研
uv run python -m experimental.simulation.experts --config <config.json> \
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
`--interactive` 允许在终端回答信息问题；
未启用或未回答时保留问题；仅有用户渠道的阻断问题时为 `needs_input`。仍需公共调研、本地检查，或审核修正预算耗尽时为 `incomplete`，不会继续改造。
`--research exchange` 使用配置中的网页工具和独立研究对话，也可选 `claude`、`codex` 或 `none`。
主流程模型由配置文件决定，调研模型单独指定。例如，配置主流程为 DeepSeek 后，可用
`--research claude --research-model claude-sonnet-5-5 --research-effort xhigh`
运行 Claude Code 调研；`--research-effort` 不会改变主流程的推理设置。离线准备与专家构建入口
均支持这些选项，具体模型和 effort 是否可用取决于本机 CLI 与账号。
Claude Code 的预算是客户端控制值，最后一次调用可能使报告金额超过上限；运行记录保留
客户端报告的模型、耗时、金额与终止原因。这些金额不是账号账单，引用核验通过也不等于结论充分。
默认不设置美元上限；确需客户端金额控制时才传 `--research-budget`。
`--research-timeout` 默认 3600 秒，是单次研究与审核的上限；`--collection-timeout` 默认 3600 秒，
限制一次信息收集的整个闭环，包括引导、调研、审核和修订，先到的时限生效。
每次委派只获得整轮剩余时间减去 `--submission-reserve`（默认 600 秒）后的部分，这段保留时间留给
提交描述和最终审核；剩余可研究时间不足 300 秒时宿主拒绝再开调研，收集器只能带着缺口提交。
每组调研的时间窗里再留 150 秒给引文核验和审核，研究代理只能用其余部分。
研究组上限由 `--research-tasks` 指定，每组最多 `--research-questions`（默认 2）个问题，
`--research-revisions` 默认每组最多修订一次。收集器被要求先一次读完列出的材料（`read_sources`），
再把只有用户能答的问题提出来，最后才委派公开证据的调研。

收集 agent 负责判断缺口、分组、任务书、修订和结束。每次委派只执行一次调研、来源核验和受限模型审核；
被退回时，返回审核问题、尝试编号和剩余额度，由收集 agent 决定是否用 `previous_attempt` 修订，
或换渠道、保留缺口结束。尝试编号只用于程序衔接，不写进语义任务书。
不再为任务书设置独立审稿循环，可选案例引导也只做有界提炼。
审核无查询工具，不独立规划或调研。旧审核意见随修订传递，最终汇总仍要检查未解决的意见。

未通过审核的正文保留在尝试记录中，不进入知识证据。网页截断、JSON 转义和 PDF 断词的核验处理保持；
失败原因与原始记录保持可追溯。超时或调用耗尽会保存 `result.json`、`snapshot.json`、`conversation.json`
和 `research-attempts.json`，返回 `incomplete` 及 `stop_reason`，不会继续构建 Harness。
下一次可以用已有快照和聚焦字段重新评估；不自动恢复全部失败任务或重跑整套调研。

离线入口支持 `--collector claude` 或 `--collector codex`，配合 `--model <模型> --collection-effort <强度>`，
通过 Claude Code 或 Codex 的受限结构化调用驱动同一个收集流程。CLI 只选择宿主提供的工具，由宿主执行；
审核同样只提交判断。两者都用本机 CLI 的登录，不需要 Raven 配置里的 key；Codex 会在只读沙箱里运行、不加载用户配置，
收集调用不开网页搜索。默认 `--collector provider` 仍使用 Raven 配置中的模型。

一次真实模型检查只验证有界闭环：收集和审核实时运行，调研使用已有记录回放，不新增网页搜索。
整次上限 300 秒、一个研究组、无自动修订，不重复启动；输入是旧销售教练试验中已保存的
`candidate-2.json` 与 `sources-2.json`，只取其中一条职业标准发现。
默认 `RESEARCH_COLLECTION_MODE=replay` 使用固定交付；设为 `source_review` 时，研究模型只根据该发现
对应的已保存来源页面实时生成交付，并允许收集 agent 自行决定一次修订。两种模式均使用生产收集流程，
整轮上限仍为 300 秒，不新增网页搜索；是否实际修订取决于收集 agent 的判断，测试脚本不指定分支。

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

```bash
cd experimental/webui && npm ci && npm run build && cd -
uv run python -m experimental.webui.serve --runs <放运行目录的目录> [--live-config <config.json>]
# 浏览器打开 http://127.0.0.1:8765 ：根路径是 Studio，/viewer 是运行查看页；默认只绑定本机
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
