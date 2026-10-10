# Memory strategy: generation guide

Memory owns initial context organization, information interactions and the projection supplied to each actual model call. Use the supplied MemoryStrategy, InitialContext, InteractionRequest, ContextRequest, ContextView and CompactionRequest definitions.

## Initialization and projection

initialize receives actual baseline sources, messages, history, host identity and a restored-state flag. Its concrete result is delivered to compose as initialization. Establish an organization or policy that compose actually uses; a ready flag alone does not establish context assembly. Preserve existing progress. Factories bind dependencies and may explicitly migrate their own state.

compose receives current sources and messages plus the actual effective capability view. Source formatting is baseline-specific; use source identity, role and ownership rather than parsing a presumed profile layout. Preserve required source text, required message mappings, the current turn's user messages and tool/result pairing. ContextView is a detached projection, not an archive rewrite. compose and compact cannot write retained state or request peer writes.

compact handles only the pressure paths selected by the binding. It must reduce the input and respect its allowance and required content. It does not own image recovery, provider retries or Loop scheduling. Missing compaction support is not a successful reduction.

## Information interaction

interact receives a concrete domain command inside a host-created InteractionRequest. Define the command vocabulary and replies needed by the task; retrieval, recording and correction can use the same operation. The input's origin distinguishes agent claims, explicit peer requests and host observations. Neither a stored claim nor a receipt proves an external action succeeded.

Successful information changes use the same session owner that composes the next input. Optional shared task knowledge is separate from session working state. Deduplicate evidence using its actual identity and scope; a tool-call identifier alone need not be unique across the entire historical archive. Query mode preserves both session and shared state and propagates through peers. A nested command cannot relax it. Valid no-ops, refusals and errors remain distinct.

## Collaboration and authoring value

Use StrategyPeers for other owners' public operations or detached views. Do not copy a plan or capability registry. A failure in this owner does not roll back another owner's successful operation.

For first customization, connect supplied material to the initialization result, interaction behavior and real model input. For a revision, identify what changes, what information remains, and how old content leaves the current projection. Ordinary memory interaction cannot install or rewrite persistent Skills; Curator decides those resource changes.
