# Action strategy on Raven

ActionBinding selects event kinds, optional requests and an optional model tool. requests enables peer-only handling. Enabled methods must be implemented with the supplied concrete common types. Factories receive session state and Task and can request infer, plan or peers dependencies.

## Event consumers

progress runs before an iteration and supports continuation, guidance and a terminal reply. proposal at a batch or reply supports native bounded resampling and completion. With dispatch=true, the native ToolGate sends a single dispatch proposal, supporting continue/reject; gate errors refuse the call. Native permissions remain independent.

outcome receives actual transcript evidence after a tool iteration. failure at terminal_answerless supports only the terminal choices stated in the event; native synthesis, early exit or scheduled rerun can make that point unreachable. control reports application receipts. An unselected kind has no implied call or state change.

The host checks the event's allowed controls before accepting state changes. Unsupported effects are errors. Hook evaluation failures stop through a truthful reply; interrupted required pre-decision checks cannot degrade into a silent provider call. Guidance becomes a per-call input contribution. revise feedback becomes native rollback injection; reason is diagnostic.

## Requests and control receipts

A tool exposes only the concrete command under request. The callback resolves the current session owner and returns its domain answer plus a host control receipt. Controls are queued for after the tool batch. Multiple conflicting queued controls are rejected; a queued finish does not itself stop sibling tools. Mandatory ordering constraints use dispatch checks.

A requested receipt is not application. Native rollback counters establish accepted/refused revision; actual appended terminal replies establish finish application. Ending without such evidence produces a rejected receipt. A dispatch refusal has the native gate's concrete non-execution consumer. Receipts and actual execution remain available to Curator.

Streaming draft content is withheld by the native draft mechanism. When Action replaces a candidate reply, the adapter discards that draft before native release, so rejected text is not first shown to the user. Existing later native transformations and their actual ordering remain part of the inspected harness.

## Collaboration and validation

The optional infer dependency uses the worker provider for a typed, single-step
judgment inside the current operation. Curator authors its prompt, selected
evidence and result-to-control mapping. Inspect worker.inference for the actual
limits and read the supplied StrategyInference guide. Inference results carry
no independent control authority; the current event still limits their effect.
An operation and its sequential peer calls share one attempt, including failed
attempts. Do not repair an invalid judgment by invoking the model again.

StrategyPeers reads detached views and invokes typed operations of the real owner. Cycle and read-only checks occur before peer writes. One owner's failure does not roll back another owner's success. Tool interaction, event rules and the gate share one active Action owner; no second policy instance or duplicate plan is created.

Verify mandatory refusal without a voluntary self-check, permitted execution, real correction input, truthful terminal replies, exhausted budgets, model-request controls, streaming visibility and revision preservation. A method result alone is not proof of behavior.
