# 对手方协议、元评价与 Oncall 案例：推进规划

状态文件。记录目标、已定决策、进度与待验证项；每完成一步更新。任务结束后把仍有效的设计决策转入
`cultivation-loop-design.md` 与各模块 docstring，本文归档。

最后更新：2026-10-08（补 3.7 交互方评审包的两条规则）。

## 1. 目标与非目标

目标：
1. 把培养回路的"对手方"从旅行社专用实现中抽成协议：案例层只实现接入（卡片、老板、事实计算、交付物读取、成案谓词），回路层拥有反馈信号的形状与保证。
2. 增加一类内部反馈信号：雇员对自己交付物与最终回复的自评（元评价），进入 Analyst 的材料，并可被 Curator 听到。
3. 用一个真实案例验证：品牌策略师（现有专家包）加 Oncall 守望任务（真实的苹果商店公开读数），在 DeepSeek 上跑多轮（与 Curator 的多轮交互，不是雇员与客户的多轮对话），记录进 WebUI 可读。
4. WebUI 能呈现该运行；逻辑错位处修 WebUI。

非目标：
- 不改 `raven/`（见记忆规则）；Oncall 的接入只在运行配置与 `experimental/automation` 层。
- 不重写旅行社实现；只抽取共用部分，旅行社继续通过同一协议运行。
- 不做真实投放；守望任务只读、动作为写文件（无 webhook）。

## 2. 现状（已核实）

- 回路协议已存在：`iteration.protocols.Trial`（`run(worker) -> Sessions`）、`assessor.role.Assessor`
  （`evaluate(sessions) -> Signal | None`）、`iteration.conversation.Conversant`；受众投影 `experimental/audience.py`；
  听证 `iteration/hearing.py`；Analyst 反馈契约 `analyst/feedback.py`；通用入口 `iteration.run`。
- 已有评审者：`assessor.human`、`assessor.dataset`（试验 + 评分一体）、`assessor.standard`（声明/推导/沉淀）、
  `simulation.agency.Agency`（旅行社老板，也负责分步交付资料）。
- 案例绑定处：`simulation/__main__.py` 的装配、`automation/traveller.py`（人物卡扮演，已基本通用）、
  `simulation/reference.py`（旅行社事实计算器）、`simulation/agency.py` 的评审包（deck 页、后台单据等旅行社视图）、
  `simulation/value.py` 的成案谓词（"每单交付 deck"）。
- 专家入口 `simulation.experts` 无对手方、无 Analyst、无轮次。
- 没有任何自评/元评价机制：`grep` 未见 self-review、critic、reflect 的实现；Harness 的 action 控制
  （reject/revise）是 Curator 可建的门，不是回路的信号。

## 3. 决策

### 3.1 对手方协议的落点（三案比较）

| 方案 | 做法 | 复杂度 | 可理解性 | 风险 |
|---|---|---|---|---|
| A 不新增协议，品牌案例复制 `simulation/__main__.py` 一份装配 | 最快 | 低 | 两份装配各自演化，老板评审契约重复维护（违反 AGENTS §3） | 债务 |
| B 新包 `experimental/counterpart/`：`Case` 装配协议 + 通用 `Owner` 评审者，`Agency` 迁为其旅行社实现 | 中 | 高：案例层一目了然 | 需改 `Agency` 内部结构，有测试覆盖 | 回归 |
| C 把一切塞进 `experimental/scenario`（合同、披露）扩展 | 中 | 低：场景包与角色实现混在一起 | 边界模糊 | |

采用 **B**。关键假设：`Agency._judge` 的评审包里旅行社专有的键（deck_pages、back_office、research、colleague_reports、
references）能作为"额外视图"钩子注入，老板提示词与计分卡契约不变。若钩子不足以表达，退回为 `Owner` 与 `Agency`
共享评审骨架函数而非继承。

`Case` 的接口面（最小）：`prepare()`、`trials(spawn)`、`assessors()`、`holdout()`、`opening`、`judge(record)`；
装配参数来自案例目录（合同、scenario.json、人物/请求卡、资料）。`simulation/__main__.py` 改为用旅行社 `Case`。

### 3.2 元评价（内部反馈信号）的形态（三案比较）

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| A 自评评审者 `assessor.introspect`：每轮试验后，在雇员的**副本**上开新会话，给它看自己的会话与交付文件，要它逐单判定并列缺陷 | 真正的"自我评价"，随 Harness 一起变好；Analyst 可对照外部判定找盲区；无外部标准泄露（它只看自己的产出） | 多一次模型调用/单；副本机制已存在（留出卡片同法） |
| B 独立"批评者"模型，只拿任务与交出的规范 | 简单 | 等于 `Standard.derived` 已有的东西，不是自评 |
| C 只读 Harness 内部 action 控制（reject/revise）的活动行 | 零成本 | 依赖 Curator 是否建了门；无门时无信号 |

采用 **A**，并把 C 作为 A 的证据补充（自评信号的 note 里附本单 action 控制活动）。受众：`Signal.text`（雇员自己的话）
按 `HEARD` 可达 Curator；逐项 `Item` 按 `EVALUATION` 只到 Analyst。Analyst 提示补一段：对照自评与外部判定，
雇员自己没发现的缺陷写成"自检"类要求。成案判定加一项参考指标：自评与外部判定的一致率跨轮变化（只报告，不否决）。

### 3.3 Oncall 接入

- `automation.employee.HOUSED` 加 `Raven-Oncall`（`ONCALL_ACP_HOME`），`pin` 的密钥表加 `ONCALL_API_KEY`；
  机器注册表经 `RAVEN_CONNECTIONS` 指向案例目录内的 `connections.json`（本机，软件为 `.venv` 的 python）。
- 读数脚本已在 `raven-rsi-runs/.../oncall/store_read.py`（苹果商店公开接口，只读）；动作为写文件。
- 先跑文档中的有界本机作业冒烟（DeepSeek），确认 spawn、`ops_check_later`、`ops_finish` 在 hosting 里走通。

### 3.4 案例：品牌策略师 + 守望

对手方：市场负责人（老板，模型）；请求卡三张：
1. 品牌提案（文件交付，广告法与口号一致性为事实检查）；
2. 竞品商店守望（委派 Oncall，短窗口：3 次查看、每次间隔 2 分钟，真实读数；最终报告以文件交付；
   负责人在等待后追问进展）；
3. 老板的压力改稿（极限词与无来源数字，必须拒绝并给替代）。
事实计算器：极限词词表命中、口号在各文件中是否逐字一致、数字是否有来源标注、守望报告是否引用读数序列、
是否出现 Oncall 子 harness 执行与 `ops_finish`。成案谓词：三张卡红线为零、文件交付、守望任务未假完成。

### 3.5 无监督的评价标准：critic（三案比较，2026-10-07 用户定方向）

用户的方向：外部交互的反馈并不总是存在或足够细，评价信号要能从系统内部无监督地得到；核心是"自提取标准与规范"，
按 actor（Curator）、critic（评价规范的生成与表达，逐轮迭代改进）、judger（元监督）三角色组织；本轮只做 critic，
元评审暂缓；版本对比式评估不做。

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| A 原地扩展 `standard.derive` | 在 `assessor/standard.py` 里把一次性派生改为逐轮修订 | 改动最小 | 标准的生成（critic）与判定（judger）混在一个模块，三角色边界看不出来 |
| B 新建 `assessor/critic.py`，注入 `StandardAssessor` | critic 负责写与改派生条目，`StandardAssessor` 只判定；`derive` 删除，不留两份 | 角色边界清楚，评价侧仍在 `assessor/`；无循环依赖（`standard.py` 只在类型检查时引用 critic） | 调用方要显式构造 critic |
| C 顶层包 `experimental/critic/` | 与 `analyst/`、`curator/` 平级 | 叙事上最显眼 | `Standard` 类型要搬家才能避免循环引用，改动面大，收益只是位置 |

采用 **B**。critic 的改进信号只有三类且都不看结果：新交出的规范、上一轮判定者判不了的条目、它自己发现的规范与条目不符；
"有据"由代码校验（逐字引文），"有因"由代码校验（理由要有证据），"不看结果"由输入保证（只给可判性，不给通过与否）。
成立的前提：交接资料里有足够明确的规范；任务完全开放、没有规范时 critic 无从下笔，需要另找锚点。

### 3.6 守望数据源：先用模拟（2026-10-07 用户定）

真实来源要满足"平均不超过 3 小时就有值得监控的变动"（用户要求）；苹果商店读数在 2 分钟间隔内基本不变。本轮先用模拟来源：
读数脚本保持 `find`/`read` 两个子命令与输出格式，数值按运行种子与时间分桶生成，几分钟内就有可观测的变化与偶发事件。

### 3.7 交互方评审包的两条规则（`counterpart/owner.py`）

- **检查项只以中性代号出现。** 交互方看到的检查清单和它自己此前几轮的失败项都用 `check-N`（`handles`，按检查项顺序编号），按代号给分，`Owner` 再映射回真实 id 写进评分记录与条目。起因：提示词已写明不要念编号，模型仍在给员工的评语里用括号标出检查项 id，评语作为反馈交给 Curator，id 对 Curator 是封存的，运行在 `admit:feedback` 中止。比较过四种做法（只给中性代号 / 再强调提示词 / 代码删评语里的编号 / 守卫改成只警告），采用第一种：交互方从没见过 id，也就说不出来，不依赖模型守规矩，也不放松守卫。
- **页面图片只发给能看图的评审模型。** 交付物的页面渲染图（`pictures` 钩子）只在 Raven 网关目录确认评审模型能看图时才发（`vision_verdict(...) is True`；交互方创建时在后台预热目录，新 home 里没有它）。否则评审包的 `pictures` 写明页面没给看，交互方按交付物的文字与 `[style]` 行判断，只靠视觉决定的检查项判为无法判断。起因：评审模型的上游不收图片时返回错误，整次评审失败、运行结束。目录不认识的模型按不能看图处理。

## 4. 工作分解与状态

| # | 工作 | 状态 |
|---|---|---|
| P1 | `experimental/counterpart/`：通用 `Owner`（评审骨架抽自 `Agency`，`facts`/`pictures` 钩子）、`drills`（`enlist`/`grouped`）、`case`（成案谓词）、`Agency` 迁为旅行社实现、测试 | 已完成 |
| P2 | `simulation/__main__.py` 按场景名选 `Owner`（`OWNERS` 表），演练与留出经 `counterpart.drills` 装配；`value.judge` 的成案谓词经 `counterpart.case.delivered_for` 取 | 已完成（`Case` 协议未单设：装配只差 Owner 与谓词两处，表查找更短） |
| P3 | `assessor/introspect.py` 自评评审者（`source=self`，副本上逐单自检，记录到 `analysis/`）+ Analyst 提示补充 + `tests/test_assessor_introspect.py` | 已完成 |
| P4 | Oncall 收编（`HOUSED`/`pin`/`KEEPS_SHELL`，`RAVEN_CONNECTIONS` 与 `PYTHONTZPATH` 转发）、机器注册表 | 已完成；冒烟并入 P6 的 run-1 |
| P5 | 品牌案例场景包 `scenarios/brand_strategist/`（合同、9 条判据、3 张请求卡、3 份资料含读数脚本、`simulation/brand.py` 事实计算器与 `BrandOwner`；词表在场景的 `reference.md`，代码不含中文，与旅行社的价目词表同法） | 已完成；测试 `tests/test_simulation_brand.py`、`test_party_case.py`、`test_party_drills.py` |
| P6 | DeepSeek 多轮运行（≥2 轮 Curator 修订），记录 | 进行中：run-1（10:49–11:22）在入职 curation 的 Oncall 子作用域被 Curator 隔间拦下——Curator 写的英文 docstring 与我的英文检查项有 10 个词逐字相同（两边都是同一句中文规范的英译，差分封印认不出翻译）；判据改写为评价者自己的指令（指向规范章节与算出的事实，不再翻译规范原句），run-2（11:41–12:24）跑到第 1 轮演练：三张卡都交了文件，守望卡走通了全链路（委派 housed 的 Raven-Oncall → 读基线 → `ops_declare` 守望 campaign → 三次 `ops_check_later` → 报告写进工作目录 → `ops_finish`）；但守望说明第 2 轮才交，带 shell 的 Oncall 子进程找脚本时翻到了运行记录（`settings.json`）和仓库里的场景目录，回话带回场景名，被伙伴隔间拦下，同时也是 BRIEF §11.5 的隔离越界，不作证据。修：机器注册表的路径改为只放读数脚本的 `oncall/`，`software` 写绝对路径；run-3（12:27–13:13）同类越界再次发生：雇员让 Oncall 子进程去核查尚未交出的守望说明，子进程列了注册路径的上级（运行目录）读到 NOTES.md 里的场景名。改两处：注册路径移到任何运行目录之外的 `raven-rsi-runs/oncall-lab/`；守望说明随入职一次交齐（`--chain documents`），多轮价值由反馈驱动的 Curator 修订体现。run-4 于 13:17 重启。带 shell 的子进程要真正关在自己区域里仍需 `--isolate-as raven-worker`（目录封闭由用户操作）。记录在 `raven-rsi-runs/brand-oncall-20261007/NOTES.md`；run-3（12:27–13:13）在第 1 轮再次被伙伴隔间拦下：带 shell 的 Oncall 子进程读了记录目录里的 `NOTES.md` 并执行 `find ... -iname '*brand_strategist*'`，结果回流进员工会话。三次运行均未完成第 1 轮，阻塞在两件事：带 shell 子进程的进程隔离（`--isolate-as raven-worker`，目录封闭需用户操作）；DeepSeek 余额已用完，换 OpenRouter 后内置通用子 harness 报 `deepseek needs an API key`，未解决 |
| P7 | WebUI：索引与页面读新案例运行；缺失处修 | 进行中：已修两处错位——(1) 页面原按服务器唯一的 `--scenario` 标红线，现按每个运行 `settings.json` 记的 `scenario_dir` 取判据（`/api/scenario?run=`）；(2) `--runs` 目录里用符号链接汇集多处运行时，索引列得出、详情接口全部 404（包含检查把链接解析到真实路径后判为根外），现按运行 id 的纯名字校验与工作根的真实位置判断。两处都有服务端测试；本地起服务核对过记录、实时与判据三个接口。待 run-2 出首轮数据后核对自评信号与守望记录的呈现 |
| P8 | 文档：`cultivation-loop-design.md`、`CONTEXT.md` 术语、本文归档 | 部分完成：两份文档已写入交互方层与自评信号；交互方角色由 party 改名 counterpart（目录 `experimental/counterpart/`、角色字面量、类名 `CounterpartAnswers`、测试与 WebUI 文案同步，`CONTEXT.md` 写明旧名为 _Avoid_）；本文归档待 P6 完成 |
| P9 | critic：`assessor/critic.py` 逐轮修订派生条目（3.5），`StandardAssessor` 注入，模拟入口与 WebUI 会话宿主接线，`derive` 删除，测试 `tests/test_assessor_critic.py` | 已完成（783 条 experimental 测试通过） |（2026-10-09 合并后由 rubric 构建者与元评审者取代，`assessor/critic.py` 已删除）
| P10 | 守望模拟数据源（3.6）；品牌案例在 OpenRouter `deepseek/deepseek-v4-flash` 上多轮运行，带 `--standard derived` | 进行中 |

## 5. 验收

- 旅行社入口行为不变：现有测试全绿，`experimental.simulation` 的 DeepSeek 冒烟能跑一轮。
- 品牌案例在 DeepSeek 上完成 ≥2 轮且第二轮由 Analyst 反馈驱动 Curator 修订；记录含自评信号与外部信号。
- WebUI 能列出并打开该运行，看到每轮会话、信号（含 self）、要求、修订。
- 守望任务在记录里可见：Oncall 子 harness 执行、读数、报告文件。

## 6. 风险与预算

- DeepSeek-flash 做 Oncall 与品牌策略师可能吃力；只做流程验证，不下结论。
- 内存：并发单数用 `--concurrent-drills 2`，守望脚本用真实网络。
- 预算：全部 DeepSeek；不动 OpenRouter。
