# Single-step strategy inference

`infer` is an optional keyword-only factory dependency implementing
StrategyInference. The worker model, not the Curator model, performs one
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
attempt. A second call in that chain is rejected even after the first failed.
The host supplies operation identity; changing helper names or invoking another
owner does not obtain another attempt. Background tasks and callbacks escaping
the operation are refused. Only active worker turns may infer: constructors,
prepare, assembly-time initialization and inspection may not call the model.

`worker.inference` reports actual turn, input, output and timeout limits. Each
new main-loop event can have a new operation, within the same turn budget.
The adapter uses one provider.chat call with the worker's effective model and
generation settings, capped by its output/timeout allowance. It does not use
the provider retry ladder, repair malformed JSON or resample its own judgment.
This constrains framework calls, not hidden transport retries inside a provider.

InferenceError identifies scope, budget, timeout, provider or result failure.
Cancellation propagates. Required checks must keep errors visible; native
dispatch refuses errors and the Action hook stops an incomplete required check.
Optional guidance can explicitly catch InferenceError and continue, recording
the chosen degradation. Never translate a failed check into a satisfied verdict.

## Verification

Trace the trigger through strategy.inference and strategy.inference.result/error
to the strategy result and any action.control receipt. Operation and source IDs
are host records, not model fields. Provider records retain actual parameters,
response and usage. Verify the number of calls, malformed/unknown results and
the actual refusal, correction input or next model request. A valid JSON verdict
alone is not proof that the Loop applied the intended intervention.
