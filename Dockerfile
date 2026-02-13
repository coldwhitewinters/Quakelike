# Using Python 3.12 (compatible with project's >=3.10 requirement)
FROM python:3.12-slim

# Create non-root user for security
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Copy dependency specification and install production dependencies only
COPY --chown=appuser:appuser pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application code
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

EXPOSE 5000

# Add health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000').read()"

CMD ["python", "server.py"]
