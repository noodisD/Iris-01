# IRIS Minimal Companion - v2.0

**A multi-user, local-first AI companion with a robust, layered data architecture.**

This version of the IRIS Minimal Companion has been re-architected from the ground up to support multiple users and provide a powerful foundation for long-term memory and insight extraction. It leverages a modern, multi-database architecture designed for resilience and flexibility.

## Core Architectural Principles

1.  **Single Source of Truth**: **PostgreSQL** is the system's memory. All raw data and even generated embeddings are stored here canonically. This ensures data integrity and allows the entire system to be rebuilt from a single source.
2.  **Disposable Lenses**: **ChromaDB** (vector store) and **Neo4j** (graph database) act as disposable, query-optimized "lenses" for exploring the data. They can be cleared and fully rebuilt from PostgreSQL at any time.
3.  **Local-First & Self-Hostable**: The entire stack is designed to run locally using Docker, making it perfect for self-hosting on a personal server or a Raspberry Pi.
4.  **Decoupled Processing**: A dedicated pipeline layer handles expensive processing (like generating embeddings and extracting graph relationships) asynchronously, so it doesn't block the main application.

## System Architecture

```
┌───────────────────┐       ┌────────────────────────┐
│   CLI Interface   │───────►│  Python Agent Service  │
│  (companion.py)   │       │      (agent/*)         │
└───────────────────┘       └──────────┬─────────────┘
                                       │
     ┌─────────────────────────────────┴─────────────────────────────────┐
     │                                                                   │
┌────▼────┐       ┌─────────────────────┐      ┌──────────────────┐      ┌──────────┐
│ Pipeline│       │    PostgreSQL       │      │     ChromaDB     │      │   Neo4j    │
│  Layer  ├───────►│ (Source of Truth)   ├──────►│ (Vector "Lens")  ├──────►│  (Graph  │
└─────────┘       │ - Raw Text          │      └──────────────────┘      │  "Lens") │
                  │ - Embeddings        │                              └──────────┘
                  └─────────────────────┘
```

## Quick Start

### 1. Prerequisites

-   Docker and Docker Compose
-   Python 3.10+
-   Poetry

### 2. Installation & Setup

1.  **Clone the repository** (if you haven't already).

2.  **Configure Environment Variables:**
    ```bash
    # Copy the example .env file
    cp .env.example .env
    ```
    Now, open the `.env` file and fill in the following:
    -   `OPENAI_API_KEY`: Your API key from OpenAI.
    -   `POSTGRES_PASSWORD`: A secure password for the PostgreSQL database.
    -   `NEO4J_PASSWORD`: A secure password for the Neo4j database.

3.  **Install Python Dependencies:**
    ```bash
    poetry install
    ```

4.  **Build and Start the Services:**
    ```bash
    docker-compose up --build
    ```
    This command will build the Python agent's Docker image and start the `postgres`, `neo4j`, and `agent` containers.

### 3. Usage

Once the services are running, you can interact with the companion through the CLI:

```bash
# Run the companion CLI
poetry run companion
```

You will be prompted to either **Login** or **Create a User**. After authenticating, you can start chatting or use the available commands.

#### CLI Commands

-   `/journal`: Create a new journal entry.
-   `/rebuild-vector`: Rebuild the ChromaDB search index from PostgreSQL.
-   `/rebuild-graph`: Rebuild the Neo4j knowledge graph from PostgreSQL.
-   `/help`: Show the list of commands.
-   `/exit`: Log out and exit the application.

## Project Structure (v2.0)

```
personal_ai_agent_minimal/
├── agent/
│   ├── core.py             # Main orchestrator
│   ├── database.py         # Source of Truth (PostgreSQL)
│   ├── graph_db.py         # Graph Lens (Neo4j)
│   ├── intelligence.py     # LLM wrapper
│   ├── journal_entry.py    # Journaling service
│   ├── memory.py           # Conversation memory service
│   ├── pipeline.py         # Data processing orchestrator
│   └── vector_store.py     # Vector Lens (ChromaDB)
├── data/                   # Persistent data for databases
├── prompts/
├── companion.py            # CLI interface
├── docker-compose.yml      # Docker services definition
├── pyproject.toml          # Dependencies
└── README.md               # This file
```
