# Capability strategy on Raven

capability.strategy uses CapabilityBinding and public prepare/register/select. Its factory may declare keyword-only registrar and host dependencies. The host is a CapabilityHost for typed native setup. Selection uses the session checkpoint. Candidate preparation and registration have a separate lifetime; private preparation attributes are not session state. See [preparation](preparation.md).

## Resources and Curator input

Produce resources in the strategy's prepare method or its _prepare_tools/_prepare_skills helpers and submit them through register. The binding has no resources field. A ToolContribution references an inert factory or a host-resolved declared interaction. Set native_context=True when a factory needs native PluginContext; its construction is deferred until those services exist. The actual native Tool supplies its schema.

For a SkillContribution, provide source and authored package-relative files, an inspected SkillPackage reference, or explicit text edits to such a package. SKILL.md is required. The contribution name must agree with native discovery. worker.skill_packages contains inspectable upload package roots, digests, file lists and entry source identifiers. Use the listed root, relative to agent home, and exact digest. Exploration scratch paths are not durable package references. Read the entry and relevant supporting material before deciding adoption.

Worker.stage_skill_package is the host upload entry: it preserves complete contents in uploads without installing them. Curator explicitly adopts the package through a candidate. Normal documents may instead be turned into authored Skill files. Missing business facts remain gaps.

The materializer preserves nested files, binary assets, empty directories and executable modes without running scripts. Selected packages are immutable resource versions. Actual adoption is checked again against the digest. Native file consumers receive read access to managed packages; this does not grant arbitrary execution permission.

## Registration and actual use

Memory, Planning and Action tools use the same public registration path. If no custom Capability class is selected, the host's base implementation registers approved contributions and delegates native selection. It does not independently adopt uploads.

Receipts distinguish staged, unchanged and rejected. Closed candidates cannot receive new registrations. Tool name collisions and invalid handlers fail before native installation. A new complete resource set is installed into a new runtime; obsolete Skill files do not remain in its discovery roots. Failed activation preserves the previous runtime and checkpoints.

Selection names offered tools and available native Skills. None delegates and an empty tuple selects nothing. Explicit Skill delivery replaces native skill-source contributions for that call and has a real body/catalogue consumer. Native protection can restore root delegation definitions; EffectiveCapabilities records the resulting final tool view before Memory composition. Selection never bypasses permissions.
