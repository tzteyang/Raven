# Action strategy: generation guide

Action handles host events and agent requests using one set of domain rules. Its public operations are handle_event and handle_request. The supplied typed events, ActionInteraction, ActionDecision, ActionResponse and ControlReceipt define their common semantics.

## Host events

ProgressEvent describes a pre-decision observation. Its offered tools can still undergo native normalization; previous_capabilities is the last actual model-call view. ProposalEvent distinguishes a batch, one dispatch and a candidate reply. OutcomeEvent supplies actual transcript evidence, not a promise that every proposed call succeeded. FailureEvent distinguishes terminal recovery from ordinary progress. ControlEvent reports a host application result.

Only selected event kinds are delivered. Use allowed_controls and can_guide from the host. continue means no intervention, not permission. reject refuses a dispatch; revise supplies correction feedback for bounded resampling; finish supplies a truthful terminal reply. Guidance and diagnostic reasons have different consumers.

A valid decision is an intention. Read the host receipt before claiming a control was applied. Repeated observations, exhausted budgets and unsupported effects require explicit behavior. Mandatory per-call constraints need the binding's native dispatch gate; a voluntary self-check tool is insufficient.

## Agent and peer requests

handle_request receives a concrete command in ActionInteraction and returns ActionResponse with a domain reply and optional control intention. The host binds identity, provenance and allowed effects; tool arguments cannot choose them. A request tool's control is queued for the post-batch boundary, so it does not by itself prevent sibling tool calls already in that batch. Use a dispatch rule when that ordering matters.

Use StrategyPeers to read a plan or effective capability view, request a plan revision, or submit an information command to Memory. Each target owns its own state and validates its request. Do not duplicate another owner's state or imply an atomic rollback across owners and external effects.

## Initial behavior and revision

Use deterministic checks for explicit, mechanically decidable constraints. When
the task needs interpretation of meaning, joint requirements or evidence, the
same operation may invoke the supplied infer dependency once. Curator authors
the mechanism; the running worker model supplies the judgment. A separate
judgment prompt belongs to Action's assets, not automatically to Memory or the
main system prompt. See [single-step inference](inference.md) for the typed
request, result and failure boundary. Do not replace a mandatory dispatch gate
with a voluntary model self-check, or infer success from a fluent explanation.

Translate supplied requirements into reachable checks and interactions, and verify actual refusals, corrections, replies and retained state. When feedback or additional information arrives, revise the identified rules while preserving still-valid constraints and progress. A mechanism that was not triggered is not automatically broken; compare its declared trigger with actual evidence.

Peer operations are awaited sequentially within one Harness's serialized strategy call chain. Calling back into an active owner or spawning concurrent peer calls from that chain is rejected explicitly. This keeps shared knowledge rollback and owner locking coherent; it does not serialize native tools or child Harness execution.
