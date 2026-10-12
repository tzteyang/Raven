# Experimental execution accounting

Experimental runs use Raven-owned instrumentation with the scope and context
propagation patterns used by OpenTelemetry and Langfuse. No external tracing
service or SDK is required.

For native providers the accounting unit is one actual request attempt. Routing wrappers,
logical calls, stages, rounds and runs only group these facts; their aggregates
are never added back into the ledger. Every attempt has a globally unique ID.
Retries create new IDs. Streaming usage replaces a cumulative snapshot under
the same ID, including on cancellation and partial failure.

Each receiver writes a local `execution.sqlite3` shard with owner-only permissions
to keep parent accounting out of confined workers. SQLite transactions and unique
IDs make snapshot replay idempotent. Versions reject stale updates and
equal-version conflicts are errors. Starts commit before requests are sent;
accounting failures are surfaced. A process killed before its final write leaves
a running record, whose outcome and final usage remain unknown. No client can
recover a provider's unreported bill without later reconciliation.

An experimental run binds an immutable context; stage scopes inherit it through
async tasks. Worker commands and ACP prompts carry the run ID, parent operation
and dimensions, never an arbitrary destination path. Each receiver chooses its
own writable shard, preserving experimental confinement. Readers merge shards
by identity, including copied shards, and report unknown usage separately from
explicit zero. Core accounting is independent of detailed prompt tracing.

Validation covers physical request counts independently of the recorder, retry
and fallback, partial streams, cancellation, concurrent attribution, subprocess
propagation, duplicate and out-of-order snapshots, failed writes and abrupt
process exit. Wall time and cumulative attempt duration are separate quantities.

## Entry points and inspection

`experimental.simulation`, `experimental.cultivation`, and the standalone
collector enable accounting for their whole run. The Studio enables it during setup and each interactive Session
step. The steps record their round and revision; Curator stages, structured
exchanges, native Turns and tools add child operations. Accounting also separates
the native Harness's Memory, Planning, Capability and Action
calls at their agent-loop boundaries, including default and replaced modules.
ACP prompt accounting also includes model calls made before the Turn, such as conversation naming.
Delayed worker announcements retain the context in which they were queued.
Validation copies merge their accounting before their temporary directories are
removed.

The experimental run viewer has an **Execution** tab. Its read-only endpoint is
`/api/execution?run=<worker>/<iteration-record>`. Select a stage to inspect its
provider attempts. Totals sum unique attempts, include known usage from failed
attempts, and show missing prices and incomplete usage. Input totals include
cache tokens; fresh input is unknown when an inclusive provider count cannot be
split reliably. The page polls while a run is active. Older runs without these
records display an explicit absence of accounting.

Python callers that assemble workers directly can enclose their setup and
execution in `with raven.observability.execution.run(records_directory):`.
Session methods also establish accounting independently, but cannot retroactively
record work that ran before the Session existed. Accounting does not capture
prompts or credentials.

## Boundaries

Concrete Raven provider adapters are instrumented at their request boundaries:
LiteLLM, Anthropic Messages, OpenAI Responses, Codex Responses and Azure OpenAI.
LiteLLM retries are disabled while execution accounting is active; Raven's own
retry ladder records each attempt. Routing wrappers do not write consumption.
Native image and speech chat calls and Images API requests are recorded at their
HTTP boundary as well, including speech streaming. A video job keeps one submission record through polling;
polls and downloading its output do not create additional consumption records.
The collector's Claude and Codex subprocesses use the same recorder, with an
explicit external-invocation grain. Their internal requests are not counted as
known attempts. A correction is a new invocation; the first invocation's
reported cost is never replaced with the recursive correction total. Claude
subscription equivalents are stored separately from metered USD; an unknown
billing source stays unclassified. Codex's reported total is retained without
inventing an input/output split. Custom integrations still need this boundary;
provider-side retries hidden by a remote gateway cannot be individually observed
by this client.

Amounts here are provider-reported USD, never inferred from a current price list.
The Execution page, experimental cost report and suite budget reader all use
this ledger when present. Historical runs fall back to their old sources.
Budget comparisons preserve the suite's existing rate-based estimate for unpriced
native calls, but derive it from the same unique attempts. The estimate, its full
rate table and content version, and the unpriceable-call count are separate from
reported spend; an estimate never becomes a reported bill. The older
TokenWise file still serves Runtime policies; it is not an input to experimental
accounting and must not be added to its totals.
Missing amounts are unknown, not free. An unfinished attempt after a process exit
has an unknown final outcome, even when some input usage was saved. A later
supplier reconciliation would update the existing identity; this implementation
does not query suppliers for missing bills.

The local SQLite shards must be on writable local storage. A durable-start
failure prevents dispatch, and ledger failures are not treated as retryable model
errors. Read errors produce an explicit unavailable response instead of a partial
total. Copied shards are deduplicated; equal-version conflicts and changes to an
operation's identity are rejected.

## Implementation and acceptance

The implementation has three responsibilities: `execution.py` owns context and
operation lifetime; `provider_usage.py` owns counter normalization;
`ledger.py` owns durable snapshots. `report.py` derives experimental execution and cost views
from the unique consumption records. A stage decorator is only syntax for
`scope`; provider requests use that same recorder directly. Repeated usage
snapshots do not cause extra writes. Counter inconsistencies remain visible
instead of being clamped into a plausible zero.
Each consumption record keeps the provider's cumulative raw usage beside its
canonical counters, including vendor-specific details and explicit nulls.
Aggregates and budget estimates read only the canonical counters; raw usage
is evidence for auditing and future normalization changes, never another bill.

`tests/test_execution_accounting.py` checks independent transport sends, cache
semantics, every native adapter, stream cancellation and repeated frames,
storage failure, identity conflicts and agreement between experimental readers.
`tests/integration/test_execution_accounting_e2e.py` runs actual worker and ACP
processes against a local HTTP server, kills a process after a partial report,
checks temporary validation cleanup, and verifies external CLI corrections and
subscription accounting. The web tests cover unknown values and stage drill-down.

References: [OpenTelemetry instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/),
[context propagation](https://opentelemetry.io/docs/concepts/context-propagation/),
[Langfuse instrumentation](https://langfuse.com/docs/observability/sdk/instrumentation),
[SQLite UPSERT](https://www.sqlite.org/lang_upsert.html).
