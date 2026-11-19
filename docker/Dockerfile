# ==============================================================================
# Multi-purpose, self-contained Docker image for Indian Equities News Scraper
# Includes Python 3.11, all dependencies, and embedded PostgreSQL/SQLite database
# ==============================================================================

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    DATABASE_TYPE=postgres

# Install system dependencies:
# - postgresql & postgresql-contrib: embedded PostgreSQL database server & tools
# - libpq-dev & gcc / g++: for compiling native C-extensions if required
# - curl & procps: for health checks and process management
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql \
    postgresql-contrib \
    libpq-dev \
    gcc \
    g++ \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies first to leverage Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Create volume mount points for SQLite data and PostgreSQL data
RUN mkdir -p /app/data /var/lib/postgresql/data /var/run/postgresql && \
    chown -R postgres:postgres /var/lib/postgresql /var/run/postgresql

# Copy application source code
COPY . .

# Copy and setup entrypoint script (convert CRLF to LF defensively)
COPY docker/docker-entrypoint.sh /app/docker-entrypoint.sh
RUN sed -i 's/\r$//' /app/docker-entrypoint.sh && \
    chmod +x /app/docker-entrypoint.sh

# Expose FastAPI application port (8000) and PostgreSQL database port (5432)
EXPOSE 8000 5432

# Health check to ensure the REST API is healthy and responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Set the entrypoint to handle database startup and schema migrations
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Default command starts the master runner (REST API server + scrapers)
CMD ["python", "run.py"]
