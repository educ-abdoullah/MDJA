"""Creer un instantane local versionne puis un clone propre, sans toucher au depot source."""

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True,
    ).stdout


def main():
    root = Path(__file__).resolve().parents[1]
    destination = root / ".validation" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    snapshot = destination / "snapshot"
    snapshot.mkdir(parents=True)
    paths = git("ls-files", "-z", "--cached", "--others", "--exclude-standard", cwd=root)
    for raw_path in paths.decode("utf-8").split("\0"):
        if not raw_path:
            continue
        relative = Path(raw_path)
        if relative.parts[0] in {".env", ".git", ".venv", ".validation", "logs"}:
            raise ValueError(f"Fichier sensible dans l'instantane : {relative}")
        source = root / relative
        if not source.is_file():
            continue
        if relative.parts[0] == "Docs":
            relative = Path("docs", *relative.parts[1:])
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    git("init", "-b", "codex/td2-livrable", cwd=snapshot)
    git("-c", "core.autocrlf=false", "add", ".", cwd=snapshot)
    git("-c", "user.name=MDJA validation", "-c", "user.email=validation@example.invalid",
        "commit", "-m", "Instantane local de validation du livrable", cwd=snapshot)
    clone = destination / "clone"
    git("clone", "--no-hardlinks", str(snapshot), str(clone), cwd=root)
    if (clone / ".env").exists() or (clone / ".venv").exists():
        raise AssertionError("Le clone ne doit pas recuperer l'environnement local")
    print(json.dumps({"clone": str(clone), "snapshot": str(snapshot),
                      "sha": git("rev-parse", "HEAD", cwd=clone).decode().strip()}))


if __name__ == "__main__":
    main()
