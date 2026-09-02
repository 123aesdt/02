import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CHECK_SCRIPT = PROJECT_ROOT / "scripts" / "check.ps1"
STEP_NAMES = ("lint.ps1", "test.ps1", "frontend-lint.ps1", "frontend-test.ps1", "frontend-build.ps1")


@pytest.fixture
def gate_tmp_path() -> Path:
    with TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        yield Path(temp_dir)


def _run_gate(tmp_path: Path, *, failing_step: str | None = None, marker_step: str | None = None) -> subprocess.CompletedProcess[str]:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    shutil.copy2(CHECK_SCRIPT, scripts_dir / "check.ps1")
    marker = tmp_path / "later-step-ran.txt"
    for step_name in STEP_NAMES:
        lines: list[str] = []
        if step_name == marker_step:
            marker_literal = str(marker).replace("'", "''")
            lines.append(f"Set-Content -LiteralPath '{marker_literal}' -Value 'ran'")
        exit_code = 7 if step_name == failing_step else 0
        lines.append(f"cmd.exe /c exit {exit_code}")
        (scripts_dir / step_name).write_text("\n".join(lines), encoding="utf-8")

    powershell = shutil.which("powershell.exe")
    assert powershell is not None
    return subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(scripts_dir / "check.ps1")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )


def test_check_script_returns_zero_when_every_step_succeeds(gate_tmp_path: Path) -> None:
    result = _run_gate(gate_tmp_path)

    assert result.returncode == 0, result.stderr


def test_check_script_returns_nonzero_when_a_step_fails(gate_tmp_path: Path) -> None:
    result = _run_gate(gate_tmp_path, failing_step="lint.ps1")

    assert result.returncode == 7


def test_check_script_stops_before_later_steps_can_overwrite_failure(gate_tmp_path: Path) -> None:
    result = _run_gate(gate_tmp_path, failing_step="lint.ps1", marker_step="test.ps1")

    assert result.returncode == 7
    assert not (gate_tmp_path / "later-step-ran.txt").exists()
