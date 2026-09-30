# Implement the selected plan

## Objective

Produce the checked plan's executable strategy behavior and necessary resources, preserving the current task's useful implementation and state.

## Inputs

Read plan, selected_contracts and their knowledge in full. Use current_authored for all active values and file contents, not just the selected bindings; history retains earlier decisions, queries and checks, including failures and obsolete proposals. Use worker facts and registered queries for missing runtime conditions or baseline code.

The selected strategy contract determines its factory input, callable signature, result shape and lifetime. Host services can construct owned native components with different contracts. Do not transfer a strategy owner's construction or lifetime assumptions to a Participant, plugin, service or context engine.

A strategy's host service may accept a native component factory reference. Read the registered assembly topic and that factory/context contract before requesting it. This is an owned dependency, not another authoring target. Do not infer constructor arguments or resource handles from a reference string.

## Work

1. Trace affected code and dependencies. Identify active consumers of any shared file before replacing it. If the change would also alter an unselected behavior, preserve that behavior or revise the plan to include the required authorized target.
2. Implement the public operations or native component methods actually requested. Give concrete input/output types where consumers derive schemas. Implement necessary methods or explicitly reuse compatible baseline behavior; no unimplemented stubs in reachable paths.
3. Construct only the required dependencies. Strategies can delegate execution to tools or other components and use skills for guidance. Reuse a single implementation of each rule and one owner of mutable state. A knowledge resource you write carries only content the task, its materials or a registered source supply; prices, policies and similar business facts you would have to make up are a gap to report or a source to read at run time, never a plausible substitute.
4. Follow the declared state and checkpoint contract. Distinguish initialization from continuation, migration from reset, and valid no-change results from errors. Preserve progress when revising code. Factory construction, startup and cleanup each follow their own contract.
5. Handle valid absent observations and empty results according to the protocol. Validate a proposed state before replacing valid state. Keep failures and unavailable evidence visible; do not catch an implementation error and fabricate acceptance.
6. Check the actual interaction path and its limits: schema/argument agreement, registered implementations, native execution authorization, available callback inputs, result composition and the subsequent consumer.

Runtime values must satisfy their declared contracts after construction and mutation as well as at initialization. A model instance is not proof that its current nested values are valid. Exercise relevant callback branches with native input types and available recorded inputs; distinguish import/assembly checks from behavior checks. Derive positive and negative checks from the plan's verification intent. Follow the result through its actual consumer; a typed empty output can still have lost the evidence your design needs. Report missing behavioral coverage honestly.

## Artifact and merge rules

Return exactly the plan's strategy bindings and supporting code/assets. Binding updates preserve omitted fields and files. Strategy prepare defines the complete owned resource and native setup effects for the resulting implementation. Retire a strategy through remove; retire obsolete supporting files through remove_files. Assets never activate independently.

Write each supporting file with the file-staging action, one complete file per call, before you check or submit; staged files join the artifact automatically, so the artifact itself then only needs the target values. A value that references module:attribute needs that module among the staged files, the artifact's files or the current authored files.

Source files form an isolated package. Use package-relative imports between supplied files and normal imports for installed dependencies. References must resolve to the object kind required by the selected binding: callable strategy factories for construction, and Prompt objects explicitly indexed and consumed by their owning strategy. Provide complete content for every file you update, including dependencies needed by retained callers; do not submit patch instructions as source code.

Resource formats, factory parameters and result types come from selected_contracts. Do not copy a redacted configuration value, duplicate an interface schema in another file, or assume a loaded skill has reached model input.

## Output

Submit the artifact through the provided artifact action. If the mechanism needs revision, request plan revision with a concrete reason; the host returns to design. If the required entries change, revise selection; that also requires a new design. Do not implement against a superseded plan. If required support or information cannot be obtained, report the concrete gap.

## Completion check

Every selected value has its required implementation or resource; references resolve; concrete types match callers and results; shared state and retained consumers remain coherent; meaningful failures stay observable. Describe only a proposal, without claiming installation or task improvement before host evidence arrives.


## Revising selection

The artifact schema contains only targets selected in the current plan. available_targets also lists the
other host-granted strategy choices. If an implementation needs another strategy owner (for example Capability to prepare new Skills), revise selection first and complete the new design. A supporting Prompt belongs to its consuming strategy and does not need a separate target.
Do not add an unselected value to the artifact or omit required resource admission to fit the current schema.
