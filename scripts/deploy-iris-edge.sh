#!/bin/bash

# ============================================================================
# iris-edge Deployment Script
# Purpose: Automated setup and health verification for databases (PostgreSQL + Neo4j)
# Author: IRIS DevOps Team
# ============================================================================

set -e # Exit on any error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REPO_DIR="/home/iris/Iris-01"
DOCKER_COMPOSE_FILE="docker-compose.iris-edge.yml"
ENV_FILE=".env"

# ============================================================================
# Logging Functions
# ============================================================================

log_info() {
  echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
  echo -e "${GREEN}[✓]${NC} $1"
}

log_warning() {
  echo -e "${YELLOW}[⚠]${NC} $1"
}

log_error() {
  echo -e "${RED}[✗]${NC} $1"
}

log_step() {
  echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${BLUE}$1${NC}"
  echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ============================================================================
# Step 1: Check if Docker is installed
# ============================================================================

step_1_check_docker() {
  log_step "STEP 1: Checking Docker Installation"

  if ! command -v docker &>/dev/null; then
    log_error "Docker is not installed"
    exit 1
  fi
  log_success "Docker is installed: $(docker --version)"

  # Check for docker compose (new) or docker-compose (old)
  if docker compose version &>/dev/null; then
    log_success "Docker Compose is installed: $(docker compose version)"
  elif command -v docker-compose &>/dev/null; then
    log_success "docker-compose is installed: $(docker-compose --version)"
  else
    log_error "Docker Compose is not installed"
    exit 1
  fi
}

# ============================================================================
# Step 2: Check if latest GitHub repo is pulled
# ============================================================================

step_2_check_repo() {
  log_step "STEP 2: Verifying Latest GitHub Repo"

  if [ ! -d "$REPO_DIR" ]; then
    log_error "Repository directory not found: $REPO_DIR"
    exit 1
  fi

  cd "$REPO_DIR"
  log_info "Checking git status..."

  # Fetch latest from remote
  git fetch origin main &>/dev/null || {
    log_error "Failed to fetch from GitHub"
    exit 1
  }

  # Check if local is behind remote
  LOCAL=$(git rev-parse @)
  REMOTE=$(git rev-parse @{u})

  if [ "$LOCAL" != "$REMOTE" ]; then
    log_warning "Local repo is behind remote. Pulling latest..."
    git pull origin main || {
      log_error "Failed to pull from GitHub"
      exit 1
    }
    log_success "Repository updated to latest version"
  else
    log_success "Repository is already at latest version"
  fi
}

# ============================================================================
# Step 3: Verify .env has all required variables
# ============================================================================

step_3_check_env() {
  log_step "STEP 3: Verifying .env Configuration"

  if [ ! -f "$ENV_FILE" ]; then
    log_error ".env file not found in $REPO_DIR"
    exit 1
  fi
  log_success ".env file found"

  # Required variables for iris-edge
  REQUIRED_VARS=(
    "POSTGRES_DB"
    "POSTGRES_USER"
    "POSTGRES_PASSWORD"
    "NEO4J_USER"
    "NEO4J_PASSWORD"
    "ENV"
    "LOG_LEVEL"
  )

  MISSING_VARS=()
  for var in "${REQUIRED_VARS[@]}"; do
    if ! grep -q "^${var}=" "$ENV_FILE"; then
      MISSING_VARS+=("$var")
    fi
  done

  if [ ${#MISSING_VARS[@]} -gt 0 ]; then
    log_error "Missing required variables in .env:"
    for var in "${MISSING_VARS[@]}"; do
      log_error "  - $var"
    done
    exit 1
  fi

  log_success "All required .env variables are present"
  log_info "Environment: $(grep '^ENV=' $ENV_FILE | cut -d= -f2)"
}

# ============================================================================
# Step 4: Verify docker-compose has all services and volumes
# ============================================================================

step_4_check_compose() {
  log_step "STEP 4: Verifying docker-compose Configuration"

  if [ ! -f "$DOCKER_COMPOSE_FILE" ]; then
    log_error "docker-compose file not found: $DOCKER_COMPOSE_FILE"
    exit 1
  fi
  log_success "docker-compose file found: $DOCKER_COMPOSE_FILE"

  # Check for required services
  log_info "Checking services..."
  if grep -q "service.*postgres" "$DOCKER_COMPOSE_FILE" || grep -q "postgres:" "$DOCKER_COMPOSE_FILE"; then
    log_success "PostgreSQL service configured"
  else
    log_error "PostgreSQL service not found in docker-compose"
    exit 1
  fi

  if grep -q "service.*neo4j" "$DOCKER_COMPOSE_FILE" || grep -q "neo4j:" "$DOCKER_COMPOSE_FILE"; then
    log_success "Neo4j service configured"
  else
    log_error "Neo4j service not found in docker-compose"
    exit 1
  fi

  # Check for pgvector image
  if grep -q "pgvector" "$DOCKER_COMPOSE_FILE"; then
    log_success "PostgreSQL image includes pgvector"
  else
    log_warning "PostgreSQL image may not include pgvector (using: $(grep 'image:.*postgres' $DOCKER_COMPOSE_FILE | head -1 | sed 's/.*image: //'))"
  fi

  # Check for volumes
  log_info "Checking volume configuration..."
  if grep -q "postgres_data\|postgres" "$DOCKER_COMPOSE_FILE"; then
    log_success "PostgreSQL volume configured"
  else
    log_warning "PostgreSQL volume configuration unclear"
  fi

  if grep -q "neo4j" "$DOCKER_COMPOSE_FILE"; then
    log_success "Neo4j volume configured"
  else
    log_warning "Neo4j volume configuration unclear"
  fi
}

# ============================================================================
# Step 5: Verify volumes exist on filesystem
# ============================================================================

step_5_check_volumes() {
  log_step "STEP 5: Verifying Volume Directories"

  VOLUME_PATHS=(
    "/iris/db/postgres_data"
    "/iris/db/neo4j/data"
    "/iris/db/neo4j/logs"
  )

  for path in "${VOLUME_PATHS[@]}"; do
    if [ ! -d "$path" ]; then
      log_warning "Directory does not exist: $path - Creating..."
      mkdir -p "$path" || {
        log_error "Failed to create directory: $path"
        exit 1
      }
      log_success "Created: $path"
    else
      log_success "Directory exists: $path"
    fi
  done

  # Check permissions
  log_info "Checking directory permissions..."
  for path in "${VOLUME_PATHS[@]}"; do
    if [ -w "$path" ]; then
      log_success "Directory is writable: $path"
    else
      log_warning "Directory may not be writable: $path"
    fi
  done
}

# ============================================================================
# Step 6: Start docker-compose
# ============================================================================

step_6_start_services() {
  log_step "STEP 6: Starting Docker Containers"

  log_info "Starting services with: docker compose -f $DOCKER_COMPOSE_FILE up -d"

  docker compose -f "$DOCKER_COMPOSE_FILE" up -d || {
    log_error "Failed to start docker compose services"
    docker compose -f "$DOCKER_COMPOSE_FILE" logs
    exit 1
  }

  log_success "Docker containers started"

  # Give services time to start
  log_info "Waiting for services to initialize (10 seconds)..."
  sleep 10
}

# ============================================================================
# Step 7: Check PostgreSQL responsiveness and pgvector
# ============================================================================

step_7_check_postgres() {
  log_step "STEP 7: Verifying PostgreSQL with pgvector (Connectivity & Functionality)"

  local max_attempts=30
  local attempt=1

  log_info "Checking PostgreSQL connectivity (max $max_attempts attempts)..."

  # Load environment variables
  export PGPASSWORD=$(grep '^POSTGRES_PASSWORD=' "$ENV_FILE" | cut -d= -f2)
  POSTGRES_USER=$(grep '^POSTGRES_USER=' "$ENV_FILE" | cut -d= -f2)
  POSTGRES_DB=$(grep '^POSTGRES_DB=' "$ENV_FILE" | cut -d= -f2)

  while [ $attempt -le $max_attempts ]; do
    log_info "Attempt $attempt/$max_attempts..."

    # Test connection
    if docker exec iris_postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" &>/dev/null; then
      log_success "PostgreSQL is responsive (port listening)"
      break
    fi

    log_warning "PostgreSQL not ready yet... waiting"
    sleep 2
    ((attempt++))
  done

  if [ $attempt -gt $max_attempts ]; then
    log_error "PostgreSQL failed to respond after $max_attempts attempts"
    log_error "Docker logs:"
    docker logs iris_postgres | tail -20
    exit 1
  fi

  # Test database layer - actually execute queries
  log_info "Testing database layer functionality..."

  # Test 1: Create test table
  log_info "  Test 1: Creating test table..."
  docker exec iris_postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
    "CREATE TABLE IF NOT EXISTS health_check_test (id SERIAL PRIMARY KEY, data TEXT);" &>/dev/null || {
    log_error "Failed to create test table - authentication or permissions issue"
    exit 1
  }
  log_success "  ✓ Table creation works"

  # Test 2: Insert data
  log_info "  Test 2: Inserting test data..."
  docker exec iris_postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
    "INSERT INTO health_check_test (data) VALUES ('iris-edge-deployment-test');" &>/dev/null || {
    log_error "Failed to insert data - database write issue"
    exit 1
  }
  log_success "  ✓ Data insertion works"

  # Test 3: Query data
  log_info "  Test 3: Querying test data..."
  QUERY_RESULT=$(docker exec iris_postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c \
    "SELECT COUNT(*) FROM health_check_test WHERE data='iris-edge-deployment-test';" 2>/dev/null)

  if [ "$QUERY_RESULT" -gt 0 ]; then
    log_success "  ✓ Data retrieval works"
  else
    log_error "Failed to retrieve data - query issue"
    exit 1
  fi

  # Test 4: Check pgvector extension availability
  log_info "  Test 4: Checking pgvector extension..."
  VECTOR_CHECK=$(docker exec iris_postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c \
    "SELECT COUNT(*) FROM pg_available_extensions WHERE name='vector';" 2>/dev/null)

  if [ "$VECTOR_CHECK" -gt 0 ]; then
    log_success "  ✓ pgvector extension is available"
  else
    log_warning "  ⚠ pgvector extension not available (may need installation)"
  fi

  # Test 5: Create pgvector extension and test it
  log_info "  Test 5: Testing pgvector functionality..."
  docker exec iris_postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
    "CREATE EXTENSION IF NOT EXISTS vector;" &>/dev/null

  docker exec iris_postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
    "CREATE TABLE IF NOT EXISTS vector_test (id SERIAL PRIMARY KEY, embedding vector(3));" &>/dev/null || {
    log_error "Failed to create pgvector table - pgvector not working"
    exit 1
  }

  docker exec iris_postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
    "INSERT INTO vector_test (embedding) VALUES ('[1.0, 2.0, 3.0]');" &>/dev/null || {
    log_error "Failed to insert vector - pgvector not functional"
    exit 1
  }

  log_success "  ✓ pgvector insertion works"

  # Test 6: Test pgvector similarity search
  log_info "  Test 6: Testing pgvector similarity search..."
  VECTOR_QUERY=$(docker exec iris_postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c \
    "SELECT COUNT(*) FROM vector_test WHERE embedding <-> '[1.0, 2.0, 3.0]' < 0.1;" 2>/dev/null)

  if [ "$VECTOR_QUERY" -gt 0 ]; then
    log_success "  ✓ pgvector similarity search works"
  else
    log_warning "  ⚠ pgvector similarity search returned no results (may need data)"
  fi

  # Cleanup test tables
  log_info "  Cleaning up test tables..."
  docker exec iris_postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
    "DROP TABLE IF EXISTS health_check_test CASCADE;" &>/dev/null
  docker exec iris_postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
    "DROP TABLE IF EXISTS vector_test CASCADE;" &>/dev/null

  log_success "PostgreSQL database layer fully functional ✓"
}

# ============================================================================
# Step 8: Check Neo4j responsiveness
# ============================================================================

step_8_check_neo4j() {
  log_step "STEP 8: Verifying Neo4j (Connectivity & Functionality)"

  local max_attempts=30
  local attempt=1

  log_info "Checking Neo4j connectivity (max $max_attempts attempts)..."

  NEO4J_USER=$(grep '^NEO4J_USER=' "$ENV_FILE" | cut -d= -f2)
  NEO4J_PASSWORD=$(grep '^NEO4J_PASSWORD=' "$ENV_FILE" | cut -d= -f2)

  while [ $attempt -le $max_attempts ]; do
    log_info "Attempt $attempt/$max_attempts..."

    # Test Neo4j connectivity
    if docker exec iris_neo4j cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "RETURN 1;" &>/dev/null; then
      log_success "Neo4j is responsive (port listening)"
      break
    fi

    log_warning "Neo4j not ready yet... waiting"
    sleep 2
    ((attempt++))
  done

  if [ $attempt -gt $max_attempts ]; then
    log_error "Neo4j failed to respond after $max_attempts attempts"
    log_error "Docker logs:"
    docker logs iris_neo4j | tail -20
    exit 1
  fi

  # Test database layer - actually execute queries
  log_info "Testing Neo4j database layer functionality..."

  # Test 1: Create a test node
  log_info "  Test 1: Creating test node..."
  docker exec iris_neo4j cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" \
    "CREATE (n:HealthCheck {name: 'iris-edge-deployment-test', timestamp: timestamp()}) RETURN n;" &>/dev/null || {
    log_error "Failed to create test node - authentication or permissions issue"
    exit 1
  }
  log_success "  ✓ Node creation works"

  # Test 2: Query the test node
  log_info "  Test 2: Querying test node..."
  QUERY_RESULT=$(docker exec iris_neo4j cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" \
    "MATCH (n:HealthCheck {name: 'iris-edge-deployment-test'}) RETURN COUNT(n) as count;" 2>/dev/null | tail -1)

  if [ "$QUERY_RESULT" -ge 1 ]; then
    log_success "  ✓ Node retrieval works"
  else
    log_error "Failed to retrieve test node - query issue"
    exit 1
  fi

  # Test 3: Create relationship
  log_info "  Test 3: Creating relationships..."
  docker exec iris_neo4j cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" \
    "MATCH (n:HealthCheck {name: 'iris-edge-deployment-test'})
         CREATE (n)-[:VERIFIED_ON]->(h:System {name: 'iris-edge'}) RETURN h;" &>/dev/null || {
    log_error "Failed to create relationship - graph structure issue"
    exit 1
  }
  log_success "  ✓ Relationship creation works"

  # Test 4: Traverse graph
  log_info "  Test 4: Traversing graph relationships..."
  TRAVERSE_RESULT=$(docker exec iris_neo4j cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" \
    "MATCH (n:HealthCheck)-[:VERIFIED_ON]->(s:System) RETURN COUNT(s) as count;" 2>/dev/null | tail -1)

  if [ "$TRAVERSE_RESULT" -ge 1 ]; then
    log_success "  ✓ Graph traversal works"
  else
    log_warning "  ⚠ Graph traversal returned no results"
  fi

  # Test 5: Delete test data (cleanup)
  log_info "  Cleaning up test data..."
  docker exec iris_neo4j cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" \
    "MATCH (n:HealthCheck {name: 'iris-edge-deployment-test'}) DETACH DELETE n;" &>/dev/null
  docker exec iris_neo4j cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" \
    "MATCH (s:System {name: 'iris-edge'}) DETACH DELETE s;" &>/dev/null

  log_success "Neo4j database layer fully functional ✓"
}

# ============================================================================
# Main Execution
# ============================================================================

main() {
  log_info "Starting iris-edge deployment..."
  log_info "Repository: $REPO_DIR"
  log_info "Timestamp: $(date)"

  step_1_check_docker
  step_2_check_repo
  step_3_check_env
  step_4_check_compose
  step_5_check_volumes
  step_6_start_services
  step_7_check_postgres
  step_8_check_neo4j

  # Summary
  log_step "✅ IRIS-EDGE DEPLOYMENT SUCCESSFUL"
  log_success "All checks passed!"
  echo -e ""
  log_info "Summary:"
  log_info "  PostgreSQL: Ready on port 5433 (internal: 5432)"
  log_info "  Neo4j: Ready on port 7688 (internal: 7687)"
  log_info "  pgvector: Extension will be created by application"
  echo -e ""
  log_info "Next steps:"
  log_info "  1. Verify connectivity from iris-core"
  log_info "  2. Deploy iris-core with updated code"
  log_info "  3. Initialize database schema with pgvector indexes"
}

# Run main function
main
