"""Run the worker process as a user who can read nothing of the evaluation, only its own area, a code image and the
system (the cultivation-loop design, section 4.2).

`Confinement.of(user, repository)` builds the image once for its content (`image`): the code the worker process
imports, copied from `repository` by a whitelist (`FILES`, `TREES`, `EXPERIMENTAL`), with an environment uv syncs
from the lock file and an interpreter the user can run, copied from this one. Nothing else of the repository is in
it: no scenario, drill card, note, document, test or `.git`. The launcher (`launch.Process`) starts the process from
the image as the user, with `options`; the worker hands the user its area and working directory before every start
and operation (`hand_over`) and gives the process its data with the repository's paths moved into the image
(`translate`). `probe` runs as the user and reports what it must reach and cannot, and what it reaches and must not.
"""

import fcntl
import hashlib
import json
import os
import pwd
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

IMAGES = Path("/opt/raven-worker")
READY = ".ready"
FILES = ("pyproject.toml", "uv.lock", "README.md", "LICENSE", "NOTICES.md", "hatch_build.py")
TREES = ("raven", "agents", "plugins-dist", "bridge", "LICENSES")
EXPERIMENTAL = (
    "__init__.py",
    "audience.py",
    "requirements.py",
    "curator",
    "scenario",
    "iteration/__init__.py",
    "iteration/compartment.py",
)
PASSED = (
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "PYTHONTZPATH",
    "TERM",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "all_proxy",
)
SYSTEM_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
SKIPPED = frozenset({"__pycache__", ".pytest_cache", ".ruff_cache", "node_modules"})


def selected(repository: Path) -> list[Path]:
    """The image's files, relative to the repository, in a stable order."""
    repository = Path(repository)
    tops = [
        *FILES,
        *TREES,
        *(f"experimental/{name}" for name in EXPERIMENTAL),
    ]
    found = []
    for top in tops:
        path = repository / top
        if path.is_file():
            found.append(Path(top))
        elif path.is_dir():
            for folder, names, files in os.walk(path):
                names[:] = sorted(name for name in names if name not in SKIPPED)
                found.extend(Path(folder, name).relative_to(repository) for name in sorted(files))
        elif top not in ("LICENSES", "NOTICES.md", "bridge"):
            raise FileNotFoundError(f"the worker image needs {top} from the repository {repository}")
    return found


def digest(repository: Path, files: list[Path]) -> str:
    total = hashlib.sha256(f"{sys.version_info[:3]}".encode())
    for name in files:
        total.update(name.as_posix().encode() + b"\0")
        total.update(hashlib.sha256((Path(repository) / name).read_bytes()).digest())
    return total.hexdigest()


def interpreter(images: Path) -> Path:
    """A copy of this interpreter's installation that any user can run, made once per version."""
    version = "python-{}.{}.{}".format(*sys.version_info[:3])
    target = images / version
    executable = target / "bin" / f"python{sys.version_info[0]}.{sys.version_info[1]}"
    if not executable.is_file():
        staging = Path(tempfile.mkdtemp(prefix=f".{version}-", dir=images))
        shutil.copytree(sys.base_prefix, staging / "python", symlinks=True)
        _readable(staging)
        (staging / "python").rename(target)
        staging.rmdir()
    return executable


def image(repository: Path, images: Path = IMAGES) -> Path:
    """The code image of `repository` (see the module's description), built under `images` unless it exists."""
    repository, images = Path(repository).resolve(), Path(images)
    images.mkdir(parents=True, exist_ok=True)
    images.chmod(0o755)
    files = selected(repository)
    target = images / digest(repository, files)[:16]
    with open(images / f"{target.name}.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (target / READY).is_file():
            return target
        if target.exists():
            shutil.rmtree(target)
        for name in files:
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repository / name, destination)
        uv = shutil.which("uv")
        if uv is None:
            raise FileNotFoundError("building the worker image needs uv")
        environment = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(target / ".venv")}
        environment.pop("VIRTUAL_ENV", None)
        for command in (
            [uv, "venv", "--quiet", "--python", str(interpreter(images)), str(target / ".venv")],
            [uv, "sync", "--quiet", "--frozen", "--all-extras", "--link-mode", "hardlink"],
        ):
            done = subprocess.run(command, cwd=target, env=environment, capture_output=True, text=True)
            if done.returncode:
                raise RuntimeError(f"building the worker image failed: {' '.join(command)}: {done.stderr[-2000:]}")
        _readable(target)
        (target / READY).write_text(json.dumps({"repository": str(repository), "files": len(files)}))
        (target / READY).chmod(0o644)
    return target


def _readable(top: Path):
    for folder, names, files in os.walk(top):
        os.chmod(folder, os.stat(folder).st_mode | 0o755)
        for name in files:
            path = Path(folder, name)
            if not path.is_symlink():
                path.chmod(path.stat().st_mode | 0o444)


@dataclass(frozen=True)
class Confinement:
    """Who the worker process runs as (`user`, with `uid` and `gid`), from which image, mirroring which repository."""

    user: str
    uid: int
    gid: int
    image: Path
    repository: Path

    @classmethod
    def of(cls, user: str, repository: Path, images: Path = IMAGES) -> "Confinement":
        if os.geteuid() != 0:
            raise PermissionError("confining the worker to another user needs root")
        try:
            entry = pwd.getpwnam(user)
        except KeyError as exc:
            raise ValueError(f"no user {user!r} on this machine; create it first (see experimental/README.md)") from exc
        if entry.pw_uid == 0:
            raise ValueError("the worker's user must not be root")
        repository = Path(repository).resolve()
        return cls(user, entry.pw_uid, entry.pw_gid, image(repository, images), repository)

    @property
    def python(self) -> Path:
        return self.image / ".venv" / "bin" / "python"

    def environment(self, area: Path) -> dict[str, str]:
        area = Path(area)
        (area / "tmp").mkdir(parents=True, exist_ok=True)
        self.hand_over(area)
        return {
            **{name: os.environ[name] for name in PASSED if name in os.environ},
            "HOME": str(area),
            "TMPDIR": str(area / "tmp"),
            "USER": self.user,
            "LOGNAME": self.user,
            "PATH": f"{self.image / '.venv' / 'bin'}:{SYSTEM_PATH}",
            "VIRTUAL_ENV": str(self.image / ".venv"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    def options(self, area: Path) -> dict:
        """What `subprocess.Popen` needs to start a process as the user in `area`."""
        return {
            "user": self.uid,
            "group": self.gid,
            "extra_groups": [],
            "env": self.environment(area),
            "cwd": str(area),
        }

    def translate(self, value):
        """`value` with every path into the repository moved to the same path in the image."""
        if isinstance(value, str):
            source, target = str(self.repository), str(self.image)
            return target if value == source else value.replace(source + os.sep, target + os.sep)
        if isinstance(value, dict):
            return {key: self.translate(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return type(value)(self.translate(item) for item in value)
        return value

    def hand_over(self, *paths: Path):
        """Give the user every entry under `paths` it does not own yet; links are changed, never followed."""
        for top in paths:
            top = Path(top)
            if not top.exists() and not top.is_symlink():
                continue
            self._own(top)
            if top.is_symlink() or not top.is_dir():
                continue
            for folder, names, files in os.walk(top):
                for name in (*names, *files):
                    self._own(Path(folder, name))

    def _own(self, path: Path):
        status = os.lstat(path)
        if (status.st_uid, status.st_gid) != (self.uid, self.gid):
            os.chown(path, self.uid, self.gid, follow_symlinks=False)

    def probe(self, *, writable=(), unlisted=(), closed=()) -> list[str]:
        """Run as the user from the image: what of `writable` it cannot write, which of the folders `unlisted` it can
        list, what of `closed` it can list, enter or read, and whether the worker imports; empty when all is as it
        must be."""
        area = Path(tempfile.mkdtemp(prefix="raven-confinement-probe-"))
        try:
            request = json.dumps(
                {
                    name: [str(path) for path in paths]
                    for name, paths in (("writable", writable), ("unlisted", unlisted), ("closed", closed))
                }
            )
            done = subprocess.run(
                [str(self.python), "-m", "experimental.curator.raven_adapter.confinement", request],
                capture_output=True,
                text=True,
                timeout=120,
                **self.options(area),
            )
        finally:
            shutil.rmtree(area, ignore_errors=True)
        if done.returncode:
            return [f"the probe could not run as {self.user}: {done.stderr[-1500:]}"]
        return json.loads(done.stdout)


def _probe(request: dict) -> list[str]:
    said = []
    try:
        import experimental.curator.raven_adapter.worker  # noqa: F401 -- the probe checks that the image imports it
    except Exception as exc:  # noqa: BLE001 -- any failure means the worker cannot start from this image
        said.append(f"the worker does not import from the image: {exc!r}")
    for path in map(Path, request["writable"]):
        try:
            descriptor, name = tempfile.mkstemp(dir=path)
            os.close(descriptor)
            os.unlink(name)
        except OSError as exc:
            said.append(f"cannot write {path}: {exc.strerror}")
    for path in map(Path, request["unlisted"]):
        if os.access(path, os.R_OK):
            said.append(f"can list {path}")
    for path in map(Path, request["closed"]):
        reached = []
        if path.is_dir():
            if os.access(path, os.R_OK):
                reached.append("list")
            if os.access(path, os.X_OK):
                reached.append("enter")
        elif os.access(path, os.R_OK):
            reached.append("read")
        if reached:
            said.append(f"can {' and '.join(reached)} {path}")
    return said


if __name__ == "__main__":
    print(json.dumps(_probe(json.loads(sys.argv[1]))))
