"""Restore a portable Studio employee once and serve it through native Raven ACP."""

import asyncio
import fcntl
import json
import os
import sys
from pathlib import Path

from experimental.harness.contract import Artifact, Task
from experimental.harness.raven_adapter.baselines import prepare
from experimental.harness.raven_adapter.materialize import _write
from experimental.webui.exporting import decoded, load_package, safe_file
from raven.config import product_render
from raven.config.schema import AgentDefaults
from raven.contracts.path_policy import CONFIG_FILENAME
from raven.home import raven_home


def prepare_employee(
    folder: Path, *, host_path: Path | None = None, root: Path | None = None, home: Path | None = None
):
    """Prepare the existing ACP hosting inputs without copying the host's credentials."""
    package, files = load_package(folder)
    product = f"{package['name']}-{package['sha256'][:12]}"
    root = (
        root or product_render.product_state_root(product, override=os.environ.get("RAVEN_STUDIO_STATE_ROOT"))
    ).resolve()
    home = (
        home or product_render.product_acp_home(product, override=os.environ.get("RAVEN_STUDIO_ACP_HOME"))
    ).resolve()
    work, state = root / "work", root / "state"
    for path in (home, work, state):
        path.mkdir(parents=True, exist_ok=True)
    host_path = host_path or raven_home() / CONFIG_FILENAME
    if not host_path.is_file():
        raise ValueError("configure the host Raven before starting this Studio employee")
    saved = json.loads(files["deployment.json"])
    baseline = prepare(host_path, workdir=work, task=Task.model_validate(saved["task"]), home=home)
    defaults = baseline.config.agents.defaults.model_dump(mode="json", by_alias=True)
    defaults.update(package["options"])
    baseline.config.agents.defaults = AgentDefaults.model_validate(defaults)
    baseline.hosting, baseline.allow_delegation = "acp", False
    marker = root / ".seeded"
    if marker.exists():
        if marker.read_text() != package["sha256"]:
            raise ValueError("this state root belongs to another employee package; choose a new state root")
    else:
        for name, (content, mode) in saved["content"].items():
            path = safe_file(home, name)
            data = decoded(content)
            if data is not None:
                _write(path, data, mode)
            else:
                path.unlink(missing_ok=True)
        for name, content in saved["state"].items():
            path = safe_file(state, name)
            data = decoded(content)
            if data is not None:
                _write(path, data)
            else:
                path.unlink(missing_ok=True)
        for name, data in files.items():
            if name.startswith("uploads/"):
                for target in (home, work):
                    path = safe_file(target, name)
                    if not path.exists():
                        _write(path, data)
        _write(marker, package["sha256"].encode())
    return baseline, Artifact.model_validate(saved["artifact"]), state


async def serve(folder: Path):
    from experimental.harness.raven_adapter.hosting.acp import serve_harness
    from raven.acp.server import install_crash_handlers
    from raven.acp.stdio import claim_stdout
    from raven.cli.acp_commands import _open_stdin

    package, _ = load_package(folder)
    product = f"{package['name']}-{package['sha256'][:12]}"
    root = product_render.product_state_root(product, override=os.environ.get("RAVEN_STUDIO_STATE_ROOT")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("this Studio employee state root is already in use") from None
        install_crash_handlers()
        with claim_stdout() as out:
            baseline, artifact, state = prepare_employee(folder, root=root)
            os.chdir(baseline.workdir)
            async with _open_stdin() as reader:
                await serve_harness(reader, out, baseline, artifact, state)


def main(folder: Path) -> None:
    try:
        asyncio.run(serve(folder))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Studio employee could not start: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
