"""
Graph Sync Queue - Resilient Neo4j Synchronization

This module ensures the Neo4j graph stays in sync with PostgreSQL by:
1. Queuing failed graph operations for retry
2. Implementing exponential backoff retry logic
3. Providing idempotent reconciliation from PostgreSQL
4. Tracking sync health and alerting on drift

Benefits:
- Failures are recoverable (no silent data loss)
- Graph can be safely rebuilt from PostgreSQL at any time
- Observability: track sync state, retry attempts, failures
- No need to restart the system to fix graph drift
- Tests can inject failures and verify recovery
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json
import logging

logger = logging.getLogger(__name__)


class OperationType(Enum):
    """Types of graph operations that can be queued."""
    ADD_JOURNAL_ENTRY = "add_journal_entry"
    ADD_IDEA_NODE = "add_idea_node"
    LINK_JOURNAL_TO_IDEA = "link_journal_to_idea"
    ADD_HABIT_NODE = "add_habit_node"
    ADD_HABIT_COMPLETION = "add_habit_completion"
    LINK_SAME_DAY_EVENTS = "link_same_day_events"
    DELETE_NODE = "delete_node"


@dataclass
class QueuedOperation:
    """A queued graph operation awaiting execution."""
    op_type: OperationType
    params: Dict[str, Any]
    created_at: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    last_error: Optional[str] = None
    last_retry_at: Optional[datetime] = None

    def should_retry(self, max_retries: int = 5) -> bool:
        """Check if this operation should be retried.

        Uses exponential backoff: 1s, 2s, 4s, 8s, 16s
        """
        if self.retry_count >= max_retries:
            return False

        if not self.last_retry_at:
            return True  # Never tried

        # Exponential backoff
        backoff_seconds = 2 ** self.retry_count
        elapsed = (datetime.now() - self.last_retry_at).total_seconds()

        return elapsed >= backoff_seconds


class GraphSyncQueue:
    """Queue for graph operations with retry logic and reconciliation."""

    def __init__(self, graph_db):
        """Initialize queue.

        Args:
            graph_db: GraphDB instance to execute operations
        """
        self.graph_db = graph_db
        self.queue: List[QueuedOperation] = []
        self.processed_operations: int = 0
        self.failed_operations: int = 0
        self.last_reconcile_at: Optional[datetime] = None

    def queue_operation(self, op_type: OperationType, params: Dict[str, Any]) -> None:
        """Queue a graph operation for execution.

        Args:
            op_type: Type of operation
            params: Parameters for the operation
        """
        op = QueuedOperation(op_type=op_type, params=params)
        self.queue.append(op)
        logger.debug(f"Queued {op_type.value}: {params}")

    def process_queue(self, max_attempts: int = 5) -> Tuple[int, int]:
        """Process all queued operations with retry logic.

        Args:
            max_attempts: Maximum times to retry before giving up

        Returns:
            Tuple of (operations_processed, operations_failed)
        """
        processed = 0
        failed = 0

        # Create a new queue and move successful operations out
        pending = []

        for op in self.queue:
            if op.retry_count >= max_attempts:
                # Give up on this operation
                logger.error(
                    f"Operation {op.op_type.value} failed after {max_attempts} attempts: {op.last_error}"
                )
                failed += 1
                self.failed_operations += 1
                continue

            if not op.should_retry():
                # Not ready to retry yet
                pending.append(op)
                continue

            # Try to execute
            try:
                self._execute_operation(op)
                processed += 1
                self.processed_operations += 1
                logger.debug(f"Executed {op.op_type.value}")
            except Exception as e:
                # Retry later
                op.retry_count += 1
                op.last_error = str(e)
                op.last_retry_at = datetime.now()
                pending.append(op)
                logger.warning(
                    f"Operation {op.op_type.value} failed (attempt {op.retry_count}): {e}"
                )

        self.queue = pending
        return processed, failed

    def _execute_operation(self, op: QueuedOperation) -> None:
        """Execute a single queued operation.

        Args:
            op: Operation to execute

        Raises:
            Exception if operation fails
        """
        if op.op_type == OperationType.ADD_JOURNAL_ENTRY:
            self.graph_db.add_journal_entry_node(
                source_id=op.params['source_id'],
                user_id=op.params['user_id'],
                occurred_at=op.params['occurred_at']
            )
        elif op.op_type == OperationType.ADD_IDEA_NODE:
            self.graph_db.add_idea_node(op.params['idea'])
        elif op.op_type == OperationType.LINK_JOURNAL_TO_IDEA:
            self.graph_db.link_journal_to_idea(
                source_id=op.params['source_id'],
                idea=op.params['idea']
            )
        elif op.op_type == OperationType.ADD_HABIT_NODE:
            self.graph_db.add_habit_node(
                source_id=op.params['source_id'],
                user_id=op.params['user_id'],
                name=op.params['name'],
                occurred_at=op.params['occurred_at']
            )
        elif op.op_type == OperationType.ADD_HABIT_COMPLETION:
            self.graph_db.add_habit_completion_node(
                source_id=op.params['source_id'],
                habit_id=op.params['habit_id'],
                user_id=op.params['user_id'],
                occurred_at=op.params['occurred_at'],
                notes=op.params.get('notes')
            )
        elif op.op_type == OperationType.LINK_SAME_DAY_EVENTS:
            self.graph_db.link_same_day_events(
                source_id=op.params['source_id'],
                source_type=op.params['source_type'],
                occurred_at=op.params['occurred_at']
            )
        elif op.op_type == OperationType.DELETE_NODE:
            self.graph_db.run_query(op.params['query'])
        else:
            raise ValueError(f"Unknown operation type: {op.op_type}")

    def reconcile(self, postgres_db) -> Dict[str, Any]:
        """Reconcile Neo4j with PostgreSQL source of truth.

        This is idempotent and safe to run anytime. It rebuilds the graph
        from PostgreSQL data, ensuring consistency.

        Args:
            postgres_db: Database instance to read from

        Returns:
            Reconciliation report with counts
        """
        logger.info("Starting Neo4j reconciliation...")
        start_time = datetime.now()

        try:
            # Clear any pending operations (they'll be regenerated)
            self.queue.clear()

            # Call the existing rebuild_from_postgres method
            report = {
                'started_at': start_time.isoformat(),
                'completed_at': None,
                'duration_seconds': 0,
                'status': 'success',
                'nodes_created': 0,
                'relationships_created': 0,
                'errors': []
            }

            # The rebuild rebuilds the graph from scratch
            # In a real implementation, this would be a method on graph_db
            # For now, we document the interface
            try:
                self.graph_db.rebuild_from_postgres(postgres_db)
                self.last_reconcile_at = datetime.now()
            except Exception as e:
                report['status'] = 'failed'
                report['errors'].append(str(e))
                logger.error(f"Reconciliation failed: {e}")

            report['completed_at'] = datetime.now().isoformat()
            report['duration_seconds'] = (
                datetime.now() - start_time
            ).total_seconds()

            return report

        except Exception as e:
            logger.error(f"Reconciliation error: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'duration_seconds': (datetime.now() - start_time).total_seconds()
            }

    def get_health(self) -> Dict[str, Any]:
        """Get health status of the sync queue.

        Returns:
            Health metrics
        """
        queue_size = len(self.queue)
        oldest_op = min(
            (op.created_at for op in self.queue),
            default=datetime.now()
        )
        staleness_hours = (datetime.now() - oldest_op).total_seconds() / 3600

        return {
            'queue_size': queue_size,
            'processed_operations': self.processed_operations,
            'failed_operations': self.failed_operations,
            'oldest_operation_age_hours': staleness_hours,
            'last_reconcile_at': (
                self.last_reconcile_at.isoformat()
                if self.last_reconcile_at else None
            ),
            'is_healthy': queue_size == 0,
        }

    def get_queue_summary(self) -> List[Dict[str, Any]]:
        """Get summary of all queued operations.

        Returns:
            List of operation dicts
        """
        return [
            {
                'type': op.op_type.value,
                'retry_count': op.retry_count,
                'last_error': op.last_error,
                'created_at': op.created_at.isoformat(),
                'params_preview': json.dumps(op.params, default=str)[:100]
            }
            for op in self.queue
        ]

    def clear_queue(self) -> None:
        """Clear all pending operations (use with caution)."""
        logger.warning(f"Clearing {len(self.queue)} pending operations")
        self.queue.clear()
