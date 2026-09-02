"""Exercise the real CountyFlowDependencyDown pending/firing/resolved lifecycle."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path


def compose(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        [os.environ["DOCKER_COMMAND"], "compose", "--env-file", os.environ["COMPOSE_ENV_FILE"], *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or "Docker Compose command failed")
    return result.stdout


def alert_state() -> str | None:
    raw = compose("exec", "-T", "prometheus", "wget", "-qO-", "http://localhost:9090/api/v1/alerts", check=False)
    if not raw:
        return None
    for alert in json.loads(raw).get("data", {}).get("alerts", []):
        if alert.get("labels", {}).get("alertname") == "CountyFlowDependencyDown" and alert.get("labels", {}).get("dependency") == "neo4j":
            return str(alert.get("state"))
    return None


def wait_for(expected: str | None, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = alert_state()
        if state == expected:
            return datetime.now(UTC).isoformat()
        time.sleep(2)
    raise RuntimeError(f"Timed out waiting for CountyFlowDependencyDown state {expected!r}")


def run(output: Path) -> None:
    states: dict[str, str] = {}
    compose("start", "neo4j")
    wait_for(None, 240)
    compose("stop", "neo4j")
    try:
        states["pending"] = wait_for("pending", 180)
        states["firing"] = wait_for("firing", 240)
    finally:
        compose("start", "neo4j", check=False)
    states["resolved"] = wait_for(None, 240)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "alert": "CountyFlowDependencyDown",
                "dependency": "neo4j",
                "states": states,
                "rule_for_unchanged": "2m",
                "passed": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the real dependency alert lifecycle without changing its for duration")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.output)
    print("Observability alert pending, firing, and resolved states verified.")


if __name__ == "__main__":
    main()
