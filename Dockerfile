# Using Python 3.12 (compatible with project's >=3.10 requirement)
FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Create non-root user for security
RUN useradd -m -u 1000 appuser

WORKDIR /app
RUN chown appuser:appuser /app

# Copy dependency specification and sync production dependencies
COPY --chown=appuser:appuser pyproject.toml uv.lock ./
USER appuser
RUN uv sync --frozen --no-dev

# Copy application code
COPY --chown=appuser:appuser . .

EXPOSE 5000

ENV PATH="/app/.venv/bin:$PATH"

# Add health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000').read()"

CMD ["python", "server.py"]
