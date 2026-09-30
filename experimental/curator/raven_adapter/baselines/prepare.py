"""Prepare native assembly inputs without duplicating a product's rendering rules."""

from dataclasses import dataclass
from pathlib import Path

from raven.config.mode_catalogue import build_mode_catalogue
from raven.config.raven import RavenConfig, load_raven_config
from raven.config.schema import Config
from raven.core.config_stack import load_runtime_config
from raven.spine.turn import Origin

from ...harness import Task


@dataclass
class Baseline:
    """The selected worker's native configuration and hosting conditions.

    `file_roots` and `read_roots`, when either is set, confine Raven's file tools: reads reach the agent home, the
    session's working directory and both sets of roots, writes and edits the home, the working directory and
    `file_roots` only; delivering a file counts as reading it. Both empty leaves Raven's own setting.
    """

    config: Config
    extensions: RavenConfig
    workdir: Path
    origin: Origin = Origin.USER
    resident: bool = True
    task: Task | None = None
    source_roots: tuple[Path, ...] = ()
    mode: str | None = None
    hosting: str = "worker"
    allow_delegation: bool = True
    inherit_model: bool = False
    file_roots: tuple[Path, ...] = ()
    read_roots: tuple[Path, ...] = ()

    def __post_init__(self):
        if self.hosting not in {"worker", "acp"}:
            raise ValueError(f"unsupported runtime hosting: {self.hosting}")
        self.config = self.config.model_copy(deep=True)
        self.config.agents.defaults.workspace = str(self.config.workspace_path.resolve())
        self.extensions = self.extensions.model_copy(deep=True)
        self.extensions.base = self.config
        self.workdir = Path(self.workdir).resolve()
        self.origin = Origin(self.origin)
        self.source_roots = tuple(Path(path).resolve() for path in self.source_roots)
        self.file_roots = tuple(Path(path).resolve() for path in self.file_roots)
        self.read_roots = tuple(Path(path).resolve() for path in self.read_roots)

    def export(self) -> dict:
        return {
            "config": self.config.model_dump(mode="json"),
            "extensions": self.extensions.model_dump(mode="json", exclude={"base"}),
            "workdir": str(self.workdir),
            "source_roots": [str(path) for path in self.source_roots],
            "mode": self.mode,
            "hosting": self.hosting,
            "allow_delegation": self.allow_delegation,
            "inherit_model": self.inherit_model,
            "file_roots": [str(path) for path in self.file_roots],
            "read_roots": [str(path) for path in self.read_roots],
            "origin": self.origin.value,
            "resident": self.resident,
            "task": self.task.model_dump() if self.task else None,
        }

    @classmethod
    def restore(cls, data: dict) -> "Baseline":
        return cls(
            Config.model_validate(data["config"]),
            RavenConfig.model_validate(data["extensions"]),
            Path(data["workdir"]),
            Origin(data["origin"]),
            data["resident"],
            Task.model_validate(data["task"]) if data.get("task") else None,
            tuple(Path(path) for path in data.get("source_roots", ())),
            data.get("mode"),
            data.get("hosting", "worker"),
            data.get("allow_delegation", True),
            data.get("inherit_model", False),
            tuple(Path(path) for path in data.get("file_roots", ())),
            tuple(Path(path) for path in data.get("read_roots", ())),
        )


def prepare(
    config: Path,
    *,
    workdir: Path,
    task: Task | None = None,
    home: Path | None = None,
    source_roots=(),
    mode: str | None = None,
) -> Baseline:
    path = Path(config).expanduser().resolve()
    native = load_runtime_config(str(path), str(home) if home else None)
    catalogue = build_mode_catalogue(native)
    selected = catalogue.default if mode is None else mode
    if selected and catalogue.get(selected) is None:
        raise ValueError(f"mode is not declared by this baseline: {selected}")
    return Baseline(
        native, load_raven_config(path), workdir, task=task, source_roots=tuple(source_roots), mode=selected or None
    )
