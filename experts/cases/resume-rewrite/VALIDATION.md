# 简历优化材料验证

状态：ready，材料自检和五份模型探测已完成，可以开始培养。本记录不表示 Agent 已经训练或通过宿主验收。

本案例对应原文 7.2：根据完整简历、事实表和目标岗位改写经历，不编数字，不把推算出的数字当事实，不夸大职责。

## 规则与题目

- R1：标题“改前改后”，三列表格，最多 8 条，排期职责写“带 N 人小组”。
- R2：标题“经历重写”，列名改变，最多 6 条，排期职责写“协调 N 人项目组”。
- R3：标题“定稿对照”，最多 5 条，排期职责写“负责 N 人内容小组的排期”；新增只采用已确认行、逐行列事实出处。
- 三套规则都要求 E1–E5 各一行；原句逐字保留，改写数字及实际动作以事实表为准。有实际工作支撑的岗位关键词全部使用，无支撑的关键词不进入改写。
- 40 题固定编排：20 道培养题、10 道同规则考试、10 道 R3 新规则考试；每组含常见及边界题。事实表 40 份均不重复。
- 边界陷阱包括阿拉伯数字/中文数字/万的等值写法、约与余、区间上下限、最高和平均、原简历中的推算增长率、无实操的 JD 关键词、协助与团队成果归属、R3 更好看但待核实的结果及错配来源。

## 可复核验证

在仓库根目录运行：

```sh
uv run python experts/cases/resume-rewrite/check.py
uv run python experts/cases/resume-rewrite/probes.py
```

`check.py` 不导入生成器，从员工可见文件重建事实依据。实际输出：

```text
measure selftest: ok
mismatches: none
independent audit mutations caught: 24/24
40 references, 40 example numeric inventories, split counts and 40 wrapper isolation checks: ok
```

另已检查：`wkr-resume-rewrite` 未出现在 Raven-port 的 Python、JSON、Markdown 文件中。

## 独立模型探测

使用探测脚本（现为 `experts/common/probe.py`）和公共 examiner，由 kimi-k3 评审；测量器只提供文本、数字与归属证据，不决定通过或失败。首次完整探测全部符合预期，日志结束为 `PROBE_EXIT 0`。

| 答卷 | RW-fact | RW-writing | RW-keyword | RW-role | RW-format |
|---|---|---|---|---|---|
| t11 正确 | pass | pass | pass | pass | pass |
| t11 错误 | fail 1 | pass | fail 1 | fail 1 | pass |
| y06 正确 | pass | pass | pass | pass | pass |
| y06 错误 | fail 1 | fail 1 | pass | pass | fail 1 |
| t11 正确 + 前后说明 | pass | pass | pass | pass | fail 1 |

探测答卷：`probes/probe-resume-rewrite.json`。
完整评审日志当时写在培养机器的 /tmp/experts/probe-resume-rewrite.log，没有随仓库保存。
探测会话 `experts-probe-resume-rewrite` 已完成并自动关闭，没有遗留进程。

本轮接续没有发现需要改题的歧义，没有改评审代码或训练配置，也没有启动 Studio。检查通过后未重复运行相同探测。
