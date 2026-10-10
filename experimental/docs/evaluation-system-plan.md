# Evaluation system implementation plan

Status: implemented and verified, 2026-10-08. Contract: [evaluation-system-design.md](evaluation-system-design.md).
The subsequent hierarchical rubric extension is implemented; its requirements and acceptance evidence are in
[hierarchical-rubric-design.md](hierarchical-rubric-design.md).
Work on `feat/self_improving_evaluation`, based on the user-confirmed current state of
`feat/expert_information_collection`. Preserve the original worktree. Do not commit or push without a user request.

## Baseline

- [x] Read repository instructions and domain vocabulary.
- [x] Confirm the base with the user and create a separate feature branch before implementation.
- [x] Copy the existing functional state into the independent worktree; retain a manifest outside git to distinguish
  inherited, uncommitted changes from this feature. At the user's request, the earlier role rename was precisely
  withdrawn from the original worktree; this branch retains it. Subsequent feature work stays in this worktree.
- [x] Consolidate the role, rubric, authority, evidence, meta-review and learning contracts before coding.
- [x] Update the editable design Page with the final memory design and implementation sequence.

The inherited implementation has RubricBuilder and Assessor, model role routing, revision records and WebUI display.
It lacks independent model gates, program checks, meta-review, adopted construction guidance and a promotion boundary.
Its `satisfied` aggregation ignores unknown hard criteria; fix this rather than preserving an optimistic result.

## Delivery steps

### P1 Rubric semantics and protected requirements

- [x] Extend Criterion and construction output with gate/guardrail/quality roles and check descriptions.
- [x] Let the Builder derive criteria from the task as well as supplied norms, including explained inferences.
- [x] Allow model-generated hard gates; retain and protect explicit external requirements and confirmations.
- [x] Preserve original authority and provenance through Signal, Analyst requirements and historical sedimentation.
- [x] Aggregate hard criteria conservatively, with explicit inapplicability distinct from missing evidence.
- [x] Update existing fixtures and add behavioral tests for external override, model-only gating, unknowns and attempts
  to erase/downgrade a protected requirement.

### P2 Evidence execution and bounded meta-review

- [x] Add the small check executor in `assessor/checks.py`; combine LLM and deterministic results with evidence.
- [x] Validate generated program checks on known outcomes and bound their evidence access and runtime.
- [x] Implement `MetaReviewer` and its prompt in `assessor/reviewer.py`; one review and one repair attempt per cycle.
- [x] Route evaluation defects to evaluation repair and verified worker gaps to the existing Analyst/Curator path.
- [x] Save complete before/after assessment evidence, including errors and unresolved issues.
- [x] Test a superficial criterion, an adversarial defect, a legitimate alternative, unavailable evidence and a
  broken checker. Verify that model consensus cannot override a deterministic failure.

### P3 Experience consolidation and independent adoption

- [x] Keep episodes in existing evaluation records; implement a local guidance store with principles/procedures,
  scope, evidence references and candidate/active/retired versions in `assessor/guidance.py`.
- [x] Add host-owned replay validation in `assessor/validation.py`, binding receipts to candidates and fixed inputs.
- [x] Actually compare old/new construction methods before adopting guidance; require independently grounded labels,
  an improvement, no protected regressions, and an unused task for cross-task claims.
- [x] Render bounded applicable active guidance into Builder instructions; persist adoption, rejection and rollback.
- [x] Distinguish experimental harness installation from stable promotion in Session using independent evidence.
- [x] Test no-evidence candidacy, false-alarm regressions, stale receipts, protected external requirements, restart
  persistence and a complete example-to-principle/procedure-to-next-rubric cycle; review the bounded selection
  and instruction-size limits.

### P4 Integrate, demonstrate and review

- [x] Wire task inputs, checks, Meta Reviewer, guidance and validation through simulation and WebUI session hosts;
  register `meta_reviewer` only when there is a real implementation. No standalone evaluation service.
- [x] Display criterion type/authority, check evidence, review corrections, guidance adoption and promotion state
  beside the existing evaluation record. Keep existing saved records readable without rewriting their evidence.
- [x] Add an end-to-end test of task/material -> generated rubric -> failure signal -> Analyst requirement -> Curator
  attribution/change -> changed worker output -> independent verification, with no external per-round grading.
- [x] Add external feedback to the same example and prove it remains the highest applicable requirement later.
- [x] Demonstrate that learned construction guidance changes a subsequent rubric and reduces an independently
  confirmed evaluation error. Preserve a valid alternative and a protected regression case.
- [x] Review the final implementation separately against every design invariant, not only the passing tests.
- [x] Update CONTEXT, README, the design Page and this plan with exact validation evidence and remaining limits.

## Verification and completion audit

Use `uv run pytest` for Python checks. Run affected evaluator, Analyst, Session, simulation and WebUI tests; then
the experimental suite if cross-module integration changes justify it. Run frontend tests and TypeScript checking
when record/display contracts change. Run Ruff and the source-language/large-file gates, including untracked files.
Do not claim a real-model run from a scripted-provider test; record separately whether a configured LLM was exercised.

Completion requires evidence for every P1-P4 checkbox and these invariants: model-only gates work; external requirements
cannot be weakened; unknown is never pass; program evidence cannot be voted away; meta-review is bounded; learned
instructions are actually consumed; validation is independent and version-bound; hidden evaluation data remains
hidden; and the closed loop produces an observable, verified harness improvement. A checklist or stored receipt alone
does not prove these behaviors. All listed implementation requirements have been checked; the empirical limits below still apply.

## Initial implementation verification

| Check | Result |
| --- | --- |
| Experimental Python unit and module integration suite, 67 modules importing experimental code | 802 passed |
| Native Curator/Worker loop and bounded checker subprocesses | 8 passed |
| Authorized real-LLM boundary simulation | 1 skipped because SIMULATION_TEST_CONFIG was not supplied |
| WebUI TypeScript checking and production build | Passed |
| WebUI tests | 151 passed across 14 files |
| Ruff check and formatting, all 35 changed Python files | Passed |
| Source-language gate, large-file gate and diff whitespace | Passed |

Commands used:

```bash
# The module list contains tests/test_*.py files importing experimental modules.
xargs -a /tmp/raven_evaluation_baseline_tltjubgo/experimental_tests.txt \
  uv run --frozen --python 3.12 --extra dev pytest -x -q
uv run --frozen --python 3.12 --extra dev pytest -m integration \
  tests/integration/test_evaluation_curator_e2e.py \
  tests/integration/test_assessor_checks_real_subprocess.py \
  tests/integration/test_iteration_boundaries_e2e.py -x -q -n 0
# In experimental/webui:
npm run build
npm test -- --reporter=dot
# In the repository root:
make check-large-files COMMIT_RANGE=HEAD
make check-source-language COMMIT_RANGE=HEAD
git diff --check
```

The unit-suite list can be regenerated with
`rg -l 'from experimental\.|import experimental\.' tests/test_*.py`.
Four existing WebUI dependency/setup files excluded by the shared local Git ignore configuration were copied into
this independent worktree to make its frontend self-contained; the source worktree was read only.

## Review against the design contract

| Invariant | Inspectable evidence |
| --- | --- |
| Model-only gates can trigger useful curation | `test_evaluation_curator_e2e.py` runs the real Session, Analyst, attribution, Curator installation and native Worker; installed context changes the observed quote |
| External conditions outrank model interpretation | Explicit quoted conditions are retained and rechecked; builder/Analyst tests reject unauthorized rewrites; the native loop retains a later external condition through restore |
| Unknown never means pass | Missing deliverables, broken programs, undecidable gates, unresolved review and missing dataset cases remain unknown; even a permissive dataset threshold cannot pass a missing case |
| A model repair cannot erase program failure | Reviewer tests attempt a model-only repair and a failed reassessment; both retain the observed failure |
| Experience changes actual construction | Guidance tests compare old/new Builder requests against independently labeled positive and negative outputs, persist the receipts, activate guidance, and inspect its use in a later request |
| Guidance stays scoped and independently validated | Task-local candidates require that task's evidence; cross-task guidance requires unused inputs from another task; changing execution ids cannot reset exposure; false-alarm regression, stale writes and stale receipts are refused |
| Hidden checks do not reach Curator | Compartment tests plus the native integration test inspect Curator requests; held-out task input and rubric ids are absent |
| Promotion is separate from experimentation | Independent failures reject; unavailable evidence and external rejection block; advisory reflection alone does not block; resumed active runs require fresh verification while retaining the historical stable reference |
| Records survive restart and remain readable | Assessor/Builder/MetaReviewer restoration tests, retained source episodes, legacy record parser tests and WebUI component tests |

The distinct review pass found and fixed mandatory-gate removal on missing evidence, loss of deterministic failures
during meta repair, external rejection being missed by promotion, advisory self-reflection accidentally blocking all
promotion, reuse of training inputs as holdout, task-scope mismatch during guidance validation, and stale shared-store
writes. No known failing check remains.

## Operational limits

These tests use scripted model responses; the Worker, artifact installation, subprocess restrictions and independent
replay execute for real. The evidence proves the implemented path and invariants, not general model accuracy,
generalization, or a measured productivity gain for arbitrary tasks. The paid real-model scenario was not exercised.

A run without independently grounded positive and negative examples keeps construction guidance pending. Live
sessions can deliberately reuse a prior corpus; they do not derive independent labels from adaptive self-evaluation.
Program checks need a host verifier or independent calibration; the built-in checks establish reply/file availability
only. Conflicting external conditions require explicit scope correction, and promotion records a verified revision
without automatically deploying it. Keep shared evaluation memory outside worker-accessible paths.

No commit or push was made. The implementation, including the agreed role names, remains in the feature worktree.

## Semantic contract refinement

Status: implemented and verified, following the user's approval of a minimal semantic representation. Keep the existing feature
worktree and all original-worktree isolation guarantees. No ontology service, claim graph, generic theorem prover,
confidence scores or duplicated executable rubric.

| Field or structure | Required consumer and value |
| --- | --- |
| Criterion.definition.subject | Builder, Assessor and Meta Reviewer share the object being evaluated |
| definition.applies_when | Distinguishes applicability from missing evidence; missing required output is not inapplicability |
| definition.acceptance | One normative statement replaces overlapping text/acceptance definitions |
| Criterion.basis | Source references, supporting quotations and host-bound content versions support grounding and stale-source detection |
| Criterion.origin | Retains declared/derived/sedimented filtering without confusing origin with evidence authority |
| Criterion.kind | Derives strength; gate/guardrail failures cannot be canceled by quality |
| assessment.evidence_requirements | Host checks access to required observations; Reviewer audits their relevance |
| assessment.decision | Explicitly identifies the whole-criterion judgment; absent qualification yields unknown |
| assessment.required_checks | Local necessary checks may refute; passing these alone cannot establish the whole criterion |
| Typed LLM/program check | Distinguishes instructions, verifier references and expressions without parsing an overloaded spec string |

- [x] Replace the canonical schema and update every live producer/consumer; retain old record display without
  inventing missing semantics or preserving an old executable API.
- [x] Bind references to supplied source contents; use host-owned, criterion-and-check-bound calibration for a
  program decision. Preserve externally specified meanings and the existing independent promotion boundary.
- [x] Make evidence requirements affect actual evaluation; keep errors and unobservable conditions unknown.
- [x] Update Builder/Assessor/MetaReviewer prompts, recovery, record display and canonical domain definitions.
- [x] Verify missing evidence, local-only passes, scope, source revision changes, protected requirements and
  real construction/assessment flow, then run affected Python and frontend checks.

| Refinement verification | Result |
| --- | --- |
| Existing experimental Python suite, 67 modules | 807 passed |
| WebUI record parser after adding the current/legacy contract case | 16 passed, including the added case |
| Native Curator/Worker and bounded checker subprocess tests | 8 passed |
| WebUI component suite after updating semantic field assertions | 151 passed |
| TypeScript and production build | Passed |
| Ruff check and formatting, 15 Python files changed in this refinement | Passed |
| Source-language, large-file and diff whitespace gates | Passed |

The refinement used the same commands above, with a final `uv run --frozen --python 3.12 --extra dev pytest
tests/test_webui_studio.py -q` for the added record-display case. Its 16 results overlap with the broad suite; they
are not 16 additional unique tests. Program calibration tests bind labels to the specific measured condition;
source changes invalidate qualification. New tests also show that local-only passes and missing evidence cannot
establish whole-criterion success, and that source versions cannot be supplied by the model.

Schema 2 supports execution restore. Older records remain readable in the UI, but must be rebuilt from original
inputs before execution; no compatibility shim fabricates absent semantic fields. External criteria remain fully
protected from Builder edits. Automatic publication of external-check repairs and real-model quality benchmarking
are not claimed. The editable design Page reflects these contracts and limits. No commit or push was made.

## Implemented hierarchical rubric extension

Status: implemented on 2026-10-09. The requirements R01-R14 and acceptance cases A01-A15 in
[hierarchical-rubric-design.md](hierarchical-rubric-design.md) govern this extension. Its verification is recorded separately from the earlier implementation below.

- [x] Add a single parent relation, tree validation and faithful record compatibility.
- [x] Enforce host-owned patch scopes for every operation and reason before enabling hierarchical revisions.
- [x] Implement bounded dynamic construction, semantic placement checks and one scoped correction cycle.
- [x] Integrate evaluation, guidance replay, feedback deduplication, record display and end-to-end validation.

No new implementation, commit, push or merge is authorized by this checklist alone.


### Hierarchy implementation evidence

The implementation adds the parent relationship, bounded node queue, host-issued operation/field permissions,
version guards, interruption recovery, persistent unresolved diagnoses, property-scoped RepairSuite validation,
hierarchical record display, and measurement-only owner signals. Source/target changes invalidate old scopes;
unrelated regression additions can retain unchanged pending branches under newly bound scopes. No commit, push or
merge was made.

The separate review pass checked the design against actual mutation paths. It found and fixed checker-only
follow-up escalation, synthetic construction uncertainty granting checker edits, loss of external parents during
sedimentation, unvalidated strength reduction dropping a blocker, interrupted unpublished construction, and pure
parent changes being mistaken for no-op revisions. Tests reproduce these cases.

Native integration uses scripted model responses with actual Worker and Curator processes. The paid model scenario
requires ASSESSOR_TEST_CONFIG and was skipped. Semantic placement instructions and scripted counterexamples do not
establish general real-model accuracy. Final commands and counts are recorded with the completion audit.


Final hierarchy verification:

| Check | Result |
| --- | --- |
| Experimental Python regression suite | 839 passed |
| Native Curator/Worker and restricted program subprocess integration | 8 passed |
| Paid Assessor model scenario | 1 skipped; ASSESSOR_TEST_CONFIG absent |
| Frontend suite | 152 passed |
| TypeScript and production build | Passed |
| Ruff, source language, large files and diff whitespace | Passed |

```bash
rg -l 'from experimental\.|import experimental\.' tests/test_*.py > /tmp/raven_hierarchy_y4fj9a22/experimental_tests.txt
xargs -a /tmp/raven_hierarchy_y4fj9a22/experimental_tests.txt uv run --frozen --python 3.12 --extra dev pytest -q
uv run --frozen --python 3.12 --extra dev pytest -m integration tests/integration/test_evaluation_curator_e2e.py tests/integration/test_assessor_checks_real_subprocess.py tests/integration/test_assessor_standard_real_llm.py -q -n 0
# In experimental/webui:
npm test -- --reporter=dot
npm run build
# In the repository root:
make check-large-files COMMIT_RANGE=HEAD
make check-source-language COMMIT_RANGE=HEAD
git diff --check
```
