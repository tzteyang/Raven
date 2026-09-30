# Diagnose each input against the current Harness

## Objective

Before anything is chosen, establish for every input of this curation where it stands against the Harness as it is: which mechanism is responsible, in what state, on what evidence, and how it was handled before.

## Inputs

`required_diagnoses` lists what must be diagnosed: each requirement by its id, each handed-over material as `material:<name>`, each requirement a parent Harness routed to this one as `node:<playbook>/<node>#<n>`, or `task` when there is none of these. Use feedback, observations, current_authored, history, the worker facts and source queries. Read the code involved; the name of a strategy or component is not its behavior.

## Work

1. For a requirement, locate the behavior in the current implementation and the host execution path, and read the cited turns' observations. Decide its state from the closed set: absent, not_exposed, not_triggered, not_consumed, wrong_logic, blocked, model_ignored, uncovered. Name the responsible mechanism when one exists and the evidence that establishes the state. A disappointing answer alone does not identify a mechanism; the absence of an observed event does not by itself prove the mechanism absent.
2. When history shows an earlier revision addressed the same requirement, say in `earlier` which round and change, and whether the behavior failed again afterwards. When a cultivation in `prior` met the same behavior, say which one and round, and how its treatment fared; it informs the treatment, not this worker's state.
3. For a handed-over material, say what it supplies as the kind it was handed over as (norm, fact, exemplar or counterexample), whether the Harness already exposes it, and in `placement` where its content lands and how the worker reads it.
4. For the task alone, at onboarding, diagnose what the task needs that the baseline does not provide.
5. Add a diagnosis for an earlier expectation that the observations show unmet, even when no requirement names it.

## Handoff

Submit once with the diagnosis action. Selection reads these diagnoses and must ground every chosen target on them; do not choose targets here. Report a gap when an input cannot be tied to a current behavior or to an explicitly missing capability.

## Completion check

Does every required input have a diagnosis with a state, evidence and, where a mechanism exists, its name? Would the evidence contradict a different state?
