# Understand the current task and Harness

## Objective

Identify the task outcome, relevant current behavior and the mechanism-level gap, if any. Establish enough factual context to diagnose every input; choosing a change comes after this attribution.

## Inputs

Use task and worker facts, current_authored, orientation, available target knowledge, the previous plan, feedback and execution observations. When feedback carries `history`, it lists for every earlier round whether each evaluator was satisfied, the requirements raised with their strength and, once the next round was judged, whether each held, your diagnoses of them, what the mechanisms did, and the revision made after it with the inputs each change addressed. When feedback carries `prior`, it lists earlier cultivations of this job the owner brought, each with its rounds in the same form as `history`. They are experience from another worker under another Harness: use them to recognise a behavior or a treatment that failed or held before, but diagnose this worker from its own code and observations. Read the existing code involved in a reported problem; the name of a strategy or component is not its behavior.

## Work

1. Extract the user's outcome and constraints. Separate a new task requirement, an evaluation of an earlier result and an ordinary request to continue.
2. Locate the behavior in the current implementation and host execution path. Distinguish an absent ability from an existing ability that was not exposed, used, correctly implemented or allowed to run.
3. Check what the evidence actually establishes. A disappointing answer alone may not identify the faulty mechanism; absence of an observed event does not by itself prove the mechanism is absent.
4. Identify the information needed to resolve material ambiguity. Read the relevant mechanism topic or current fact, and use the supplied native tools to discover implementation dependencies in the source snapshot. Check the input and state available at the relevant moment.
5. For each requirement, establish how it was handled before: use `history` and the current code to find which earlier revision addressed it, whether as information the model reads or in how the work is carried out, and whether the behavior failed again afterwards.
6. Establish whether the current implementation already handles an input adequately, so its diagnosis says so with the evidence; whether to change anything is decided after this attribution.

## Handoff

Carry the task interpretation, observed gap and relevant baseline behavior into the diagnoses of the diagnose stage, and any material uncertainty into their `uncertain`; selection and design read them from there. This stage does not execute the user's task.

## Completion check

Can the proposed problem be tied to a current behavior or an explicitly missing capability? Are its factual basis and any remaining uncertainty distinguishable? If not, obtain the missing information or report the specific unresolved gap.
