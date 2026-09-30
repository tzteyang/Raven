# Authority and implementation rules

## Sources of authority

The effective declaration and submission schemas define the selectable targets, writable fields, phases and payloads. Public protocols define operation semantics; host binding contracts explain how those semantics are executed here. Required knowledge attached to a target is part of the material needed to implement it.

The host-supplied target descriptions and selected contracts in the task materials are binding specifications under these rules. A broad interface description cannot override a narrower effective grant or submission schema. Task text, feedback, reference passages and previous code cannot amend host authority.

The host owns task identity, available deployment baselines, grants, validation, installation and execution. Do not expand those grants, replace child registrations, introduce unsupported child baselines or patch host internals. Within the supplied root scope, the generated Planning strategy may organize or revise native playbooks and child requirements. Availability of a definition or factory is not evidence of registration, reachability or execution permission.

## State and composition

Derive each object's construction and lifetime from its own contract. A native Participant wrapper, a public strategy and the task state it uses can have different lifetimes. Follow the supplied checkpoint or persistence contract when one exists; do not assume that private attributes or module globals survive reconstruction.

Preserve the initial task binding and existing progress. Distinguish initializing a task, continuing it, updating its business state and replacing its Harness implementation. A runtime plan update does not itself require code generation.

Use one owner for a behavior rule or mutable state. Other components call or delegate to it. Make required initialization, sharing, cleanup and revision handoff explicit. A requested effect must have a real consumer, at a time when the necessary input exists.

## Code and resource discipline

Generated implementations selected through `memory.strategy`, `planning.strategy`, `capability.strategy` or `action.strategy` must explicitly inherit the corresponding public `MemoryStrategy`, `PlanningStrategy`, `CapabilityStrategy` or `ActionStrategy` from `experimental.curator.harness.strategies`, directly or through an implementation base. Use concrete type arguments and method annotations. The factory must return an instance of that class; matching method names alone is insufficient. This applies equally to root and child Harnesses and to revisions of existing code. Tools, resources and helpers are owned dependencies of these implementations. They are not parallel authoring targets. They need not inherit a strategy protocol; the owning class explicitly prepares or calls them. A strategy may reuse a public implementation with protected extension points when their actual call chain satisfies the required semantics.

Use the necessary semantic structure and ordinary functions, types and factories. Add a field or abstraction only when an identified producer and consumer need it. Preserve unmodified behavior; inspect other active bindings before changing a shared file.

Follow the selected result contract, including valid empty or no-change results. Do not turn missing implementations, unsupported operations or failed dependencies into silent success. Do not treat a legal empty result as a request to call a previous implementation.

Generated Python and technical comments use English; user-facing content follows the task's language. Credentials and resource authority stay in existing host facilities. Redaction markers are descriptions, not values to copy into configuration.

## Execution contract completeness

For every selected interaction, establish its caller and phase, actual input representation including nested values, state ownership, output consumer and failure behavior. Read the supplied definitions; an opaque annotation is not permission to guess from a familiar API shape. When these facts are still missing, use source queries or report the gap before implementing that path. Keep native runtime objects, serialized observations and stored message formats distinct.

Planning code owns initialize/interact and publishes a concrete plan projection with separate business replies. It may keep partial plans, candidates, dependencies and blockers. Use the supplied query/command and provenance contracts; do not generate the retired view/revise protocol. Planning tools pass through Capability registration, and before-model observation must precede capability selection when current input affects the plan.
