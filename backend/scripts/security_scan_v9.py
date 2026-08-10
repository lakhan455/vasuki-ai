from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

SKIP_FILES = {"backend/scripts/security_scan_v9.py"}

TEXT_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json",
    ".yml", ".yaml", ".md", ".sql", ".ps1", ".txt", ".toml"
}

PATTERNS = [
    ("OpenAI-style secret", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("Supabase secret", re.compile(r"\bsb_secret_[A-Za-z0-9_-]{20,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    (
        "VAPID private key assignment",
        re.compile(r"VAPID_PRIVATE_KEY\s*=\s*[A-Za-z0-9_-]{80,}")
    ),
]

def tracked_files(root: Path) -> list[Path]:
    raw = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "-z"]
    )
    return [
        root / item
        for item in raw.decode("utf-8", errors="replace").split("\0")
        if item
    ]

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    findings: list[str] = []

    for path in tracked_files(root):
        if not path.is_file():
            continue

        rel = path.relative_to(root).as_posix()

        if rel in SKIP_FILES:
            continue

        name = path.name

        if name == ".env" or (
            name.startswith(".env.") and name != ".env.example"
        ):
            findings.append(f"Tracked private env-like file: {rel}")
            continue

        if (
            path.suffix.casefold() not in TEXT_SUFFIXES
            and name != "Dockerfile"
        ):
            continue

        text = path.read_text(
            encoding="utf-8",
            errors="ignore",
        )

        for label, pattern in PATTERNS:
            if pattern.search(text):
                findings.append(f"{label}: {rel}")

    if findings:
        print("Vasuki V9 security scan FAILED")
        for finding in findings:
            print(" -", finding)
        return 1

    print("Vasuki V9 security scan PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
