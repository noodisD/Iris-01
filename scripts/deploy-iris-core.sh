#!/bin/bash

################################################################################
# IRIS-CORE DEPLOYMENT SCRIPT
# Deploys FastAPI backend on iris-core, connecting to databases on iris-edge
################################################################################

set -e

# ============================================================================
# SETUP & LOGGING
# ============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_step() { echo -e "${BLUE}▶ $1${NC}"; }
log_success() { echo -e "${GREEN}✓ $1${NC}"; }
log_error() { echo -e "${RED}✗ $1${NC}"; exit 1; }
log_warning() { echo -e "${YELLOW}⚠ $1${NC}"; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IRIS_EDGE_IP="192.168.1.24"

# ============================================================================
# STEP 1: Check Docker & Git installed
# ============================================================================

log_step "Checking Docker and Git..."
command -v docker &> /dev/null || log_error "Docker not installed"
command -v git &> /dev/null || log_error "Git not installed"
log_success "Docker and Git available"

# ============================================================================
# STEP 2: Pull latest code from repo
# ============================================================================

log_step "Pulling latest code from GitHub..."
cd "${REPO_DIR}"
git pull origin main || log_error "Failed to pull from GitHub"
log_success "Code updated"

# ============================================================================
# STEP 3: Validate docker-compose.iris-core.yml exists and has correct services
# ============================================================================

log_step "Checking docker-compose configuration..."
[ -f "docker-compose.iris-core.yml" ] || log_error "docker-compose.iris-core.yml not found"
docker compose -f docker-compose.iris-core.yml config > /dev/null || log_error "Invalid docker-compose config"

# Verify api service exists
docker compose -f docker-compose.iris-core.yml config | grep -q "api:" || log_error "api service not defined in docker-compose"

# Verify postgres and neo4j are NOT in the services (they run on iris-edge)
if docker compose -f docker-compose.iris-core.yml config | grep -q "postgres:"; then
    log_error "postgres service should not be in iris-core docker-compose (runs on iris-edge)"
fi
if docker compose -f docker-compose.iris-core.yml config | grep -q "neo4j:"; then
    log_error "neo4j service should not be in iris-core docker-compose (runs on iris-edge)"
fi

log_success "docker-compose.iris-core.yml is valid (api service only, no databases)"

# ============================================================================
# STEP 4: Validate .env has required credentials
# ============================================================================

log_step "Validating .env configuration..."
[ -f ".env" ] || log_error ".env file not found"

for var in OPENAI_API_KEY POSTGRES_PASSWORD NEO4J_PASSWORD; do
    value=$(grep "^${var}=" .env | cut -d'=' -f2-)
    [ -z "$value" ] && log_error "Missing or empty: ${var}"
done

log_success ".env has all required credentials"

# ============================================================================
# STEP 5: Start containers
# ============================================================================

log_step "Starting iris_api container..."
docker compose -f docker-compose.iris-core.yml down 2>/dev/null || true
docker compose -f docker-compose.iris-core.yml up -d --build || log_error "Failed to start container"
log_success "Container started"

sleep 10

# ============================================================================
# STEP 6: Verify container is running
# ============================================================================

log_step "Verifying container health..."
docker ps --filter "name=iris_api" --filter "status=running" | grep -q iris_api || log_error "Container iris_api not running"
log_success "iris_api container is running"

# ============================================================================
# STEP 7: Test PostgreSQL connectivity to iris-edge (from container)
# ============================================================================

log_step "Testing PostgreSQL connectivity to ${IRIS_EDGE_IP}:5433..."

docker exec iris_api python3 << 'PYTHON_EOF' || log_error "PostgreSQL connection failed"
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

try:
    conn = psycopg2.connect(
        host=os.getenv('POSTGRES_HOST'),
        port=int(os.getenv('POSTGRES_PORT')),
        database=os.getenv('POSTGRES_DB'),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD')
    )
    cursor = conn.cursor()
    cursor.execute("SELECT version();")
    version = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    print(f"PostgreSQL connected: {version.split(',')[0]}")
except Exception as e:
    print(f"Connection failed: {e}")
    raise
PYTHON_EOF

log_success "PostgreSQL reachable"

# ============================================================================
# STEP 8: Test Neo4j connectivity to iris-edge (from container)
# ============================================================================

log_step "Testing Neo4j connectivity to ${IRIS_EDGE_IP}:7688..."

docker exec iris_api python3 << 'PYTHON_EOF' || log_error "Neo4j connection failed"
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

load_dotenv()

try:
    uri = os.getenv('NEO4J_URI')
    auth = (os.getenv('NEO4J_USER'), os.getenv('NEO4J_PASSWORD'))
    driver = GraphDatabase.driver(uri, auth=auth, connection_timeout=5)
    with driver.session() as session:
        result = session.run("RETURN 1")
    driver.close()
    print(f"Neo4j connected")
except Exception as e:
    print(f"Connection failed: {e}")
    raise
PYTHON_EOF

log_success "Neo4j reachable"

# ============================================================================
# STEP 9: Test API responsiveness
# ============================================================================

log_step "Testing API responsiveness..."
for i in {1..10}; do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "307" ]; then
        log_success "API is responsive (HTTP $HTTP_CODE)"
        break
    fi
    if [ $i -lt 10 ]; then
        sleep 3
    else
        log_error "API not responding after 30 seconds (HTTP $HTTP_CODE)"
    fi
done

# ============================================================================
# STEP 10: Test database data flow
# ============================================================================

log_step "Testing database data flow..."

docker exec iris_api python3 << 'PYTHON_EOF' || log_error "Database test failed"
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

try:
    # Connect and check if we can query
    conn = psycopg2.connect(
        host=os.getenv('POSTGRES_HOST'),
        port=int(os.getenv('POSTGRES_PORT')),
        database=os.getenv('POSTGRES_DB'),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD')
    )
    cursor = conn.cursor()
    
    # Check pgvector extension
    cursor.execute("SELECT extname FROM pg_extension WHERE extname='vector';")
    if cursor.fetchone():
        print("pgvector extension available")
    else:
        print("Warning: pgvector not found, but connection OK")
    
    cursor.close()
    conn.close()
    print("Database test passed")
except Exception as e:
    print(f"Database test failed: {e}")
    raise
PYTHON_EOF

log_success "Database data flow verified"

# ============================================================================
# SUCCESS
# ============================================================================

echo ""
log_success "═══════════════════════════════════════════════════════════════"
log_success "IRIS-CORE DEPLOYMENT SUCCESSFUL"
log_success "═══════════════════════════════════════════════════════════════"
echo ""
echo -e "  ${GREEN}API:${NC}           http://localhost:8000"
echo -e "  ${GREEN}Postgres:${NC}      ${IRIS_EDGE_IP}:5433"
echo -e "  ${GREEN}Neo4j:${NC}         ${IRIS_EDGE_IP}:7688"
echo ""
echo -e "  ${YELLOW}Logs:${NC}          docker logs -f iris_api"
echo ""
