"""Settings read from env vars (and the repo-root .env). See .env.example."""

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
QUERIES_DIR = REPO_ROOT / "queries"
DATA_DIR = REPO_ROOT / "data"
# LORE_RAW_DIR: a test sync works on a copy of the raw cache (scripts/sync.py --simulate-merge).
RAW_DIR = Path(os.environ.get("LORE_RAW_DIR") or DATA_DIR / "raw")
CACHE_DIR = DATA_DIR / "cache"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
LLM_CACHE_DIR = CACHE_DIR / "llm"
# The deployed image keeps the model outside the data volume (FASTEMBED_CACHE, see Dockerfile).
EMBED_MODEL_DIR = Path(os.environ.get("FASTEMBED_CACHE") or CACHE_DIR / "fastembed")
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

# Co-change and impact radius (queries/10_*, M7). Golden q10: parser -> planner, runtime.
CO_CHANGE_MAX_MODULES = 6  # commits touching more modules are refactors, not coupling
CO_CHANGE_MIN_COUNT = 2  # commits a pair must share to get a CO_CHANGED edge
IMPACT_MIN_COUNT = 3  # CO_CHANGED count shown in the impact radius

# Graph algorithms on COLLABORATES (queries/08_*, M7).
BETWEENNESS_SAMPLING_SIZE = 200  # source nodes sampled; FalkorDB has ~300 people
BETWEENNESS_SEED = 42  # fixed so the bridge-people ranking is repeatable
LPA_MIN_WEIGHT = 2  # COLLABORATES_STRONG: shared PRs needed for label propagation to settle


# Decision extraction (ingest/extract.py, M5).
EXTRACT_MIN_PR_BODY = 300  # characters of human-written PR body, after stripping bot blocks
EXTRACT_MIN_ISSUE_COMMENTS = 5  # human comments on a closed issue
EXTRACT_MAX_INPUT_CHARS = 24000  # per candidate prompt; longer text is cut at the end
EXTRACT_MAX_MODULES = 40  # affected-module choices offered to the LLM per candidate
# Merged PRs the golden "why" questions depend on; always candidates, and first in --sample.
EXTRACT_MUST_INCLUDE: dict[str, list[int]] = {"FalkorDB/FalkorDB": [2678, 2349, 2279, 2695]}
# Decisions below this confidence stay in the graph but are excluded from answers.
DECISION_MIN_CONFIDENCE = 0.6
# Ranking weight per decision kind, stored as Decision.weight. "parity" choices (match C /
# openCypher) are real reasons but say less about this project, so they rank lower.
# "test" decisions are dropped at extraction and never loaded.
DECISION_KIND_WEIGHT = {"architecture": 1.0, "behavior": 1.0, "process": 1.0, "parity": 0.5, "test": 0.0}

# Embeddings and the entry point (M6). Issue text is title + the first ISSUE_EMBED_BODY chars
# of the body; docs are cut into ~DOC_CHUNK_CHARS chunks that overlap by DOC_CHUNK_OVERLAP.
ISSUE_EMBED_BODY = 500
DOC_CHUNK_CHARS = 800
DOC_CHUNK_OVERLAP = 150
# Query 2 fuses vector and full-text ranks with reciprocal rank fusion: w / (RRF_K + rank).
# Vector: top ENTRY_CANDIDATES at weight 1. Full-text: only its top ENTRY_TEXT_CANDIDATES at
# RRF_TEXT_WEIGHT: an OR query over a question's words has a long noisy tail (q02/q03's
# decisions are not in its top 20), so it may only lift a precise match. Tuned on q01-q04 + s01.
RRF_K = 60
ENTRY_CANDIDATES = 20
ENTRY_TEXT_CANDIDATES = 3
RRF_TEXT_WEIGHT = 0.5

# Triage (related_work, M8). Distances are cosine distances (0 = same direction, lower = closer).
SIMILAR_MAX_DISTANCE = 0.5  # similar issues further than this are not shown
# Duplicate candidate below this. Measured on the sandbox: a restatement of #3 is 0.10 from it; related
# but different issues sit at 0.19 (CSV clicks missing vs #9 CSV timeout; #6 vs #1), the demo issue 0.35 from #3.
DUPLICATE_MAX_DISTANCE = 0.15

# Steward (M13). A triage draft lists similar issues within RELATED_MAX_DISTANCE, plus always the
# nearest one. Sandbox: CSV clicks missing -> #9 at 0.19 and #4 at 0.25 (#3 at 0.42 left out); the
# demo issue -> only its nearest, #3 at 0.35 (#7 at 0.40 and #1 at 0.41 are noise).
RELATED_MAX_DISTANCE = 0.30
# A reviewer may have less expertise than an answer's experts: one review of one PR scores ~0.5.
REVIEWER_MIN_SCORE = 0.1
# Modules that say little about who should own a bug: test and doc folders touched by every fix.
TRIAGE_SKIP_MODULES = ("tests", "test", "docs", "doc", "/")
STEWARD_MAX_ATTEMPTS = 3
# The triage Playbook's steps before any Feedback (procedural memory, docs/PLAN.md). A human's edit
# of a draft adds a rule after these (queries/13_feedback_add.cypher).
PLAYBOOK_NAME = "triage"
PLAYBOOK_DEFAULT_STEPS = [
    "Start with every likely duplicate and related past issue, each as a link: say how each closed one was fixed (the PR, as a link) and which are still open.",
    "If an earlier fix rests on a recorded decision, state that decision in one sentence and link where it was made.",
    "Suggest an owner: the person who actually works on the module. If CODEOWNERS lists someone who does not work there, say so plainly.",
    "Suggest a reviewer, with the reason in a few words.",
    "Mention people who have a GitHub login as @login, and people without one by name.",
    "Keep it short: one opening line and at most 6 bullets; no greeting or sign-off.",
]  # a Task whose draft failed this often stays open but is no longer retried

# trace_decision: linked issues shown per decision (query 03 ranks them first).
TRACE_MAX_ISSUES = 6

# lore-mcp (M8): knowledge_risk lists at most this many modules with bus factor >= 1, and the
# top RISK_BRIDGE_PEOPLE by betweenness.
RISK_MAX_MODULES = 30
RISK_BRIDGE_PEOPLE = 5

# Agent LLM pool (Navigator, Steward), tried in this order, quality first:
#   (provider, env var holding the key, model, supports a strict json_schema response)
# provider -> base URL: gemini = LLM_FAST_BASE_URL, groq = LLM_SMART_BASE_URL.
# A per-minute 429 cools an endpoint down for its retry-after; a daily-quota or spend-cap error
# marks it exhausted until its reset (llm/agent.py). Free-tier keys only: never put a
# billing-enabled key in these env vars (a spend-cap error is logged as a misconfiguration).
AGENT_LLM_POOL: list[tuple[str, str, str, bool]] = [
    ("gemini", "LLM_FAST_API_KEY", "gemini-3.8-flash", True),
    ("groq", "LLM_SMART_API_KEY", "openai/gpt-oss-120b", True),
    ("gemini", "LLM_FAST_API_KEY", "gemini-3.6-flash", True),
    ("groq", "LLM_SMART_API_KEY", "openai/gpt-oss-20b", True),
    ("gemini", "LLM_FAST_API_KEY", "gemini-3.5-flash-lite", True),
]
AGENT_LLM_STATE = LLM_CACHE_DIR / "endpoint_state.json"  # cooldowns and exhausted endpoints, shared by runs
AGENT_COOLDOWN_DEFAULT = 60  # seconds, when a per-minute 429 gives no retry-after
AGENT_WAIT_MAX = 65  # seconds worth waiting for the soonest cooldown when every endpoint is cooling down
GEMINI_DAILY_RESET_UTC_HOUR = 8  # free-tier daily quotas reset at midnight Pacific (07:00 or 08:00 UTC)

# Navigator answer cache: data/cache/answers/<key>.json, key = normalized question + org +
# graph data version (query 93) + a hash of the Navigator's prompts.
ANSWER_CACHE_DIR = CACHE_DIR / "answers"

# Navigator (M9): tool calls per question, find_entities included (remember, step 7, is not counted).
NAVIGATOR_MAX_TOOL_CALLS = 4

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
    # API (M10): browser origins allowed by CORS (comma-separated), and /ask limits per user.
    # The frontend runs on 3001: 3000 is the FalkorDB browser in docker-compose.yml.
    cors_origins: str = "http://localhost:3001,http://127.0.0.1:3001"
    ask_per_minute: int = 5
    ask_per_day: int = 100
    # Signs triage approvals: the UI mints a token for (issue, exact draft) when a human clicks
    # approve; post_triage refuses without it. Empty = every post is refused.
    triage_approval_secret: str = ""
    # M13: post_triage only prints the comment while this is true; set DRY_RUN=false to post for real
    # (still only to SANDBOX_REPO, still only with an approval token).
    dry_run: bool = True
    # Approve (the only route that leads to a GitHub write) also needs this passcode, typed in the
    # triage inbox; the API checks it before minting the approval token. Empty = every approval refused.
    approve_passcode: str = ""
    # The API polls SANDBOX_REPO for new issues this often and lets Steward draft them (0 = off; the
    # deployed backend uses the webhook instead).
    steward_poll_seconds: int = 60
    # TEST ONLY (M15 timing test on a test FalkorDB): a pull_request 'merged' webhook is synced as a
    # simulated merge (the PR's head branch read as if merged). Never set on a real deployment.
    sync_simulate_merge: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


def graph_name(org: str) -> str:
    """One graph per org: lore_<org>, lowercase."""
    return f"lore_{org.strip().lower()}"
