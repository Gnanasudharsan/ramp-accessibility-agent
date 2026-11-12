"""Self-check run *inside* the browser container: ``python -m ramp.security.sandbox_check``.

Prints JSON facts about the sandbox and exits non-zero if any expectation fails:
- the root filesystem is read-only and /tmp is writable (tmpfs),
- the process runs as a non-root user with no effective Linux capabilities,
- internal services (Redis, Langfuse, MLflow, Postgres) are unreachable,
- no Ramp or provider secrets are present in the environment.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
from pathlib import Path

INTERNAL = [("redis", 6379), ("langfuse-web", 3000), ("mlflow", 5000), ("postgres", 5432)]
SECRET_NAMES = (
    "GROQ_API_KEY",
    "GEMINI_API_KEY",
    "GITHUB_PERSONAL_ACCESS_TOKEN",
    "LANGFUSE_SECRET_KEY",
    "REDIS_AUTH",
    "HF_TOKEN",
)


def _writable(path: str) -> bool:
    try:
        with tempfile.NamedTemporaryFile(dir=path):
            return True
    except OSError:
        return False


def _reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def _effective_caps() -> str:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("CapEff:"):
            return line.split()[1]
    return "unknown"


def main() -> int:
    root_writable = _writable("/app") or _writable("/")
    tmp_writable = _writable("/tmp")  # noqa: S108 - checking the tmpfs mount itself
    caps = _effective_caps()
    reachable = {f"{h}:{p}": _reachable(h, p) for h, p in INTERNAL}
    secrets = [name for name in SECRET_NAMES if os.environ.get(name)]
    ok = (
        not root_writable
        and tmp_writable
        and os.getuid() != 0
        and caps != "unknown"
        and int(caps, 16) == 0
        and not any(reachable.values())
        and not secrets
    )
    facts = {
        "root_fs_writable": root_writable,
        "tmp_writable": tmp_writable,
        "uid": os.getuid(),
        "effective_capabilities": caps,
        "internal_reachable": reachable,
        "secrets_in_env": secrets,
        "ok": ok,
    }
    print(json.dumps(facts, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
