"""把 Studio 培养出来的员工导出成一个 Raven agent 文件夹，放进宿主 Raven 的 agents 目录就会被自动发现、按 ACP 派活。

  uv run python experts/common/export.py <案例目录> <agents 目录> [会话 id]

不给会话 id 就用案例目录里 session.txt 记的那个；会话 id 写 plain，导出的是没培养过的 plain Raven（空 Harness、没有
策略状态，只带同一份任务说明），用来在同一条派活链路上量“培养前”；写 v0，导出的是会话入职那次改造后、第一轮培养前的版本
（取自会话第一份改造记录，策略状态是入职时的空状态），用来把“入职改造”和“培养轮次”的作用分开量。导出的是这个会话 Studio 保存的版本（deployment.json，Studio 每次
改造后都会保存当前装着的版本），文件夹名 expert-<案例名>：
- subagent.json：花名册这一行，宿主的模型按 description / owns 决定把什么活派给它（取自案例目录的 manifest.json）；
- harness.json：培养出来的 Harness（artifact）、它的策略状态文件（记忆、计划等）和任务，取自 Studio 保存的版本；
- config.json：培养时员工用的模型设置，不含任何 key，启动时从宿主 Raven 的配置借 providers；
- run.py：启动器，渲染配置、第一次启动时放好策略状态，再用 Raven 的 Harness 托管入口在 stdio 上提供 ACP 服务。
"""

import base64
import hashlib
import json
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))

from experimental.curator.raven_adapter.deployment import _digest  # noqa: E402


RUN = '''#!/usr/bin/env python
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
PRODUCT = __PRODUCT__
try:
    import raven
except ImportError as exc:
    sys.exit(f"[{PRODUCT}] start this agent with the Python of a Raven source checkout: {exc}")
# A source checkout keeps experimental/ beside the raven package.
REPOSITORY = Path(raven.__file__).resolve().parents[1]
if not (REPOSITORY / "experimental" / "curator").is_dir():
    sys.exit(f"[{PRODUCT}] {REPOSITORY} is not a Raven source checkout with experimental/")
sys.path.insert(0, str(REPOSITORY))

from raven.config import product_render as render  # noqa: E402

# The rendered settings carry the host's provider keys, so they stay beside the host's own configuration file.
PRIVATE = (render.raven_home() / render.CONFIG_FILENAME).resolve().parent / "expert-runtime"


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
'''


def export(case: Path, agents: Path, session: str | None = None) -> Path:
    live = json.loads((case / "live.json").read_text())
    root = (case / live["root"]).resolve()
    session = session or (case / "session.txt").read_text().strip()
    if session == "plain":
        task = (case / live["scenario"] / "profile.md").read_text().strip()
        saved = {"artifact": {"values": {}, "files": {}, "remove": [], "remove_files": []}, "state": {},
                 "task": {"text": task, "id": f"plain-{case.name}"}, "revision": "plain", "children": {}}
        saved["sha256"] = _digest(saved)
    elif session == "v0":
        run = root / "runs" / (case / "session.txt").read_text().strip()
        record = json.loads(next((run / "iteration").glob("*.json")).read_text())
        first = json.loads((run / "curation" / record["initial_curation"][0]).read_text())
        task = json.loads((run / "deployment.json").read_text())["task"]
        empty = {"assembly/content-state.json": {"files": {}, "released": {}}, "capability.json": {"data": {}, "task_id": task["id"]}}
        state = {name: base64.b64encode(json.dumps(empty[name]).encode()).decode() if name in empty else None
                 for name in ("assembly/content-state.json", "memory.json", "planning.json", "capability.json", "action.json")}
        saved = {"artifact": first["generated"]["candidate"]["artifact"], "state": state, "task": task, "revision": "v0",
                 "children": {}}
        saved["sha256"] = _digest(saved)
    else:
        saved = json.loads((root / "runs" / session / "deployment.json").read_text())
    if _digest({key: item for key, item in saved.items() if key != "sha256"}) != saved.get("sha256"):
        raise ValueError("the saved deployment does not match its checksum")
    if saved["children"]:
        raise ValueError("a delegating employee cannot be exported as a single agent")
    manifest = json.loads((case / "manifest.json").read_text())
    name, description, owns = manifest["name"], manifest["description"], manifest["owns"]
    product = f"expert-{case.name}"
    folder = agents / product
    folder.mkdir(parents=True, exist_ok=True)
    trained = json.loads((case / live["config"]).resolve().read_text())
    config = {key: value for key, value in trained.items() if key != "providers"}
    config["agents"] = {"defaults": {k: v for k, v in trained["agents"]["defaults"].items() if k != "workspace"}}
    harness = {
        "artifact": saved["artifact"], "state": saved["state"], "task": saved["task"], "revision": saved["revision"],
        "source": {"case": case.name, "session": session, "deployment_sha256": saved["sha256"]},
    }
    (folder / "harness.json").write_text(json.dumps(harness, ensure_ascii=False, indent=1))
    (folder / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2))
    (folder / "subagent.json").write_text(json.dumps({
        "name": name, "kind": "acp", "description": description, "owns": owns, "enabled": True,
        "command": "{PYTHON} {SUBAGENT_DIR}/run.py", "cwd": "{SUBAGENT_DIR}", "readyTimeoutMs": 180000,
        "timeout": None, "maxOutputChars": 60000,
    }, ensure_ascii=False, indent=2))
    run = RUN.replace("__PRODUCT__", repr(product))
    (folder / "run.py").write_text(run)
    digest = hashlib.sha256(json.dumps(harness["artifact"], sort_keys=True).encode()).hexdigest()[:12]
    print(f"exported {product} (revision {saved['revision'][:12]}, artifact {digest}) to {folder}")
    return folder


if __name__ == "__main__":
    export(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), sys.argv[3] if len(sys.argv) > 3 else None)
