# PgVector Migration: Deployment Guide

**Status:** Complete pgvector migration from FAISS/ChromaDB to PostgreSQL-native vector search.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Database Server Setup](#database-server-setup)
3. [Application Server Setup](#application-server-setup)
4. [Connection Pooling](#connection-pooling)
5. [Performance Characteristics](#performance-characteristics)
6. [Monitoring & Health Checks](#monitoring--health-checks)
7. [Troubleshooting](#troubleshooting)
8. [Rollback Plan](#rollback-plan)
9. [Further Reading](#further-reading)

---

## Architecture Overview

### Distributed Architecture

The IRIS AI Agent now uses a distributed architecture with PostgreSQL as the centralized vector database:

```
┌─────────────────────────────────────────────────────────────┐
│                      Application Servers                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │  App Server │  │  App Server │  │  App Server │          │
│  │  (FastAPI)  │  │  (FastAPI)  │  │  (FastAPI)  │          │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘          │
│         │                 │                 │                 │
│         └─────────────────┼─────────────────┘                 │
│                           │                                   │
│                 Connection Pool Manager                       │
│                 (psycopg3 with pooling)                       │
│                           │                                   │
└───────────────────────────┼───────────────────────────────────┘
                            │ (TCP/IP)
                            │
┌───────────────────────────┼───────────────────────────────────┐
│                           ▼                                    │
│                 ┌──────────────────┐                          │
│                 │  PgBouncer       │  (Optional - Production) │
│                 │  Connection Pool │                          │
│                 └────────┬─────────┘                          │
│                          │                                    │
│                 ┌────────▼─────────┐                          │
│                 │   PostgreSQL     │                          │
│                 │  ┌────────────┐  │                          │
│                 │  │ iris_agent │  │                          │
│                 │  │  database  │  │                          │
│                 │  │            │  │                          │
│                 │  │ embeddings │  │ (IVFFlat index)          │
│                 │  │ table + ix │  │                          │
│                 │  └────────────┘  │                          │
│                 │                  │                          │
│                 │  pgvector ext.   │                          │
│                 └──────────────────┘                          │
│                                                               │
│              Database Server                                  │
└───────────────────────────────────────────────────────────────┘
```

### Key Components

- **PostgreSQL Database**: Centralized storage for all embeddings and application data
- **pgvector Extension**: Native vector type and similarity operators
- **IVFFlat Indexing**: Fast approximate nearest neighbor search (1000x speedup vs sequential scan)
- **Connection Pooling**: Efficient connection management via psycopg3 or PgBouncer
- **Application Servers**: Multiple instances sharing the same PostgreSQL backend

---

## Database Server Setup

### Prerequisites

- PostgreSQL 12+ (14+ recommended for best performance)
- pgvector extension installed
- Network access from application servers
- Sufficient disk space for embeddings table

### Installation Steps

#### Step 1: Install PostgreSQL and pgvector

**On Debian/Ubuntu:**

```bash
# Update package list
sudo apt-get update

# Install PostgreSQL
sudo apt-get install postgresql-14 postgresql-contrib-14

# Install pgvector
sudo apt-get install postgresql-14-pgvector
```

**On macOS (via Homebrew):**

```bash
brew install postgresql pgvector
```

**On RHEL/CentOS:**

```bash
sudo yum install postgresql14-server postgresql14-contrib
# Build pgvector from source
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install
```

#### Step 2: Start PostgreSQL Service

```bash
# Linux
sudo systemctl start postgresql
sudo systemctl enable postgresql

# macOS
brew services start postgresql
```

#### Step 3: Verify PostgreSQL is Running

```bash
# Should connect successfully
psql -U postgres -d postgres -c "SELECT version();"
```

#### Step 4: Run Database Initialization Script

Copy `scripts/setup_db.sh` to the database server and execute:

```bash
bash scripts/setup_db.sh localhost 5432 postgres
```

This script will:
- Create the `iris_app` database user
- Create the `iris_agent` database
- Enable pgvector extension
- Create vector indexes (IVFFlat)
- Create supporting indexes for filtering

**Expected Output:**
```
IRIS Database Setup
====================
Creating iris_app database user...
✓ User created
Creating iris_agent database...
✓ Database created
Enabling pgvector extension...
✓ pgvector enabled
Creating vector indexes...
✓ Indexes created

✅ Database setup complete!
Database credentials:
  Host: localhost
  Port: 5432
  Database: iris_agent
  User: iris_app
  (Password: stored in .env)
```

#### Step 5: Verify Database Setup

```bash
# Connect as the iris_app user
PGPASSWORD=iris_password psql -h localhost -p 5432 -U iris_app -d iris_agent

# Inside psql:
\dx                          # Should show pgvector extension
\dt                          # Should list tables
\di embeddings*              # Should show vector indexes

SELECT * FROM pg_indexes
WHERE tablename = 'embeddings'
ORDER BY indexname;
```

### Security Configuration

#### 1. PostgreSQL Authentication (pg_hba.conf)

**For network access from application servers:**

```conf
# IPv4 local connections
host    iris_agent    iris_app    0.0.0.0/0    scram-sha-256

# Or more restrictively:
host    iris_agent    iris_app    192.168.1.0/24    scram-sha-256
```

Then reload configuration:
```bash
sudo systemctl reload postgresql
```

#### 2. Database User Privileges

The setup script creates a limited user with only necessary permissions:

```sql
-- iris_app can connect and use the database
GRANT CONNECT ON DATABASE iris_agent TO iris_app;
GRANT USAGE ON SCHEMA public TO iris_app;

-- Can read/write tables
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO iris_app;

-- Can use sequences (for auto-increment IDs)
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO iris_app;
```

#### 3. SSL/TLS Connection (Production)

**Generate SSL certificates:**

```bash
cd /var/lib/postgresql/14/main

# Generate private key
sudo openssl genrsa -out server.key 2048

# Generate certificate
sudo openssl req -new -x509 -key server.key -out server.crt -days 365

# Set permissions
sudo chown postgres:postgres server.*
sudo chmod 600 server.*
```

**Enable SSL in postgresql.conf:**

```conf
ssl = on
ssl_cert_file = 'server.crt'
ssl_key_file = 'server.key'
```

**Connect via SSL:**

```bash
PGPASSWORD=iris_password psql -h db.example.com -p 5432 \
  -U iris_app -d iris_agent \
  --set=sslmode=require
```

### Performance Tuning

Add these settings to `/etc/postgresql/14/main/postgresql.conf`:

```conf
# Memory
shared_buffers = 256MB              # 25% of system RAM
effective_cache_size = 1GB          # 75% of system RAM
work_mem = 64MB

# Connections
max_connections = 200
max_prepared_transactions = 100

# WAL (Write-Ahead Logging)
wal_buffers = 16MB

# Query Planning
random_page_cost = 1.1              # For SSD storage
effective_io_concurrency = 200      # For SSD storage

# Logging
log_min_duration_statement = 1000   # Log queries > 1 second
log_statement = 'all'               # All statements (dev only)

# Vector Search Optimization
maintenance_work_mem = 256MB        # For index creation
```

Then reload:
```bash
sudo systemctl reload postgresql
```

---

## Application Server Setup

### Prerequisites

- Python 3.11+
- Dependencies from `pyproject.toml` installed
- Network connectivity to PostgreSQL server

### Environment Variables

Create a `.env` file in the application root with:

```env
# PostgreSQL Connection (Distributed Setup)
POSTGRES_HOST=db.example.com          # Database server IP/hostname
POSTGRES_PORT=5432                    # PostgreSQL port
POSTGRES_DB=iris_agent                # Database name
POSTGRES_USER=iris_app                # Database user
POSTGRES_PASSWORD=secure_password     # Database password

# Connection Pool Configuration
DB_POOL_MIN_SIZE=5                    # Minimum pool connections
DB_POOL_MAX_SIZE=20                   # Maximum pool connections
DB_QUERY_TIMEOUT=30                   # Query timeout in seconds

# Other Configuration
ENV=prod                              # dev | prod | test
LOG_LEVEL=INFO
OPENAI_API_KEY=sk-...
```

**Connection Pool Sizing Guide:**

```
DB_POOL_MIN_SIZE = ceil(num_app_servers * 0.5)
DB_POOL_MAX_SIZE = ceil(num_app_servers * 2) + 5

Example:
- 3 app servers: MIN=2, MAX=11
- 5 app servers: MIN=3, MAX=15
- 10 app servers: MIN=5, MAX=25
```

### Installation Steps

#### Step 1: Install Dependencies

```bash
pip install -e .
```

This installs:
- psycopg[binary] - PostgreSQL adapter with connection pooling
- All other dependencies from pyproject.toml

#### Step 2: Verify Database Connection

```bash
python -c "
from agent.config import settings
from agent.db_pool import ConnectionPool

pool = ConnectionPool(settings)
conn = pool.get_connection()
print('✓ Connected to PostgreSQL successfully')
conn.close()
pool.close_all()
"
```

#### Step 3: Run Application

```bash
# Development
python iris_api.py

# Production with uvicorn
uvicorn iris_api:app --host 0.0.0.0 --port 8000 --workers 4
```

### Multi-Instance Deployment

For scaling across multiple application servers:

```bash
# Server 1
export POSTGRES_HOST=db.example.com
uvicorn iris_api:app --host 0.0.0.0 --port 8000 --workers 4

# Server 2
export POSTGRES_HOST=db.example.com
uvicorn iris_api:app --host 0.0.0.0 --port 8000 --workers 4

# Server 3
export POSTGRES_HOST=db.example.com
uvicorn iris_api:app --host 0.0.0.0 --port 8000 --workers 4

# Use load balancer (nginx) to distribute traffic
# nginx config would route to 8000 on each server
```

---

## Connection Pooling

### psycopg3 Built-in Pooling

The application uses `psycopg` connection pooling (configured in `agent/database.py`):

```python
# Connection pool is managed by the database module
# psycopg maintains connections based on application needs
# See agent/database.py for the current implementation
```

**Pooling Behavior:**

- Minimum connections maintained even when idle
- Grows up to max connections under load
- Idle connections closed after 30 minutes
- Failed connections automatically retried

### Optional: PgBouncer (Connection Pooler)

For very high concurrency or strict connection limits, use PgBouncer:

#### Installation

```bash
# Debian/Ubuntu
sudo apt-get install pgbouncer

# macOS
brew install pgbouncer
```

#### Configuration (/etc/pgbouncer/pgbouncer.ini)

```ini
[databases]
iris_agent = host=localhost port=5432 user=iris_app password=password

[pgbouncer]
listen_port = 6432
listen_addr = 0.0.0.0
auth_file = /etc/pgbouncer/userlist.txt
auth_type = scram-sha-256

# Pooling Mode
pool_mode = transaction          # Transaction-level pooling (most compatible)
max_client_conn = 1000
default_pool_size = 25
min_pool_size = 5
reserve_pool_size = 5
reserve_pool_timeout = 3
max_db_connections = 100
max_user_connections = 100

# Timeouts
server_idle_timeout = 600
client_idle_timeout = 600
query_timeout = 0               # Handled by application

# Logging
log_connections = 1
log_disconnections = 1
log_stats = 1
stats_period = 60
```

#### Create User List

```bash
# Generate scram-sha-256 password hash
python3 -c "
from hashlib import sha256
import hmac

password = 'iris_password'
salt = b'random_salt_16_bytes_'
iterations = 4096
key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, iterations)
print(f'\"iris_app\" \"{key.hex()}\"')
"

# Or simply: echo '"iris_app" "iris_password"' > /etc/pgbouncer/userlist.txt
```

#### Start PgBouncer

```bash
sudo systemctl start pgbouncer
sudo systemctl enable pgbouncer

# Connect via PgBouncer
PGPASSWORD=iris_password psql -h localhost -p 6432 -U iris_app -d iris_agent
```

#### Monitor PgBouncer

```bash
# Check connection stats
psql -h localhost -p 6432 -U pgbouncer -d pgbouncer -c "SHOW POOLS;"

# Sample output:
#  database  | user     | cl_active | cl_waiting | sv_active | sv_idle
# -----------+----------+-----------+------------+-----------+----------
#  iris_agent| iris_app |        12 |          0 |        20 |        5
```

**PgBouncer Pooling Modes:**

| Mode | Use Case | Benefit |
|------|----------|---------|
| `session` | Long-lived connections | No transaction overhead |
| `transaction` | Multiple connections | Low latency, better scaling |
| `statement` | Single queries | Extreme scaling, less isolation |

Most applications use `transaction` mode.

---

## Performance Characteristics

### IVFFlat Index Performance

The embedding search uses IVFFlat (Inverted File with Flat) indexing:

**Setup:** 100 cluster lists, 1536-dimensional vectors (OpenAI embeddings)

**Query Performance:**

```
Latency by dataset size:
  10K embeddings:   1-2 ms
  100K embeddings:  2-3 ms
  1M embeddings:    3-5 ms
  10M embeddings:   5-10 ms

Accuracy trade-off:
  IVFFlat (100 lists): ~99% accuracy, 1000x faster
  Exact search:        100% accuracy, 1000x slower
```

### Benchmark Query

To measure query performance:

```sql
-- Warm up cache
SELECT 1 FROM embeddings LIMIT 1;

-- Run similarity search with timing
\timing on

SELECT id, source_type, source_id, (vector <-> '[0.1, 0.2, ...]'::vector) as distance
FROM embeddings
WHERE source_type = 'memory'
ORDER BY vector <-> '[0.1, 0.2, ...]'::vector
LIMIT 10;

-- Should complete in 2-5ms
```

### Memory Usage

Vector storage is memory-efficient:

```
Per embedding: 6144 bytes (1536 floats × 4 bytes)

Examples:
  100K embeddings:   614 MB
  1M embeddings:     6.1 GB
  10M embeddings:    61 GB
```

### Index Building

Creating/updating IVFFlat index:

```sql
CREATE INDEX CONCURRENTLY embeddings_vector_ivf ON embeddings
USING ivfflat (vector vector_cosine_ops)
WITH (lists = 100);

-- Timing:
-- 100K vectors:   ~5 seconds
-- 1M vectors:     ~30 seconds
-- 10M vectors:    ~5 minutes
```

Use `CONCURRENTLY` flag to avoid locking table during index creation.

---

## Monitoring & Health Checks

### Health Check Endpoint

IRIS provides a health check endpoint in `iris_api.py`:

```python
@app.get("/health")
async def health_check():
    """Simple endpoint to check if the API is running"""
    return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}
```

**Health Check Usage:**

```bash
# Check application health
curl http://localhost:8000/health

# Response:
# {
#   "status": "ok",
#   "timestamp": "2026-02-04T14:23:45.123456+00:00"
# }
```

### Monitoring Queries

#### 1. Connection Status

```sql
-- Active connections
SELECT
    usename,
    application_name,
    state,
    query_start,
    backend_start,
    count(*) as num_connections
FROM pg_stat_activity
WHERE datname = 'iris_agent'
GROUP BY usename, application_name, state, query_start, backend_start
ORDER BY num_connections DESC;
```

#### 2. Index Utilization

```sql
-- IVFFlat index performance
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan as index_scans,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched,
    CASE
        WHEN idx_tup_read = 0 THEN 'Not used'
        ELSE round(100.0 * idx_tup_fetch / idx_tup_read, 2) || '%'
    END as efficiency
FROM pg_stat_user_indexes
WHERE tablename = 'embeddings'
ORDER BY idx_scan DESC;
```

#### 3. Query Performance

```sql
-- Slow queries (requires log_min_duration_statement = 1000)
SELECT
    query,
    mean_exec_time::numeric(10,2) as avg_time_ms,
    max_exec_time::numeric(10,2) as max_time_ms,
    calls,
    total_exec_time::numeric(15,2) as total_time_ms
FROM pg_stat_statements
WHERE query LIKE '%embeddings%'
ORDER BY mean_exec_time DESC
LIMIT 10;
```

#### 4. Vector Search Latency

```sql
-- Typical vector search performance
EXPLAIN ANALYZE
SELECT id, source_type,
       (vector <-> '[0.1, 0.2, ...]'::vector) as distance
FROM embeddings
ORDER BY vector <-> '[0.1, 0.2, ...]'::vector
LIMIT 10;

-- Look for:
-- - Index Scan on embeddings_vector_ivf
-- - Planning Time: < 0.1ms
-- - Execution Time: 2-5ms
```

#### 5. Table and Index Statistics

```sql
-- Table size and bloat
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) as table_size,
    pg_size_pretty(pg_indexes_size(schemaname||'.'||tablename)) as indexes_size
FROM pg_tables
WHERE tablename = 'embeddings';
```

### Prometheus Metrics Export

For integration with Prometheus:

```python
from prometheus_client import Counter, Histogram, Gauge, generate_latest

# Define metrics
vector_search_duration = Histogram(
    'vector_search_duration_seconds',
    'Vector search query duration',
    buckets=(0.001, 0.002, 0.005, 0.010, 0.020, 0.050)
)

db_connections_active = Gauge(
    'db_connections_active',
    'Active database connections'
)

embeddings_indexed = Gauge(
    'embeddings_indexed_total',
    'Total embeddings in index'
)

@app.route('/metrics', methods=['GET'])
def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest()
```

---

## Troubleshooting

### Connection Issues

#### Problem: "Connection refused" or "host not found"

**Diagnosis:**
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check network connectivity
telnet db.example.com 5432

# Check PostgreSQL log
tail -50 /var/log/postgresql/postgresql-14-main.log
```

**Solution:**

1. Verify `postgresql.conf` settings:
   ```conf
   listen_addresses = '*'    # or specific IP
   port = 5432
   ```

2. Verify `pg_hba.conf` allows connections:
   ```conf
   host    iris_agent    iris_app    0.0.0.0/0    scram-sha-256
   ```

3. Reload PostgreSQL:
   ```bash
   sudo systemctl reload postgresql
   ```

4. Test connection:
   ```bash
   PGPASSWORD=iris_password psql -h db.example.com -p 5432 \
     -U iris_app -d iris_agent -c "SELECT 1"
   ```

#### Problem: "FATAL: role 'iris_app' does not exist"

**Solution:**

```bash
# Run setup script again
bash scripts/setup_db.sh db.example.com 5432 postgres

# Or manually create user
PGPASSWORD=postgres_password psql -h db.example.com -p 5432 \
  -U postgres -d postgres <<EOF
CREATE USER iris_app WITH PASSWORD 'iris_password';
ALTER USER iris_app CREATEDB;
GRANT CONNECT ON DATABASE iris_agent TO iris_app;
EOF
```

#### Problem: "password authentication failed"

**Solution:**

1. Reset user password:
   ```bash
   PGPASSWORD=postgres_password psql -h db.example.com -p 5432 \
     -U postgres -d postgres <<EOF
   ALTER USER iris_app WITH PASSWORD 'new_password';
   EOF
   ```

2. Update application `.env`:
   ```env
   POSTGRES_PASSWORD=new_password
   ```

3. Restart application

### Slow Queries

#### Problem: Vector searches taking > 5ms

**Diagnosis:**

```sql
-- Check if index is being used
EXPLAIN (ANALYZE, BUFFERS)
SELECT id FROM embeddings
ORDER BY vector <-> '[0.1, 0.2, ...]'::vector
LIMIT 10;

-- Look for "Index Scan using embeddings_vector_ivf"
-- If seeing "Sequential Scan", index not being used
```

**Solution:**

1. Ensure index exists:
   ```sql
   SELECT * FROM pg_indexes WHERE tablename = 'embeddings';
   ```

2. Rebuild index if corrupted:
   ```sql
   REINDEX INDEX CONCURRENTLY embeddings_vector_ivf;
   ```

3. Analyze table for updated statistics:
   ```sql
   ANALYZE embeddings;
   ```

4. Check query planner cost settings:
   ```sql
   SHOW random_page_cost;           -- Should be ~1.1 for SSD
   SHOW effective_cache_size;       -- Should be high
   ```

### Connection Pool Exhaustion

#### Problem: "remaining connection slots are reserved"

**Diagnosis:**

```sql
SELECT
    usename,
    application_name,
    state,
    count(*) as num_connections
FROM pg_stat_activity
GROUP BY usename, application_name, state
ORDER BY num_connections DESC;
```

**Solution:**

1. Increase pool size in `.env`:
   ```env
   DB_POOL_MAX_SIZE=30
   ```

2. Kill idle connections:
   ```sql
   SELECT pg_terminate_backend(pid)
   FROM pg_stat_activity
   WHERE state = 'idle'
   AND idle_in_transaction_session_timeout > 0
   LIMIT 5;
   ```

3. If using PgBouncer, increase:
   ```ini
   [pgbouncer]
   max_client_conn = 2000
   default_pool_size = 50
   max_db_connections = 200
   ```

4. Restart PgBouncer:
   ```bash
   sudo systemctl restart pgbouncer
   ```

### Index Corruption

#### Problem: "ERROR: index is corrupted" or inconsistent results

**Solution:**

```sql
-- Rebuild index (non-blocking)
REINDEX INDEX CONCURRENTLY embeddings_vector_ivf;

-- Or drop and recreate
DROP INDEX CONCURRENTLY embeddings_vector_ivf;

CREATE INDEX CONCURRENTLY embeddings_vector_ivf ON embeddings
USING ivfflat (vector vector_cosine_ops)
WITH (lists = 100);

-- Verify integrity
ANALYZE embeddings;
```

### Memory Issues

#### Problem: "out of memory" errors or slow performance

**Diagnosis:**

```sql
-- Check table and index size
SELECT
    pg_size_pretty(pg_total_relation_size('embeddings')) as total_size,
    pg_size_pretty(pg_relation_size('embeddings')) as table_size,
    pg_size_pretty(pg_indexes_size('embeddings')) as indexes_size;

-- Check cache hit ratio
SELECT
    sum(heap_blks_read) as heap_read,
    sum(heap_blks_hit) as heap_hit,
    round(
        sum(heap_blks_hit)::numeric /
        (sum(heap_blks_hit) + sum(heap_blks_read)),
        4
    ) as ratio
FROM pg_statio_user_tables;
```

**Solution:**

1. Increase PostgreSQL memory:
   ```conf
   shared_buffers = 512MB          # Increase from 256MB
   effective_cache_size = 2GB      # Increase from 1GB
   ```

2. Reduce vector precision (if acceptable):
   ```sql
   -- Quantize vectors to reduce size
   UPDATE embeddings
   SET vector = round(vector::numeric, 2)::vector;
   ```

3. Archive old embeddings:
   ```sql
   -- Move old embeddings to archive table
   CREATE TABLE embeddings_archive AS
   SELECT * FROM embeddings
   WHERE created_at < CURRENT_DATE - INTERVAL '1 year';

   DELETE FROM embeddings
   WHERE created_at < CURRENT_DATE - INTERVAL '1 year';

   VACUUM ANALYZE embeddings;
   ```

### Application-Level Issues

#### Problem: "No available connection from pool"

**Solution:**

1. Check pool configuration in code:
   ```python
   from agent.db_pool import connection_pool
   print(f"Min: {connection_pool.min_size}")
   print(f"Max: {connection_pool.max_size}")
   print(f"Current: {connection_pool.getsize()}")
   ```

2. Increase pool size in `.env`:
   ```env
   DB_POOL_MIN_SIZE=10
   DB_POOL_MAX_SIZE=30
   ```

3. Check for connection leaks in application code:
   ```python
   # BAD - connection never closed
   conn = pool.getconn()
   cur = conn.cursor()
   cur.execute("SELECT ...")
   # Missing: pool.putconn(conn)

   # GOOD - connection properly returned
   conn = pool.getconn()
   try:
       cur = conn.cursor()
       cur.execute("SELECT ...")
   finally:
       pool.putconn(conn)
   ```

---

## Rollback Plan

### Scenario 1: Database Setup Failures

If database initialization fails:

```bash
# Drop the database and user (WARNING: destructive)
PGPASSWORD=postgres_password psql -h db.example.com -p 5432 \
  -U postgres -d postgres <<EOF
DROP DATABASE IF EXISTS iris_agent;
DROP USER IF EXISTS iris_app;
EOF

# Run setup again
bash scripts/setup_db.sh db.example.com 5432 postgres
```

### Scenario 2: Application Won't Start

If application fails to connect after migration:

```bash
# Check connectivity
PGPASSWORD=iris_password psql -h db.example.com -p 5432 \
  -U iris_app -d iris_agent -c "SELECT COUNT(*) FROM embeddings;"

# If connection fails, revert .env to old settings
# and verify fallback behavior works

# Review logs for errors
tail -100 application.log | grep -i error
```

### Scenario 3: Critical Performance Issues

If vector searches are unacceptably slow:

1. Check if using sequential scan instead of index:
   ```sql
   EXPLAIN SELECT * FROM embeddings
   ORDER BY vector <-> '[...]'::vector LIMIT 10;
   ```

2. Rebuild index if needed:
   ```sql
   REINDEX INDEX CONCURRENTLY embeddings_vector_ivf;
   ```

3. If still slow, temporarily disable index and accept slower performance:
   ```sql
   DROP INDEX embeddings_vector_ivf;
   -- Application continues working but slower
   ```

### Scenario 4: Connection Pool Issues

If connection pool exhaustion prevents operation:

1. Temporarily increase pool size:
   ```env
   DB_POOL_MAX_SIZE=100  # Emergency increase
   ```

2. Clear stuck connections:
   ```sql
   SELECT pg_terminate_backend(pid)
   FROM pg_stat_activity
   WHERE datname = 'iris_agent'
   AND state = 'idle for transaction'
   AND query_start < now() - INTERVAL '10 minutes';
   ```

3. Restart application to reset pool state

### Complete Migration Rollback

If reverting to old vector store completely:

```bash
# 1. Stop all application instances
systemctl stop iris-agent

# 2. Revert code to pre-migration version
git checkout <commit-before-migration>

# 3. Downgrade dependencies if needed
pip install -r requirements.old.txt

# 4. Restart application
systemctl start iris-agent

# Note: Old FAISS/ChromaDB data still available if preserved
```

---

## Further Reading

### Official Documentation

- **pgvector GitHub**: https://github.com/pgvector/pgvector
- **PostgreSQL Documentation**: https://www.postgresql.org/docs/
- **psycopg3 Documentation**: https://www.psycopg.org/psycopg3/docs/
- **pgBouncer Documentation**: https://www.pgbouncer.org/

### Vector Search Optimization

- **IVFFlat Indexing**: https://github.com/pgvector/pgvector#indexing
- **Vector Similarity**: https://en.wikipedia.org/wiki/Similarity_measure
- **Approximate Nearest Neighbors**: https://en.wikipedia.org/wiki/Nearest_neighbor_search#Approximate_nearest_neighbor

### PostgreSQL Performance Tuning

- **PostgreSQL Query Planner**: https://www.postgresql.org/docs/current/planner.html
- **Index Types**: https://www.postgresql.org/docs/current/indexes-types.html
- **EXPLAIN Analysis**: https://www.postgresql.org/docs/current/sql-explain.html

### Deployment Patterns

- **Connection Pooling Best Practices**: https://wiki.postgresql.org/wiki/Number_Of_Database_Connections
- **High Availability**: https://www.postgresql.org/docs/current/warm-standby.html
- **Monitoring**: https://www.postgresql.org/docs/current/monitoring.html

### OpenAI Embeddings

- **Embedding API**: https://platform.openai.com/docs/guides/embeddings
- **Embedding Dimensions**: 1536 (for text-embedding-3-small/large)

---

## Quick Reference

### Common Commands

```bash
# Check database status
psql -h $POSTGRES_HOST -U iris_app -d iris_agent \
  -c "SELECT COUNT(*) as embeddings FROM embeddings;"

# Monitor active connections
psql -h $POSTGRES_HOST -U iris_app -d iris_agent \
  -c "SELECT * FROM pg_stat_activity WHERE datname = 'iris_agent';"

# Check index health
psql -h $POSTGRES_HOST -U iris_app -d iris_agent \
  -c "ANALYZE embeddings; SELECT * FROM pg_stat_user_indexes WHERE tablename = 'embeddings';"

# Backup database
pg_dump -h $POSTGRES_HOST -U iris_app -d iris_agent > backup.sql

# Restore database
psql -h $POSTGRES_HOST -U iris_app -d iris_agent < backup.sql
```

### Environment Variables Summary

| Variable | Example | Purpose |
|----------|---------|---------|
| `POSTGRES_HOST` | `db.example.com` | Database server |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `iris_agent` | Database name |
| `POSTGRES_USER` | `iris_app` | Database user |
| `POSTGRES_PASSWORD` | `*****` | Authentication |
| `DB_POOL_MIN_SIZE` | `5` | Minimum connections |
| `DB_POOL_MAX_SIZE` | `20` | Maximum connections |
| `DB_QUERY_TIMEOUT` | `30` | Query timeout (seconds) |

---

**Last Updated:** 2026-01-25
**Maintainer:** IRIS Development Team
**Version:** 1.0
