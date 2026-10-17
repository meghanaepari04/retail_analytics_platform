"""
Database connection helper.
Reads config from pipeline/config.yaml with env-var overrides.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def _resolve_env(value: str) -> str:
    """Expand ${VAR:-default} style placeholders from environment variables."""
    pattern = re.compile(r"\$\{(\w+)(?::-(.*?))?\}")

    def replacer(m: re.Match) -> str:
        var, default = m.group(1), m.group(2) or ""
        return os.environ.get(var, default)

    return pattern.sub(replacer, str(value))


def load_config(config_path: str = "pipeline/config.yaml") -> dict:
    p = Path(config_path)
    if not p.exists():
        return {}
    with open(p) as f:
        raw = yaml.safe_load(f) or {}

    # Recursively resolve env vars in string values
    def resolve(obj):
        if isinstance(obj, str):
            return _resolve_env(obj)
        if isinstance(obj, dict):
            return {k: resolve(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [resolve(i) for i in obj]
        return obj

    return resolve(raw)


@lru_cache(maxsize=1)
def get_engine(config_path: str = "pipeline/config.yaml") -> Engine:
    cfg = load_config(config_path).get("database", {})
    host = cfg.get("host", "localhost")
    port = cfg.get("port", 5432)
    dbname = cfg.get("dbname", "retail_analytics")
    user = cfg.get("user", "etl_writer")
    password = cfg.get("password", "changeme")
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
    return create_engine(
        url,
        pool_size=cfg.get("pool_size", 5),
        connect_args={"connect_timeout": cfg.get("connect_timeout", 10)},
        future=True,
    )
