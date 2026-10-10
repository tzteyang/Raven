# Single-step strategy inference

`infer` is an optional keyword-only factory dependency implementing
StrategyInference. The worker model, not the Curator model, performs each
runtime judgment. Use it when interpreting supplied evidence or combined task
constraints helps; deterministic rules remain valid and need no inference.
It neither runs tools nor calls a child agent or the main Loop recursively.

## Authored mechanism

Keep the trigger, selected input, output type and result consumer in the owning
strategy class. Keep a reusable judgment instruction in its supporting assets,
such as `prompts/review.md`, optionally using the existing typed Prompt helper.
Indexing it through host.prompt during prepare does not invoke or inject it.
Curator's generation instructions explain this option; the authored judgment
prompt supplies the task-specific standard at runtime.

A minimal call inside an active strategy operation is:

```python
from typing import Literal
from pydantic import BaseModel, ConfigDict

class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["satisfied", "needs_revision", "insufficient_evidence"]
    explanation: str

review = await self.infer(
    instruction=self.review_instruction,
    data={"criteria": criteria, "candidate": candidate, "evidence": evidence},
    output_type=Review,
)
```

The call may also set `max_output_tokens` and `reasoning_effort` (one of the
choices `worker.inference` lists); omitted, each follows the worker's own
generation settings. Neither may exceed the worker's own: a judgment is never
made by a stronger configuration than the work it judges. A reasoning model
spends its reasoning from the same output allowance, so a judgment over a long
standard and evidence needs room for both; a lower effort reduces the reasoning
only where the worker's provider honours it. A judgment cut off before its JSON
is a result failure, not a verdict.

## Judging one rule at a time

A judgment that weighs many rules against a long text at once is the one most
likely to run out of output, and the one whose verdict says least about which
rule failed. Judge each rule that needs interpretation on its own, with the
candidate and only the evidence that rule needs, and let the strategy combine
the verdicts by its own rule:

```python
from experimental.harness.contract.inference import InferenceError, InferenceRequest

requests = [
    InferenceRequest(instruction=rule.instruction, data={"candidate": text, "evidence": rule.evidence(evidence)})
    for rule in self.rules
]
verdicts = await self.infer.each(requests, output_type=RuleVerdict)
unjudged = [rule.name for rule, verdict in zip(self.rules, verdicts) if isinstance(verdict, InferenceError)]
violated = [
    rule.name
    for rule, verdict in zip(self.rules, verdicts)
    if not isinstance(verdict, InferenceError) and verdict.verdict == "violated"
]
```

`each` makes the judgments at once and returns them in order, each a result
or the InferenceError that kept it from one. A rule's instruction states what
the rule allows as well as what it forbids, in the material's own terms; where
the material leaves a boundary open, the instruction says how the judgment
treats the open case instead of leaving the model to guess. What the strategy
does with an unjudged rule is part of the commitment that owns the check: say
there what happens when the judgment cannot be made, and which actions other
commitments carry out that this choice could stop.

This result type is an example, not a fixed verdict protocol. The result must
be a concrete BaseModel with extra='forbid'. The host derives the output schema,
asks for JSON and validates it strictly. Supply JSON data, not messages with
self-assigned roles. Keep criteria/instructions separate from candidate text.
The prompt should distinguish a violated requirement from insufficient evidence
and request concrete, relevant feedback. It cannot acquire missing evidence.

The strategy maps this domain result to its own public result. Action must use
the event's allowed_controls and can_guide: progress can supply guidance,
per-call dispatch can continue/reject, and candidate review can request revise
only while the native rollback allowance permits it. A judgment cannot grant
permission. A requested control is separate from its actual host receipt.

Build delivery criteria from customer requirements and the expert's business
rules, not instructions to Curator about implementing this mechanism. A reply
proposal can also be a progress update while native background work continues.
Distinguish that from a claimed final delivery using the available evidence;
do not require every interim update to contain the final deliverables. The
review is internal: the customer need not receive its schema or a report about
how the Harness was built. Keep dynamic candidate/evidence data in `data`,
instead of duplicating it inside the system instruction template.

## Candidate shape for reply review

A reply-review implementation can submit just this binding and its supporting
`action_impl.py` and `prompts/review.md` files:

```json
{"values": {"action.strategy": {"factory": "action_impl:create", "events": ["proposal"]}}}
```

The module exports `create(state, task, *, infer, host)` returning an
ActionStrategy implementation. It may inherit handle_event and implement
`_handle_proposal(ProposalEvent) -> ActionDecision`, checking `stage == "reply"`
before inferring. A reusable Prompt can be indexed by prepare through
`host.prompt("action_impl:REVIEW")`; its instruction is rendered only at the
runtime call. The strict result model lives with its consumer in that module.

Select only actually available evidence. ProposalEvent supplies the candidate
and the current plan view, not the complete conversation or proof of completed
work. Additional evidence needs a declared peer operation or a relevant host
observation. Do not fabricate event fields to obtain it. A result requiring
revision maps to feedback only when revise is allowed; an exhausted allowance
needs an explicit supported fallback, not an unbounded retry.

An internal judgment needs no model-facing tool or Capability contribution.
Register an interaction tool only when the agent should explicitly request an
Action operation. This example explains the connection and does not require
every strategy to use the same class layout, verdict type or judgment algorithm.

## Host boundaries

The outermost host strategy operation and its sequential peer calls share one
allowance of calls and of time from its first judgment; every call spends from
it, failed or not, and from the turn's allowance of calls and input tokens. A
batch through `each` is admitted whole or refused whole. Input is measured in
tokens against bands derived from the worker model's context window, one for a
single judgment and one for the turn's total: an estimate below the band's
`clear` bound passes, one from its `refuse` bound on is refused, and the
provider's reported usage settles what the turn actually spent. A judgment
repeated within one turn with the same instruction, data, schema and sampling
is answered from the turn's memory and spends nothing, so judge each candidate
once per turn and vary the input when a fresh sample is wanted. The host supplies
operation identity; changing helper names or invoking another owner does not
obtain another allowance. Tasks the strategy starts itself, background tasks
and callbacks escaping the operation are refused; `each` is the way to judge
at once. Only active worker turns may infer: constructors, prepare,
assembly-time initialization and inspection may not call the model.

`worker.inference` reports the actual operation and turn limits, the input and
timeout limits, the accepted reasoning efforts and the worker's defaults. Each
new main-loop event can have a new operation, within the same turn allowance.
Each judgment is one provider.chat call with the worker's effective model, the
strategy's chosen output allowance and effort, and the worker's generation
settings for anything not chosen. The host does not use the provider retry
ladder, repair malformed JSON or resample a judgment; a strategy that wants a
second judgment asks for it within its allowance.
This constrains framework calls, not hidden transport retries inside a provider.

InferenceError identifies scope, budget, timeout, provider or result failure.
None of them is a verdict on the candidate. At a dispatch, a strategy that
cannot obtain its judgment returns `ActionDecision(unverified=<reason>)`: the
host lets the call through and records the reason for reviewers, and an
InferenceError that escapes the strategy there is treated the same way. Mapping
an unavailable judgment to reject refuses work the strategy never reviewed.
Cancellation propagates. An error the strategy lets propagate ends its
operation: native dispatch refuses the call being decided, and the Action hook
stops the incomplete check. An error that `each` returns, or that the strategy
catches, stops nothing by itself; the strategy's own result decides what
follows and records the choice. A failed judgment is neither a satisfied nor a
violated verdict.

## Verification

Trace the trigger through strategy.inference and strategy.inference.result/error
to the strategy result and any action.control receipt. Operation and source IDs
are host records, not model fields. Provider records retain actual parameters,
response and usage. Verify the number of calls, malformed/unknown results and
the actual refusal, correction input or next model request. A valid JSON verdict
alone is not proof that the Loop applied the intended intervention.
