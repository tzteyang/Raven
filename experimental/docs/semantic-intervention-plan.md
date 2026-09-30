# 单步语义干预实施计划

状态：本轮实施与针对性验证完成。日期：2026-09-29。验证范围是单步机制、原生控制与小型真实模型判断，不是五专家案例的完整重新评估。

## 目标与选择

Curator 生成触发条件、判断提示词、结果类型和控制映射；Worker 的运行时模型完成一次判断；Action 与 Raven 原生消费者实施受阶段约束的干预。保留四策略生成入口和 Action.handle_event/handle_request，不增加 Agent 子流程、工具调用循环或独立 judge Target。

已比较三种方式：保留文本 infer 并让每个生成实现重复解析与限制，约束易遗漏；固定语义 Action 基类会过早限定所有实现的判断算法；采用有类型的单步 infer 依赖，由宿主统一保证调用边界，策略保留业务表达自由。

## 契约

- 公共 StrategyInference 接收 instruction、JSON data、具体 Pydantic output_type，返回校验后的领域对象。领域对象不固定为同一种 verdict，更不自动执行控制。
- 配套提示词由消费它的策略所有，可以复用 Prompt 与 Artifact.files。Curator 初选、设计、实现均能找到调用契约、使用条件和最小机制例子。
- 宿主的最外层策略操作与其顺序 peer 调用共享一次推理额度；事件/请求标识用于关联，额度不由生成代码填写标识领取。跨任务、离开操作后、构造/prepare 与非活动 turn 不得调用。
- 仍有整个 turn 的辅助调用预算、输入字节限制、输出 token 上限与超时。一次尝试后额度消耗，错误不自动修复或再次采样；使用单次 provider.chat，并显式继承有效生成参数。
- 工具调用、空回复、截断和不符合 schema 的输出均为明确失败。必要检查沿原生 gate/hook 错误处理拒绝或停止；可选指导只有策略显式处理失败才可降级。
- 一次新主循环事件可再请求判断；不能在同一介入中通过不同 helper 或 peer 绕过限制。判断结果与宿主实际应用回执分别记录。

## 实施范围

1. 公共推理依赖与错误类型、adapter 的单次实现、宿主操作作用域、可检查的预算事实。
2. 迁移现有 infer 调用、Prompt 集成中残留的旧输出入口和生成说明；补充 Action 的规则/语义选择、提示词归属、领域结果到控制的映射。
3. 针对额度共享、作用域、模型参数、错误和严格解析进行必要单测；通过真实 Loop 的回放集成验证判断引发修正或拒绝。
4. 条件允许时做一次小型真实模型判断检查，明确区别于完整专家案例和真实 Curator 生成评估，不重新运行五案例矩阵。

## 验收与非目标

检查 Curator 可见信息是否包含该选项及表达方式；检查每次介入的实际 provider 调用数量；检查模型结果是否改变原生执行。保持主要确定性逻辑可用，不强迫任何策略调用模型。

不新增账户配置、任意子角色接纳、长期判断记忆或跨事件缓存；不改变宿主权限。源码及技术提示词使用英文，验证经 uv 运行，不提交或推送。

## 实施记录

- 已新增公共 StrategyInference/InferenceError，替换旧文本 infer 调用；未保留旧签名兼容层。Action 的两个公共操作和四策略生成入口保持不变。
- 宿主 owner_operation 创建一次操作上下文，顺序 peer 调用继承同一额度；离开作用域、后台任务、无活动 turn 均被拒绝。错误不退还尝试额度，整个 turn 预算仍由 runner 释放。
- adapter 使用一次 provider.chat，显式继承模型及生成默认值，并施加输入、输出、时间和 turn 上限。严格解析具体结果类型；没有格式修复、工具调用或模型重试循环。提供关联源事件的请求、结果、错误与用量记录。
- Curator 的初选 Action effect、公共协议、shared knowledge、设计提示和参考说明均提供该选项。worker.inference 暴露实际限制，配套提示词由消费它的策略拥有。已清理旧 infer(messages) 说明及 Prompt 集成中的旧资源 Target。
- 单测：`uv run --offline --no-sync pytest tests/test_harness_curator_inference.py tests/test_harness_curator_prompts.py tests/test_harness_curator_interactions.py tests/test_harness_curator_contracts.py -q --tb=short`，60 项通过。
- 原生集成：Prompt 与交互文件共 11 个用例。首次 9 通过、2 个工具拒绝用例被更早的原生权限检查拦住；为这两个机制测试明确允许 write_file 后，仅重跑它们，2 项通过。实际验证了单步 guidance、候选修正、拒绝执行、损坏判断不执行及既有跨策略行为。日志为 `/tmp/raven-semantic-intervention-native.log` 和 `/tmp/raven-semantic-dispatch-native.log`；模型响应使用回放，不宣称真实模型端到端专家表现。
- 真实模型：沿用 `deepseek/deepseek-flash` 配置，分别判断相互矛盾与有充分支持的两份行程材料；每份一次调用，分别得到 needs_revision 和 satisfied。结果与原始 provider 记录保存在 `/tmp/raven-semantic-judgment-20260929/`。这是推理依赖的真实 provider 检查，没有运行新的 Curator 生成或完整专家 Loop，不能推出一般准确率。
- 相关源码通过导入/未使用项检查、格式及差异检查；文档执行仓库大文件和源码语言门禁。没有提交或推送。

当前使用入口为 [单步推理说明](../curator/harness/reference/inference.md) 和公共协议源码；本计划保留范围、选择与验证证据。

用户将本项与说明/真实入口对齐设为联合目标后，已重新验收单步契约、原生控制和生成知识链，并补充绑定、配套文件及真实证据选择的说明。尚不能用这些机制检查代替正常部署下的 Curator 真实生成结果；联合目标的完整验收与外部配置缺项见[联合验收表](curator-docs-and-scenario-alignment-plan.md#7-与-action-实现的联合验收)。
