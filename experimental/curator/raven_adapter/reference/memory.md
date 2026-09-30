# Memory strategy on Raven

Memory also supports code-owned candidate prepare through an optional keyword-only MemoryHost dependency. This precedes session initialization; see [candidate preparation](preparation.md). The observe flag selects the same class's _observe method. Optional intake/archive flags select its async _intake and _archive host methods, with actual lifecycle inputs from memory/contracts.py.

Generate memory.strategy with MemoryBinding. The factory receives session state and Task; optional keyword-only shared holds task-wide JSON knowledge, infer supplies a typed single-step judgment during an active turn, plan reads the current plan, and peers provides named cross-strategy operations. Do not store live Python objects in checkpoints. Read the supplied StrategyInference contract before choosing a model-backed operation; it shares one attempt with its sequential peer chain.

## Real input lifecycle

The adapter captures ContextSource from native SegmentBuilder outputs, including profile, identity, memory and Skills. A custom ContextEngine can provide context_sources(session_key). require_sources defaults to true; an opaque engine fails clearly rather than silently pretending its initial contents are editable.

After actual assembly and scope binding, initialize runs once for that active session owner. Its validated result reaches every compose call. The host composes at the final native model-request boundary, after tool selection and root delegation protection. A tool interaction can therefore affect the next request in the same turn. The loop transcript is not rewritten by this per-call projection.

Required source text and current user messages survive unchanged. Unknown runtime addenda are protected. Native sources retain their own formatting and lifecycle; do not assume every product has the same profile text. Token allowance and tool/result validation are host-owned.

## Commands and state

tool declares a name and description. Its schema is derived from the concrete command in InteractionRequest, exposed under request; scope, origin and request_id are host-created. requests enables peer interaction without a model tool. observe is a synchronous MemoryObservation-to-command translation and enters the same interact operation with observation provenance.

Session state and explicit shared task knowledge are saved separately. Repeated initialization preserves progress; revisions may explicitly migrate owned state. compose/compact are read-only, including peer-write prohibitions. Invalid results restore this owner's JSON mappings, not other owners' completed operations or external effects.

## Compaction

compact selects projection, proactive and/or overflow paths. Projection runs when compose exceeds the actual model-input allowance. Selected native pressure paths share Raven's compression retry count; proactive uses the native trigger ratio, while image and other provider recovery remain delegated. Before a first model call, a native pressure request can have capabilities=None; no future effective view is fabricated.

A failed or ineffective reduction is observable and is never reported as changed. If required content cannot fit, expose the failure. Verify actual provider inputs, retained state, source protection and native recovery, not merely method invocation.

A valid compose result that remains over allowance, including when projection compaction is not selected, produces a local context-pressure response at the model-input boundary. The native Loop then uses its existing overflow shrink and retry budget; the adapter does not start a separate retry loop or send the oversized request to the provider. This recovery is bounded and may still fail when required content cannot fit or generated content grows again. Invalid message pairing or protected-source changes remain contract errors and do not enter this recovery path.
