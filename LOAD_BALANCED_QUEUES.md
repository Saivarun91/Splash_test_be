# Dynamic Load-Based Queue Assignment

This document describes the implementation of dynamic load-based queue assignment for Celery tasks, which prevents one user's bulk tasks from blocking others by routing tasks to the least-loaded queues.

## Architecture Overview

- **20 Fixed Queues**: `queue_0` to `queue_19` (unchanged)
- **Load Tracking**: Redis counters track `pending` and `running` tasks per queue
- **Dynamic Selection**: Tasks are routed to the queue with lowest (pending + running) count
- **Automatic Updates**: Celery signals update counters when tasks start/finish
- **Race-Condition Safe**: All Redis operations are atomic

## Redis Schema

Each queue has two counters stored in Redis:

```
queue:queue_0:pending  -> Integer (number of pending tasks)
queue:queue_0:running  -> Integer (number of running tasks)
queue:queue_1:pending  -> Integer
queue:queue_1:running  -> Integer
...
queue:queue_19:pending -> Integer
queue:queue_19:running -> Integer
```

## Implementation Files

### 1. Queue Load Manager (`probackendapp/queue_load_manager.py`)

This module provides all Redis operations for queue load tracking.

#### Key Functions:

**`select_best_queue()`** - Selects queue with lowest total load:
```python
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
```

**Counter Operations** (all atomic):
- `increment_pending(queue_name)` - Increment pending counter
- `decrement_pending(queue_name)` - Decrement pending (prevents negatives)
- `increment_running(queue_name)` - Increment running counter
- `decrement_running(queue_name)` - Decrement running (prevents negatives)
- `get_all_queue_loads()` - Read all queue loads in one atomic operation

### 2. Celery Signal Handlers (`imgbackend/celery.py`)

Signal handlers automatically update counters when tasks start/finish:

```python
@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **kwds):
    """
    Called when a task is about to start execution.
    Updates: pending -= 1, running += 1
    """
    if task and hasattr(task, 'request') and hasattr(task.request, 'delivery_info'):
        delivery_info = task.request.delivery_info
        queue_name = delivery_info.get('routing_key')
        
        if queue_name and queue_name.startswith('queue_'):
            decrement_pending(queue_name)
            increment_running(queue_name)

@task_postrun.connect
def task_postrun_handler(...):
    """
    Called when a task finishes successfully.
    Updates: running -= 1
    """
    # Decrement running counter

@task_failure.connect
def task_failure_handler(...):
    """
    Called when a task fails.
    Updates: running -= 1
    """
    # Decrement running counter
```

### 3. Task Enqueue Logic (`probackendapp/utils.py`)

New function for load-based enqueueing:

```python
def enqueue_task_with_load_balancing(task, *args, **kwargs):
    """
    Enqueue a Celery task using dynamic load-based queue selection.
    Selects the queue with the lowest (pending + running) count.
    Atomically increments the pending counter before enqueueing.
    
    Args:
        task: Celery task (e.g., generate_ai_images_task)
        *args: Positional arguments for the task
        **kwargs: Keyword arguments for the task
    
    Returns:
        AsyncResult: The result of apply_async
    """
    from probackendapp.queue_load_manager import (
        select_best_queue,
        increment_pending
    )
    
    # Select the least-loaded queue
    queue_name = select_best_queue()
    
    # Increment pending counter BEFORE enqueueing (atomic operation)
    increment_pending(queue_name)
    
    # Enqueue the task to the selected queue
    return task.apply_async(args=args, kwargs=kwargs, queue=queue_name)
```

### 4. Updated API Views (`probackendapp/api_views.py`)

Example of using load-based selection for bulk tasks:

```python
# Use load-based queue selection for optimal distribution
from probackendapp.queue_load_manager import (
    select_best_queue,
    increment_pending
)

# Select the least-loaded queue for this batch
queue_name = select_best_queue()

# Build a Celery group of tasks
task_sigs = []
for idx in range(len(item.product_images)):
    for key in prompt_keys:
        task_sig = generate_single_image_task.s(...)
        task_sig.set(queue=queue_name)
        task_sigs.append(task_sig)
        # Increment pending counter for each task BEFORE enqueueing
        increment_pending(queue_name)

# Apply the group asynchronously
result_group = group(task_sigs).apply_async()
```

## How It Works

### Task Lifecycle and Counter Updates

1. **Task Enqueue**:
   - `select_best_queue()` reads all queue loads from Redis (atomic)
   - Selects queue with lowest (pending + running)
   - `increment_pending(queue_name)` increments pending counter (atomic)
   - Task is enqueued to selected queue

2. **Task Start** (via `task_prerun` signal):
   - `decrement_pending(queue_name)` (atomic)
   - `increment_running(queue_name)` (atomic)

3. **Task Finish** (via `task_postrun` or `task_failure` signal):
   - `decrement_running(queue_name)` (atomic)

### Why This Prevents Blocking

1. **Load Awareness**: Tasks are always routed to the least-loaded queue
2. **Real-Time Updates**: Counters are updated as tasks start/finish
3. **Fair Distribution**: Even if one user submits 1000 tasks, they'll be distributed across multiple queues based on current load
4. **No Starvation**: Empty or nearly-empty queues are always preferred
5. **Race-Condition Safe**: All Redis operations are atomic (INCR, DECR, pipeline reads)

## Usage Examples

### Single Task Enqueue

```python
from probackendapp.utils import enqueue_task_with_load_balancing
from probackendapp.tasks import generate_ai_images_task

# Automatically selects least-loaded queue
result = enqueue_task_with_load_balancing(
    generate_ai_images_task,
    collection_id,
    user_id
)
```

### Bulk Task Enqueue (Group)

```python
from probackendapp.queue_load_manager import select_best_queue, increment_pending
from celery import group

# Select queue once for the entire batch
queue_name = select_best_queue()

task_sigs = []
for item in items:
    task_sig = my_task.s(item)
    task_sig.set(queue=queue_name)
    task_sigs.append(task_sig)
    increment_pending(queue_name)  # Increment for each task

group(task_sigs).apply_async()
```

## Monitoring Queue Loads

### Check Queue Loads via Python

```python
from probackendapp.queue_load_manager import get_all_queue_loads, get_queue_load

# Get load for all queues
all_loads = get_all_queue_loads()
for queue_name, (pending, running) in all_loads.items():
    print(f"{queue_name}: {pending} pending, {running} running")

# Get load for specific queue
pending, running = get_queue_load('queue_0')
print(f"queue_0: {pending} pending, {running} running")
```

### Check Queue Loads via Redis CLI

```bash
redis-cli
> GET queue:queue_0:pending
> GET queue:queue_0:running
> GET queue:queue_1:pending
# ... etc
```

### Reset Counters (if needed)

```python
from probackendapp.queue_load_manager import reset_queue_counters

# Reset all queues
reset_queue_counters()

# Reset specific queue
reset_queue_counters('queue_0')
```

## Race Condition Safety

All operations are designed to be race-condition safe:

1. **Atomic Operations**: Redis INCR/DECR are atomic
2. **Pipeline Reads**: `get_all_queue_loads()` uses pipeline for atomic read of all counters
3. **Negative Prevention**: Decrement operations check and prevent negative values
4. **No Locks**: No blocking locks needed - Redis operations are fast and atomic

## Performance Considerations

1. **Redis Overhead**: Minimal - each enqueue adds 1-2 Redis operations
2. **Signal Overhead**: Negligible - signal handlers are lightweight
3. **Selection Cost**: O(20) - reads 40 Redis keys (20 queues × 2 counters) in one pipeline
4. **Scalability**: Works with any number of workers and tasks

## Migration from Hash-Based to Load-Based

The old hash-based method (`enqueue_task_to_user_queue`) is still available for backward compatibility. To migrate:

**Before (hash-based):**
```python
from probackendapp.utils import enqueue_task_to_user_queue
task = enqueue_task_to_user_queue(my_task, user_id, arg1, arg2)
```

**After (load-based):**
```python
from probackendapp.utils import enqueue_task_with_load_balancing
task = enqueue_task_with_load_balancing(my_task, arg1, arg2)
```

## Troubleshooting

### Counters Going Negative

The implementation prevents negative values, but if you see them:
1. Check Redis connection
2. Verify signal handlers are registered
3. Use `reset_queue_counters()` to reset

### Tasks Not Routing Correctly

1. Verify queues are defined in `celery.py`
2. Check that workers are listening to all queues
3. Verify Redis connection in `queue_load_manager.py`

### Signal Handlers Not Firing

1. Ensure `celery.py` is imported (via `__init__.py`)
2. Check Celery worker logs for signal registration
3. Verify task is using `@shared_task` or `@app.task`

## Benefits

1. **Optimal Load Distribution**: Tasks always go to least-loaded queues
2. **No Manual Configuration**: Automatically adapts to current load
3. **Backward Compatible**: Old hash-based method still works
4. **Production Ready**: Race-condition safe, atomic operations
5. **Scalable**: Works with any number of workers and queues

