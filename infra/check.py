"""Memes commandes dans bin/test et dans la CI ; propagation des codes d'erreur."""

import subprocess
import sys


def main():
    for command in (
        [sys.executable, "-m", "ruff", "check", ".", "--no-cache"],
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *sys.argv[1:]],
    ):
        result = subprocess.run(command, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
