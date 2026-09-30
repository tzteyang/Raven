# Strategy behavior, prompt resources and model calls

## Operations and consumers

Memory initializes context organization, handles typed information interaction, composes each actual input and optionally compacts declared pressure paths. Planning initializes session state and handles typed interactions, publishing a committed view and optional guidance. Query mode preserves state and projection; business replies are separate. Capability registers candidate resources and selects active capabilities. Action handles typed host events and agent/peer requests. Each operation has concrete inputs, state ownership and an actual consumer.

These contracts do not prescribe a private method chain or one model call per operation. Deterministic implementations are valid. Independent lifecycle operations should be added only when a real caller needs them.

## Three prompt paths

1. Worker guidance: Memory projections, Capability skill/guidance delivery, Planning context and Action guidance enter the normal worker model request. Action revision feedback enters through native rollback injection. Diagnostic reasons alone are not injected.
2. Agent interaction: actual Skills and registered tools expose the authored protocols. Memory.interact, Action.handle_request and the existing Planning tool resolve the same live owners used elsewhere. Capability registration is candidate-scoped and does not hot-install resources inside a turn.
3. Single-step inference: a factory may request keyword-only infer. It accepts instruction, JSON data and a concrete output_type; the host returns a strictly validated result from one worker-model attempt. The strategy owns the judgment prompt and result consumer. Read the supplied StrategyInference contract and [inference guide](inference.md), and inspect worker.inference for actual limits. This is not a tool-capable Agent loop. Translations remain synchronous; credentials and invocation identity stay host-owned.

## Prompt organization

Use Prompt when a reusable template is useful. UTF-8 templates live in Artifact.files and load relative to the declaring module. The owning strategy may index its module:symbol reference through host.prompt during prepare. Prompt.render validates a concrete input model and substitutes named variables once; strategy code chooses its actual consumer.

Separate stable instructions from current user data, evidence and state. Memory.initialize can establish an organization while compose uses current source content, effective capabilities and working state. Do not freeze current questions, directories, model bindings or Skill selections in an initial prompt.

Do not force a model dependency, a prompt field or a fixed profile layout on every strategy. The adapter owns host timing and constraints; the strategy owns domain rules and interpretation.

## Cooperation and evidence

StrategyPeers supplies narrow reads and requests to existing owners. Optional shared Memory knowledge has explicit task scope; ordinary working state has session scope. Read-only projection cannot modify a peer. Cyclic awaited calls are refused. Record partial success honestly rather than assuming a cross-strategy transaction.

For both initial customization and later revision, connect supplied information to real installed behavior and verify the actual result. A resource list, a returned decision, or an untriggered mechanism does not by itself establish success or failure.

Runtime methods need concrete input and return annotations so the host can validate generated data. Missing annotations produce an operation-specific authoring error. Preserve the synchronous PreparationRequest -> None signature for prepare; inherit it when no setup is needed.
