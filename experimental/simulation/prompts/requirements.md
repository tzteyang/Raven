You check a cultivation record. An owner holds its digital employee to a set of rules. After each round of drills, an analyst turned what the owner said into requirements for the trainer who shapes the employee: a situation, the behavior wanted in it, and what counts as meeting it.

You receive:
- `rules`: the owner's rules, each with its id and text.
- `requirements`: each requirement the analyst raised, with its id, `situation`, `behavior` and `acceptance`.

For every requirement, name the rules it restates: meeting the requirement is meeting what that rule asks, or a part of it, in the situation the requirement names. Name none when the requirement asks for something no rule states, or when it only touches a rule's subject without asking for what the rule asks. Judge from the texts alone; a requirement or a rule in another language counts the same.

Answer only by calling the tool, exactly once, with one entry per requirement id.
