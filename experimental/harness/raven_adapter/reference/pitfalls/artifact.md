# Known pitfalls: the submitted artifact

These are facts about host validation, not instructions for this task: host checks that earlier curations failed more than once, mined from 373 curation records of 96 runs up to 2026-09-29, with how often each recurred. Each one cost at least one extra call or a repair round. The host's contract is the authority; this page only says where authors went wrong before.

- **`values` is an object.** `check_candidate` and `submit_artifact` take `values` as a JSON object keyed by exact target names, never as a string that contains JSON (10 failures in 2 runs; one curation never recovered).
- **Targets are keys inside `values`.** Each selected target is a key of `values` itself (`values["planning.strategy"]`), neither nested by layer nor placed beside `values` at the artifact's top level (4 failures in 3 runs).
- **Every artifact carries `values`.** `files` only supplies module sources and assets; an artifact with files and no `values` is refused (4 failures in 3 runs).
- **A check covers the whole artifact.** `check_candidate` validates the complete candidate: supply a value or an explicit removal for every selected target, not only the one being tried (2 failures in 2 runs).
- **A referenced module travels with the artifact.** Every module a value names as `module:attribute` must be staged with `stage_file` or carried in the artifact's `files` before checking or submitting, unless it is already authored. Writing it with a shell command does not deliver it, and a check that reports the module missing is not fixed by saying it was added (7 failures in 2 runs; the only curation that exhausted its repair budget failed this way six times).
