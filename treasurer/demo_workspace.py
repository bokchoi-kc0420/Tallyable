"""Private demo workspaces addressed by a randomly generated return code."""
import hashlib
import os
import re
import secrets
from pathlib import Path


def public_demo() -> bool:
    return os.getenv("TALLYABLE_PUBLIC_DEMO", "").lower() == "true"


def workspace_path(root: Path, code: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", code):
        raise ValueError("Invalid return code")
    return root / "demo_users" / hashlib.sha256(code.encode()).hexdigest()


def create_workspace(root: Path) -> str:
    code = secrets.token_hex(16)
    workspace_path(root, code).mkdir(parents=True, exist_ok=False)
    return code
