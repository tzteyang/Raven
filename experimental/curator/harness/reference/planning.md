# Planning strategy: generation guide

Planning owns task organization, planning interactions and the published plan. Generate one class inheriting PlanningStrategy[ViewT, CommandT, ReplyT], plus its concrete data types and supporting resources. The public protocol is authoritative. Planning is the only planning Target; assets and host declarations take effect through its code.

## Initialization and projection

initialize(PlanningInitialization) creates or restores a session owner and returns PlanningProjection[ViewT]. Restored progress survives reconstruction. Factories bind dependencies and may explicitly migrate an owned representation. Initialization works during validation without live inference or initialized peers. Task text is the business mission; customer input arrives at runtime, separately from Curator construction instructions.

A projection contains view and optional guidance. Named subclasses with the same concrete ViewT and these public fields are accepted; the host normalizes the published envelope. Put domain extensions in ViewT, not extra projection fields. Views may be empty, partial, hierarchical or graph-shaped; no checklist schema is prescribed. Keep candidate alternatives distinguishable from the active plan. Store everything necessary to reconstruct the projection in owned state or explicit stable resources. Queries and private caches must not silently change the published plan.

The host publishes a projection only after a successful checkpoint. Other strategies read a detached committed view. guidance is this plan's contribution to model input; None withdraws it. Memory owns final message organization. Creating a plan or marking a step complete is not proof that external work succeeded.

## Information and planning interaction

interact(InteractionRequest[CommandT]) returns PlanningResult[ViewT, ReplyT]. Scope, request identity and agent/strategy/observation provenance come from the host. Tools expose business commands and query/command mode, not host identity. A model-supplied execution report remains a claim.

Queries may explain or propose alternatives, but cannot change retained state or the published projection. The same constraint follows peer requests. Commands may update goals, dependencies, progress or evidence, or legitimately do nothing. A normal refusal can record a blocker; business outcomes belong to ReplyT. Invalid requests and dependency failures remain errors rather than unchanged success or a fabricated negative verdict.

The business reply is delivered to tools and peers. The complete result, including its projection, is retained by the host. Deduplicate evidence using actual identity and session scope. Replanning changes future arrangements and preserves past execution facts. Failure restores this owner's state, not another owner's completed changes or an external action.

## Collaboration and execution boundaries

Capability registers the declared planning.interact tool and chooses available tools/Skills using the current plan. Internal collaboration uses peers.interact_planning and read_plan without impersonating Agent tool calls. Memory queries can be used under the common read-only constraint. Action owns runtime intervention; requesting a plan change does not itself retry the Loop or perform task actions.

prepare can publish reusable procedures and child requirements. Reusable Playbooks, session progress and actual delegation are different facts. The host supplies available children and execution authority; naming a child does not provision or invoke it. Existing native planning mechanisms must have explicit ownership or delegation rather than a second unsynchronized authority for the same progress.

Checklist tracking, incremental planning, plan-then-execute, hierarchical decomposition, stage transitions and replanning fit these operations. DAG concurrency, suspension and actual dispatch require host capabilities. Native DAGs cannot contain cycles. Multi-call search inside one interaction is outside the single-step inference allowance; cross-session concurrent plan sharing is not provided by session checkpoints.

Read the supplied binding and current implementation before choosing host paths. Helpers are an implementation choice; initialize has no mandatory private method sequence. The optional observation translator is a host binding, not an alternative state owner.
