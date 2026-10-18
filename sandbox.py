import subprocess
import tempfile
import uuid
from pathlib import Path

IMAGE = "analyst-sandbox"
TIMEOUT_S = 25
MAX_OUTPUT_CHARS = 3000


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + "\n...[truncated]"


def run_in_sandbox(code: str, csv_path: str) -> dict:
    """Run untrusted, LLM-generated code in a throwaway container.

    Returns: {"ok": bool, "stdout": str, "stderr": str, "chart_path": str | None}
    """
    work = Path(tempfile.mkdtemp(prefix="sbx_"))
    script = work / "script.py"
    script.write_text(code, encoding="utf-8")
    script.chmod(0o644)

    out_dir = work / "out"
    out_dir.mkdir()
    out_dir.chmod(0o777)  # container user is non-root, needs write access

    csv = Path(csv_path).resolve()
    csv.chmod(0o644)

    name = f"sbx_{uuid.uuid4().hex[:8]}"
    cmd = [
        "docker", "run", "--rm", "--name", name,
        "--network", "none",            # no outbound calls
        "--memory", "256m",             # memory cap
        "--cpus", "0.5",                # cpu cap
        "--pids-limit", "64",           # blocks fork bombs
        "--read-only",                  # immutable root filesystem
        "--tmpfs", "/tmp:size=64m",     # scratch space only
        "-e", "MPLBACKEND=Agg",         # headless matplotlib
        "-e", "MPLCONFIGDIR=/tmp",
        "-v", f"{csv}:/data/input.csv:ro",
        "-v", f"{script}:/app/script.py:ro",
        "-v", f"{out_dir}:/output",
        IMAGE, "python", "/app/script.py",
    ]

    try:
        proc = subprocess.run(
    cmd, capture_output=True, text=True, timeout=TIMEOUT_S,
    encoding="utf-8", errors="replace",
)
    except subprocess.TimeoutExpired:
        # killing the docker client does not stop the container, so kill it explicitly
        subprocess.run(["docker", "kill", name], capture_output=True)
        return {
            "ok": False,
            "stdout": "",
            "stderr": f"TimeoutError: code exceeded {TIMEOUT_S}s and was killed",
            "chart_path": None,
        }

    chart = out_dir / "chart.png"
    return {
        "ok": proc.returncode == 0,
        "stdout": _truncate(proc.stdout),
        "stderr": _truncate(proc.stderr),
        "chart_path": str(chart) if chart.exists() else None,
    }
