"""The Assessor role: whoever holds a standard the worker never sees and measures each round against it.

The standard (criteria, materials, references, held-out cases) is the assessor's own state; the loop sees only the
`Signal` it returns. `role.AssessorProtocol` is the protocol; `human` and `dataset` are the generic implementations,
`builder.RubricBuilder` constructs and revises criteria; `standard` holds the evaluation side's `Standard` and the
automatic `Assessor` that judges with a model. `introspect` asks the
worker to review its own round, and the simulated owner (`experimental.counterpart.owner`) is the case's.
"""
