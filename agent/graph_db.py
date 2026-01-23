"""
Graph Database Layer - Neo4j Lens

This module serves as a disposable, query-optimized lens for exploring
relationships and patterns in the data. It is fully rebuildable from
the PostgreSQL source of truth.
"""

import logging
import atexit
from neo4j import GraphDatabase
from .config import settings

logger = logging.getLogger(__name__)

class GraphDB:
    """Manages the Neo4j graph database connection and all graph-related operations."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GraphDB, cls).__new__(cls)
            cls._instance.driver = None
            cls._instance._connect()
            # Register cleanup function to run at program exit
            atexit.register(cls._instance._cleanup)
        return cls._instance

    def _connect(self):
        """Establish a connection to the Neo4j database."""
        if self.driver is not None:
            return

        logger.info(f"Connecting to Neo4j at {settings.NEO4J_URI}...")
        try:
            self.driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
            )
            self.driver.verify_connectivity()
            logger.info("Successfully connected to Neo4j.")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            self.driver = None
            raise

    def _cleanup(self):
        """Internal method to safely close the Neo4j driver connection."""
        if hasattr(self, 'driver') and self.driver is not None:
            try:
                self.driver.close()
                logger.info("Neo4j connection closed safely.")
            except Exception as e:
                # During shutdown, some errors are expected and can be ignored
                logger.debug(f"Error during Neo4j cleanup: {e}")

    def close(self):
        """Closes the Neo4j driver connection."""
        self._cleanup()

    def run_query(self, query, parameters=None):
        """A generic method to run a Cypher query."""
        with self.driver.session() as session:
            result = session.run(query, parameters)
            return [record for record in result]

    def _create_constraints(self):
        """Create uniqueness constraints in the graph to prevent duplicates."""
        with self.driver.session() as session:
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (j:JournalEntry) REQUIRE j.id IS UNIQUE;")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (i:Idea) REQUIRE i.text IS UNIQUE;")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE;")
            logger.info("Ensured graph constraints exist.")

    def add_journal_entry_node(self, entry_id: int, user_id: int, created_at):
        """Adds or updates a journal entry node and links it to a user."""
        query = """
        MERGE (j:JournalEntry {id: $entry_id})
        SET j.created_at = $created_at
        MERGE (u:User {id: $user_id})
        MERGE (u)-[:WROTE]->(j)
        """
        self.run_query(query, {"entry_id": entry_id, "user_id": user_id, "created_at": created_at})

    def add_habit_node(self, habit_id: int, user_id: int, name: str, created_at):
        """Adds or updates a habit node."""
        query = """
        MERGE (h:Habit {id: $habit_id})
        SET h.name = $name, h.created_at = $created_at
        MERGE (u:User {id: $user_id})
        MERGE (u)-[:TRACKS]->(h)
        """
        self.run_query(query, {"habit_id": habit_id, "user_id": user_id, "name": name, "created_at": created_at})

    def add_habit_completion_node(self, completion_id: int, habit_id: int, user_id: int, completed_at, notes: str = None):
        """Adds a habit completion event."""
        query = """
        MERGE (hc:HabitCompletion {id: $completion_id})
        SET hc.completed_at = $completed_at, hc.notes = $notes
        MERGE (h:Habit {id: $habit_id})
        MERGE (u:User {id: $user_id})
        MERGE (u)-[:COMPLETED]->(hc)
        MERGE (hc)-[:OF_HABIT]->(h)
        """
        self.run_query(query, {
            "completion_id": completion_id, 
            "habit_id": habit_id, 
            "user_id": user_id, 
            "completed_at": completed_at,
            "notes": notes
        })

    def add_idea_node(self, idea_text: str):
        """Adds an idea node. Ideas are unique by their text."""
        query = "MERGE (i:Idea {text: $text})"
        self.run_query(query, {"text": idea_text})

    def link_journal_to_idea(self, entry_id: int, idea_text: str):
        """Creates a [:CONTAINS_IDEA] relationship."""
        query = """
        MATCH (j:JournalEntry {id: $entry_id})
        MATCH (i:Idea {text: $idea_text})
        MERGE (j)-[:CONTAINS_IDEA]->(i)
        """
        self.run_query(query, {"entry_id": entry_id, "idea_text": idea_text})

    def link_same_day_events(self, source_id: int, source_type: str, date_obj):
        """
        Links events (Reflections, HabitCompletions) that occurred on the same day.
        Creates a [:CO_OCCURRED_ON] relationship.
        """
        if not date_obj:
            return

        # Map source_type to Neo4j Label
        label_map = {
            'journal_entry': 'JournalEntry',
            'reflection': 'JournalEntry', # Reflections share JournalEntry label currently
            'habit_completion': 'HabitCompletion'
        }
        source_label = label_map.get(source_type)
        if not source_label:
            return

        date_str = date_obj.strftime("%Y-%m-%d") if hasattr(date_obj, "strftime") else str(date_obj)[:10]

        query = f"""
        MATCH (source:{source_label} {{id: $source_id}})
        MATCH (target)
        WHERE target <> source 
          AND (target:HabitCompletion OR target:JournalEntry)
          AND (
            (target.created_at IS NOT NULL AND toString(target.created_at) STARTS WITH $date_str) OR 
            (target.completed_at IS NOT NULL AND toString(target.completed_at) STARTS WITH $date_str)
          )
        MERGE (source)-[:CO_OCCURRED_ON {{date: $date_str}}]->(target)
        """
        self.run_query(query, {"source_id": source_id, "date_str": date_str})

    def rebuild_from_postgres(self):
        """
        Clears the entire graph and rebuilds it from PostgreSQL data.
        This is a complex operation that demonstrates the 'disposable lens' principle.
        For simplicity, this example only rebuilds journal entries and ideas.
        """
        logger.info("Rebuilding Neo4j graph from PostgreSQL source of truth...")
        
        # Import here to avoid circular dependencies
        from .database import db

        # 1. Clear the entire graph
        logger.info("Clearing existing Neo4j graph...")
        self.run_query("MATCH (n) DETACH DELETE n")

        # 2. (Re)create constraints
        self._create_constraints()
        
        conn = db.get_connection()
        with conn.cursor() as cur:
            # 3. Rebuild journal entries and link to users
            cur.execute("SELECT id, user_id, created_at, raw_text FROM journal_entries;")
            journal_count = 0
            idea_count = 0
            for row in cur:
                entry_id, user_id, created_at, raw_text = row
                
                # Add the journal entry node and link it to the user
                self.add_journal_entry_node(entry_id, user_id, created_at)
                journal_count += 1
                
                # 4. Extract and add ideas (simple example)
                # In a real app, this would use the result of pipeline.extract_entities()
                ideas = [line.strip() for line in raw_text.split('\n') if line.strip().startswith('- ')]
                for idea in ideas:
                    idea_text = idea.lstrip('- ').strip()
                    self.add_idea_node(idea_text)
                    self.link_journal_to_idea(entry_id, idea_text)
                    idea_count += 1
            
            logger.info(f"Successfully rebuilt graph with {journal_count} journal entries and {idea_count} ideas.")


# Global instance
graph_db = GraphDB()
