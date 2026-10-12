#!/usr/bin/env python
"""Launcher for a Studio-cultivated expert: renders its baseline from this folder's settings and the host Raven's
provider block, puts the cultivated strategy state in place on first start, and serves the checked Harness over ACP
on stdio through Raven's Harness hosting entry. stdout belongs to the protocol; diagnostics go to stderr."""

import base64
import json
import hashlib
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY = Path('/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/Raven-port')
PRIVATE = Path('/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/secrets/expert-runtime')
PRODUCT = 'expert-booking-page'
sys.path.insert(0, str(REPOSITORY))

from raven.config import product_render as render  # noqa: E402


def main() -> None:
    harness = json.loads((HERE / "harness.json").read_text())
    config = json.loads((HERE / "config.json").read_text())
    host = render.host_config()
    if not host.get("providers"):
        sys.exit(f"[{PRODUCT}] the host Raven has no providers to lend; configure one first")
    config["providers"] = host["providers"]
    root = render.product_state_root(PRODUCT)
    home, work, state = render.product_acp_home(PRODUCT), root / "work", root / "state"
    for folder in (home, work, state):
        folder.mkdir(parents=True, exist_ok=True)
    config["agents"]["defaults"]["workspace"] = str(home)
    private = PRIVATE / hashlib.sha256(str(root).encode()).hexdigest()[:24]
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    def save_private(path, value):
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream, ensure_ascii=False)
    rendered = private / "config.json"
    save_private(rendered, config)

    from experimental.curator.harness import Task
    from experimental.curator.raven_adapter.baselines import prepare

    baseline = prepare(rendered, workdir=work, task=Task.model_validate(harness["task"]), home=home)
    baseline.hosting, baseline.allow_delegation = "acp", False
    seeded = state / f".seeded-{harness['revision']}"
    if not seeded.exists():
        for name, data in harness["state"].items():
            path = state / name
            if data is None:
                path.unlink(missing_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base64.b64decode(data))
        seeded.touch()
    definition = private / "deployment.json"
    save_private(definition,
        {"baseline": baseline.export(), "artifact": harness["artifact"], "state_dir": str(state), "grants": {}}
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, (str(REPOSITORY), os.environ.get("PYTHONPATH"))))}
    print(f"[{PRODUCT}] serving revision {harness['revision'][:12]} from {definition}", file=sys.stderr)
    os.execve(sys.executable, [sys.executable, "-m", "experimental.curator.raven_adapter.hosting.acp",
                               "--deployment", str(definition)], env)


if __name__ == "__main__":
    main()
