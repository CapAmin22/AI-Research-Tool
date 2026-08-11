# ──────────────────────────────────────────────────────────────────────
# services/runner.py — Async subprocess runner for CLI tools
# ──────────────────────────────────────────────────────────────────────
"""
Thin async wrapper around ``asyncio.create_subprocess_exec``.

Every public function returns a ``CommandResult`` dataclass so the rest
of the application never has to think about subprocesses.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass, field
from typing import Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommandResult:
    """Immutable result of a CLI invocation."""

    command: str
    args: tuple[str, ...]
    stdout: str
    stderr: str
    return_code: int
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.return_code == 0 and not self.timed_out

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "args": list(self.args),
            "stdout": self.stdout,
            "stderr": self.stderr,
            "return_code": self.return_code,
            "timed_out": self.timed_out,
            "ok": self.ok,
        }


async def run(
    command: str,
    args: Sequence[str] = (),
    *,
    timeout: int = 120,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Run *command* with *args* asynchronously and return a ``CommandResult``.

    Parameters
    ----------
    command:
        Absolute path or name of the executable.
    args:
        Positional arguments forwarded to the executable.
    timeout:
        Maximum wall-clock seconds before the process is killed.
    env:
        Optional extra environment variables (merged with ``os.environ``).
    """
    resolved = shutil.which(command) or command
    full_args = (resolved, *args)

    logger.info("Running: %s", " ".join(full_args))

    import os

    merged_env = {**os.environ, **(env or {})}

    try:
        proc = await asyncio.create_subprocess_exec(
            *full_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=merged_env,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        return CommandResult(
            command=command,
            args=tuple(args),
            stdout=stdout_bytes.decode("utf-8", errors="replace").strip(),
            stderr=stderr_bytes.decode("utf-8", errors="replace").strip(),
            return_code=proc.returncode or 0,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        logger.warning("Command timed out after %ds: %s", timeout, " ".join(full_args))
        return CommandResult(
            command=command,
            args=tuple(args),
            stdout="",
            stderr=f"Command timed out after {timeout}s",
            return_code=-1,
            timed_out=True,
        )
    except FileNotFoundError:
        logger.error("Binary not found: %s", resolved)
        return CommandResult(
            command=command,
            args=tuple(args),
            stdout="",
            stderr=f"Binary not found: {resolved}",
            return_code=-1,
        )
    except Exception as exc:
        logger.exception("Unexpected error running %s", resolved)
        return CommandResult(
            command=command,
            args=tuple(args),
            stdout="",
            stderr=str(exc),
            return_code=-1,
        )
