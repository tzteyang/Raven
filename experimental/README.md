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
├── research/                    # 【通用】调研阶段：培养开始前，把交出的资料读进契约类别，写出新场景目录
│   ├── slots.py                 #   每个类别一个槽位：给了什么、缺口怎么补
│   ├── induction.py             #   从范例与反例归纳已有规范没说的规则
│   ├── confirm.py               #   交互方逐条确认、修正、驳回（决定文件，或模拟交互方）
│   ├── package.py               #   复制场景（去掉没交出的资料），写入规则包与 provenance.json
│   └── prompts/                 #   归纳与确认提示词
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

```bash
# 旅行社模拟：一次运行（需要自备带 key 的配置文件）
uv run python -m experimental.simulation --config <config.json> --home <基线 home> \
  --state-dir <新的空目录> --scenario travel_agency --chain documents --rounds 4

# 调研阶段：培养前从范例与反例归纳规则，交互方确认后写出新场景目录（再用 --scenario 指向它）
uv run python -m experimental.research --scenario <场景目录> --out <新目录> --records <新目录> \
  --config <config.json> --without <没交出的资料> --party-knows <模拟交互方按哪些资料确认>

# 同上，另外用网页研究空的事实槽：研究者可选 claude、codex 或 exchange（本阶段模型加配置里的 Serper 与 Jina）
uv run python -m experimental.research --scenario <场景目录> --out <新目录> --records <新目录> \
  --config <config.json> --research claude --research-model sonnet --research-budget 2 \
  --party-knows <模拟交互方按哪些资料确认>

# 交互方写好的决定文件：只结算往期运行记下的条目
uv run python -m experimental.research --scenario <场景目录> --out <新目录> --records <新目录> \
  --from-records <往期 --records> --decisions <决定文件>

# 留出集：这些题卡每轮演练，只由按声明检查项评分的自动 Assessor 评，Analyst 与 Curator 看不到
uv run python -m experimental.simulation --config <config.json> --state-dir <新的空目录> \
  --scenario travel_agency --holdout <题卡名>

# 真人 CLI：真人既是对话方也是评价者
uv run python -m experimental.iteration --help

# 完整专家包：正常根／子部署；可重复 --request-file 提交构建后的真实任务
uv run python -m experimental.simulation.experts --config <config.json> \
  --expert <专家包目录> --output <新的运行目录> \
  --request-file <客户需求.md>

# 测试
uv run pytest tests/test_harness_curator_*.py tests/test_analyst_*.py tests/test_iteration_*.py tests/test_simulation_*.py \
  tests/test_scenario_*.py tests/test_assessor_*.py tests/test_research_*.py
```

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
