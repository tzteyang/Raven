# 恢复后慢请求诊断

观察时间：2026-10-11 22:16–22:24 UTC。此报告只用已存在记录与本地健康检查；没有新派题、改参数或重启服务。

结论：两道题的长等待包含**上游明确的120秒无响应超时、原生重试和本地排队**，不能解释为单次持续思考。没有发现适配器吞流或认证失败的证据。简历题已经完成；亚马逊题仍在原上下文继续。

## 两道题的证据

| 案例 / run-id / 题 | 同一请求参数 SHA256 前12位 | 恢复后已确认的重试 | 后续结果 |
| --- | --- | --- | --- |
| amazon-listing / parallel-v1-a6acd033c4b6-2 / x07 | `9d41b381cbf3` | 同一hash连续4次上游120秒超时，均0条delta；第5次才返回 | 22:02:03.613521–22:18:59.464136 的 `llm.call` 最终HTTP200、`finish=length`、4096输出token；22:21:35再返回length，22:23:20返回tool_calls并执行工具。截至22:24，题仍dispatching，不能称整题完成。 |
| resume-screen / parallel-v1-44acc1a36688-3 / x09 | `e86da12c683c` | 同一hash连续3次上游120秒超时，均0条delta；第4次才返回 | 22:00:17.764824–22:12:22.551581 的调用HTTP200、length、4096输出token；之后多次工具调用，22:18:21.620049最终stop。checkpoint已scored，answer.seconds=1102、error=null。 |

原生逐次请求证据：

- `runs/experts/accept-hosts/amazon-listing/parallel-v1-a6acd033c4b6-2/workspace/subagent_sessions/expert-amazon-listing/state/observations.jsonl`，会话 `acp:20261011_220009_db4325`；错误在11359、11361、11363、11365行。
- `runs/experts/accept-hosts/resume-screen/parallel-v1-44acc1a36688-3/workspace/subagent_sessions/expert-resume-screen/state/observations.jsonl`，会话 `acp:20261011_220008_976a70`；错误在8867、8869、8871行。

这7条错误都包含上游原文：`The platform sent nothing back within 120s`。它们不是本地600秒首字节/流空闲超时。

完成事件与答卷状态分别在相同host下的 `traces/logs/audit-spans.log`，以及 `experts/cases/<case>/accept-runs/<run-id>/partial.json`。简历最终stop位于其audit-spans.log第231行。`llm.call`记录包住了整个stream重试过程，所以1015.9秒/724.8秒不能当作单条HTTP请求的耗时。

代码证据：`Raven-port/raven/agent/loop/turn_path.py:408`的span包住`stream_llm_call`；`Raven-port/raven/providers/streaming.py:203`的重试循环使用1次立即重连和15/30/60秒等待，最多5次尝试。此次失败尝试均未产生delta；框架保留当前员工上下文，未重新派发整题。

## HTTP504与健康统计缺口

22:16:59的18874健康记录显示active=10、waiting=16；18875显示transport_errors=0、credential_errors=0。后者只说明本地转发与凭据读取没有这些错误，**不代表上游HTTP都成功**。截至约22:18，18875完成日志已有33条HTTP504。

可直接对齐：

- `runs/experts/employee-gateway-18875.log:79`：22:02:20.274，request=22，status=504，122.50秒。
- `runs/experts/gateway-queue.log:4572`：同一时刻request=4515，status=504，attempts=1，122.50秒。
- 简历最终成功的那一次HTTP：employee日志第202行，22:12:22.531，request=192，200，143.79秒；queue日志第4705行对应request=4692、attempts=1。
- 亚马逊重试组最终成功的HTTP：employee日志第315行，22:18:59.442，request=302，200，144.60秒。

适配器与queue在传输异常时生成502，不生成504；queue仅会重试指定的503并发拒绝。这里的504来自更上游，随后由Raven的stream层重试。较长的单次墙钟时间还包含本地等待；仅凭现有queue结束日志，不能逐条精确拆出排队与上游用时。

降低同时发起的工作量可能减少本地排队，但**不能消除上游明确的120秒无响应限制**。不应通过延长本地600秒/1800秒超时来解释或修复这一限制。是否降低负载能减少上游超时频率仍需证据，当前没有做参数或并发调整。

## 健康观测修复

已在`experts/common/employee_gateway.py`新增：

- `status_counts`：逐上游HTTP状态计数；
- `upstream_errors`：上游HTTP >=400计数；
- `last_upstream_error`：仅status和epoch时间，不存内容或凭据。

10项离线测试和ruff通过，包含504原样转发、只计一次、transport_errors仍为0。**现有服务未重启，修复尚未热加载**；当前health仍不具有这些新字段。没有中断活跃请求。

## 复现

在`gtm_rsi`下执行，输出仅参数指纹、错误类别与完成类型，不输出prompt或凭据：

```bash
uv run --no-project python - <<'PY'
import hashlib, json
from pathlib import Path
cases = [
    ('amazon-listing', 'parallel-v1-a6acd033c4b6-2', 'acp:20261011_220009_db4325'),
    ('resume-screen', 'parallel-v1-44acc1a36688-3', 'acp:20261011_220008_976a70'),
]
for case, run, conversation in cases:
    path = (Path('runs/experts/accept-hosts') / case / run / 'workspace/subagent_sessions'
            / ('expert-' + case) / 'state/observations.jsonl')
    attempts = []
    for line in path.open():
        row = json.loads(line)
        if row.get('conversation') != conversation:
            continue
        if row['kind'] == 'provider.request':
            fingerprint = hashlib.sha256(json.dumps(row.get('parameters'), sort_keys=True).encode()).hexdigest()[:12]
            attempts.append({'hash': fingerprint, 'deltas': 0})
        elif row['kind'] == 'provider.error' and attempts:
            attempts[-1]['upstream120s'] = 'within 120s' in row.get('error', '')
        elif row['kind'] == 'provider.delta' and attempts:
            attempts[-1]['deltas'] += 1
            if row['delta'].get('finish_reason'):
                attempts[-1]['finish'] = row['delta']['finish_reason']
    print(case, json.dumps(attempts))
PY
```

建议保留上述原始错误、重试和最终答卷记录，让已恢复题在原上下文完成；不按最终分数选择重做。待没有活跃请求的服务切换窗口，再加载新增health统计。

## 输出上限与推理参数的离线协议核验

对当前Raven及已安装LiteLLM执行了一次完全离线的HTTP发送前截获：使用假凭据、假prompt，`httpx.AsyncClient.send`被替换为只读请求结构的函数，真实socket连接被禁用。没有调用生产适配器或模型，也没有改变运行参数。此处是当前客户端转换的复现；**历史生产请求的线级body未保存，不能宣称抓到了那两次历史HTTP包**。

发送前JSON字段为：`max_tokens, messages, model, reasoning, stream, stream_options, temperature, tool_choice, tools, usage`。非敏感标量为：

| 字段 | 离线发送前值 | 18875处理 |
| --- | --- | --- |
| model | z-ai/glm-5.3-flash | 显式映射为glm-5.3-flash |
| max_tokens | 64000 | 原值保留 |
| max_completion_tokens | 没有发送 | 无此字段 |
| reasoning | `{"effort":"medium"}` | 原结构保留 |
| reasoning_effort | 没有平铺发送 | 无此字段 |
| stream | true | 原值保留 |
| stream_options | `{"include_usage":true}` | 原结构保留 |
| usage | `{"include":true}` | 唯一被丢弃的字段 |

`usage`是LiteLLM的OpenRouter转换器自动补充的成本统计扩展：`Raven-port/.venv/lib/python3.12/site-packages/litellm/llms/openrouter/chat/transformation.py:171`。适配器仍保留标准的`stream_options.include_usage=true`。此次离线复现中，`dropped_fields=1`对应usage，不对应token上限或推理参数。

`experts/common/employee_gateway.py:33`白名单包含`max_tokens`、`max_completion_tokens`、`reasoning`、`reasoning_effort`；第135–138行只过滤顶层键和映射model。18874队列原样转发body字节，没有4096上限或reasoning重写。历史原生request记录在转换前只明确给了`reasoning_effort=medium`，默认`max_tokens=null`；64000是客户端解析的模型输出上限，因此与导出配置中的`maxTokens=8192`不是同一个实际观测层次。

上游18791的实际实现、请求映射和模型有效limits没有得到可核实证据。故**nested reasoning是否被采纳、4096是否属于上游输出/思考预算，仍然未知**；不能依据模型名字或两次恰好4096就下结论。已保存输出证实两次均HTTP200、finish=length、completion_tokens=4096，而content和reasoning_content均为空。

还有一项客户端兼容性风险，尚不能归因于这两次请求：已安装的OpenRouter流解析器在同文件第281行，用`delta.reasoning`无条件覆盖`delta.reasoning_content`。纯离线构造仅含reasoning_content的chunk，解析结果不再提供该字段（直接读取抛出AttributeError），与该赋值行为一致。若18791只发送reasoning_content，当前OpenRouter解析器会丢失它；但历史记录仅保留经过LiteLLM处理的尾部chunk，没有上游原始SSE，**无法确认这两次生产响应是否触发了该分支**。本次没有修改解析器、适配器响应或模型参数。

## 2026-10-12 模型目录复核

使用既有模型调用凭据读取 `/openai/v1/models`（普通模型API，未访问管理端）。`glm-5.3-flash` 的目录声明 `supported_parameters=["reasoning", "reasoning.effort"]`，档位为 low、medium、high、xhigh、max；其来源是 `host_catalog`，`verified_efforts=[]`，默认档位为 null。目录没有给出 max_tokens 或输出上限的值。

这与当前客户端发送嵌套 reasoning 的格式一致，但目录声明不能独立证明生产调用的档位生效，也不能由“未列出”推断 max_tokens 一定被忽略。4096 截断的上游原因仍未核实。没有为此改动请求参数、路由或实验记录。
