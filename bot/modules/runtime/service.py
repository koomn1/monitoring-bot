"""Process lifecycle operations used by administrative commands."""

from __future__ import annotations

import asyncio
import os
import signal


def _terminate_process() -> None:
    """Ask the host supervisor to restart the process after graceful shutdown."""
    os.kill(os.getpid(), signal.SIGTERM)


async def request_restart(*, delay_seconds: float = 1.0) -> None:
    """Schedule a graceful process termination for the host to restart.

    The delay gives Telegram a chance to send the confirmation result before the
    process exits. The bot must be run under a supervisor (systemd, Docker,
    Railway, or equivalent) for the process to come back automatically.
    """
    asyncio.get_running_loop().call_later(delay_seconds, _terminate_process)
