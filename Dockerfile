# Lore backend: the FastAPI app (lore-mcp in process, Steward's poll). FalkorDB runs in its own
# container and Caddy serves HTTPS in front (deploy/docker-compose.yml). Build from the repo root:
#   docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
# No secrets in the image: they come from the server's .env at run time. Nothing is fetched from
# GitHub or sent to an LLM at build time; the graphs come from the v0.1-snapshot release.

FROM python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend
# Dependencies first (cached layer): the locked runtime deps, no dev group.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend/lore ./lore
COPY backend/scripts ./scripts
COPY queries /app/queries
COPY docs/TOPICS.md /app/docs/TOPICS.md
COPY docs/golden_set.yaml /app/docs/golden_set.yaml
# The embedding model (BAAI/bge-small-en-v1.5) is downloaded once at build, into the image, not into
# the data volume mounted at /app/data/cache.
ENV FASTEMBED_CACHE=/opt/fastembed
RUN .venv/bin/python -c "from lore.llm.embed import embed; print(len(embed(['warm up'])[0]), 'dims')"

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD .venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
CMD [".venv/bin/uvicorn", "lore.api.app:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
