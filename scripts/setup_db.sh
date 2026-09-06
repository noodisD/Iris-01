#!/bin/bash
# Create the IRIS database inside the local PostgreSQL container.
#
# IRIS needs PostgreSQL with the pgvector extension. On Omarchy the convention
# is a container per database engine; the stock `omarchy-install-docker-dbs`
# recipe uses the plain postgres image, which has no pgvector, so use this:
#
#   sudo docker run -d --restart unless-stopped \
#     -p 127.0.0.1:5432:5432 \
#     -v iris_pgdata:/var/lib/postgresql \
#     --name postgres18 \
#     -e POSTGRES_HOST_AUTH_METHOD=trust \
#     -e POSTGRES_USER=iris_user -e POSTGRES_DB=iris_db \
#     pgvector/pgvector:pg18
#
# Note the volume path: PostgreSQL 18 moved PGDATA to a version-specific
# directory, so mount /var/lib/postgresql, NOT /var/lib/postgresql/data — the
# old path looks fine and silently persists nothing.
#
# If the container already exists with different credentials, this script
# creates the role and database inside it. Names must match .env.
set -euo pipefail

DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-iris_db}"
DB_USER="${POSTGRES_USER:-iris_user}"
ADMIN_USER="${POSTGRES_ADMIN_USER:-postgres}"

echo "Creating role ${DB_USER} and database ${DB_NAME} on ${DB_HOST}:${DB_PORT}…"

psql -h "$DB_HOST" -p "$DB_PORT" -U "$ADMIN_USER" -d postgres -v ON_ERROR_STOP=1 <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} LOGIN SUPERUSER;
  END IF;
END \$\$;
SQL

if ! psql -h "$DB_HOST" -p "$DB_PORT" -U "$ADMIN_USER" -d postgres -tAc \
     "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}';" | grep -q 1; then
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$ADMIN_USER" -d postgres -v ON_ERROR_STOP=1 \
       -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"
fi

psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 \
     -c "CREATE EXTENSION IF NOT EXISTS vector;"

echo "Done. The application creates its own tables on first start."
