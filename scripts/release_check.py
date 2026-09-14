"""Verify the founder-facing offline release without Airtable credentials."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "fixtures" / "clean_snapshot.json"
AS_OF = "2025-02-01"
REQUIRED = {
    "briefing.json",
    "briefing.md",
    "briefing.html",
    "findings.json",
    "findings.csv",
    "findings.md",
    "memo.md",
    "candidate_actions.json",
}
SECRET_MARKERS = ("Bearer pat", "GEMINI_API_KEY=", "secret-token")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="recruitment-release-") as temp:
        env_root = Path(temp) / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(env_root)
        env_python = env_root / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        subprocess.run(
            [str(env_python), "-m", "pip", "install", "-e", ".[dev]"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        output = Path(temp) / "outputs"
        command = [
            str(env_python),
            "-m",
            "recruitment_intelligence.cli",
            str(SNAPSHOT),
            "--as-of",
            AS_OF,
            "--output-dir",
            str(output),
        ]
        subprocess.run(command, cwd=ROOT, check=True)
        actual = {path.name for path in output.iterdir()}
        missing = REQUIRED - actual
        if missing:
            raise SystemExit(f"release check failed: missing artifacts: {sorted(missing)}")
        first = {name: (output / name).read_bytes() for name in REQUIRED}
        subprocess.run(command, cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        for name, content in first.items():
            if content != (output / name).read_bytes():
                raise SystemExit(f"release check failed: non-reproducible artifact: {name}")
        for path in output.iterdir():
            text = path.read_text(encoding="utf-8")
            if any(marker in text for marker in SECRET_MARKERS):
                raise SystemExit(f"release check failed: secret marker found in {path.name}")
        payload = json.loads((output / "briefing.json").read_text(encoding="utf-8"))
        if "findings" not in payload or "quality_warnings" not in payload:
            raise SystemExit("release check failed: briefing contract is incomplete")
    print("release check passed: clean install, deterministic offline run, artifacts, and secret audit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
