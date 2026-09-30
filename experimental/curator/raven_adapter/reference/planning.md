# Planning strategy: Raven binding

This adapter binds the host-independent PlanningStrategy through planning.strategy. Consult its public protocol, PlanningInitialization, PlanningProjection, PlanningResult, InteractionRequest and PlanningBinding schemas together.

## Factory and session state

A Task is required. The factory create(state) returns an inert instance explicitly inheriting PlanningStrategy[ViewT, CommandT, ReplyT]. Keyword-only host, peers, infer and plan dependencies are optional. plan reads this session's detached committed view, or None before initialization; it never exposes the current operation's uncommitted state. State is one mutable JSON checkpoint per conversation, preserved across turns and Harness revisions. Factories may explicitly migrate representations. Session identity is host-owned and cannot be changed by task text or model arguments.

Each newly constructed session owner runs initialize, including a restored owner. Its restored flag means previous state exists, not that this process has initialized the owner. Initialization must preserve restored state and reconstruct the projection without model inference or ready peers. The host initializes at the shared worker/ACP turn boundary and before direct native planning use.

Initialization and result projection annotations must have the same concrete ViewT and the public view/guidance fields. A named projection subclass is valid; the host normalizes the envelope before publication and query comparison. Successful commands checkpoint before publishing a detached projection. Queries must preserve both state and the existing projection. Invalid results and errors restore owned state and retain the last published projection. The next use reinitializes a reconstructed owner. Cross-owner effects commit independently. The host validates mechanics, not the semantic truth of a generated projection.

## Optional interaction paths

- tool declares an InteractionTool name and description. The adapter derives its concrete command schema, exposes request plus query/command mode, and contributes owner=planning, interaction=planning.interact through Capability.register. Tools return only result.reply. Registration does not bypass native authorization.
- requests enables peer interactions without requiring a model-facing tool. An enabled tool also admits peers. peers.interact_planning validates the same command type and returns the business reply; read_plan returns the latest detached committed view or None before initialization.
- context supplies committed projection.guidance as a native system addendum. The native hook removes its previous contribution before the next call, including when the replacement is None. No _render_context method is required. A generated implementation may use its own private formatting helper.
- observe selects before_model and/or after_iteration. The same owner's synchronous _observe(view: ViewT, observation: PlanningObservation) returns CommandT or None. This translation must not mutate state. A command enters interact with observation provenance. Read actual tool results and IDs, preserving their untrusted-data boundary; response is a proposal, not an execution receipt.

Before-model synchronization runs in the adapter hook before native participant capability selection. It can incorporate the first customer input, not just the long-lived expert mission. Capability therefore sees the committed current plan. Before-model observations carry offered tool schemas, not a promise that they will remain visible or executable. Effective capability feedback is consumed by subsequent interactions; Planning and Capability do not recursively select each other.

Planning callback failure stops the current native path with an explicit failure rather than letting native callback isolation treat a required update as no opinion. Observations can repeat during recovery; preserve their event identity and make evidence updates idempotent. No callback adds another model loop. Optional infer uses the existing one-attempt operation-chain allowance.

Query constraints propagate through Memory/Planning peers, including a nested call that asks for command mode. The receiving owner validates its own retained state. Action requests that can apply controls remain forbidden in a read-only operation. Cyclic owner calls and parallel children within a single ownership chain are rejected.

## Candidate delivery and evidence

Planning.prepare may call PlanningHost.playbook with PlaybookSpec and node-to-Requirement mappings. Their exact schemas are in worker.preparation_contracts.policies.planning. The host inspects the parent procedure before selecting child customization. Existing nodes without requirements can still run; requirements do not themselves invoke children. Root Curator supplies behavior goals and child Curator authors its implementation.

Submit the factory, selected binding paths and supporting files. New tools and complete Skill packages are owned by Capability code; there are no independent resource/configuration Targets. See [candidate preparation](preparation.md) and [composition](composition.md).

Inspection includes published view/projection, checkpoint sessions, command/reply schemas and bindings. Execution records distinguish initialize/interact, observations, published projections, model context and peer calls. Verify actual provider inputs and delegated work; a valid schema or generated graph does not establish planning quality or task completion.
