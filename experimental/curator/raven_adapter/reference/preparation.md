# Code-owned candidate preparation

Raven exposes exactly four authoring targets: memory.strategy, planning.strategy,
capability.strategy and action.strategy. Each names a generated strategy factory.
Artifact.files contains supporting code and assets. Assets do not install or
activate themselves. Retained strategies keep their implementations; a change
does not require rewriting all four classes.

## Lifecycle and dependencies

Every public strategy supports synchronous prepare(PreparationRequest) -> None.
The default leaves native setup unchanged. The host invokes it on a candidate
owner before constructing the native runtime, then closes all setup services.
The factory constructs an inert object. Preparation cannot mutate its session
checkpoint, start services, call tools or perform model inference. The Curator
has already authored the implementation and its text assets.

The request supplies task identity, candidate identity, complete text assets and
material roots. Read a supplied text through request.assets[path]. A factory may
request a keyword-only host dependency: MemoryHost, PlanningHost, CapabilityHost
or ActionHost according to its strategy. Import host policy types from
experimental.curator.raven_adapter.preparation. The exact policy field schemas
are in worker.preparation_contracts.policies; query the relevant role before
configuring it. Native defaults are preserved for fields not supplied.

Session owners are constructed separately with restored checkpoints. Private
attributes written during prepare are not transferred to those instances.
Runtime selection reads actual installed capabilities. Model input initialization
receives actual context sources. Domain progress belongs to the existing public
runtime operations and their owned checkpoint.

## Role-owned setup

Choose an owner from the intended behavior before choosing a storage format.
An expert package can contain identity, reusable methods, task workflow and
execution constraints in the same document. Memory organizes identity and facts;
Capability adopts reusable Skills and tools; Planning owns progress and procedure
structure; Action owns checks with actual execution consumers. Existing native
behavior may satisfy a requirement without a new override. Record the relevant
source requirement, its consumer and any unsupported dependency in the design.

Keep the concrete signature def prepare(self, request: PreparationRequest) -> None when overriding setup. An owner with no setup can inherit the default; an unannotated no-op override is not needed.

Preparation is not the running session: factory -> candidate prepare -> native
construction/installation -> session initialization -> model calls and events.
Checks and restart repeat preparation. A revised owner describes its full desired
effects, while an omitted strategy update keeps that owner's code. Do not use a
prepare instance's private attributes as the handoff to a session instance.

- MemoryHost.context(ContextPolicy), window(WindowPolicy), tokens(TokenPolicy)
  and backend(BackendPolicy) expose distinct native policies. profile(files)
  owns native bootstrap paths listed in worker.preparation_contracts.profile_paths.
  engine(factory) selects a ContextEngine delegate. backend_factory(name, factory)
  and session_observer(name, factory) request native dependencies with their actual
  lifecycle. Identity, credentials and arbitrary file roots are not profile data.
- PlanningHost.playbook(PlaybookSpec, requirements) compiles a complete native
  procedure. Requirements map actual node IDs to nonempty Requirement lists.
  The parent graph is inspectable before child generation. A leaf cannot add
  delegation. A procedure is distinct from a session's current planning view.
- CapabilityHost.tools(ToolPolicy), skills(SkillPolicy), pin_skills(names),
  mcp(name, MCPServerConfig) and plugin(name, enabled=...) configure approved
  native capability mechanisms. They do not replace Capability.register.
  Unknown plugin roots and enabling host-disabled plugins are unsupported.
  A requested MCP connector must actually connect before activation succeeds.
- ActionHost.generation(GenerationPolicy) and execution(ExecutionPolicy) apply
  native sampling and loop policies before provider and budget construction.
  Context/window settings belong to Memory. Native user grants remain in force.
- Every role's host provides service(name, factory) for a native resident
  dependency and prompt(reference) to validate/index an authored Prompt object.
  A prompt still needs a consumer in strategy code; indexing never injects it.

The generated strategy owns these choices and invokes the relevant service from
prepare. The adapter validates and applies the resulting effects. There is no
parallel profile, configuration, plugin, Skill or Playbook submission target.

## Protected extension points

Capability.prepare calls _prepare_tools(request) and _prepare_skills(request),
then submits their contributions through register. Both producers default to
empty tuples. Override the necessary producer or provide another prepare
algorithm. Tool factories are inert; native_context=True defers construction
until PluginContext is available. Accepted resources still use ToolRegistry.

Planning publishes view/guidance from initialize and interact. Its binding can
select before_model and after_iteration for _observe(view, PlanningObservation).
Memory can enable _observe(MemoryObservation) to translate actual evidence into
an interact command. These synchronous translations do not mutate state and are
resolved on the current owner, not captured from a different session instance.

Memory's optional async _intake(MemoryInput) -> str | None operates before context
initialization. It returns derived model-facing input; Raven retains the raw
input. Optional async _archive(MemoryArchive) -> dict[str, JsonValue] | None
annotates the native turn record. Neither method controls execution. Their
actual availability depends on the inbound origin. Resident session retirement
uses the native nonblocking observer contract, not a fabricated active turn.

Action.handle_event has a default dispatcher to optional _handle_input,
_handle_progress, _handle_proposal, _handle_outcome, _handle_failure and
_handle_control methods. Implement the selected rules or override handle_event.
An enabled policy needs a real handler. Unchanged branches continue by default.
GenerationOverrides is available only on revise and cannot exceed the already
reserved output allowance. Control receipts distinguish requests from effects.

## Resources, updates and recovery

Adopt a SkillPackage by inspected root and exact digest, or generate a complete
SkillContribution.files map. Complete packages preserve binary files, nested
resources, empty directories and modes. The host retains adopted inputs in an
immutable cache so validation and restart do not depend on a temporary upload.
Prepared parent Skills can be staged as complete child inputs; the child Curator
must still adopt them through its own code.

The next prepare result defines the revised strategy's complete owned resource
set. Omit a strategy update to retain its code; remove the strategy to withdraw
its effects. Artifact.remove_files explicitly deletes obsolete supporting assets.
Removing an asset still used by retained code fails validation.

Native content has a host-owned file ledger. Withdrawal restores prior content;
unchanged requests relinquish outside edits, and revised requests cannot overwrite
them. Failed activation restores files, ledgers and flushed checkpoints. These
rules do not claim to undo already executed external actions.

The initially granted workspace Skill library is pinned for the deployment.
Later worker writes remain material files and do not become active Skills merely
because a process restarts. Managed adopted Skill versions receive native read
access, including when confinement comes only from restrict_to_workspace.
