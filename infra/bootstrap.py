"""Generer les secrets locaux depuis le conteneur, sans Python sur l'hote."""

import argparse
import base64
import os
import secrets
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/workspace"))
    parser.add_argument("--uid", default="50000")
    args = parser.parse_args()
    for directory in ("logs", "plugins", "data", "data/raw"):
        path = args.root / directory
        path.mkdir(parents=True, exist_ok=True)
        if os.getuid() == 0:
            os.chown(path, int(args.uid), 0)
            path.chmod(0o770)
    path = args.root / ".env"
    if not path.exists():
        content = (
            f"AIRFLOW_UID={args.uid}\n"
            f"POSTGRES_PASSWORD={secrets.token_hex(32)}\n"
            f"AIRFLOW_JWT_SECRET={secrets.token_hex(32)}\n"
            f"AIRFLOW_FERNET_KEY={base64.urlsafe_b64encode(os.urandom(32)).decode()}\n"
        )
        with path.open("x", encoding="utf-8") as stream:
            stream.write(content)
        path.chmod(0o600)
        print(".env cree ; secrets locaux exclus de Git")


if __name__ == "__main__":
    main()
