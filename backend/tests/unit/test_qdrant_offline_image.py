import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_qdrant_health_image_builds_without_package_network() -> None:
    result = subprocess.run(
        [
            "docker",
            "build",
            "--network",
            "none",
            "--tag",
            "countyflow-ai-qdrant:offline-test",
            "--file",
            str(PROJECT_ROOT / "infra" / "qdrant.Dockerfile"),
            str(PROJECT_ROOT / "infra"),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
