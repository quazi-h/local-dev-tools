"""Command-line entry point for Diff Checker Tool."""

import os
from pathlib import Path
import subprocess
import sys

import cyclopts

from dct.app import launch

app = cyclopts.App(name="dct")
STARTUP_CHECK_SECONDS = 1


@app.default
def open_diff_checker(left: Path | None = None, right: Path | None = None, debug: bool = False) -> None:
    """Open two files in the local, tabbed diff checker."""
    for path in (left, right):
        if path is not None and not path.is_file():
            raise cyclopts.ValidationError(f"Not a file: {path}")
    if debug:
        launch(left, right)
        return
    _launch_detached(left, right)


def _launch_detached(left: Path | None, right: Path | None) -> None:
    """Start the foreground launcher in a detached child process.

    A short startup check keeps the normal command detached while reporting a
    child-process failure instead of silently discarding it.
    """
    command = [sys.executable, "-m", "dct.cli", "--debug"]
    if left is not None:
        command.extend(["--left", str(left)])
    if right is not None:
        command.extend(["--right", str(right)])
    if os.name == "nt":
        creationflags = int(getattr(subprocess, "DETACHED_PROCESS", 0)) | int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=creationflags,
        )
    else:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    try:
        process.wait(timeout=STARTUP_CHECK_SECONDS)
    except subprocess.TimeoutExpired:
        return
    stdout, stderr = process.communicate()
    details = stderr.strip() or stdout.strip() or "The app exited during startup without an error message."
    raise RuntimeError(f"Diff Checker Tool could not start:\n{details}")


if __name__ == "__main__":
    app()
