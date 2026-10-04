"""Build build/space/ and push it to the Hugging Face Space, then wait for the new data_version."""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
import urllib.request

from engine import config

log = logging.getLogger("tenantly.deploy")

COPY_DIRS = ["engine", "artifacts", "dataset", "out"]
COPY_FILES = ["pyproject.toml", "uv.lock", "Dockerfile"]
SECRETS = ["ANTHROPIC_API_KEY", "ADMIN_TOKEN", "GROQ_API_KEY"]
VARIABLES = {
    "ALLOWED_ORIGINS": "*",  # public read-only API; admin routes need the token
    "DEMO_MODE": "live",
    "BUDGET_USD_CAP": "6",
    "INGEST_BUDGET_USD": "0.5",
    "MODEL_FAST": "claude-haiku-4-5-20251001",
    "MODEL_STRONG": "claude-sonnet-5-5",
    "MODEL_JUDGE": "claude-sonnet-5-5",
}
SKIP = shutil.ignore_patterns("__pycache__", "*.pyc", "cache", "compile", "web", ".pytest_cache")


def build_space() -> os.PathLike[str]:
    space = config.ROOT / "build" / "space"
    if space.exists():
        shutil.rmtree(space)
    space.mkdir(parents=True)
    for d in COPY_DIRS:
        src = config.ROOT / d
        if src.exists():
            shutil.copytree(src, space / d, ignore=SKIP)
        else:
            (space / d).mkdir()
    for f in COPY_FILES:
        shutil.copy2(config.ROOT / f, space / f)
    shutil.copy2(config.ROOT / "deploy" / "hf" / "README.md", space / "README.md")
    return space


def local_data_version() -> str:
    from engine.api.deps import get_store

    return get_store().health()["data_version"]


def space_url(space_id: str) -> str:
    owner, _, name = space_id.partition("/")
    return f"https://{owner.lower()}-{name.lower()}.hf.space"


def deploy(timeout_s: int = 900) -> str:
    token = os.environ.get("HF_TOKEN")
    space_id = os.environ.get("HF_SPACE_ID", "")
    if not token or "<" in space_id or "/" not in space_id:
        raise SystemExit("Set HF_TOKEN and HF_SPACE_ID (owner/name) in .env before deploying.")
    from huggingface_hub import HfApi

    space = build_space()
    api = HfApi(token=token)
    api.create_repo(space_id, repo_type="space", space_sdk="docker", exist_ok=True)
    for name in SECRETS:  # values are read from .env and never printed
        if os.environ.get(name):
            api.add_space_secret(space_id, name, os.environ[name])
    for name, value in VARIABLES.items():
        api.add_space_variable(space_id, name, os.environ.get(name, value))
    api.upload_folder(folder_path=str(space), repo_id=space_id, repo_type="space")
    want = local_data_version()
    url = space_url(space_id) + "/v1/health"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:  # noqa: S310
                got = json.loads(resp.read())
            if got.get("data_version") == want:
                log.info("deploy ok url=%s data_version=%s", url, want)
                return url
        except Exception as exc:  # noqa: BLE001
            log.info("waiting url=%s reason=%s", url, type(exc).__name__)
        time.sleep(15)
    raise SystemExit(f"Space did not report data_version {want} within {timeout_s}s: {url}")
