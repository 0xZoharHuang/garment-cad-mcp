from __future__ import annotations

import fcntl
from pathlib import Path
from types import TracebackType

from garmentcad.errors import ProjectLockedError


class ProjectLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._stream = None

    def acquire(self, blocking: bool = False) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = self.path.open("a+")
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(self._stream.fileno(), flags)
        except BlockingIOError as exc:
            self._stream.close()
            self._stream = None
            raise ProjectLockedError(f"Project is already being modified: {self.path}") from exc

    def release(self) -> None:
        if self._stream is not None:
            fcntl.flock(self._stream.fileno(), fcntl.LOCK_UN)
            self._stream.close()
            self._stream = None

    def __enter__(self) -> ProjectLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()
