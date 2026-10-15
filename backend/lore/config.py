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

# Default fetch window.
FETCH_SINCE_DAYS = 548  # ~18 months

# Branches to read commits from in addition to the default branch, per repo.
# FalkorDB/FalkorDB: the Rust engine replaced main's tree in one commit (PR #2279);
# its real history (~2,900 commits) lives only on main-rs.
EXTRA_BRANCHES: dict[str, list[str]] = {
    "FalkorDB/FalkorDB": ["main-rs"],
}

# Module mapping: a file's module is its first MODULE_DEPTH directories, one level
# deeper under these per-repo prefixes. FalkorDB's engine parts live at graph/src/<x>.
MODULE_DEPTH = 2
MODULE_DEEP_PREFIXES: dict[str, list[str]] = {
    "FalkorDB/FalkorDB": ["graph/src"],
}

# A commit touching more than this many files replaced a tree (FalkorDB PR #2279);
# it is loaded with bulk = true and skipped when deriving expertise.
BULK_COMMIT_FILES = 500

# Bus factor (queries/07_bus_factor.cypher): who counts as someone who could maintain a module.
# Tuned on the golden set (q09: parser and udf -> 1; s03: sandbox storage -> 1). See the query.
BUS_FACTOR_MIN_SCORE = 0.9  # decayed authored score: one commit this week (1.0 decays to 0.97 in a week)
BUS_FACTOR_MIN_SHARE = 0.10  # of the module's total authored score
BUS_FACTOR_WINDOW = 180 * 86400  # last authored touch within this many seconds


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

    # Two OpenAI-compatible endpoints, one per role.
    llm_fast_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_fast_api_key: str = ""
    llm_fast_model: str = ""
    llm_smart_base_url: str = "https://api.groq.com/openai/v1"
    llm_smart_api_key: str = ""
    llm_smart_model: str = ""
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
