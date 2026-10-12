# Diagnose each input against the current Harness

## Objective

Before anything is chosen, establish for every input of this curation where it stands against the Harness as it is: which mechanism is responsible, in what state, on what evidence, and how it was handled before.

## Inputs

`required_diagnoses` lists what must be diagnosed: each requirement by its id, each handed-over material as `material:<name>`, each requirement a parent Harness routed to this one as `node:<playbook>/<node>#<n>`, or `task` when there is none of these. Use feedback, observations, current_authored, history, the worker facts and source queries. Read the code involved; the name of a strategy or component is not its behavior.

## Work

1. For a requirement, locate the behavior in the current implementation and the host execution path, and read the cited turns' observations. Use the state definitions in the diagnosis submission schema. Choose adequate when the evidence shows that the current mechanism already handles this input adequately, and identify that mechanism and evidence; a correct existing behavior does not need an invented fault. For a problem, choose the state its evidence establishes. A disappointing answer alone does not identify a mechanism; the absence of an observed event does not by itself prove the mechanism absent or adequate. Record uncertainty when the evidence is incomplete. Name the responsible mechanism when one exists, with the id of the commitment in `commitments` it carries out when one does. When a mechanism intervened on a cited turn, refusing, rewriting or rolling back what the model did, and the failure is what the model did next, the intervention is part of the cause: read why it intervened, and when it stopped an action the requirement wants, name it with the state wrong_logic, however many violations it caught elsewhere.
2. When history shows an earlier revision addressed the same requirement, say in `earlier` which round and change, and whether the behavior failed again afterwards. When a cultivation in `prior` met the same behavior, say which one and round, and how its treatment fared; it informs the treatment, not this worker's state.
3. For a handed-over material, say what it supplies as the kind it was handed over as (norm, fact, exemplar or counterexample), whether the Harness already exposes it, and in `placement` where its content lands and how the worker reads it.
4. For the task alone, at onboarding, diagnose what the task needs that the baseline does not provide.
5. Add a diagnosis for an earlier expectation that the observations show unmet, even when no requirement names it.

## Handoff

Submit once with the diagnosis action. Selection reads these diagnoses and must ground every chosen target on them; do not choose targets here. Report a gap when an input cannot be tied to a current behavior or to an explicitly missing capability.

## Completion check

Does every required input have a diagnosis with a state, evidence and, where a mechanism exists, its name? Would the evidence contradict a different state?

Before diagnosing, read all available replies and delivered files, including uncited successful turns. A later failure on a different input does not establish that the previous revision caused it. Separate observed effects from causal hypotheses.
