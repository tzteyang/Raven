# 亚马逊英文 Listing 案例验证

本目录已准备好供 Studio 从普通 Raven 培养独立专家。材料和答案由固定种子生成，未启动 Studio。

## 规则与材料

| 规则 | 卖家 | 标题上限 | 要点上限 | 指定公制单位 | 美制小数位 | 开头分隔符 |
|---|---|---:|---:|---|---:|---|
| R1 | PawNest | 150 | 250 | L / cm / kg | 1 | `: ` |
| R2 | TailHaven | 120 | 210 | mL / mm / g | 2 | ` — ` |
| R3 | WhiskerWay | 135 | 230 | L / cm / kg | 2 | `: ` |

所有规则都交一个英文标题和五条要点。R2 改了段名、禁用词与单位口径；例如 R1 禁 `best`，R2 不禁，而 R2 禁 `ultimate`、`risk-free`。认证必须按目标 SKU、已取得状态和别名核对，按资料准许的成句写法写。R3 新增证据日期筛选（有效至当天有效、此前失效、日期缺失不可写）和第一条要点原样引用使用限制。

40 题严格采用 t01–t20、x01–x10、y01–y10 的固定编排。common 有容量、粒径、最多餐数、录音、颜色和供电；edge 增加机身三边、净重、物流干扰字段和其他 SKU 的已取得认证。英式拼写、未经证实的功能、夸大词与认证声称来自待改营销草稿。每题都提供全部工作规则、参数 CSV、认证记录与别名、拼写表及单位换算表。

## 可复现检查

在仓库根目录运行：

```sh
uv run python experts/cases/amazon-listing/make.py
uv run python experts/cases/amazon-listing/check.py
```

实测输出：

```text
generated 40 questions; R1/R2 train and same, R3 new
measure self-test: ok
mismatches: none
examples checked: 40; independent-key mutations caught: 15
```

独立复核器只读员工可见的规则和 CSV，不导入生成器。它采用有理数算法另算换算结果，与生成器的 Decimal 算法互相核对；还复核认证、禁词、段名、单位、小数位及限制。15 类故意改错的参考值均被检出。40 份示例的标题、要点格式、参数覆盖、转换值、认证与拼写均有可复现检查。

`measure.py` 只提供事实测量，没有输出 pass/fail；题目判定由 kimi-k3 模型完成。测量自测覆盖引号、括号、Markdown、完整词边界、最长认证别名和正文/外部说明隔离。

## 模型探测

使用探测脚本（现为 `experts/common/probe.py`）运行 `probes.json` 中五份手写答卷。完整原始评审见 `probe.log`，末行为 `PROBE_EXIT 0`。

| 答卷 | AL-title | AL-facts | AL-units | AL-safe | AL-format |
|---|---|---|---|---|---|
| t12 正确 | pass | pass | pass | pass | pass |
| t12 错误 | FAIL 1 | pass | FAIL 1 | FAIL 4 | pass |
| y06 正确 | pass | pass | pass | pass | pass |
| y06 错误 | pass | FAIL 1 | pass | FAIL 2 | FAIL 1 |
| t12 正确 + 前后说明 | pass | pass | pass | pass | FAIL 1 |

t12 错误分别是缺 SKU、cups 错算、两项未取得认证、guaranteed、colour；y06 错误分别是缺限制原文、过期 FCC、无日期 CE、要点首短语未全大写。正确 + 前后说明即使说明里有禁词、认证和错误数值，也仅扣一处格式分。

本次修正了示例中 `a 8-second` 的语法，改为 `your 8-second`；自检扩展到直接从规则抽出禁词、段名与开头分隔符，避免参考答案和生成器共享错误而空过。评审探测第一次即全部符合预期，无需改题迎合评审。

`Raven-port` 中没有 `wkr-amazon-listing` 场景目录名的命中。探测 tmux session `experts-probe-amazon-listing` 已自动结束，独立核对确认不存在。
