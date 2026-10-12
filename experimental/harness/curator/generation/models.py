"""Keep model identity and explicit recovery at completed request boundaries auditable."""


def effective_model(provider, model):
    if model:
        return model
    default = getattr(provider, "get_default_model", None)
    return default() if default else None


def resume_model(state, model, *, previous=None, check=False):
    calls = [row for row in state.trace if row.get("event") == "model.call"]
    if not calls:
        if previous is None or previous == model:
            return None
        raise ValueError("model change requires a recorded failed provider call")
    latest = calls[-1]
    previous = latest.get("model", previous)
    events = [
        row
        for row in state.trace
        if row.get("event")
        in {
            "model.call",
            "model.error",
            "model.changed",
            "model.paused",
        }
    ]
    if events[-1]["event"] == "model.changed":
        previous = events[-1]["model"]
    if previous == model:
        return None
    failure = events[-1]
    if failure["event"] != "model.error" or failure["call"] != latest["call"]:
        raise ValueError("model change requires a recorded failed provider call")
    change = {
        "event": "model.changed",
        "stage": latest["stage"],
        "after_call": latest["call"],
        "previous_model": previous,
        "model": model,
        "reason": failure["error"],
    }
    if not check:
        state.trace.append(change)
        state.messages = []
    return change
