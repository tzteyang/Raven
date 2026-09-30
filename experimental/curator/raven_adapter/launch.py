"""Start a worker process and hand it its arguments over the pipe (see `worker._serve`).

Unconfined, the process runs this interpreter as this user and takes this process's module path, as a spawned
multiprocessing child would. Confined (`confinement.Confinement`), it runs the image's interpreter as the
confinement's user, in the confinement's environment, and keeps its own module path: it imports only the image.
"""

import multiprocessing
import subprocess
import sys
from multiprocessing.connection import Connection
from pathlib import Path

ENTRY = "experimental.curator.raven_adapter.launch"


class Process:
    """The part of `multiprocessing.Process` a worker uses, over a subprocess that reads its arguments from a pipe."""

    def __init__(self, arguments: tuple, *, confinement=None, area: Path | None = None):
        self.arguments, self.confinement, self.area = arguments, confinement, area
        self._popen = None

    def start(self) -> Connection:
        parent, child = multiprocessing.Pipe()
        descriptor = child.fileno()
        if self.confinement is None:
            command, options, path = [sys.executable, "-m", ENTRY, str(descriptor)], {}, list(sys.path)
        else:
            command = [str(self.confinement.python), "-m", ENTRY, str(descriptor)]
            options, path = self.confinement.options(self.area), None
        try:
            self._popen = subprocess.Popen(command, pass_fds=[descriptor], stdin=subprocess.DEVNULL, **options)
        except BaseException:
            parent.close()
            raise
        finally:
            child.close()
        try:
            parent.send(path)
            parent.send(self.arguments)
        except BaseException:
            parent.close()
            self._popen.kill()
            self._popen.wait()
            raise
        return parent

    @property
    def pid(self):
        return self._popen.pid

    @property
    def exitcode(self):
        return self._popen.poll()

    def is_alive(self) -> bool:
        return self._popen is not None and self._popen.poll() is None

    def join(self, timeout=None):
        try:
            self._popen.wait(timeout)
        except subprocess.TimeoutExpired:
            pass

    def terminate(self):
        self._popen.terminate()

    def kill(self):
        self._popen.kill()

    def close(self):
        if self._popen is not None and self._popen.poll() is None:
            raise ValueError("cannot close a worker process that is still running")


def main():
    connection = Connection(int(sys.argv[1]))
    path = connection.recv()
    if path is not None:
        sys.path[:] = path
    from .worker import _serve

    _serve(connection, *connection.recv())


if __name__ == "__main__":
    main()
