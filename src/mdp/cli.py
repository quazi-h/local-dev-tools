"""Command-line entry point for Markdown Previewer."""

import os
from pathlib import Path
import subprocess
import sys

import cyclopts

from mdp.app import launch

app = cyclopts.App(name="mdp")
STARTUP_CHECK_SECONDS = 1


@app.default
def open_previewer(files: list[Path] | None = None, debug: bool = False) -> None:
    """Open one or more Markdown files in the local editor and previewer."""
    selected_files = files or []
    for file in selected_files:
        if not file.is_file():
            raise cyclopts.ValidationError(f"Not a file: {file}")
    if debug:
        launch(selected_files)
        return
    _launch_detached(selected_files)


def _launch_detached(files: list[Path]) -> None:
    """Start the foreground launcher in a detached child process.

    A short startup check keeps the normal command detached while reporting a
    child-process failure instead of silently discarding it.
    """
    command = [sys.executable, "-m", "mdp.cli", "--debug", *(str(file) for file in files)]
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
    raise RuntimeError(f"Markdown Previewer could not start:\n{details}")


if __name__ == "__main__":
    app()
