"""Settings read from env vars (and the repo-root .env). See .env.example."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
QUERIES_DIR = REPO_ROOT / "queries"
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = DATA_DIR / "cache"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"

# Separate graph for the healthcheck so test nodes never land in an org graph.
HEALTHCHECK_GRAPH = "lore_healthcheck"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    github_token: str = ""
    demo_org: str = "FalkorDB"
    sandbox_repo: str = ""

    falkordb_host: str = "localhost"
    falkordb_port: int = 6379
    falkordb_password: str = ""

    llm_provider: str = ""
    llm_api_key: str = ""
    llm_model_fast: str = ""
    llm_model_smart: str = ""
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    llm_daily_call_cap: int = 2000

    github_webhook_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


def graph_name(org: str) -> str:
    """One graph per org: lore_<org>, lowercase."""
    return f"lore_{org.strip().lower()}"
