# Remaining generation budget

- Model calls, including this response: ${calls}
- Exploration tool calls: ${queries}
- Exploration tool calls left in this stage: ${stage_queries} of ${stage_allowance}
- Draft preflight checks: ${checks}
- Repair rounds after failed final validation: ${repairs}

This note supersedes any earlier budget note above it. These counters apply to this entire curation across all stages and revisions. They are separate from the worker's execution limits. Each exploration call in a parallel batch consumes one query. A stage that spends its own allowance is refused further queries and submits from what it has read; the stages after it keep the rest of the pool.

Use the supplied materials and retained evidence before querying again. In selection, establish a plausible direction and submit it; investigate detailed implementation contracts during design. Reserve model calls for design and implementation. Spend queries on concrete uncertainties that affect the current decision, rather than auditing every available mechanism.

${pacing}

When no queries remain, further queries will be refused without ending this curation. Submit from established evidence or report a specific unresolved gap. Do not invent facts to fit the budget. The host still enforces these limits.
