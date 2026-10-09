# Self-improving evaluation system

Implementation design, 2026-10-08. The first objective is better iterative improvement of the Harness Curator:
identify consequential task failures, turn them into grounded behavior requirements, support mechanism attribution,
and verify that the resulting harness change helps. An evaluator's rising score is not sufficient evidence.

The editable discussion is [the evaluation design Page](https://chatgpt.com/space/page_d0f36c746ce88191afc85d4a0399ea2e).
This document defines the implementation contract; [the plan](evaluation-system-plan.md) tracks delivery and evidence.

The implemented extension is specified in [Hierarchical rubric construction and incremental revision](hierarchical-rubric-design.md).
It records the requirements, relation checks, bounded construction queue, host-owned patch scopes, recovery behavior
and acceptance evidence. Each criterion now carries an optional parent_id; its definition remains complete.

## Decisions and boundaries

We considered three implementations: extending one judging prompt; a structured rubric with bounded review and
local records; and a separate evaluation platform with services, a verifier registry and a memory database.
Choose the second. A single prompt cannot enforce source authority, unknown handling or independent adoption.
A separate platform adds deployment and consistency costs without helping the current cultivation loop.

Retain `experimental/assessor/` and the existing `Signal -> Analyst -> Feedback -> Curator` interface. The roles are
Rubric Builder (construct/revise), Assessor (measure) and Meta Reviewer (audit and propose corrections/principles).
They are responsibilities, not three new services. Session owns execution budgets, records and adoption decisions.
`Standard` remains the rubric data type; `Criterion` is one requirement. Verifier and Promotion Gate describe
host functions, not additional model personas. The existing worker remains the execution boundary.

Self-generated criteria may drive evaluation and experimental harness changes without a person rating each round.
Stable adoption requires independent evidence. A run ending, several models agreeing, or a candidate receiving its
own highest score does not make it validated. Evidence that is unavailable remains unknown.

## 1. Express useful criteria and distinguish meaningful failures

### One structured rubric

Use one semantic contract in `assessor/rubric.py`, shared by construction, assessment and review. It stays inside the
existing `Standard`; there is no second executable representation or separate ontology service. Keep observed results
outside the criterion definition. Each field has a concrete consumer:

| Field | Meaning and consumer |
| --- | --- |
| `id` | Stable identity used by revisions, findings and feedback |
| `origin` | Declared, derived or sedimented entry path; used by existing source selection |
| `kind` | `gate`: necessary result; `guardrail`: prohibited behavior; `quality`: improvement among acceptable results. Derives mandatory/advisory strength |
| `authority` | External or model; the host protects externally supplied conditions from model edits |
| `definition.subject` | What is evaluated; shared by Builder, Assessor and Meta Reviewer |
| `definition.applies_when` | When the condition applies; an empty value means unconditional |
| `definition.acceptance` | The sole normative statement; replaces overlapping text and acceptance fields |
| `basis.references` | Source names and supporting quotes, bound by the host to content versions; supports grounding and stale-source detection |
| `basis.derivation` | Why an inferred condition follows from its inputs, distinct from the explanation for a revision |
| `assessment.evidence_requirements` | Observation channels the host must supply; missing required evidence prevents a pass |
| `assessment.decision` | One judgment of the complete criterion, defaulting to an LLM reading its definition |
| `assessment.required_checks` | Necessary local checks that can refute a criterion; passing them alone cannot establish it |

`LLMCheck` carries an optional instruction. `ProgramCheck` carries exactly one named verifier or restricted expression.
No overloaded `spec` string determines execution. Strength follows from kind: gate and guardrail are `must_hold`,
quality is `should`; models do not maintain both fields. An absent decision yields unknown even when every local check
passes. Auxiliary observations stay in the evidence packet rather than becoming another category of voting checks.

For example, a quotation criterion names the delivered quotation as its subject, applies when a priced offer is
requested, and requires the listed costs and tax in its acceptance statement. Its basis quotes the supplied pricing
policy; its evidence plan requires the quotation text and policy material. A whole-criterion LLM judgment considers
that definition, while a necessary arithmetic verifier checks the total. Correct arithmetic alone cannot prove
that all required costs were included.

The Builder starts from the task and available materials. It connects each important goal or constraint to an
observable property, obtainable evidence and a check. It can infer missing criteria, with the inference recorded,
and use known failure patterns to find omissions. The task alone can supply an initial anchor when no norms have
been handed over. The target output is never allowed to redefine what the task requires.

Rubric revisions use `add`, `rewrite` and `remove`. Removal excludes a criterion from the current rubric while
retaining its prior definition and reason in revision history. It does not erase historical evidence. The UI reads
the former `retire` operation as removal; new construction requests and revision records use `remove`.

Model criteria can be gates. Existing declared checks remain external. A counterpart's explicit confirmation can
make a model criterion external. Host code owns this transition; a model cannot claim authority in its tool output.
The Builder may only edit the model-owned part of the rubric. The implementation conservatively retains quoted
external conditions. Conflicting external conditions need explicit scope correction by the host; models cannot silently
pick one, supersede it, or weaken it through meta-review or historical sedimentation.

The current `declared`, `derived` and `sedimented` categories describe how a criterion entered the rubric, not its
authority. Keep original authority and source references when Analyst requirements are retained as regression checks.
Feedback grounding must bind to actual supplied signals; the model's choice of a source name is not proof of origin.
The host hashes referenced inputs; a model cannot supply its own source version. A changed document under the same
name becomes fresh Builder input, and unreconciled derived criteria cannot pass against stale source versions.
Quotation matching verifies a passage's presence, not semantic entailment; the latter remains a review responsibility.
Definition and measurement are separate structures, but this release does not automatically publish measurement
repairs to external criteria: the Builder still protects the entire external criterion from model edits.

### Evidence and check execution

The Assessor reads actual conversations, retained deliverables and execution observations. It gives each check a
criterion reference, evidence and a result. A checker may establish a local property, such as correct arithmetic,
without establishing overall task success. File existence is not content correctness; API success is not goal completion.

Program checks run over the evidence packet with bounded execution and no authority to change requirements. Host
verifiers can perform existing environment/tool checks. Every program used as the whole-criterion decision, and every
generated expression even when used locally, requires independently known positive and negative examples before use.
The calibration key binds the definition, kind, source basis, entire assessment plan and selected program; changing
them invalidates the old qualification. Example labels concern the property being checked, not assumed perfection of
the whole task. Expressions run in a restricted, bounded child process over supplied evidence only.
Neither determinism nor model agreement makes a newly generated checker an independent oracle.

Evidence requirements name conversation, execution, delivered text or a supplied material. The host records gaps and
blocks a pass when required observations are missing or truncated. Applicability is a separate semantic decision;
failure to produce required output is not proof that the criterion does not apply.

Any necessary failure fails the criterion. A missing result, missing evidence, an execution error or an unresolved
disagreement is unknown, never a pass. Explicitly inapplicable criteria do not count as successful checks. At least
one applicable hard criterion must be exercised to conclude that the gates pass. An unknown applicable hard criterion
blocks that conclusion. Quality scores never offset a gate or guardrail failure.

Discrimination is tested using a targeted defect and a valid alternative: a quotation with a missing tax must fail;
a correct quotation with different wording must remain acceptable. The test concerns the verified property only,
not an assumed label that the entire original artifact is perfect.

### Feed the Curator actionable behavior gaps

Return the violated criterion, observed evidence and the expected behavior difference through `Signal` and `Item`.
Keep causal hypotheses distinct from observed facts. Analyst merges overlapping feedback and emits one `Feedback`;
Curator then attributes the mechanism and changes the harness. Evaluation-apparatus errors go back to the evaluation
side, not to Curator as invented worker defects. Preserve the existing audience boundary around hidden checks and
reference answers; the Curator gets behavior requirements, permitted materials and execution evidence.

External rejection cannot be canceled by a model pass. A rejection with no reason remains a rejection of that round
and a request for clarification, not an invented permanent rule. Explicit optional advice remains optional.

## 2. Supervise and improve evaluation without self-certification

### Bounded meta-review

Meta Reviewer reads the task/materials, rubric, actual check records and relevant prior evaluation episodes. It checks
coverage, source fidelity, contradictory requirements, unverifiable claims, superficial proxies and reward hacking.
It produces two distinct outputs: corrections to the current rubric/checking method and candidate reusable guidance.
An issue names its evidence and repair target: requirement, checker, evidence collection, or construction method.

One review and at most one corrective rebuild/reassessment are allowed per assessment cycle. Save the initial and
revised evaluation separately. A model dispute alone cannot overturn an independently observed failure. Unresolved
questionable judgments remain unknown; an unresolved audit adds an evaluation-integrity item, never an invented worker
failure. External requirements remain protected throughout repair. Provider failures
and exhausted budgets are recorded instead of triggering an unbounded reflection loop.

### Independent adoption

Freeze the validation inputs, expected observations, acceptance conditions and candidate identity before evaluating
the candidate. Use host-controlled verifiers, environment outcomes or held-out replays that the candidate cannot
rewrite. A replay judged only by the candidate's own rubric is diagnostic, not independent validation.

For evaluator changes, compare missed defects and false alarms on the same independently grounded cases. Require an
actual improvement and no protected regression. Missing or unknown checks leave the change a candidate. No invented
numeric confidence threshold substitutes for evidence. An approved result is bound to the exact candidate and test
set; later edits invalidate it. Preserve the prior active version and the reason for every adoption or rejection.

For harness changes, the cultivation worker may try successive candidates, but the host distinguishes experimental
installation from promotion to a stable revision. Independent checks of the actual candidate and protected cases
decide promotion. With no independent channel, continue useful diagnosis and improvement while recording the harness
as unvalidated. External rejection or a required unknown cannot coexist with a successful promotion record. Advisory
self-reflection is not itself a mandatory gate. Promotion records verified installation identity; it does not deploy
to another environment or automatically reinstall a prior revision.

The assessment order is bounded Builder work -> frozen evidence collection and checks -> Meta Reviewer -> at most one corrective
rebuild/reassessment -> final Signal. Without a review issue, the initial assessment supplies the Signal. Unresolved
evaluation issues remain explicit; verified program failures survive model repair. Analyst then translates the
Signal into feedback, and Curator attributes worker defects and changes the harness. The next worker run supplies
new observations. Guidance adoption and stable harness promotion each require their own host-controlled independent
validation; neither follows automatically from a favorable model judgment.

## 3. Accumulate experience as usable construction knowledge

### Three forms with different jobs

Compare three storage approaches: append every reflection to one prompt; preserve episodes with typed, validated
guidance; or build an embedding/graph memory service. Choose the second. An append-only prompt accumulates duplication
and unsupported generalizations. A graph service has no demonstrated retrieval requirement here.

| Form | Meaning | Representation and consumer |
| --- | --- | --- |
| Episode | What happened in one evaluation, and what evidence corrected it | Existing versioned evaluation record; Meta Reviewer can cite it |
| Principle | A scoped invariant or heuristic explaining what makes a useful criterion | A short guidance entry with scope and episode references; rendered into Builder instructions |
| Procedure | When and how to apply a method, including checks and stopping conditions | The same guidance entry shape, with type `procedure` and steps in its text; rendered into Builder instructions |

This is an engineering analogy to episodic/semantic memory, declarative/procedural skill acquisition and metacognitive
monitoring/control. It is not a claim to reproduce a human brain, and the three forms are not an authority ladder.
Facts do not become principles automatically; a principle need not become a procedure; repetition is not validation.

A guidance entry needs an identity, type (`principle` or `procedure`), scope, instruction text and links to episodes.
Its candidate/active/retired state and validation receipt are host-managed. Evidence episodes already exist in the
assessment log. The local guidance file retains only cited episode snapshots so cross-run references remain useful;
it is not a second general-purpose memory database.

Example: an episode records a report passing because it has three irrelevant citations. The proposed principle is
"check whether sources support the important claims, not just the citation count." The procedure is "identify the
important claims, open each cited source, compare its support, and mark missing support unknown or failed as appropriate."
An explicit requirement for three citations remains in effect as well.

### Consolidation and retrieval

Meta Reviewer proposes additions or replacements with their scope and source episodes. Compare the old and proposed
construction instructions by building rubrics and evaluating independently grounded examples, including an unused
task when the proposal claims cross-task usefulness. Only the host can activate a supported change. A local repair
can be used experimentally before there is enough evidence to generalize it.

Render a bounded, deterministic selection of applicable active principles and procedures into the Builder's actual
task instructions. Scope can narrow use; an experience cannot silently broaden the business objective. Preserve the
base duties and external-priority rules outside model-editable guidance. Record which guidance versions were used.
Keep candidates, retire superseded entries instead of losing their history, reject dangling evidence references and
allow rollback to the previous active version. Reopening a run must load the same adopted guidance.

Monitor downstream usefulness separately: whether a real behavior gap reached Curator, whether its attribution and
change addressed that gap, whether the next task improved, and whether protected behavior regressed. A failed Curator
repair alone does not establish that the rubric was wrong; improving the rubric's own score alone is not success.

### Research incorporated

| Research line supplied in the discussion | Mechanism retained here | Implementation boundary |
| --- | --- | --- |
| Environment as a weak oracle: ToolRL, Q-Evolve, MOSS, AgentDevel | Read real execution observations and retained deliverables; check observable properties | `observations`, named verifiers and independent held-out executions; a local success is not whole-task success |
| Compile goals and constraints: DeepVerifier, SAVeR | Connect an atomic requirement to scope, acceptance and evidence | Builder receives the task/materials; gate/guardrail/quality criteria carry LLM or program checks |
| Ground implicit standards in knowledge/history: EvalAgent, ReasoningBank and related memory work | Ground quotes and distinguish inferences; retain episodes, principles and procedures | No unguided invention of external authority; only validated scoped guidance reaches later Builder requests |
| Rich textual feedback: GEPA, TPGO, MARS | Preserve what failed, observed evidence and the expected difference | `Signal -> Analyst -> Feedback -> Curator`; evaluation errors are repaired on the evaluation side |
| Relative critique and counterexamples: Tool-R0, DarwinTOD, WebEvolver | Check both a targeted defect and a valid alternative | The initial implementation consumes independently labeled replay pairs; it does not build a world model or autonomous self-play curriculum |
| Improve the evaluator/optimizer: ToolRM, MAS-ProVe, metaTextGrad, RewardHarness | Audit the evaluator and compare old/new construction instructions | Meta Reviewer proposes; host validation adopts. No reward-model training or self-issued approval |

The design Page retains the source links and research-specific limitations. These mechanisms do not require six
new roles. In particular, model-proposed counterexamples cannot supply their own authoritative labels.

### Runtime and recovery

Simulation and live-session hosts enable Builder, Assessor and Meta Reviewer with the derived source. `standard.json`
persists schema 3 rubric forests, construction work, UUID-qualified episodes, review records and validation references.
Schema 2 semantic contracts resume as flat forests; historical instructions remain in the migration record while new
construction uses the current protocol. Older records without semantic contracts remain display-only and require
rebuilding from original inputs. No restoration invents subjects, evidence requirements or parent relations.
`--evaluation-memory` / live `evaluation_memory` selects deliberate cross-run guidance reuse outside worker-accessible
paths. The bounded corpus is fed by frozen independent `Session.holdout` outcomes, never by adaptive self-judgment.
Previously pending proposals are retried when the evidence set or active guidance changes. Shared-file locks and stale
write checks prevent concurrent runs from silently overwriting guidance.

Guidance validation uses at most six frozen cases; activation needs independently grounded positive and negative
outcomes, actual improvement, no regression, and unused inputs from another task for cross-task claims. A proposal
contains at most 1,600 characters, and retrieval includes at most eight active entries. Missing labels keep a proposal
pending; a live session without an independent corpus can still evaluate and correct its current rubric.

The Python checker language is restricted JSON-oriented expressions in a bounded child process, not arbitrary code
execution. Hosts may supply domain-specific verifiers; generated expressions require independent positive/negative
calibration. Inability to read a necessary deliverable remains explicit unknown evidence.

Operational tests use scripted model providers and real native worker/subprocess execution. They establish the code
path and invariants. They do not establish real-model judging accuracy, generalization or a measured productivity gain.

Memory references: [Tulving (2002)](https://www.annualreviews.org/content/journals/10.1146/annurev.psych.53.100901.135114)
distinguishes recollection of past experiences; [Anderson (1982)](https://www.researchgate.net/publication/232496982_Acquisition_of_cognitive_skill)
describes declarative knowledge, procedural skill and knowledge compilation;
[Nelson and Narens (1990)](https://pdf.retrievalpractice.org/metacognition/4_Nelson_Narens_1990.pdf)
separates monitoring from control. The record/guidance/validation design above is our application of these ideas,
whose value must be checked against actual cultivation results.
