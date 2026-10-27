# Raven 数字员工操作手册（写给执行操作的 AI）

这份手册让一个 AI 在一台新机器上，从源码把整套系统跑起来：用 Studio 一个一个培养数字员工，用流水线按案例批量生产专家，
再把专家装进宿主 Raven 里上班。按章节顺序执行，每一步都给了检查方法；检查不通过就停下，先看第 8 节。

约定：

- `<ws>` 是工作区目录，例如 `~/raven-work`。仓库检出在 `<ws>/Raven`，运行数据在 `<ws>/runs`，key 和口令在 `<ws>/secrets`。
- 除非特别说明，命令都在 `<ws>/Raven` 里执行。
- 要长时间运行的进程（Studio 服务、流水线）一律放进 tmux，用完关掉对应的 tmux 会话。
- 不要打印、复制或提交任何 key。key 文件权限设成 600。

## 1. 这套系统由什么组成

| 部分 | 位置 | 作用 |
|---|---|---|
| Studio | `experimental/webui` | 浏览器里的培养台：演练、批注、分析、改造、考试，一轮一轮把员工培养出来 |
| 自进化循环 | `experimental/`（iteration、curator、analyst、assessor 等） | Studio 背后的各个角色 |
| 批量流水线 | `experts/common/` | 不用人点页面，按案例自动跑完培养、导出和验收 |
| 案例数据 | `experts/cases/<案例>/` | 每个专家的工作规则、题目、脚本、场景包和评审定义 |
| 产出的专家 | `experts/agents/expert-<案例>/` | 22 个验收过的专家，每个是一个 Raven ACP agent |

参与培养的模型角色：

- **员工**：被培养的 Raven 本身，用 Raven 配置里的 `agents.defaults.model`；
- **改造师**（curator）：改员工的 Harness；
- **归因**（attribution）：给改造找依据；
- **分析师**（analyst）：读演练和批注，提改造要求；
- **评审**（assessor）：按验收项给员工的答卷打分。流水线里的评审插件 `experts/common/examiner.py`、验收判卷和评审探测都用这个角色的模型；
- 其余角色（collector、counterpart、conversant、rubric_builder、meta_reviewer、sub-harness）不单独配置时，用员工的模型。

## 2. 准备机器

需要（我们在 Linux 上运行）：Python 3.12 或更高，[uv](https://docs.astral.sh/uv/)，git，Node.js 和 npm（我们用的是 Node v24.16、npm 11.13），tmux。

### 2.1 目录布局（必须照做）

员工的工作目录不能在仓库里面，也不能是仓库的上级目录（`experimental/automation/employee.py` 的 `workplace` 会直接报错
`the employee's workdir may not be the repository, inside it or above it`），因为仓库里放着场景、演练卡和评审用的考题。
所以运行数据和 key 都放在仓库外面、和检出并排：

```
<ws>/
  Raven/      仓库检出
  runs/       Studio 会话、流水线状态、验收宿主（自动创建）
  secrets/    raven-experts.json、experts.token
  studio/     手动用 Studio 时的 live.json（第 4 节）
```

流水线的代码按这个布局找文件：`experts/common/*.py` 里的 `REPOSITORY` 是检出，`ROOT`（有的脚本里叫 `GTM`）是检出的上一级目录。
案例 `live.json` 里的 `../../../../secrets/...`、`../../../../runs/...` 也指向这里。

### 2.2 安装

```bash
mkdir -p ~/raven-work && cd ~/raven-work
git clone https://github.com/tzteyang/Raven.git
cd Raven
uv sync --all-extras
uv run playwright install chromium
cd experimental/webui && npm ci && npm run build && cd ../..
mkdir -p ../runs ../secrets ../studio && chmod 700 ../secrets
```

- 必须用 `uv sync --all-extras`。只跑 `uv sync` 会缺 `python-pptx` 等依赖，Studio 和流水线一导入 `experimental` 就报
  `ModuleNotFoundError: No module named 'pptx'`。
- Chromium 只有 landing-page、booking-page 两个案例的测量要用：它们会真开浏览器量交付的网页。
- `npm run build` 生成 `experimental/webui/dist/`。不构建的话，Studio 服务只有接口没有页面，启动时会打印
  `No built page at ...; run npm run build in experimental/webui first`。

检查：

```bash
uv run python -c "import raven, experimental, pptx; print('ok')"     # 打印 ok
ls experimental/webui/dist/studio.html                              # 文件存在
uv run python -m unittest discover -s experts/common -p 'test_*.py' # 最后一行是 OK（85 个测试，不调模型）
```

## 3. Key 和模型配置

### 3.1 需要哪些 key

| 用途 | 什么时候需要 | 放在哪 |
|---|---|---|
| 模型服务 key（OpenRouter） | 一直需要。一个 OpenRouter key 就能调到下面三个模型 | `<ws>/secrets/raven-experts.json` 的 `providers.openrouter.apiKey`；用专家时还要放进宿主的 `~/.raven/config.json`（第 6 节） |
| Studio 访问口令 | 流水线必需；手动 Studio 开放给别的机器访问时需要 | `<ws>/secrets/experts.token`，流水线固定读这个文件 |
| 网页搜索 key | 手动 Studio 里员工要委托调研同事时（例如自带的海岚旅行场景，`delegation` 默认开启），或开了 `"information": "research"` 时需要；流水线用不到 | Studio 页面「服务设置…」里的搜索服务（第 4.3 节第 2 步），或 Raven 配置的 `tools.web`（第 4.4 节） |

除此之外不需要别的 key。

### 3.2 每个角色用什么模型、什么 effort

下面就是这 22 个专家培养和验收时的设置，只是写成了 OpenRouter 的模型名。

| 角色 | 模型（OpenRouter 名） | effort | 在哪配置 |
|---|---|---|---|
| 员工 | `z-ai/glm-5.3-flash` | medium | `<ws>/secrets/raven-experts.json` 的 `agents.defaults.model` / `reasoningEffort`；导出的专家把它带在自己的 `config.json` 里 |
| 改造师 curator | `openai/gpt-6-astra` | high | 每个案例 `live.json` 的 `models` / `efforts` |
| 归因 attribution | `openai/gpt-6-astra` | high | 同上 |
| 分析师 analyst | `openai/gpt-6-astra` | high | 同上 |
| 评审 assessor | `moonshotai/kimi-k3` | high | 同上；流水线评审插件、验收判卷、评审探测也读这一项 |

员工的其他设置：`temperature` 0.1、`maxTokens` 8192、`contextWindowTokens` 262144、`llmCallTimeout` 1800、`maxToolIterations` 40、
`llmFirstByteTimeout` 600、`streamIdleTimeout` 600、`enablePersonalization` false。权限是 `mode: full`、`trustHarnessTools: true`、
`tools.restrictToWorkspace: false`，也就是员工能执行命令、读写工作目录以外的文件。

每个案例 `live.json` 里还有改造预算：`curator_calls` 160、`curator_queries` 240、`attribution_calls` 16、`attribution_queries` 48，
以及 `rounds` 12（轮数上限）、`turns` 8、`timeout` 1800、`delegation` false（员工不分派子员工，这样才能导出成单个 agent）、
`standard` `["sedimented"]`、`assessor` `../../common/examiner.py:make`。22 个案例的这些值完全相同。

### 3.3 写 `<ws>/secrets/raven-experts.json`

这是 Studio 和流水线共用的 Raven 配置，案例 `live.json` 的 `config` 指向它，验收宿主的 `config.json` 也软链接到它。
用编辑器写入下面的内容，把 `<OpenRouter key>` 换成真实的 key，然后 `chmod 600 ../secrets/raven-experts.json`：

```json
{
  "agents": {
    "defaults": {
      "provider": "openrouter",
      "model": "z-ai/glm-5.3-flash",
      "reasoningEffort": "medium",
      "temperature": 0.1,
      "maxTokens": 8192,
      "contextWindowTokens": 262144,
      "llmCallTimeout": 1800,
      "maxToolIterations": 40,
      "enablePersonalization": false,
      "llmFirstByteTimeout": 600,
      "streamIdleTimeout": 600
    }
  },
  "providers": {
    "openrouter": {
      "apiKey": "<OpenRouter key>",
      "models": ["z-ai/glm-5.3-flash", "openai/gpt-6-astra", "moonshotai/kimi-k3"]
    }
  },
  "tools": {"restrictToWorkspace": false},
  "permissions": {"judgeTimeoutSeconds": 60, "trustHarnessTools": true, "mode": "full"}
}
```

`models` 列表要写全三个模型。只配 OpenRouter 一家时，写全以后三个模型都会确定交给 OpenRouter。

检查（不打印 key）：

```bash
uv run python - <<'EOF'
from pathlib import Path
from raven.config.loader import load_config
c = load_config(Path("../secrets/raven-experts.json"))
c.agents.defaults.provider = "auto"
for m in ("z-ai/glm-5.3-flash", "openai/gpt-6-astra", "moonshotai/kimi-k3"):
    print(m, "->", c.get_provider_name(m))      # 三行都应该是 -> openrouter
EOF
```

### 3.4 写 `<ws>/secrets/experts.token`

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(24))" > ../secrets/experts.token
chmod 600 ../secrets/experts.token
```

口令必须是 16–128 个字母、数字、`-` 或 `_`，上面这条命令生成的是 32 个字符。流水线启动 Studio 时用 `--token-file` 读它，
驱动脚本 `experts/common/run.py` 调 Studio 接口时也带着它。

### 3.5 模型服务是怎么选的（换服务商之前必读）

规则在 `raven/config/schema.py` 的 `_match_provider` 和 `experimental/model_roles.py`：

1. `agents.defaults.provider` 写了具体的服务商（不是 `auto`）时，员工的调用都走它。
2. 只要有角色用的模型和员工不同，这些角色就按模型名各自选服务商（`auto`）。评审插件也固定用 `auto`。
3. `auto` 的顺序：先看哪家 `providers.<名字>.models` 列了这个模型名；再看名字的前缀或关键词指向哪家（例如 `openai/...`
   指 openai），而且那家要配了 key；都不行时，交给配了 key 的网关类服务，`custom` 排在 `openrouter` 前面。

所以：

- 不同服务商的模型名写法不同。OpenRouter 要带前缀（`openai/gpt-6-astra`）；我们的内部网关只认不带前缀的名字，
  带前缀的会返回 HTTP 422。
- 换成别的服务商时，要同时改三处：`raven-experts.json` 的员工模型和 `providers`；22 个案例 `live.json` 的 `models` / `efforts`；
  要装进宿主的专家的 `config.json`。并且在 `providers.<名字>.models` 里列出所有模型名。
- 一次改完 22 个案例的角色模型：

```bash
uv run python - <<'EOF'
import json
from pathlib import Path
models = {"curator": "openai/gpt-6-astra", "attribution": "openai/gpt-6-astra", "analyst": "openai/gpt-6-astra", "assessor": "moonshotai/kimi-k3"}
for path in sorted(Path("experts/cases").glob("*/live.json")):
    live = json.loads(path.read_text())
    live["models"] = models
    path.write_text(json.dumps(live, ensure_ascii=False, indent=2) + "\n")
    print("updated", path)
EOF
```

### 3.6 我们实际是怎么跑的（对照用）

模型和上表一样，走的路线不同：

- 改造师、归因、分析师和评审都走我们的内部网关（服务商 `custom`，模型名 `gpt-6-astra`、`kimi-k3`），前面加了一个限 10 路并发的排队转发；
- 员工走 OpenRouter 的 `z-ai/glm-5.3-flash`。2026-10-11 21:59 UTC 共享 key 额度用完后，改走内部网关上的同名模型 `glm-5.3-flash`。
  验收答卷里 93% 走的是 OpenRouter；
- 这些转发脚本只服务于我们的机器，没有放进仓库。用 OpenRouter 时不需要它们。

## 4. 用 Studio 培养一个员工（手动）

### 4.1 写 `<ws>/studio/live.json`

```json
{
  "config": "../secrets/raven-experts.json",
  "root": "../runs/studio",
  "title": "旅行社线上顾问",
  "models": {"curator": "openai/gpt-6-astra", "attribution": "openai/gpt-6-astra", "analyst": "openai/gpt-6-astra", "assessor": "moonshotai/kimi-k3"},
  "efforts": {"curator": "high", "attribution": "high", "analyst": "high", "assessor": "high"},
  "rounds": 4,
  "timeout": 1800
}
```

- 相对路径都相对这个文件所在的目录。`root` 必须在仓库外面（见 2.1）。
- 不写 `scenario` 时，用仓库自带的示例场景“海岚旅行”（`experimental/simulation/scenarios/travel_agency`，杭州一家精品短途游旅行社的线上数字顾问）。
  仓库里还带了 `brand_strategist` 场景。培养自己的员工，就在页面上新建场景（4.3 第 1 步）。
- 只认这些键：`config`、`root`、`scenario`、`rounds`（默认 4）、`turns`（8）、`timeout`（600）、`models`、`efforts`、`curator_calls`（48）、
  `curator_queries`（72）、`attribution_calls`（8）、`attribution_queries`（24）、`standard`、`evaluation_memory`、`experience_memory`、
  `experience_scope`、`experience_migrate`、`delegation`（true）、`scripts`、`assessor`、`versions`、`information`、`title`、
  `endpoints`（`experimental/webui/live.py` 的 `LiveConfig`），写别的键会直接报错。
- `endpoints` 是页面上登记的模型服务存放的文件，不写时是 `config` 同目录下的 `studio-endpoints.json`（见 4.3 第 2 步）。

### 4.2 启动

```bash
mkdir -p ../runs/view
tmux new-session -d -s studio "cd $PWD && uv run python -m experimental.webui.serve --runs ../runs/view --live-config ../studio/live.json"
```

然后在浏览器打开 `http://127.0.0.1:8765/studio`。会话存在 `root` 下面，重启服务后还在。

- 要让别的机器打开：命令里加 `--host 0.0.0.0 --port 8765 --token-file ../secrets/experts.token`，第一次用
  `http://<机器地址>:8765/studio?token=<口令>` 打开，浏览器会记住。对外开放却不设口令时，服务启动会打印警告：谁都能打开，花的是你配置的 key。
- Studio 只有这一个口令，没有账号体系，不要直接暴露到公网。

### 4.3 页面上的操作

按钮名以中文界面为准。

1. **建场景**（第一次用时）：点「新建培养」，在「场景」下拉里选「新场景…」，填写：
   - 名称、岗位说明（员工做什么、为谁做、交付什么）；
   - 资料（.md、.txt 或 .csv，合计 1 MB 以内）；
   - 练习需求和考试需求，每行一条。考试需求只用来给每个版本打分，分析师和改造师都看不到；
   - 验收项，每行一条，可以先空着。

   填完点「建好场景」。自建场景自带评审，按验收项和你后来选定的规矩打分。
2. **新建会话**：在「新建培养」对话框里填名称、选场景，起点选「干净的 Raven 基线」，写好岗位说明，点「创建」。
   - **换模型**（可选）：对话框的「模型」区给员工、改造师、诊断、分析师、评审分别选服务、填模型名、选推理强度。
     不选的沿用 Raven 配置和 `live.json` 的设置。只对这一个会话生效，创建后不能再改。
   - **登记服务**：点「服务设置…」，填名称、地址（Base URL，例如 `https://api.example.com/v1`）、Key、协议
     （OpenAI Chat Completions、OpenAI Responses 或 Anthropic Messages）和模型名（每行一个），点「保存」，
     再点「测试」向第一个模型发一条请求，确认能通。改已登记的服务时 Key 留空表示不改。
   - Key 只在服务器上：服务登记在 `studio-endpoints.json`（权限 600）；员工换了服务的会话，另有一份自己的 Raven 配置写在旁边的
     `studio-sessions/` 里（目录 700，每次启动会话时重写，删除会话时一起删掉）。页面只显示 Key 的最后四位；会话记录、设置和导出的
     员工包只有模型名，没有地址和 Key，员工包拿到别处运行时，那台机器要自己配好能调这个模型的服务。和直接用 Raven 配置时一样，
     员工运行时会把自己的整份配置（含 Key）展开到会话目录的 `employee/` 下（文件 600，目录 700），删除会话后随会话一起进回收目录。
   - 一个会话里同一个模型名只能由一个服务提供。删掉某个服务后，用它创建的会话下次启动（例如重启 Studio 后）会报错，
     重新登记同名服务即可继续。
   - 「评审」一栏只换 Studio 自带的标准评审。`live.json` 里 `assessor` 指定的评审插件（例如专家流水线的 examiner）按自己的设置选模型，不受影响。
   - **搜索服务**：同一个窗口下方登记，选服务商（默认 serper）、填搜索 Key，点「保存搜索服务」，再点「试搜一次」确认能用。
     所有会话共用：它写进每个会话自己的员工配置 `tools.web`，员工自己的联网搜索、调研同事和入职前的调研（4.4）都用它，
     新会话马上生效，已有会话下次启动时生效。登记了搜索服务后，员工没换模型的会话也会改用自己的一份配置。
   - 从别的机器打开 Studio 时，Key 会经 HTTP 明文发到服务器，最好在服务器本机或通过 SSH 隧道登记服务。
3. **入职**：在输入框（提示“描述岗位，并附上入职材料”）里写岗位要求，用「附件」附上材料，然后发送。改造师据此做出第一个版本。
4. **演练和批注**（每轮都做）：
   - 「开一场演练」，扮演给员工派活的人，不知道问什么就点「AI 出题」，问完点「结束演练」；
   - 在回复下面选「做对了」「应该是…」「做错了」或「漏了…」，写说明后点「批注」；
   - 场景有练习需求时，可以点「脚本演练」自动跑一批；
   - 「AI 提验收项」：AI 把还没定下的规矩做成二选一，选一条或自己写一条。选定的规矩之后每次评审都会用。
5. **交给分析师**：点「交给分析师」。场景配了评审时，评审先给本轮演练打分，再由分析师写出改造要求。
6. **改造**：看到“分析师提了 N 条要求，请求改造。下一步？”时，可以先在输入框里告诉改造师哪条不对、哪里别动，
   然后点「开始改造」；不改就点「跳过本轮」。改完会自动装上新版本，回到第 4 步开始下一轮。
7. **考试**：新版本装上后点「考试」，页面显示“考试：N 项中 M 项不合格”，并和上一个版本对比。点「并排对比」可以看同一道考题在各版本的回答；
   变差了点「退回」，换回改造前的版本。
8. **收尾**：点「归档 vN」把这个版本冻结成快照，之后会话只能查看。点「导出员工」下载员工包，用法见第 6.1 节。

其他：

- 对某一步有疑问，在「问谁」里选分析师或改造师，然后点「提问」。回答依据这一步的记录，不会改动任何东西。
- 某一步出错时会出现「重试分析」或「重试评审」，演练和批注都保留。改造中途停下时点「继续改造」。
- 不要的会话可以「删除会话」，会被挪到服务器的回收目录。

### 4.4 可选：入职前先收集信息

在 `live.json` 里加 `"information": "ask"`，入职前页面会出现「入职前，AI 想先问你」，逐条回答或点「跳过」。
写成 `"research"` 还会上网调研，这时要有搜索服务的 key：在页面「服务设置…」里登记（4.3 第 2 步），或者写进 Raven 配置：

```json
"tools": {"restrictToWorkspace": false, "web": {"search": {"provider": "serper"}, "providers": {"serper": {"apiKey": "<key>"}}}}
```

`provider` 也可以是 tavily、brave、exa、jina、serpapi、serply、firecrawl、anysearch。

## 5. 批量生产专家（流水线）

### 5.1 一个案例由什么组成

每个案例 `experts/cases/<案例>/` 里有：

- `rules/R1.md R2.md R3.md`：三套工作规则。R1、R2 用于培养和同规则考试，R3 只用于新规则考试；
- `questions.json`：40 道题，每题有原文、随题文件和参考答案；
- `scripts.json`：40 个演练脚本；
- `wkr-<案例>/`：场景包（岗位说明、入职材料、人设、验收项 `scenario.json`）；
- `make.py`：生成上面这些材料；
- `check.py`：独立复核参考答案；
- `measure.py`：给评审用的测量值；
- `live.json`：这个案例的 Studio 配置；
- `manifest.json`：导出后的派活说明；
- `probes/`：评审探测答卷；
- `records/`：我们的验收原始记录。

40 道题的编排：

- t01–t20 是培养题：奇数用 R1，偶数用 R2；
- x01–x10 是同规则考试：用 R1、R2，培养时没出现过；
- y01–y10 是新规则考试：全用 R3，员工从没见过。

做新案例的完整要求见 [BUILDING.md](BUILDING.md)。

### 5.2 先确认案例材料（每个案例都做）

```bash
cd experts/cases/<案例> && uv run python make.py && uv run python check.py; cd ../../..
```

`check.py` 最后一行应是 `mismatches: none`。`make.py` 按固定种子重新生成材料：20 个案例和仓库里逐字节一致，git status 没有变化；
contract-review、contract-sheet 的 `questions.json`、`scripts.json` 会显示有改动，因为里面嵌的 Word、Excel 文件带上了新的打包时间，
内容不变，可以用 `git checkout -- experts/cases/<案例>` 还原。

改了评审模型，或者做了新案例，要先跑评审探测，确认评审判得准：

```bash
tmux new-session -d -s experts-probe-<案例> "cd $PWD && uv run python experts/common/probe.py experts/cases/<案例> experts/cases/<案例>/probes/<答卷>.json > /tmp/probe-<案例>.log 2>&1; echo PROBE_EXIT \$? >> /tmp/probe-<案例>.log"
until grep -q PROBE_EXIT /tmp/probe-<案例>.log; do sleep 5; done
grep -- "->" /tmp/probe-<案例>.log      # 每份答卷都应该是 -> MATCH
tmux kill-session -t experts-probe-<案例> 2>/dev/null
```

### 5.3 放行并启动流水线

流水线要看到两个放行文件才开始：一个按案例，一个全局。

```bash
mkdir -p ../runs/experts/control/ready ../runs/experts/control/logs
echo '{}' > ../runs/experts/control/ready/<案例>.json
touch ../runs/experts/control/dispatch.ready
tmux new-session -d -s experts-pipeline-<案例> "cd $PWD && uv run python experts/common/pipeline.py <案例> >> ../runs/experts/control/logs/<案例>-pipeline.log 2>&1"
```

- 一次跑全部 22 个：`uv run python experts/common/pipeline.py --all`。它会给每个还没完成的案例各开一个 tmux 会话
  `experts-pipeline-<案例>`，22 个同时跑，对模型服务的并发压力很大。
- 每个案例的 Studio 用固定端口，端口表是 `experts/common/pipeline.py` 的 `PORTS`（8811 起）。端口被占用时，用 `--port <空闲端口>` 指定。
- 新案例要先登记：在 `experts/common/domains.py` 的 `DOMAINS` 里加一行（`--all` 按它启动），在 `PORTS` 里加一个没用过的端口，
  或者单独运行时加 `--port`。

### 5.4 流水线做了什么

`pipeline.py <案例>` 依次：

1. 在 tmux 会话 `experts-studio-<案例>` 里启动这个案例的 Studio，地址是 127.0.0.1 加上这个案例的端口；
2. 运行驱动 `experts/common/run.py`，依次做：
   - 新建会话，会话号写进 `experts/cases/<案例>/session.txt`；
   - 用场景包里的 `onboarding.md` 入职；
   - 考一次试；
   - 4 轮培养，每轮 5 道题：t01–t05、t06–t10、t11–t15、t16–t20。每轮依次脚本演练、自动评审、交给分析师，分析师要求改造就改造，然后再考一次试；
   - 全部做完后在 `run.log` 里写 `ALL ROUNDS DONE`；
3. 导出三个版本：
   - 培养后的版本，导出到 `<ws>/runs/experts/host/agents/`；
   - 没培养过的 plain Raven，导出到 `host-plain`；
   - 入职改造后、第一轮培养前的 v0，导出到 `host-v0`；
4. 三个版本各做 3 次验收：
   - 每次把 20 道考试题（x01–x10、y01–y10）一道道派给导出的专家，派活走宿主 Raven 的 ACP 链路，每道题一个新的临时工作目录；
   - 用评审逐项判卷；
5. 关掉这个案例的 Studio。

我们跑这 22 个案例时，从新建会话到 `ALL ROUNDS DONE` 用时中位数 1.3 小时，最短 0.5 小时，最长 4.7 小时；其中入职改造约 5 分钟。验收另算。

中断后重新执行同一条命令即可：

- 已完成的步骤按记录跳过；
- 会话中途停了，用 `resume.py` 接着跑；
- 验收按 `run-id` 从检查点恢复。

驱动遇到分析失败会自动重试，最多 8 次；仍然失败时以退出码 75 停下，等人检查。

### 5.5 看进度和结果

| 看什么 | 在哪 |
|---|---|
| 当前阶段 | `<ws>/runs/experts/control/<案例>.json` 的 `stage` 字段，依次是 waiting_materials、training、exporting、acceptance、complete；出错是 failed，看 `error` 字段 |
| 培养过程 | `experts/cases/<案例>/run.log`（每步开始、结束和用时）、`run.out`（驱动的完整输出） |
| Studio 页面 | `http://127.0.0.1:<端口>/studio?token=<口令>`，可以看到自动跑的会话的全部过程 |
| Studio 服务日志 | `<ws>/runs/experts/serve-<案例>.log` |
| 验收日志 | `<ws>/runs/experts/control/logs/<案例>-parallel-v1-<版本>-<次>.log` |
| 验收报告 | `experts/cases/<案例>/accept-<版本>-<时间>.json`，版本是 plain、v0，或培养后 revision 的前 12 位 |
| 成绩单 | `uv run python experts/common/scorecard.py <案例> > /tmp/<案例>.md` |
| 培养出来的专家 | `<ws>/runs/experts/host/agents/expert-<案例>/` |

成绩单里“全对题 x / y”就是 README 里的“同规则 / 新规则”：完全答对的答卷数 / 答卷总数。

### 5.6 我们的 22 个专家的数据

`experts/cases/<案例>/records/` 是我们验收的原始报告（166 份），`experts/README.md` 里的成绩都能从它们复算：

```bash
uv run python experts/common/scorecard.py --records refund-desk
```

输出表格里 plain、v0、培养后三行的“全对题 x / y”应和 README 一致（22 个专家都已核对过）。`experts/reports/` 是我们当时的成绩单和
审计记录，包括 2026-10-11 OpenRouter 额度事故的处理过程。

## 6. 让员工上班：装进宿主 Raven

宿主 Raven 收到请求后，用 `spawn` 工具按每个员工 `subagent.json` 里的 `description` 和 `owns` 决定把活派给谁。宿主用同一份检出运行。

### 6.1 准备宿主

```bash
uv run raven onboard      # 向导：选模型服务、填 key，配置保存在 ~/.raven/config.json
```

宿主配置的 `providers` 里要有能调到专家所用模型的服务：我们的 22 个专家用的是 OpenRouter 的 `z-ai/glm-5.3-flash`，
所以宿主配置里要有 `providers.openrouter.apiKey`。专家启动时会把宿主的 `providers` 借过去用，并把渲染好的配置
（含 key）存到宿主配置文件所在目录的 `expert-runtime/` 下，权限 600。

### 6.2 装专家

- 仓库里的 22 个专家：

```bash
mkdir -p ~/.raven/agents
cp -r experts/agents/expert-* ~/.raven/agents/          # 也可以只拷要用的几个
```

- 流水线自己培养出来的专家：拷 `<ws>/runs/experts/host/agents/expert-<案例>/`。
- Studio 页面「导出员工」下载的 ZIP：把里面整个文件夹解压到 `~/.raven/agents/`，包里有自己的 README；宿主要能调到包里
  `package.json` 记录的模型。会分派子员工的员工导不出来，所以手动 Studio 想导出时，`live.json` 里要写 `"delegation": false`。

设了 `RAVEN_HOME` 时，agents 目录是 `$RAVEN_HOME/agents/`。不要把专家放进仓库根目录的 `agents/`：从源码运行的 Raven 会自动发现那里的
agent，所有员工都会多出这些专家。装完要重启宿主。

### 6.3 使用

```bash
uv run raven agent -m "<一条请求>"      # 发一条消息就退出
uv run raven tui                         # 交互聊天；第一次用要先构建：cd ui-tui && npm install && npm run build && cd ..
```

请求里要讲清楚任务，并提供 `experts/README.md` 里这个专家需要的材料，比如退款客服需要工作规则、退款政策表和学员的订单记录。
主 Raven 不保证每次都把活派给专家，我们测试时遇到过它自己动手的情况。

## 7. 已知问题

- **评审有波动**：同一个版本重复评审 7 次，32 项里不合格的项数在 0 到 3 之间变化。每个版本只考一次时，差一两项说明不了好坏。
- **前后分数不完全可比**：「AI 提验收项」选定的规矩只对之后的评审生效，旧的考试记录不会按新规矩重评。
- **数据缺口**：
  - booking-page 培养后的版本没有验收数据；
  - store-ticket 每个版本只验收了 1 次。现在的流水线对所有案例都跑 3 次；
  - 最早 5 个专家的 39 份验收报告没有登记评审模型；
  - 10-11 额度事故后，一部分员工答卷走的是内部网关。
- **员工权限大**：员工以 `mode: full` 运行，能执行命令、读写自己工作目录以外的文件，所以只在可信的机器上跑。
- **代码状态**：Studio 和流水线都是实验代码，放在这个实验仓库里，不会合入 Raven 主仓库。

## 8. 故障排查

| 现象 | 原因和处理 |
|---|---|
| `ModuleNotFoundError: No module named 'pptx'` | 没装可选依赖，执行 `uv sync --all-extras` |
| `the employee's workdir may not be the repository, inside it or above it` | 运行数据放进了仓库。按 2.1 的布局把 `runs/` 放到仓库外，`live.json` 的 `root` 指向外面 |
| `the live configuration has unknown keys` / `needs ['config', 'root']` | `live.json` 写了不认识的键或缺键，对照 4.1 |
| Studio 页面打不开，日志里有 `No built page` | 没构建页面，执行 2.2 里的 `npm ci && npm run build` |
| 接口返回 `this Studio needs its access token` | 用 `?token=<口令>` 打开一次；流水线读的是 `<ws>/secrets/experts.token` |
| `the token file must hold 16-128 letters, digits, '-' or '_'` | 口令格式不对，用 3.4 的命令重新生成 |
| 模型调用报模型名错误（我们的内部网关对带前缀的名字返回 HTTP 422） | 模型名和服务商不匹配，对照 3.5 改名字，并在 `providers.<名字>.models` 里列出 |
| `[expert-...] the host Raven has no providers to lend` | 宿主配置里没有 `providers`，先 `uv run raven onboard` |
| `start this agent with the Python of a Raven source checkout` | 宿主不是从源码检出运行的，改用检出里的 `uv run raven ...` |
| 端口被占用，或 `This port serves a different expert` | 这个端口上跑着别的服务，用 `--port` 换一个空闲端口 |
| `run this long-lived worker inside tmux` | `baseline_worker.py` / `repeat_worker.py` 要在 tmux 里运行 |
| 驱动以退出码 75 停下 | 分析失败重试 8 次仍失败。看 `run.out` 和 Studio 页面，修好后重新执行流水线命令 |
