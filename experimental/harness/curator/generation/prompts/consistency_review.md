# Harness consistency review

## Objective

Inspect the complete effective Harness in the current scope after host validation and before delivery. Identify conflicts between strategies and their shared dependencies, incompatibilities between new and retained behavior, and contradictions between the executable implementation and the current plan or commitments_after. This scope's consistency review does not establish consistency of the final root-and-children composition. Treat the implementation and earlier reasoning as proposals to examine, not proof of correctness.

## Work

Use the complete effective_artifact and registered sources to trace every listed surface's real entry points, inputs, outputs, state lifetime and consumers. Examine three relationships:

- Across strategies: check schemas and arguments, shared state ownership, preparation and tool registration, prompt delivery, failure behavior and operation order. Follow shared helpers to all callers, including strategies not selected for change. The per-file change report names only direct binding references; it does not establish the full impact of shared code.
- Across new and retained behavior: identify intentional changes and verify that retained commitments and native behavior remain supported. A change that works for one consumer may break another. A valid empty result may still lose protected input or required evidence.
- Across design and execution: trace the cooperation promised by the current plan and commitments_after into executable paths. Check that outputs reach their intended consumers and that one strategy does not omit or cancel behavior another relies on.

Ground each inconsistency in concrete implementation or execution evidence. Explain which behavior changes intentionally, which commitments remain supported, and what missing coverage limits the conclusion. Focus on these consistency relationships; code style, optional optimizations and incomplete business improvement alone are not blockers. Legitimate no-change behavior and future task iterations remain valid.

Use the host validation observations as evidence only for paths actually exercised. Their index is supplied; read a full observation with read_observation, giving its row index and the validation event's trace_index from history. Assembly or one successful probe does not establish all business behavior. Identify unverified paths in limitations. Respect the existing information boundaries; consistency review does not grant hidden checks, expected answers or withheld sources.

## Output

Submit one consistency review for the supplied candidate_id through submit_consistency_review. Cover exactly the listed surfaces and explain their cross-strategy interactions. Each issue names affected surfaces, concrete code or execution evidence of the inconsistency, a feasible correction, and whether it blocks this candidate's delivery. Blocking issues include incompatible interfaces, lost retained commitments, contradictory state transitions and behavior promised by the current plan with no executable path.

This stage identifies and explains inconsistencies; do not edit code or change the plan here. The host routes blocking issues to the existing repair stage, where Curator can correct the artifact or explicitly reopen design or selection. Every repaired candidate must pass host validation and receive a fresh consistency review. Submit no blocking issues only when the inspected candidate has none supported by the evidence; do not invent a defect, claim unobserved tests ran or hide uncertainty to finish.
