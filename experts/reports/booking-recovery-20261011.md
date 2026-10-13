# 预约页面分析中断恢复

2026-10-11 19:51 UTC，`live-20261011193431-2c14a0` 第一轮分析遇到分析模型 HTTP 503（模型暂不可用）。Studio 原来的终态恢复接口拒绝该记录，外层重试不能推进。员工答卷、规则评审和独立考试结果均已保存。

修复在框架增加显式分析恢复入口，拒绝其他终态错误，校验员工版本未改变。旧失败轮完整保存在迭代记录的 `analysis_failures`，包含原错误、版本、恢复时间和证据引用；恢复该轮的答卷和判定后，再由正常 Analyst 执行分析。考试证据仍独立保存，不进入 Analyst/Curator 的训练反馈。暂态恢复拒绝或次数耗尽时，驱动以退出码 75 停止，外层不再空转。

现场执行记录：

- 20:09 UTC，仅重启预约页面自己的 Studio，加载新恢复接口。
- 请求 `POST /api/studio/live/live-20261011193431-2c14a0/resume`，内容为 `{"retry":"analyse"}`，返回 202。
- 恢复完成后，状态为 running，已完成轮数为 0，待分析训练题 5 道，独立考试题 20 道。
- 恢复前后，对 `sessions`、`signals`、`holdout`、`holdout_signals` 分别按排序后的 JSON 求 SHA-256，四项均完全相同；审计备份中的四项也完全相同。原错误、revision 均保留。
- 20:10:31 UTC，正常驱动重新提交 analyse；20:12:10 UTC 已进入 curate。未重跑员工、未修改答卷或评审判定。

证据：[`run.out`](../cases/booking-page/run.out)、[迭代原记录](../../runs/experts/booking-page/runs/live-20261011193431-2c14a0/iteration/7fb0036339dc48ce88d630b8893ca0d7.json)、[恢复前指纹](/tmp/experts/booking-recovery-before.json)。

补丁验证：98 项框架/Live/Studio/iteration_run 测试、20 项驱动测试、4 项 pipeline 测试通过。
