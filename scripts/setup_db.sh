#!/bin/bash
set -e

# setup_db.sh - Initialize PostgreSQL database for IRIS AI agent
# Run this once on the database server

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}IRIS Database Setup${NC}"
echo "===================="

# Get connection parameters
DB_HOST=${1:-localhost}
DB_PORT=${2:-5432}
POSTGRES_USER=${3:-postgres}

read -sp "PostgreSQL superuser password: " POSTGRES_PASSWORD
echo

IRIS_USER="iris_app"
read -sp "New iris_app user password: " IRIS_PASSWORD
echo

echo -e "${YELLOW}Creating iris_app database user...${NC}"
PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$POSTGRES_USER" -d postgres <<EOF
CREATE USER $IRIS_USER WITH PASSWORD '$IRIS_PASSWORD';
ALTER USER $IRIS_USER CREATEDB;
EOF

echo -e "${GREEN}✓ User created${NC}"

echo -e "${YELLOW}Creating iris_agent database...${NC}"
PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$POSTGRES_USER" -d postgres <<EOF
CREATE DATABASE iris_agent OWNER $IRIS_USER;
EOF

echo -e "${GREEN}✓ Database created${NC}"

echo -e "${YELLOW}Enabling pgvector extension...${NC}"
PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$POSTGRES_USER" -d iris_agent <<EOF
CREATE EXTENSION IF NOT EXISTS vector;
EOF

echo -e "${GREEN}✓ pgvector enabled${NC}"

echo -e "${YELLOW}Running database migrations (if they exist)...${NC}"
# This assumes alembic or similar is set up; if not, manually run the schema
# PGPASSWORD="$IRIS_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$IRIS_USER" -d iris_agent -f scripts/schema.sql

echo -e "${YELLOW}Creating vector indexes...${NC}"
PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$POSTGRES_USER" -d iris_agent -f scripts/setup_pgvector_indexes.sql

echo -e "${GREEN}✓ Indexes created${NC}"

echo
echo -e "${GREEN}✅ Database setup complete!${NC}"
echo -e "${YELLOW}Database credentials:${NC}"
echo "  Host: $DB_HOST"
echo "  Port: $DB_PORT"
echo "  Database: iris_agent"
echo "  User: $IRIS_USER"
echo "  (Password: stored in .env)"
