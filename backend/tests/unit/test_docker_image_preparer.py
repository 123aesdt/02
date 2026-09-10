import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOCKER_IMAGE_PREPARER = PROJECT_ROOT / "scripts" / "ensure-docker-images.ps1"


def test_present_image_is_reused_without_remote_pull(tmp_path: Path) -> None:
    docker_log = tmp_path / "docker.log"
    fake_docker = tmp_path / "docker.cmd"
    fake_docker.write_text(
        "@echo off\n"
        "echo %*>>\"%CF_DOCKER_LOG%\"\n"
        "if \"%1 %2\"==\"image inspect\" exit /b 0\n"
        "if \"%1\"==\"pull\" exit /b 0\n"
        "exit /b 0\n",
        encoding="ascii",
    )
    environment = os.environ.copy()
    environment["CF_DOCKER_LOG"] = str(docker_log)

    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(DOCKER_IMAGE_PREPARER),
            "-DockerCommand",
            str(fake_docker),
            "-Images",
            "neo4j:5.26-community",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    calls = docker_log.read_text(encoding="utf-8")
    assert "image inspect neo4j:5.26-community" in calls
    assert "pull neo4j:5.26-community" not in calls
    assert "使用本地已有镜像" in result.stdout
