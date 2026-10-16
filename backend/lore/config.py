"""Settings read from env vars (and the repo-root .env). See .env.example."""

import re
from dataclasses import dataclass
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
LLM_CACHE_DIR = CACHE_DIR / "llm"
TOPICS_FILE = REPO_ROOT / "docs" / "TOPICS.md"

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


# Decision extraction (ingest/extract.py, M5).
EXTRACT_MIN_PR_BODY = 300  # characters of human-written PR body, after stripping bot blocks
EXTRACT_MIN_ISSUE_COMMENTS = 5  # human comments on a closed issue
EXTRACT_MAX_INPUT_CHARS = 24000  # per candidate prompt; longer text is cut at the end
EXTRACT_MAX_MODULES = 40  # affected-module choices offered to the LLM per candidate
# Merged PRs the golden "why" questions depend on; always candidates, and first in --sample.
EXTRACT_MUST_INCLUDE: dict[str, list[int]] = {"FalkorDB/FalkorDB": [2678, 2349, 2279, 2695]}
# Decisions below this confidence stay in the graph but are excluded from answers.
DECISION_MIN_CONFIDENCE = 0.6

# Free-tier pacing for the fast (Gemini) endpoint: minimum seconds between uncached calls,
# and retries with exponential backoff on 429 / 5xx.
LLM_MIN_INTERVAL = 4.5  # ~13 requests per minute
LLM_MAX_RETRIES = 6


@dataclass(frozen=True)
class Topic:
    id: str
    covers: str
    paths: str = ""
    labels: str = ""


# Sandbox topics: TOPICS.md gives only the ids, so the hints live here (from SANDBOX_STORY.md).
_SANDBOX_TOPIC_HINTS = {
    "link-cache": ("Caching resolved links: in-process LRU, Redis, TTLs, invalidation", "cache/"),
    "short-codes": ("Generating short codes: format, length, randomness, aliases", "api/"),
    "redirects": ("Redirect handling and short-code lookup", "api/"),
    "analytics": ("Click counting, dashboards, CSV export", "analytics/"),
    "storage": ("Database, compaction, locks", "storage/"),
    "api-limits": ("Rate limits and quotas on the API", "api/"),
    "docs": ("Documentation and ADRs", "docs/"),
}


def _parse_topics_md(text: str) -> tuple[list[Topic], list[str]]:
    """The FalkorDB table rows (| n | `id` | covers | paths | labels |) and the sandbox id list."""
    topics = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 5 and cells[0].isdigit():
            topics.append(Topic(cells[1].strip("`"), cells[2], cells[3], cells[4]))
    m = re.search(r"For the sandbox org.*?list.*?:(.*)", text)
    sandbox = re.findall(r"`([a-z0-9-]+)`", m.group(1)) if m else []
    return topics, sandbox


@lru_cache
def topics_for(org: str) -> tuple[Topic, ...]:
    """Fixed topic list for an org: docs/TOPICS.md for FalkorDB, the short list for the sandbox."""
    org_topics, sandbox_ids = _parse_topics_md(TOPICS_FILE.read_text(encoding="utf-8"))
    sandbox_owner = get_settings().sandbox_repo.split("/")[0].lower()
    if org.lower() == sandbox_owner:
        return tuple(Topic(t, *_SANDBOX_TOPIC_HINTS.get(t, ("", ""))) for t in sandbox_ids)
    return tuple(org_topics)


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
