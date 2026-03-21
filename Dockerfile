# Using Python 3.12 (compatible with project's >=3.10 requirement)
FROM python:3.12-slim

# Install uv (pinned for reproducible builds)
COPY --from=ghcr.io/astral-sh/uv:0.10.6 /uv /uvx /bin/

# Create non-root user for security
RUN useradd -m -u 1000 appuser

WORKDIR /app
RUN chown appuser:appuser /app

# Copy dependency specification and sync production dependencies
COPY --chown=appuser:appuser pyproject.toml uv.lock ./
USER appuser
# Install dependencies only (not the project) — cached layer, rebuilt only when deps change
RUN uv sync --frozen --no-dev --no-install-project
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY --chown=appuser:appuser . .

# Install the project itself now that source is present
RUN uv sync --frozen --no-dev

EXPOSE 8080

# Add health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080').read()"

CMD ["python", "server.py"]
