"""Demontrer rouge puis vert sur une fixture d'un clone local de validation."""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("clone", type=Path)
    args = parser.parse_args()
    clone = args.clone.resolve()
    if ".validation" not in clone.parts or not (clone / ".git").is_dir():
        parser.error("Utiliser un clone local sous .validation pour preserver le depot de travail")
    fixture = clone / "tests/fixtures/sample_rss.xml"
    original = fixture.read_bytes()
    broken = original.replace("Article récent".encode(), "Article cassé".encode(), 1)
    if original == broken:
        raise ValueError("Fixture attendue introuvable")
    results = {}
    try:
        fixture.write_bytes(broken)
        result = subprocess.run(
            [sys.executable, "infra/check.py"], cwd=clone,
            capture_output=True, text=True, check=False,
        )
        (clone.parent / "red.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        results["red"] = result.returncode
        if result.returncode != 1 or "test_filters_duplicates" not in result.stdout:
            raise AssertionError("Le test du parseur doit echouer avec le code pytest 1")
    finally:
        fixture.write_bytes(original)
    result = subprocess.run(
        [sys.executable, "infra/check.py"], cwd=clone,
        capture_output=True, text=True, check=False,
    )
    (clone.parent / "green.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    results["green"] = result.returncode
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    (clone.parent / "red-green.json").write_text(json.dumps(results), encoding="utf-8")
    print(json.dumps(results))


if __name__ == "__main__":
    main()
