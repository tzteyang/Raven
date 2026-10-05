# Expert information collection

Status: closed after implementation, independent flow review and regression verification. The shared collector replaces the legacy Scenario preprocessing pipeline. Automatic later-round collection remains out of scope.

## Goal and scope

Collect and review the information needed to construct a digital expert before the first Curator invocation. The expert description covers role and boundaries, tasks and context, knowledge, abilities, working methods and rules, judgement, cases, and performance and learning. Tools, executable resources and operating prerequisites are described separately from claims that a capability has been demonstrated.

Material purpose is explicit. Interaction inputs, including product packages when supplied in that role, participate directly in information coverage assessment. They do not require abstraction or new research merely because of their origin. Optional research references serve only the research step: when research is necessary, they can suggest grouped questions and directions. Their abstraction is not established expert knowledge. Examples, invented personas and claims of experience are not evidence of real practice.

The collector is a task-driven agent with three acquisition channels: existing Raven file and shell tools; a delegated research task; and questions to the user. A separate review checks coverage, evidence support, reference independence and unresolved prerequisites. The host enforces the output contract, budgets and handoff; it does not encode a fixed domain research workflow.

Only initial construction is wired now. The collection API accepts an existing information snapshot, a focused objective and answers to previous questions. Research groups can address multiple dimensions and reuse existing evidence. These are forward-compatible contracts for later improvement requests, not an implementation of automatic per-round research or automatic restart after a Curator gap.

## Alternatives

| Approach | Tradeoff |
|---|---|
| Always abstract every product package before collection | Uniform, but changes the meaning of ordinary interaction inputs and forces research even when adequate material is supplied. |
| Maintain separate guided and unguided collection pipelines | Makes the branch explicit but duplicates coverage assessment, evidence handling and review. |
| One collector with interaction inputs and optional research guidance | Keeps coverage assessment common, groups related research needs and resolves optional guidance only when research is requested. Adopted. |

## Implementation boundaries

- `experimental/research/`: expert information contracts, collection and review prompts, a bounded collection/review runner, and a Curator handoff adapter. The offline entry and Scenario onboarding now share collection; no material-presence gap classifier remains.
- Existing Raven `Exploration`: owned source snapshots, native file tools and shell where the configured executor supports it. No new shell implementation or relaxation of its visibility rules.
- Existing research delegation: explicit questions, source-backed findings and unresolved questions; its raw source checks are supplemented by semantic review of the complete expert description.
- User interaction: an injected question callback; unavailable answers remain explicit unresolved questions instead of invented business content.
- `experimental/research/guidance.py`: bounded abstraction of research-only references into questions linked to dimensions. It is invoked lazily and shared across research groups; it never supplies factual evidence to the expert description.
- `experimental/simulation/experts.py`: accept the business task and optional interaction materials, plus separately declared research references or prepared guidance. Only the initial collection and review are connected to Curator.
- `CONTEXT.md` and current design documentation: describe the distinction between information coverage and mechanism attribution, and the initial-only integration.

## Acceptance

1. Partial material is evaluated by its content; the presence of a file does not close a dimension.
2. Submissions cover all dimensions and identify their evidence and unresolved questions.
3. The collector can read through native tools, delegate a research question and obtain an injected user answer.
4. Review can reject a conclusion contradicted by its evidence and request a bounded repair.
5. Missing answers and failed review cannot produce an approved Curator handoff.
6. Prior information can be supplied to a focused collection without discarding unrelated content.
7. Interaction materials are assessed without mandatory abstraction. Research-only source packages do not enter the worker uploads or the collector's available material sources.
8. Existing source isolation and protected snapshots remain enforced.
9. Initial expert construction invokes collection and review before Curator, with records of both outcomes.
10. A research group can cover several dimensions, uses known evidence and optionally uses relevant guidance. Complete supplied information needs no research call, with or without research references.
11. Focused collection preserves unrelated information and supports explicit answers to earlier questions. Handoff checks its base version before replacing an existing information version.
12. Run relevant tests through `uv run pytest`, then source-language and large-file checks for the changed documentation and generated source.

## Implementation and verification

- Shared initial preparation is connected to the expert entry, offline CLI and Scenario onboarding. Later iterations keep their existing scheduling.
- `prepare_research` makes optional guidance available to the collector before it groups work; irrelevant guidance can be declined and sufficient inputs require no acquisition.
- Independent review receives all acquired tool/research/user evidence, including uncited user answers. Request context is available separately; source IDs remain checked.
- `Manifest` binds task, objective, scope, released inputs, context and observed environment. `Result.reviewed_version` binds review to the snapshot. Matching reviewed results replay without model calls; mismatches fail before acquisition.
- Local and composite checkpoint protection is owned by Curator. Journaled publication recovers interrupted content/version writes and detects unrelated edits.
- Section, resource and question changes are recorded. A question has a unique ID and an optional exact adoption proposal; its recorded answer is not reused for a different proposal.
- Scenario adapters preserve actual disclosure and evaluation isolation. Optional simulated-party answers use private sources internally and refuse outgoing sealed content. No automatic promotion to evaluation norms occurs.
- Legacy slot routing, fixed induction/settlement and Scenario package generation are removed; directory identity belongs to `scenario.digest`, while web execution and verification are retained.
- Controlled tests cover the flow and native file/shell behavior. Paid LLM research, live external services and end-to-end expert quality have not been measured.

## Replacement design: one information preparation responsibility

### Existing responsibilities and overlap

The earlier cultivation design already assigned `research/` the job of completing inputs before Curator and proposed later answering Analyst `supplement`/`clarify` and Curator `report_gap`. The new collector expands that same responsibility. They do not require two permanent pipelines.

| Existing code | Actual behavior | Replacement decision |
|---|---|---|
| `research/slots.py`, `research/__main__.py` | Material presence selects `inducible`, `researchable`, or `party`; the CLI branches on those values. | Remove the gap classifier and its orchestration. The LLM assesses content against the task and dimensions. Existing material metadata suffices for inventory; do not preserve `Slot` without a caller. |
| `research/induction.py` | A separate exchange turns examples into unstated norms, checking sources and visibility. | Absorb understanding examples into collector reasoning, retaining conditions, alternatives, outcomes and limits. Retire the dedicated rule exchange after migrating consumers; preserve source/visibility validation in the appropriate adapters. |
| `research/inquiry.py`, `researchers.py`, `web.py` | Delegate web investigation, read pages, validate quotes, retain findings and failures. | Reuse acquisition. Separate generic findings/verification from Scenario brief construction and supplied-material precedence. Eight dimensions do not require eight finding types. |
| `research/confirm.py` | A party confirms, amends, rejects or leaves proposals undecided; `ModelParty` sees its own private materials. | Preserve party decisions. Integrate necessary adoption/clarification through user answers; keep simulated-party access on the simulation side. Remove mandatory settlement of every researched fact. Review is never a party decision. |
| `research/package.py` | Copies a Scenario, generates norm/fact packages, changes disclosure schedules and records provenance. | Default output becomes reviewed snapshots and records. Do not rewrite Scenario materials or disclosure merely because research ran. Remove obsolete package generation after callers migrate. |
| `scenario/contract.py`, `disclosure.py`, `sealed.py` | Define fixtures, material roles, audiences and release plans. | Retain these responsibilities. Permit supplied references without automatic endorsement; keep expert dimensions separate from material kinds. |
| `curator/attribution`, generation inspection/query tools | Diagnose how the actual Harness handles requirements and investigate its implementation. | Retain. Information sufficiency does not establish implementation correctness; technical investigation remains inside Curator. |
| `analyst/feedback.py`, `iteration/session.py` | Record supplement/clarification needs; a Curator gap ends curation and its reason is recorded. | Retain need producers and design a common request mapping. Do not enable automatic round-by-round acquisition. |

There is no existing research scheduler in the run loop to replace. Without new attachments, Analyst supplement/clarification normally follows ordinary continuation/termination. `report_gap` records a question without answering it. Those intended future paths must not be described as already implemented.

### Alternatives and decision

| Approach | Consequences |
|---|---|
| Keep the Scenario preprocessor and collector beside each other | Small immediate migration, but two definitions of sufficiency, authority and completion persist. Rejected. |
| Shared collection with task and Scenario adapters | One LLM-led assessment/review, reusable acquisition, preserved Scenario isolation and Curator diagnosis. Adopted for replacement. |
| Fold acquisition into attribution/generation | Reuses Curator calls, but mixes information review with implementation decisions and complicates adoption, replay and evaluation isolation. Rejected. |

This assumes expert construction and Scenario onboarding share information preparation before curation. A separately requested scenario-authoring/export feature could justify an exporter later; it would consume reviewed information, not own another classifier. No such exporter is required here.

### Target sequence and ownership

1. The caller identifies the business task, improvement objective and previous information version. The host supplies only inputs available for this invocation.
2. The collector LLM reads the inputs, compares content with the expert dimensions, explains coverage and decides whether acquisition is needed. Categories describe content; they do not determine completeness.
3. It chooses native Raven tools, user questions or grouped research. Interpreting an existing example is reasoning, not a fourth acquisition channel or mandatory induction stage.
4. After a research need is established, optional guidance is derived or reused and shown to the collecting agent before it finalizes groups. It can merge questions across dimensions, reuse evidence or decline guidance. No research need means no guidance work.
5. Findings and answers return to the same assessment. Ask about adopting an organisational policy only when the task requires that choice; verification of public facts is separate.
6. Separate review checks evidence, coverage, conflicts and applicability. All new user answers and explicit constraints remain visible even when omitted by the proposal. Large raw evidence can be read by reference, with a complete inventory so selective citation cannot hide relevant inputs.
7. The host enforces references, budgets, visibility, blocking questions and base-version consistency. Accepted, unblocked information is frozen for one Curator invocation. Otherwise record the unmet need without starting curation or trials that assume preparation succeeded.
8. Curator attributes and changes the Harness against that input. Review neither installs capabilities nor creates assessment criteria.

Application-level composition uses the existing `collect_for_curator` / `handover_information` boundary. Both entries call the same collector; low-level `improve`, `attribute` and child `propose` do not each launch research. Only initial construction/onboarding is enabled in this scope.

### Contracts, authority and replay

- Keep `Request` / `Snapshot` / `Result`. Extend their metadata to bind the business task, source versions, invocation scope and feedback origin. A future focused request can carry a projected Analyst need or Curator question without changing acquisition channels.
- Keep material kind, expert dimension, origin, invocation purpose and adoption status distinct. One source may support multiple dimensions. Research-only examples belong to a research request, not Scenario disclosure.
- Retain review decisions bound to snapshot identity. A loaded `Snapshot` alone is evidence for reassessment, not proof of review acceptance or a match to current inputs.
- Return resource and unresolved-question changes as well as section changes. Revalidate environment-dependent resource availability when reusing information in another worker workspace.
- Publish readable information, resolvable evidence references and version/change metadata for attribution and curation records. Do not publish raw acquisition transcripts or private evaluation records to the worker.
- Preserve adoption decisions with stable item/source identity and the information version they concern. Revised content must not inherit approval through positional IDs. Supplied content is not automatically endorsed; reviewed industry practice is not automatically a business rule.
- Curator owns a public query for unfinished local or composite curation. New information cannot replace a paused generation's inputs. Reassessment precedes an explicit restart, not resumption under different facts.

Frozen experiments remain possible: record Scenario digest, released-material manifest, reviewed information version and Curator configuration separately. Replay of a matching reviewed result need not rerun research. New acquisition produces a new version before curation; each curation still has fixed inputs. This replaces the old requirement that the loop know nothing about research.

### Entry points and migration

| Surface | Target behavior |
|---|---|
| `simulation.experts` | Retain task/package inputs and separate research references; shared preparation, curation, optional tasks. Fix task-only execution and retire unused staging duplication. |
| `python -m experimental.research` | Offline entry to the same collector, using a task or Scenario-derived allowed input view. Output a versioned collection result and records, not a rewritten Scenario. Update help/callers together; do not silently retain former `--out` semantics. |
| Scenario first onboarding | Once opening handovers are determined and staged, prepare the actual released materials and Curator-visible task/context. Replay a reviewed offline result only when its task/source manifest matches; otherwise reassess. |
| Later rounds | Keep current behavior. Preserve need origin and scope for a future request; no automatic supplement/clarification/gap dispatch. Missing authority or capability is not automatically a web-research question. |
| User answers | Use the common answer channel. A simulation adapter may use party-private knowledge internally, but must enforce outgoing release/sealing rules. No private source text or evaluation result becomes collector context. |

`Scenario.handed` is eligibility, not actual release. Use opening handovers / `agency.released`, filtered for the receiving role. Never import the whole fixture or future disclosure steps. Apply audience projection and compartment checks to collection, review and delegated requests/results. Professional practice cases are not trial `Case`; professional experience is not prior cultivation records.

Offline Scenario preparation must declare its release scope: an opening plan or selected eligible materials. Information built from later-disclosed inputs cannot be replayed at onboarding. Research-only references do not become released source evidence or enter disclosure schedules. Their source exclusions travel as policy metadata into handoff, replay and resumed curation.

Directory identity now belongs to `scenario.digest`; the simulation entry, run-record reader and tests use it. Generic inquiry no longer constructs Scenario briefs, and sealing support lives in `scenario.sealed`. Obsolete exports and their tests were removed or migrated with their callers.

Replace `--decisions` / `--from-records`, which address positional Rule/Finding IDs, with answers/adoption bound to the new version. Never apply old decisions to newly generated IDs. Leave user data and historical run directories unchanged; no automatic historical converter is required. Existing material kinds and the provenance reader can describe already-authored fixtures independently of new collection storage.

### Implementation order and acceptance

1. Repaired task-only execution, reviewer access to uncited answers, composite pause protection and guidance-before-grouping; added version-bound answers and result manifests.
2. Migrated the offline entry, decoupled web verification, moved the digest helper and removed old routing, unused exports and package-generation paths.
3. Connected Scenario initial onboarding using released, audience-projected inputs, with preparation status and information versions in records. Assessment remains independent.
4. Replaced obsolete routing tests and updated README, context, CLI examples and the run-record reader. Later-round acquisition remains unimplemented.

Acceptance covers: present categories with insufficient content; sufficient inputs with no research; omitted user constraints visible to review; guided/unguided grouping; task-only construction and execution; local/composite pause protection; resource-only and question-only changes; rejected/blocked preparation preventing onboarding; matching replay and refusal/reassessment on mismatch; future-disclosed/evaluation-only data unavailable to collection; adoption never inferred from review; unchanged later-round scheduling.

The review findings for task-only execution, composite pause protection and uncited user answers now have regression tests. The final checks below distinguish executable flow evidence from semantic model quality.

No historical input is modified in place. The old orchestration is removed, with no permanent fallback. Interrupted preparation keeps records without publishing readiness. Publication of content/version metadata must be recoverable as one operation. Reversal restores previous code and explicitly selects an intact prior result; it must not mix information versions in a paused curation.

## Flow review checklist

| Demonstrated path | Executable evidence |
|---|---|
| Sufficient information | No research/guidance calls; review then handoff. |
| Native tools | Actual file and subprocess evidence reaches review without changing protected sources. |
| Unguided research | Explicit multi-dimension assignment with verified findings. |
| Guided research | Guidance must be read before a group is submitted; source cases remain isolated. |
| Waiting for a user | Questions cannot disappear; unready onboarding never curates or starts trials. |
| Review repair | Rejected content returns for bounded revision; uncited user constraints remain visible. |
| Later improvement | The initial version reaches later curation; preparation is called once only. |
| Frozen replay | Matching inputs cause zero model calls; changed sources or changed reviewed content are refused. |
| Lifecycle | Composite/local pending work blocks publication; interrupted publication recovers one version. |

The independent review checks these paths against the source, the tests and the demonstrated flow. It does not infer real-model sufficiency or expert effectiveness from controlled responses.

## Final verification

- 260 tests passed across information preparation, native file/subprocess smoke cases, Scenario contracts and disclosure, iteration, attribution, generation, composition, assessment and record reading.
- Ruff check/format, targeted `ty check`, all three CLI help commands, `git diff --check`, source-language and large-file gates passed.
- Review repairs include submission acknowledgements before retrying a model conversation, mandatory visibility of uncited user answers, version-bound answer files, replay invalidation on new answers, restoration of research-only source exclusions, and ignoring abandoned checkpoints while blocking active curation.
- These initial tests use controlled model responses and source readers. Subsequent live information-preparation validation is described below; neither exercise establishes production expert quality.

Test command:

```bash
uv run --offline --no-sync pytest tests/integration/test_expert_information_smoke.py tests/test_simulation_information.py tests/test_research_collection.py tests/test_research_scenario.py tests/test_iteration_session.py tests/test_harness_curator_composition.py tests/test_harness_curator_attribution.py tests/test_harness_curator_generation.py tests/test_simulation_experts.py tests/test_research_inquiry.py tests/test_research_web.py tests/test_scenario_contract.py tests/test_scenario_disclosure.py tests/test_simulation_scenario.py tests/test_simulation_record.py tests/test_assessor_standard.py -q -o addopts='' --tb=short
```

## Live information-preparation validation

The follow-up uses three representative GTM expert packages: `sales-coach`, `marketing-growth-team`, and `chuangye-manor`. DeepSeek handles guidance, collection and review. Each case freezes one research assignment generated by the real collector and replays that planning prefix identically for Claude Code researchers requesting `claude-sonnet-5-5` and `claude-opus-5-5`, both at `xhigh`. Continuation and review remain live model calls. Product materials are research guidance only. This is not a full eight-dimension research campaign, a Harness construction run, or a deployed-expert evaluation.

Each researcher receives a 900-second timeout and a USD 3.50 CLI budget. Collection permits one research task, at most eight findings, two review cycles, and three calls per review; helper calls use a 9,000-token output limit. Independent page verification uses a 60,000-character cap, above the production default of 12,000. These settings must accompany any interpretation of completion, latency or citation checks. CLI model labels and API-equivalent costs are reported metadata, not independently attested model identities or account invoices. Some Sonnet pricing metadata reports an unknown basis, so cost figures do not establish relative model prices. A final CLI request can overshoot the requested monetary cap.

Live preparation exposed incorrect source identifiers for hidden directories. Guidance reads now return exact catalogue identifiers, and validation names unknown identifiers; original failed preparations remain separate from retries. A second repair parses Claude's structured failure result before stderr, preserving budget-exhaustion reasons and reported usage metadata instead of misclassifying a warning as a model failure. Both repairs have regression coverage. The CLI now forwards an explicit research effort independently of the main model's settings.

Observed research results (one trial per cell; time excludes host verification and DeepSeek review):

| Case | Sonnet 5.5, xhigh | Opus 5.5, xhigh |
|---|---|---|
| Sales coach | No delivery: CLI budget exhausted after 333.5 s | 8/8 findings passed quote verification, 407.9 s |
| GTM advisor | 8/8 findings passed quote verification, 266.5 s | 7/8 findings passed quote verification, 277.2 s |
| Founder advisor | No delivery: CLI budget exhausted after 337.6 s | 7/8 findings passed quote verification, 340.9 s |

The two refused findings quoted passages not found in the host's retrieved views. This does not distinguish misquotation from differences between retrieval views. Across the six trials, four delivered structured research and 30 of 32 submitted findings survived quote verification. These observations describe this bounded experiment, not a general ranking of the models.

The GTM/Opus continuation hit a separate DeepSeek review failure: three successive 9,000-token responses contained no tool submission and exhausted the review budget. A diagnostic replay of the identical first review input with an 18,000-token limit returned a valid accepting review in 67.7 seconds. That diagnosis is stored separately; it neither overwrites the original failed trial nor publishes the candidate. The accepted review explicitly retained the refused PMM claim as an open boundary instead of adopting it. Partial or missing dimensions and blocking questions remain valid outcomes when only one research group is funded.

The original continuations ended with five `needs_input` results and one review error; none reached Harness construction. Manual inspection found a semantic defect in the accepted founder/Opus candidate: it reused a refused vendor finding as a lower-confidence working rule and attributed host verification failure to the researcher's intent. The review had accepted those caveats. Collection and review instructions now explicitly distinguish failed evidence from weaker retained evidence: refused items can guide further investigation, but do not support professional rules unless independently supported by retained evidence. This is a semantic review obligation, not a keyword-based coverage rule. A separate diagnostic review preserves the original candidate and does not replace the original trial.

With those review instructions and an 18,000-token limit, DeepSeek identified the defect in a plain JSON response. One protocol reminder then produced a valid rejecting `review_information` submission identifying the unsupported knowledge, method, judgement, ability and example, plus the incorrect attribution. This is a successful targeted diagnostic, not proof that all future reviews reject unsupported claims. The candidate remains unpublished. Including preflights, original failures, retries and the three diagnostic calls, recorded API-equivalent costs and token estimates total approximately USD 14.75; they are not an account invoice.

Claude traces now retain the full reported per-model usage metadata separately from truncated stdout, so unknown pricing bases remain inspectable even when the structured result is large. Historical traces are not backfilled with invented usage data.

The initial comparison identified these operational gaps (the follow-up below repairs the allowance and timeout defaults):

- The collector does not see the remaining research-task budget upfront. It can plan several groups before discovering that only one is executable. Budget-aware grouping should retain the LLM's responsibility for semantic decisions.
- The production preparation adapter shares its timeout with research, defaulting to 300 seconds. Several live research tasks exceed that value; the benchmark's 900-second agent limit is not the production default.
- Long reviews can consume all output tokens in reasoning without submitting a tool result. Repeating an unchanged budget is not a reliable recovery strategy. A diagnostic retry must remain distinguishable from the original comparison and must not publish an unreviewed proposal.
- Quote verification establishes passage presence in the retrieved view. It does not establish entailment of every claim, source independence, organisational adoption or demonstrated ability; semantic review is still required.

Raw requests, responses, failures, candidate descriptions and comparison artifacts are stored outside the repository. No generated reports or web assets belong in the change.

## Historical occupation validation and collector ownership correction

### Collector-owned closure (implemented)

The multi-hour experiment did not validate autonomous collection: its test-only planner, independent plan-review loop, manual restarts and per-package repair loop made decisions outside the collector. Five packages eventually passed; the sixth and the aggregate were unfinished when further calls were stopped. These artifacts remain diagnostic inputs, not end-to-end success evidence.

The collector must own gap assessment, grouping, briefs, follow-up research and final synthesis. Review is a bounded, tool-free model function returning defects; it never chooses the next action. Code enforces references, admission, state and execution limits. The existing Request/previous Snapshot/focus contract remains usable for later invocations; automatic later-round acquisition remains out of scope.

| Option | Decision |
|---|---|
| Promote the bespoke planning/review test into another workflow engine | Reject: duplicates the collector and preserves autonomous nested repair loops. |
| Keep the existing collector, return each research review to it, and enforce one overall deadline | Select: one decision owner and reusable Curator integration with limited changes. |
| Collapse research and review into the collector's own context | Reject: loses independent source checking and weakens the review boundary. |

Implementation: remove pre-research brief auditing and repeated guidance auditing; keep a bounded optional guidance extraction. Execute and review one research attempt per collector delegation. An explicit retry handle lets the collector revise a prior attempt while retaining its source views and review history; code caps revisions and never starts them automatically. Add an overall deadline and preserve an incomplete result, evidence and checkpoint when execution ends. Replace the bespoke real-test planner with the production collector; a Claude Code provider adapter may select host tools but cannot execute them itself.

Validation: deterministic tests for acceptance, rejection followed by collector-chosen repair, unreadable evidence, revision limits and an overall deadline across nested work. Replay saved evidence without new searches. One opt-in live collector test is limited to 300 seconds for the entire run, uses retained evidence, and does not launch a six-package campaign or auto-resume. Review the implementation separately against the ownership and visibility requirements, then record the actual outcome including incompleteness.

Implementation is complete. The durable contracts and usage are in `CONTEXT.md`, `experimental/README.md` and the cultivation-loop design. The new live check invoked the production Curator collection path, with live Claude Code collection/review and retained research replay. It finished in 124.26 seconds with four model calls and one research attempt. Research review rejected the replay as off-brief; with zero repair allowance the collector retained public-research gaps and submitted an honest incomplete description. Final review accepted that accounting, and no Harness handoff occurred. This validates autonomous bounded termination on a rejected delivery, not a successful new web investigation or a complete occupational profile. A startup-only failure first exposed an absent working directory in the offline entry; it was fixed before any live model call.

The correction also preserves review history across explicit research repairs and final-description revisions, records actual changed dimensions on an interrupted focused invocation, and makes terminal user input cancellable without waiting for a blocked input thread. Controlled integration tests exercise successful collector-requested repair through the shared Curator adapter. Neither the test driver nor an external assistant chooses the next runtime action.

Final regression verification: 291 tests passed and two opt-in real tests were skipped in the default run. The separately enabled bounded live check passed its execution/termination assertions with the incomplete outcome described above. Ruff, targeted type checking, source-language and large-file gates, CLI help and diff whitespace checks passed. No commit or push was performed.

Follow-up validation added `RESEARCH_COLLECTION_MODE=source_review`: the research model creates a new delivery from the captured page rather than replaying a fixed answer, with one collector-controlled revision allowed and the same 300-second overall limit. The single run finished normally in 298.85 seconds (307.90 seconds including test/worker startup and cleanup). There were five model invocations: task delegation 28.70 seconds, research 150.72, research review 23.22, collector synthesis 59.15, and final review 37.02. Eight findings passed verification and review on the first attempt, so this live run did not exercise repair. The focused knowledge update returned ready with partial coverage and four explicit nonblocking questions; other dimensions were preserved unchanged. Readiness applies only to that provisional captured-source objective, not to a complete occupation or current verification of the standard. No fresh web search was performed. The follow-up's 68 relevant regression tests passed, including controlled repair, unreadable-source and deadline paths. The run was close to the deadline and does not establish adequate latency for larger tasks.

### Full occupation trial with an incorrect 900-second budget

The 900-second overall limit in this trial was an implementation/test configuration mistake. The user's agreed limit is 3600 seconds for the whole collection loop. This trial is not acceptance evidence for that agreed budget.

A subsequent production CLI run started with no previous snapshot and all eight dimensions for an organisation-neutral B2B sales coach. The expert package README, role description and five business skills were research-only references. No recorded research delivery, captured-page substitute, scripted plan or external repair decision was supplied. Collection and research requested Claude Code Opus 5.5 at xhigh, with a 900-second overall deadline, at most six groups and one collector-controlled revision per group.

The first startup failed before model calls because bootstrapping an unrelated installed Raven-Research worker profile required a Serper key. A separate test configuration disabled the unrelated Raven-Research and Raven-PPT worker profiles; the user's configuration stayed unchanged, and delegated research still used Claude Code's real web tools. This isolates the environment dependency rather than fixing the production bootstrap behavior.

Acceptance failed. The collector derived optional guidance and delegated one group covering role, tasks, abilities, methods and knowledge. Actual research made 17 WebSearch and 33 WebFetch calls and produced eight candidate findings; independent quote checking retained seven and refused one. Its semantic review was cancelled at the global deadline. There was no accepted research evidence, collector synthesis or final information review. The host returned incomplete/time_limit in 900.02 seconds; startup and cleanup brought process elapsed time to 907.23 seconds. All original case files were unchanged. The saved snapshot is an unassessed host fallback, not a model finding that all occupational information is missing.

Timing: collector decisions and guidance consumed about 222 seconds; first research 550.85 seconds; source verification about 42.75 seconds; research review ran for 84.36 seconds before cancellation. The research request carries no remaining-time allowance, while the child retains a 3600-second limit and only the parent enforces 900 seconds. No time is reserved for synthesis and final review. The initial collector prompt also contains 259 host-source entries and 87,465 characters; its causal contribution to latency was not isolated in this run.

This validates real search execution, source checking, deadline cancellation, record preservation and refusal to hand off unfinished information. It does not validate successful full-occupation closure. Budget propagation, bounded subtask allocation and a closing allowance remain unresolved design issues; simply raising the global timeout would not demonstrate that those responsibilities work. No additional model run or manual package repair was launched after the deadline.

### Whole-loop budget correction and rerun

Restore the default overall collection deadline to 3600 seconds in CollectionLimits and both CLI entrypoints. Each ResearchAssignment carries the actual remaining time; the Curator adapter caps acquisition and its review by that remainder. The researcher and reviewer receive their remaining allowance as execution metadata, outside the semantic brief. No fixed 900-second collection cap or new shorter closing deadline is added. The caller can still explicitly choose a shorter smoke-test budget.

The complete sales-coach scenario was rerun through the production CLI with all eight dimensions, no previous snapshot, actual web research and the same isolated worker configuration. Both per-call and per-research maxima were set to 3600 seconds, subject to the one shared overall deadline. No test driver planned groups or repaired content. Original records remain unchanged; each run uses a separate output directory.

The first corrected-budget trial received SIGTERM after 385.90 seconds, with no final collection result. The signal sender is unknown; the user confirmed they had not stopped the run. Monitoring initially misread stale event files as a live process and incorrectly attributed the delay to a webpage. That diagnosis is withdrawn: the records do not establish a prolonged fetch stall. The interrupted trial is not acceptance evidence. The next trial recorded the process PID and checked/reported actual exit status every 30 seconds, without changing any collection decision.

The monitored trial reached the agreed 3600-second collection deadline normally (3600.03 seconds; 3607.34 seconds including process startup and cleanup). It independently formed three research groups, each covering several dimensions. All three first deliveries were rejected; the collector explicitly requested one repair per group, and all three repaired deliveries passed their source-aware reviews. Six research attempts made 41 WebSearch and 85 WebFetch calls. The shared remaining allowances decreased from 3428.51 to 2807.12, 2435.27, 1715.48, 1274.95 and 728.39 seconds; no child received a new hour.

The collector then submitted a complete eight-dimension draft: seven dimensions partial, cases missing. Final review rejected seven issues, including renewed attribution of an unsupported forecast-error threshold to Salesforce, broadening supported configurability claims, moving public-research gaps into user-only questions, and omitting a coaching-method difference across experience levels and sales roles. The final-description stage took 218.12 seconds and its review 172.99 seconds. The collector began another revision, but its call was cancelled after the remaining 67.39 seconds. Result: incomplete/time_limit, not ready. Original case materials were unchanged and no unapproved description was handed off.

The budget correction and autonomous research-repair transitions are verified; final acceptance of the full occupational description is not. In particular, per-group acceptance did not prevent previously corrected evidence-boundary errors from reappearing in synthesis. No model calls were appended after the deadline. The new default/shared-budget tests and related regressions passed (297 tests in the full selected run); static checks also passed. Further work on synthesis fidelity, prioritisation of missing cases and time for final revision is separate from this budget correction.


The accepted validation scope is one complete B2B sales-coach description across all eight information dimensions. The model assesses the whole scope and groups related gaps into multiple research briefs, executes every planned group within the declared allowance, and synthesizes and reviews the combined description. A passing citation or a single successful group does not establish occupation-wide sufficiency. Private organisational decisions, further public research and unavailable local resources remain distinguishable.

Options considered:

| Approach | Tradeoff |
|---|---|
| Extend only the external one-off experiment | Fast, but the runtime retains the defects already observed. Rejected. |
| Correct shared research execution, contracts and review; validate the complete occupation using those components | Reuses the existing information/Curator boundary and supplies directly relevant regression coverage. Selected. |
| Replace the whole Curator loop with a new CLI workflow engine | Expands into native-tool bridging and later-round scheduling, neither required by this validation. Deferred. |

Implementation scope:

- Reuse the six semantic brief fields; keep dimension associations in the collection plan, outside the researcher handoff.
- Make acquisition allowances visible before grouping and report remaining capacity. Do not silently truncate a multi-group plan to one group.
- Separate the research timeout (3600 seconds) from ordinary model/tool calls; subscription CLI runs have no monetary cap unless explicitly requested.
- Persist Claude stream events, including on failure, and reuse this execution for structured preparation/review stages in the validation harness.
- Carry synthesis and source disagreements in the research delivery. Preserve source-verification state independently of semantic acceptance.
- Integrate bounded, source-aware review and repair before research enters the information evidence inventory.
- Distinguish blocking public-research gaps from questions only the user can answer; retain existing snapshot/version and Scenario visibility protections.

Validation: targeted contract, subprocess, timeout, multi-group, budget, repair and routing tests; then a real whole-occupation run with Claude Code subscription authentication, explicit planning over all dimensions, up to six model-chosen groups and at most two concurrent researchers. Model assessment determines adequacy; structural checks only enforce references, focus and execution limits. Inspect the final eight-dimension coverage, unresolved needs, source quality, synthesis and conflicts. Preserve failures and all original attempts outside git. Do not infer demonstrated expert competence from a reviewed description. No commits or deployment are part of this work.

Before the ownership correction, verifier regression tests passed, and independent guidance and brief review had been added. Those pre-execution audits are now removed in favour of collector-owned decisions and bounded guidance extraction. Package failure records retain the exception type, including timeouts and cancellations. The live test initially exposed pytest's isolated home hiding Claude login; its explicit opt-in configuration now accepts `RESEARCH_CLAUDE_CONFIG_DIR` without changing global test isolation.

The historical authenticated whole-occupation run was stopped without an aggregate result. Its approved plan contains six groups covering all eight dimensions. Planning itself required repeated reviews and proved expensive; explicit structured-output resubmission and local text corrections avoid silently accepting contradictory reviews or rewriting the entire plan for a small defect. Completed planning stages can be replayed only when their inputs match, with current contract validation.

The first two research groups exposed independent verifier defects: truncated page views were never expanded when a quote appeared later; JSON returned inside a reader's Markdown wrapper retained escaped Unicode; conflict descriptions were incorrectly validated as material identifiers despite the semantic-only handoff; and filtering findings shifted positional references. Verification now expands truncated views within a finite ceiling, decodes JSON text values without joining unrelated fields, treats conflicts as narrative claims for semantic review, and preserves original finding indices. Regression tests cover each behavior. Existing candidates were re-verified without repeating initial searches, and both changed from six to eight retained findings. Semantic review still rejected genuine unsupported claims, including an overbroad confidentiality exception and mixing distinct coaching competency frameworks. These are content defects for the bounded research repair loop, not reasons to relax verification.

A subsequent legal-source passage was falsely refused because PDF conversion rendered `activities` as `activi- ties`. Quote verification now also permits explicit word-wrap and soft-hyphen normalization, without joining ordinary spaces, paragraph boundaries or unrelated JSON fields. A replay of the preserved WIPO view confirms that correction separately from the original attempt.

The review loop exposed two further semantic problems. A researcher repeatedly treated its own successful fetch as overriding the host's failed independent read, retaining unsupported Gong-based rules until one package exhausted its repair allowance. Research instructions now make that distinction explicit and require removing such support or replacing it with another verifiable source. Also, some reviewers accepted unsupported working rules while listing their defects as nonblocking caveats. A separate real Claude Code diagnostic rejected the same group-five delivery after clarifying that incomplete optional scope differs from incorrectly asserted knowledge. The normal review and final information review now enforce that distinction through model instructions. This is evidence of a targeted improvement, not a guarantee of future semantic correctness. Selected packages were re-verified from saved candidates; five eventually passed, while the sixth and the aggregate remained unfinished. Original outcomes remain intact; no automatic continuation of that campaign is configured.

### Submission reserve, narrower groups, user-first sequencing and batched reads (2026-10-05)

Three incomplete-input cases were run on 2026-10-04 through the offline entry with Codex gpt-6.1-sol at xhigh as
collector and researcher (records outside the repository). With research enabled every case reached the 3000-second
deadline before submitting anything: one research attempt took 758 to 1027 seconds when it finished and hit its
1200-second cap three times, the collector delegated with 100 seconds left, no user question was asked, and the saved
snapshot was the unassessed fallback. With research disabled the same cases submitted reviewed descriptions in 313 to
1084 seconds with 10 to 11 channel-labelled questions each. Collector calls on the full package spent 16 of 20 calls
reading one file each, resending the growing conversation every time (2.17M tokens for one case).

Goal: let a bounded collection end with a submitted, reviewed description whenever the material allows, and make
research cost proportional to one narrow question group. Non-goals: changing the review contract, automatic repair,
or compressing conversation history.

| Decision | Alternatives considered | Chosen |
|---|---|---|
| Time for research | (a) leave the remainder to research; (b) fixed per-group share; (c) remainder minus a submission reserve, refused under a minimum | (c): `CollectionLimits.reserve` (default 600 s) and `research_minimum` (120 s); `delegate_research` is refused once the reserve begins and the assignment carries the exact window |
| Research size | (a) prompt advice only; (b) cap dimensions per group; (c) cap questions per group | (c): `research_questions` (default 2) enforced by the host, since questions drive search time and dimensions are labels |
| Reading material | (a) one `read_file` per file; (b) drop old tool results from the conversation; (c) a host tool reading several listed sources in one call | (c): `read_sources` reads up to 12 listed sources, each retained as its own evidence, truncated at 30k characters; (b) would remove content the collector needs when it writes the description |
| Asking first | (a) host refuses research before a user question; (b) prompt sequencing | (b): the prompt orders read, ask, research; some tasks have no user question, so a host veto would be wrong |

The first validation run showed a second gap: the researcher received the whole research window, so a 477-second
acquisition left no time for quote verification and the review, and the group timed out after succeeding.
`CollectionLimits.verification_reserve` (150 s) is now kept out of the researcher's own timeout, and the research
minimum is 300 s so that a group is only started when acquisition can still get at least 150 s.

Both CLIs expose `--submission-reserve` and `--research-questions`. Acceptance: research is refused inside the reserve
with an instruction to submit; an assignment's `remaining_seconds` excludes the reserve; a group with more questions
than allowed is refused before spending a research call; `read_sources` reads listed sources together, refuses unknown
names and is absent when nothing is listed. A DeepSeek run of one case validates the sequence before Codex is used
again.

Quote verification was tuned for Latin text (2026-10-05): in the OpenRouter collector run the compliance research
group lost three findings whose passages were present, word for word, in the pages they cited. `quoted` refused any
folded passage under 20 characters as "a few words", and a Chinese clause such as a numbered statutory item folds to
9 to 17 characters. `weight` now counts a CJK character as three Latin characters, so a clause passes and a fragment of
a few characters still does not; replaying the saved candidate accepts all seven readable findings. Alongside,
`problems` searches every page the research read and names the page that holds a passage listed under the wrong
source, so a misattribution is corrected by changing the citation rather than researching again.
