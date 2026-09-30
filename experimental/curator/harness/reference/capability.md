# Capability strategy: generation guide

Capability owns candidate resource preparation, registration policy and runtime selection. Tools, readable Skills and existing delegate descriptions have distinct meanings and consumers.

## Registration and selection

register accepts a CapabilityContribution and returns a RegistrationReceipt. Delegate accepted entries to the host-supplied registrar. Exact repeated contributions are unchanged; conflicting identity or a closed candidate is rejected. Registration stages inert resources and never executes tools or grants permissions. The host validates the policy's receipt against actual registration.

select receives SelectionRequest with current offered tools, discovered Skills, delegate descriptions and relevant state. Return CapabilitySelection: None delegates the corresponding native choice, an empty tuple selects nothing, and explicit names must identify available resources. Use SkillSelection to request body or catalogue delivery; source disambiguates duplicate native names.

The host applies remaining native rules before publishing EffectiveCapabilities. Memory and Action read actual views, not staged resources. Tool visibility is not execution permission.

## Curator-mediated Skill resources

Two supported paths meet in the same candidate lifecycle: adopt a complete inspected package by its root and digest, or author Skill files from supplied material. Curator decides adoption, generation, revision and retirement. Uploading a package makes it input, not an installed capability. Binary and nested resources travel by package reference; do not ask a model to reproduce binary bytes.

Every capability change is implemented through capability.strategy code. Its synchronous prepare receives PreparationRequest before native construction. The default preparation calls _prepare_tools and _prepare_skills and passes their proposals through register; override the necessary protected producer or the preparation algorithm. There is no independent resource authoring target. Supporting asset files remain inert until the implementation explicitly adopts them.

A revised preparation produces the complete managed set. Omission of a strategy update preserves its implementation; retiring it removes its effects. Preserve unrelated resources and recover the previous active version when activation fails. A resource's existence is not proof that its body was read or its tool ran.
