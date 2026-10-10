# Design one coherent change

## Objective

Turn the selected behavior and bindings into a concrete mechanism that implementation and host validation can assess.

## Inputs

Use selection, the current code and bindings, selected_contracts with the shared_knowledge they name, host facts and history. Each contract also lists references: documents and types read on demand with `read_source` by the `name` given, each with what it answers and when it matters. Design from what is supplied; open a reference or query a mechanism only when the plan depends on what it settles, and read the part that settles it. Initial selection is not proof that a path works. Reuse existing components whose behavior and state are compatible with the proposal.

## Work

For each proposed change, connect the caller or trigger to the semantic operation, available input, state access, result and actual consumer. State the expected difference from the current behavior and what must remain intact.

Specify the cooperation that matters for implementation: representation and concrete types, construction dependencies, one owner of shared rules/state, initialization, subsequent updates and state handoff when replacing code. Keep task state distinct from a turn-scoped wrapper. Private implementation details need not become new public methods or output fields.

When a requirement is expressed in how the work is carried out, specify what the mechanism reads to decide, what it stops or redirects, what the model is told so it can continue, and how the normal path still completes.

Check interaction conditions. A tool request and observed execution evidence may have different authority. A callback can only use information available at its phase. Returned guidance, requested control and the host's actual action have distinct meanings. Account for composition order, permitted budgets and failure behavior from the relevant contracts.

Define verification in terms of observations: what call or input should occur, what state or result should change, and what evidence would contradict the proposal. Include meaningful empty, repeated, rejected or failed operations when they affect the mechanism. A schema check alone cannot validate a behavioral claim.

When interpretation needs a model judgment, select the optional single-step infer
dependency instead of creating another agent loop. Specify its trigger, authored
judgment prompt, supplied evidence, concrete result type and actual consumer.
Explain insufficient-evidence and call-failure behavior separately. Check
worker.inference and the supplied contract: an operation and its peer chain
share an allowance of calls and time, several rules can be judged at once one
rule per judgment, and the call chooses its own output allowance and reasoning
effort up to the worker's own, from which a reasoning model also pays for its
reasoning. A deterministic rule remains sufficient when no semantic
interpretation is needed. Curator designs this mechanism; the worker model
performs the runtime judgment.

## Output

Submit one plan using the provided plan-submission action. Use understanding for the factual basis, diagnosis and any remaining nonblocking uncertainty. The person who gave the feedback reads it as your answer, so write it in the language of the task and its feedback and in their terms: what you understood and what the assistant will do differently, without target, strategy, file, tool or module names, which belong in design and changes. Use design for the concrete invocation path, semantic operations, essential types, explicit dependencies, state ownership and failure behavior. This must guide implementation without leaving the core mechanism to be invented there. For each changes entry, say in `treatment` whether it modifies the diagnosed mechanism, replaces it or adds one beside it, and connect reason, expected behavior and verification to its target. Cover exactly the current selection. Use state descriptions for resources whose ownership or lifetime the mechanism depends on. If the chosen entries are wrong or incomplete, revise selection first; the host will reopen design with the corresponding contracts. Report a gap if a critical unknown cannot be resolved.

Submit in `commitments` the changes this design makes to the Harness commitments, the standing list of what each strategy surface of the Harness does (`commitments` in the materials). A commitment is your own statement of one surface's behavior: in which situation, from what input, what it does and with what effect, and, for a model judgment, what happens when the judgment cannot be made. It serves the inputs it answers, named as in the diagnoses. Add what is new; modify what changes, with a new statement, a new surface or new serves (a reason alone keeps the commitment and revises its implementation); retire what no longer holds; leave the rest out, because omitted commitments stay. Every selected target needs a change on its surface, a change that asks for code needs its surface selected (a change of serves alone does not), and the grounds of each selected target are served by its commitments once the changes apply. Record behavior the host provides without authored code on the surface native when an authored commitment relies on it or could stop it. When a new or changed commitment can stop an action, read the commitments that carry out such actions and say in its statement which of those actions it could stop and what then happens to them.

## Completion check

Could an implementer follow the proposal without inventing an invocation path, essential type, state owner or permission? Can the host check the intended behavior? Resolve missing dependencies before submission; keep unverified benefits explicitly framed as expectations.
