#!/usr/bin/env bash
set -e

# Default settings
DATABASE_TYPE="${DATABASE_TYPE:-postgres}"
API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8000}"

echo "=========================================================="
echo " Starting News Scraper Container Setup"
echo " DATABASE_TYPE : ${DATABASE_TYPE}"
echo " API_HOST      : ${API_HOST}"
echo " API_PORT      : ${API_PORT}"
echo "=========================================================="

# Handle Database Configuration
if [ "$DATABASE_TYPE" = "postgres" ]; then
    if [ -z "$DATABASE_URL" ] || [[ "$DATABASE_URL" == *"localhost"* ]] || [[ "$DATABASE_URL" == *"127.0.0.1"* ]]; then
        echo "[1/3] Starting internal PostgreSQL service..."
        
        # Ensure directories and permissions
        mkdir -p /var/run/postgresql /var/lib/postgresql
        chown -R postgres:postgres /var/run/postgresql /var/lib/postgresql

        # Configure PostgreSQL to accept connections from all interfaces
        PG_CONF=$(find /etc/postgresql -name postgresql.conf 2>/dev/null | head -n 1)
        PG_HBA=$(find /etc/postgresql -name pg_hba.conf 2>/dev/null | head -n 1)
        if [ -n "$PG_CONF" ] && [ -n "$PG_HBA" ]; then
            grep -q "listen_addresses = '*'" "$PG_CONF" || echo "listen_addresses = '*'" >> "$PG_CONF"
            grep -q "host all all 0.0.0.0/0 md5" "$PG_HBA" || echo "host all all 0.0.0.0/0 md5" >> "$PG_HBA"
        fi

        # Start postgresql
        service postgresql start

        # Wait for PostgreSQL to be ready
        echo "Waiting for PostgreSQL service to be ready..."
        until su - postgres -c "pg_isready" > /dev/null 2>&1; do
            sleep 1
        done

        echo "[2/3] Configuring PostgreSQL user and database..."
        # Create database and user if needed
        su - postgres -c "psql -tc \"SELECT 1 FROM pg_database WHERE datname = 'news_scraper'\" | grep -q 1 || psql -c \"CREATE DATABASE news_scraper;\""
        su - postgres -c "psql -c \"ALTER USER postgres WITH PASSWORD 'postgres_password';\""
        su - postgres -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE news_scraper TO postgres;\""

        export DATABASE_URL="postgresql+psycopg2://postgres:postgres_password@127.0.0.1:5432/news_scraper"
        echo "PostgreSQL internal database configured and ready."
    else
        echo "[1/3] Using external PostgreSQL database at: $DATABASE_URL"
    fi
elif [ "$DATABASE_TYPE" = "sqlite" ]; then
    echo "[1/3] Using embedded SQLite database..."
    mkdir -p /app/data
    if [ -z "$DATABASE_URL" ]; then
        export DATABASE_URL="sqlite:////app/data/news.db"
    fi
    echo "SQLite database path configured at: $DATABASE_URL"
fi

export DATABASE_URL
export API_HOST
export API_PORT

echo "[3/3] Initializing database schema..."
python -m scripts.init_db

echo "=========================================================="
echo " News Scraper environment initialized successfully."
echo " Launching application: $@"
echo "=========================================================="

exec "$@"
