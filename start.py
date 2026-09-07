#!/usr/bin/env python3
"""Start the trading desk. This is the only file you need to run.

    python3 start.py

It sets up everything on first run — a private Python environment, the
libraries, a config file — then starts the desk in paper mode (pretend money)
and opens the dashboard in your browser.

Nothing here touches real money. Real trading needs a separate, deliberate
step you take later, from the Settings screen.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import venv
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV = HERE / ".venv"
CONFIG = HERE / "desk.config.json"
EXAMPLE = HERE / "desk.config.example.json"
ENV_FILE = HERE / ".env"
MIN_PYTHON = (3, 9)
PORT = 8787

GREEN, YELLOW, RED, DIM, BOLD, RESET = (
    "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"
)
if platform.system() == "Windows" and not os.environ.get("WT_SESSION"):
    GREEN = YELLOW = RED = DIM = BOLD = RESET = ""


def say(message: str = "") -> None:
    print(message, flush=True)


def step(number: int, total: int, message: str) -> None:
    say(f"{DIM}[{number}/{total}]{RESET} {message}")


def die(message: str, fix: str = "") -> None:
    say(f"\n{RED}Stopped:{RESET} {message}")
    if fix:
        say(f"{YELLOW}What to do:{RESET} {fix}")
    say("")
    if platform.system() == "Windows":
        input("Press Enter to close this window. ")
    raise SystemExit(1)


def venv_python() -> Path:
    """Where the private environment's Python lives on this OS."""
    if platform.system() == "Windows":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def running_inside_venv() -> bool:
    try:
        return Path(sys.executable).resolve() == venv_python().resolve()
    except OSError:
        return False


def ensure_venv() -> None:
    """Create a private Python environment so nothing else on the PC changes."""
    if venv_python().exists():
        return
    say(f"    {DIM}first run — building a private Python environment...{RESET}")
    try:
        venv.EnvBuilder(with_pip=True, clear=False).create(VENV)
    except Exception as exc:
        die(
            f"could not create a Python environment ({exc}).",
            "On Debian or Ubuntu, run:  sudo apt install python3-venv",
        )
    if not venv_python().exists():
        die("the Python environment was created but looks incomplete.",
            f"Delete the folder {VENV} and run this again.")


def pip_install(args: list[str], label: str) -> bool:
    result = subprocess.run(
        [str(venv_python()), "-m", "pip", "install", "--quiet", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        say(f"    {YELLOW}could not install {label}{RESET}")
        tail = (result.stderr or result.stdout or "").strip().splitlines()
        for line in tail[-3:]:
            say(f"    {DIM}{line}{RESET}")
        return False
    return True


def ensure_libraries() -> None:
    marker = VENV / ".installed"
    requirements = HERE / "requirements.txt"
    if marker.exists() and marker.read_text().strip() == _requirements_stamp(requirements):
        return
    say(f"    {DIM}downloading the libraries the desk needs (once, ~30s)...{RESET}")
    if not pip_install(["-r", str(requirements)], "the core libraries"):
        die("the libraries could not be downloaded.",
            "Check your internet connection and run this again.")
    marker.write_text(_requirements_stamp(requirements))


def _requirements_stamp(requirements: Path) -> str:
    try:
        return requirements.read_text().strip()
    except OSError:
        return ""


def ensure_config() -> None:
    if CONFIG.exists():
        return
    if EXAMPLE.exists():
        shutil.copyfile(EXAMPLE, CONFIG)
    else:
        CONFIG.write_text(json.dumps({"starting_capital_usd": 100.0}, indent=2))
    say(f"    {DIM}created {CONFIG.name} — you can change everything from the browser{RESET}")


def protect_env_file() -> None:
    """Make .env unreadable to other accounts on this machine.

    That file holds wallet keys. On a shared or work computer, default
    permissions would let any other user on the box read it.
    """
    if not ENV_FILE.exists() or platform.system() == "Windows":
        return
    try:
        ENV_FILE.chmod(0o600)
    except OSError:
        pass


def load_env_file() -> None:
    """Read KEY=value lines from .env into this process's environment.

    Deliberately never printed, never logged, and never written anywhere else.
    """
    if not ENV_FILE.exists():
        return
    for raw in ENV_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    # Only the process that actually starts the desk prints the banner. This
    # script re-launches itself inside a private environment, so the test is
    # "am I already in it" — anything else prints the header twice and looks
    # like something crashed and restarted.
    if running_inside_venv():
        say(f"\n{BOLD}Trading Desk{RESET}")
        say(f"{DIM}{'─' * 46}{RESET}")

    if sys.version_info < MIN_PYTHON:
        die(
            f"this needs Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer "
            f"(you have {sys.version_info.major}.{sys.version_info.minor}).",
            "Install the latest Python from https://python.org/downloads and try again.",
        )

    total = 4
    first_run = not venv_python().exists()
    if first_run:
        say(f"\n{BOLD}Setting up — this happens once and takes about a minute.{RESET}\n")

    if not running_inside_venv():
        ensure_venv()
        ensure_libraries()
        # Re-launch inside the private environment so the libraries are found.
        environment = {**os.environ, "DESK_RELAUNCHED": "1"}
        return subprocess.call(
            [str(venv_python()), str(Path(__file__).resolve()), *sys.argv[1:]],
            env=environment,
        )

    step(1, total, "Checking Python... ok")
    step(2, total, "Setting up")
    ensure_libraries()
    say("    ready")

    step(3, total, "Loading your settings")
    ensure_config()
    protect_env_file()
    load_env_file()
    say("    ready")

    step(4, total, "Starting the desk")
    sys.path.insert(0, str(HERE))
    from trading_desk.cli import main as desk_main

    url = f"http://127.0.0.1:{PORT}"
    say("")
    say(f"  {GREEN}{BOLD}Dashboard:{RESET} {BOLD}{url}{RESET}")
    say(f"  {DIM}Opening it in your browser now. If it doesn't open, click the link above.{RESET}")
    say(f"  {DIM}This window must stay open. Press Ctrl-C here to stop the desk.{RESET}")
    say("")

    try:
        # Give the server a moment to bind before the browser asks for the page.
        import threading

        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    except Exception:
        pass

    argv = ["-c", str(CONFIG), "serve", "--port", str(PORT)] + sys.argv[1:]
    return desk_main(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        say(f"\n{DIM}Stopped. Your positions and history are saved.{RESET}\n")
