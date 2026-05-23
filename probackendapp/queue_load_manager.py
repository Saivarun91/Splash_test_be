"""
Queue Load Manager for Dynamic Load-Based Queue Assignment

This module provides utilities for tracking queue load in Redis and selecting
the least-loaded queue for task assignment.
"""

import redis
from django.conf import settings
from typing import Optional, Tuple

# Redis connection pool (reused across requests)
_redis_client = None

NUM_QUEUES = 20


def get_redis_client():
    """
    Get or create a Redis client connection.
    Uses connection pooling for efficiency.
    """
    global _redis_client
    
    if _redis_client is None:
        # Parse Redis URL from Celery broker URL
        broker_url = getattr(settings, 'CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0')
        
        # Extract connection details
        if broker_url.startswith('redis://'):
            # Parse redis://host:port/db
            parts = broker_url.replace('redis://', '').split('/')
            host_port = parts[0]
            db = int(parts[1]) if len(parts) > 1 else 0
            
            if ':' in host_port:
                host, port = host_port.split(':')
                port = int(port)
            else:
                host = host_port
                port = 6379
            
            _redis_client = redis.Redis(
                host=host,
                port=port,
                db=db,
                decode_responses=True,  # Return strings instead of bytes
                socket_connect_timeout=5,
                socket_timeout=5,
            )
        else:
            # Fallback to default
            _redis_client = redis.Redis(
                host='127.0.0.1',
                port=6379,
                db=0,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
    
    return _redis_client


def get_queue_pending_key(queue_name: str) -> str:
    """Get Redis key for pending tasks counter."""
    return f'queue:{queue_name}:pending'


def get_queue_running_key(queue_name: str) -> str:
    """Get Redis key for running tasks counter."""
    return f'queue:{queue_name}:running'


def increment_pending(queue_name: str) -> int:
    """
    Atomically increment the pending tasks counter for a queue.
    
    Args:
        queue_name: Name of the queue (e.g., 'queue_0')
    
    Returns:
        New pending count after increment
    """
    r = get_redis_client()
    key = get_queue_pending_key(queue_name)
    return r.incr(key)


def decrement_pending(queue_name: str) -> int:
    """
    Atomically decrement the pending tasks counter for a queue.
    Prevents negative values.
    
    Args:
        queue_name: Name of the queue
    
    Returns:
        New pending count after decrement
    """
    r = get_redis_client()
    key = get_queue_pending_key(queue_name)
    # Use MAX(0, value - 1) to prevent negative values
    pipe = r.pipeline()
    pipe.get(key)
    pipe.decr(key)
    result = pipe.execute()
    current = int(result[0] or 0)
    new_value = max(0, current - 1)
    if new_value != current - 1:
        # If we prevented negative, set it explicitly
        r.set(key, new_value)
    return new_value


def increment_running(queue_name: str) -> int:
    """
    Atomically increment the running tasks counter for a queue.
    
    Args:
        queue_name: Name of the queue
    
    Returns:
        New running count after increment
    """
    r = get_redis_client()
    key = get_queue_running_key(queue_name)
    return r.incr(key)


def decrement_running(queue_name: str) -> int:
    """
    Atomically decrement the running tasks counter for a queue.
    Prevents negative values.
    
    Args:
        queue_name: Name of the queue
    
    Returns:
        New running count after decrement
    """
    r = get_redis_client()
    key = get_queue_running_key(queue_name)
    # Use MAX(0, value - 1) to prevent negative values
    pipe = r.pipeline()
    pipe.get(key)
    pipe.decr(key)
    result = pipe.execute()
    current = int(result[0] or 0)
    new_value = max(0, current - 1)
    if new_value != current - 1:
        # If we prevented negative, set it explicitly
        r.set(key, new_value)
    return new_value


def get_queue_load(queue_name: str) -> Tuple[int, int]:
    """
    Get current load for a queue (pending, running).
    
    Args:
        queue_name: Name of the queue
    
    Returns:
        Tuple of (pending_count, running_count)
    """
    r = get_redis_client()
    pending_key = get_queue_pending_key(queue_name)
    running_key = get_queue_running_key(queue_name)
    
    # Use pipeline for atomic read
    pipe = r.pipeline()
    pipe.get(pending_key)
    pipe.get(running_key)
    results = pipe.execute()
    
    pending = int(results[0] or 0)
    running = int(results[1] or 0)
    
    return (pending, running)


def get_all_queue_loads() -> dict:
    """
    Get load for all queues in a single Redis operation.
    
    Returns:
        Dictionary mapping queue_name -> (pending, running)
    """
    r = get_redis_client()
    
    # Build all keys
    queue_names = [f'queue_{i}' for i in range(NUM_QUEUES)]
    pending_keys = [get_queue_pending_key(q) for q in queue_names]
    running_keys = [get_queue_running_key(q) for q in queue_names]
    
    # Read all counters in one pipeline (atomic)
    pipe = r.pipeline()
    for key in pending_keys + running_keys:
        pipe.get(key)
    
    results = pipe.execute()
    
    # Split results into pending and running
    num_queues = len(queue_names)
    pending_values = results[:num_queues]
    running_values = results[num_queues:]
    
    # Build result dictionary
    loads = {}
    for i, queue_name in enumerate(queue_names):
        pending = int(pending_values[i] or 0)
        running = int(running_values[i] or 0)
        loads[queue_name] = (pending, running)
    
    return loads


def select_best_queue() -> str:
    """
    Select the queue with the lowest total load (pending + running).
    If multiple queues have the same lowest load, pick deterministically
    (by queue index).
    
    Returns:
        Queue name (e.g., 'queue_0')
    """
    loads = get_all_queue_loads()
    
    # Calculate total load for each queue
    queue_loads = []
    for queue_name, (pending, running) in loads.items():
        total_load = pending + running
        queue_loads.append((total_load, queue_name))
    
    # Sort by load (ascending), then by queue name for determinism
    queue_loads.sort(key=lambda x: (x[0], x[1]))
    
    # Return the queue with lowest load
    return queue_loads[0][1]


def reset_queue_counters(queue_name: Optional[str] = None):
    """
    Reset queue counters (useful for testing or recovery).
    If queue_name is None, resets all queues.
    
    Args:
        queue_name: Optional specific queue to reset, or None for all
    """
    r = get_redis_client()
    
    if queue_name:
        r.delete(get_queue_pending_key(queue_name))
        r.delete(get_queue_running_key(queue_name))
    else:
        # Reset all queues
        queue_names = [f'queue_{i}' for i in range(NUM_QUEUES)]
        keys_to_delete = []
        for q in queue_names:
            keys_to_delete.append(get_queue_pending_key(q))
            keys_to_delete.append(get_queue_running_key(q))
        
        if keys_to_delete:
            r.delete(*keys_to_delete)

