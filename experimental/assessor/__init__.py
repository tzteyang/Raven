"""The Assessor role: whoever holds a standard the worker never sees and measures each round against it.

The standard (criteria, materials, references, held-out cases) is the assessor's own state; the loop sees only the
`Signal` it returns. `role.Assessor` is the protocol; `human` and `dataset` are the generic implementations,
`standard` holds the evaluation side's `Standard` and the automatic Assessor judged by a model, and the simulated
owner (`experimental.simulation.agency`) is the scenario's.
"""
