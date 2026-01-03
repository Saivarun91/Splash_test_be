# Celery Multi-Queue Setup for Multi-Tenant System

This document describes the implementation of a fixed-queue Celery system that prevents one user's bulk tasks from blocking other users' tasks.

## Architecture Overview

- **20 Fixed Queues**: `queue_0` to `queue_19`
- **Consistent Hashing**: Users are consistently routed to the same queue based on their `user_id`
- **Multiple Workers**: All workers listen to all queues, providing horizontal scalability
- **No Per-User Queues**: Fixed number of queues prevents queue proliferation
- **No Task Limits**: No hard caps on tasks per user

## Why This Approach Prevents Blocking

1. **Queue Isolation**: Tasks from different users are distributed across 20 queues using consistent hashing
2. **Parallel Processing**: Multiple workers consume from all queues simultaneously
3. **Fair Distribution**: Even if one user submits many tasks, they only occupy one queue, leaving 19 other queues available for other users
4. **Consistent Routing**: Same user always goes to the same queue, ensuring task ordering within a user's workflow

## Implementation Files

### 1. Celery Configuration (`imgbackend/celery.py`)

```python
import os
from celery import Celery
from kombu import Queue

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'imgbackend.settings')

app = Celery('imgbackend')
app.config_from_object('django.conf:settings', namespace='CELERY')

# Define fixed number of queues (20 queues: queue_0 to queue_19)
NUM_QUEUES = 20
task_queues = [
    Queue(f'queue_{i}', routing_key=f'queue_{i}')
    for i in range(NUM_QUEUES)
]

# Configure task queues
app.conf.task_queues = task_queues

# Set default queue (workers will listen to all queues, but this is a fallback)
app.conf.task_default_queue = 'queue_0'
app.conf.task_default_exchange = 'tasks'
app.conf.task_default_exchange_type = 'direct'
app.conf.task_default_routing_key = 'queue_0'

# Ensure workers can consume from all queues
app.conf.task_create_missing_queues = False

app.autodiscover_tasks()
```

### 2. Queue Selection Utility (`probackendapp/utils.py`)

```python
import hashlib

def get_queue_for_user(user_id, num_queues=20):
    """
    Select a queue for a user based on consistent hashing of user_id.
    This ensures tasks from the same user are routed to the same queue,
    while distributing users across available queues.
    
    Args:
        user_id: User identifier (string or number)
        num_queues: Total number of queues (default: 20)
    
    Returns:
        Queue name string (e.g., 'queue_0', 'queue_1', ..., 'queue_19')
    """
    # Convert user_id to string for consistent hashing
    user_str = str(user_id)
    
    # Hash the user_id to get a consistent integer
    hash_value = int(hashlib.md5(user_str.encode('utf-8')).hexdigest(), 16)
    
    # Map hash to queue index (0 to num_queues-1)
    queue_index = hash_value % num_queues
    
    return f'queue_{queue_index}'


def enqueue_task_to_user_queue(task, user_id, *args, **kwargs):
    """
    Helper function to enqueue a Celery task to the user's assigned queue.
    
    Args:
        task: Celery task (e.g., generate_ai_images_task)
        user_id: User identifier for queue routing
        *args: Positional arguments for the task
        **kwargs: Keyword arguments for the task
    
    Returns:
        AsyncResult: The result of apply_async
    """
    queue_name = get_queue_for_user(user_id) if user_id else 'queue_0'
    return task.apply_async(args=args, kwargs=kwargs, queue=queue_name)
```

### 3. Task Definition (`probackendapp/tasks.py`)

```python
from celery import shared_task

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def generate_single_image_task(self, job_id, collection_id, user_id, product_index, prompt_key):
    """
    Celery task that generates exactly ONE image for a single product/prompt
    combination. All bulk jobs should dispatch many of these tasks in a group.
    """
    return generate_single_product_model_image_background(
        collection_id=collection_id,
        user_id=user_id,
        product_index=product_index,
        prompt_key=prompt_key,
        job_id=job_id,
    )
```

### 4. Task Enqueue Logic Example (`probackendapp/api_views.py`)

```python
from .tasks import generate_single_image_task
from .utils import get_queue_for_user
from celery import group

# Get queue for this user (consistent routing based on user_id)
queue_name = get_queue_for_user(user_id) if user_id else 'queue_0'

# Build a Celery group of single-image tasks, each routed to the user's queue
task_sigs = []
for idx in range(len(item.product_images)):
    for key in prompt_keys:
        task_sig = generate_single_image_task.s(
            job_id,
            str(collection_id),
            user_id,
            idx,
            key,
        )
        # Set queue for this task
        task_sig.set(queue=queue_name)
        task_sigs.append(task_sig)

# Apply the group asynchronously
result_group = group(task_sigs).apply_async()
```

## Celery Worker Command

### Single Worker (Development/Testing)

```bash
cd /path/to/Splash_backend_2/imgbackend
celery -A imgbackend worker --loglevel=info --concurrency=4
```

### Production Worker (Listens to All Queues)

```bash
cd /path/to/Splash_backend_2/imgbackend
celery -A imgbackend worker \
    --loglevel=info \
    --concurrency=4 \
    --queues=queue_0,queue_1,queue_2,queue_3,queue_4,queue_5,queue_6,queue_7,queue_8,queue_9,queue_10,queue_11,queue_12,queue_13,queue_14,queue_15,queue_16,queue_17,queue_18,queue_19
```

### Multiple Workers (Recommended for Production)

Run multiple worker processes to scale horizontally. Each worker listens to all queues:

**Worker 1:**
```bash
celery -A imgbackend worker --loglevel=info --concurrency=4 --hostname=worker1@%h --queues=queue_0,queue_1,queue_2,queue_3,queue_4,queue_5,queue_6,queue_7,queue_8,queue_9,queue_10,queue_11,queue_12,queue_13,queue_14,queue_15,queue_16,queue_17,queue_18,queue_19
```

**Worker 2:**
```bash
celery -A imgbackend worker --loglevel=info --concurrency=4 --hostname=worker2@%h --queues=queue_0,queue_1,queue_2,queue_3,queue_4,queue_5,queue_6,queue_7,queue_8,queue_9,queue_10,queue_11,queue_12,queue_13,queue_14,queue_15,queue_16,queue_17,queue_18,queue_19
```

### Using systemd (Production VPS)

Create `/etc/systemd/system/celery-worker.service`:

```ini
[Unit]
Description=Celery Worker Service
After=network.target redis.service

[Service]
Type=forking
User=your_user
Group=your_group
WorkingDirectory=/path/to/Splash_backend_2/imgbackend
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/celery -A imgbackend worker \
    --loglevel=info \
    --concurrency=4 \
    --queues=queue_0,queue_1,queue_2,queue_3,queue_4,queue_5,queue_6,queue_7,queue_8,queue_9,queue_10,queue_11,queue_12,queue_13,queue_14,queue_15,queue_16,queue_17,queue_18,queue_19 \
    --logfile=/var/log/celery/worker.log \
    --pidfile=/var/run/celery/worker.pid

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable celery-worker
sudo systemctl start celery-worker
```

## Configuration Notes

1. **Concurrency**: Adjust `--concurrency` based on your VPS CPU cores (typically 2-4x CPU cores)
2. **Redis**: Ensure Redis is running and accessible at `redis://127.0.0.1:6379/0`
3. **Monitoring**: Consider using Flower for monitoring: `celery -A imgbackend flower`

## Testing Queue Routing

To verify queues are working:

1. Check Redis queues:
```bash
redis-cli
> KEYS celery*
```

2. Monitor worker logs to see which queue tasks are consumed from

3. Use Flower dashboard:
```bash
pip install flower
celery -A imgbackend flower
```
Visit `http://localhost:5555` to see queue statistics

## Benefits

1. **Isolation**: One user's bulk tasks don't block others
2. **Scalability**: Add more workers to increase throughput
3. **Consistency**: Same user always uses the same queue (maintains order)
4. **Simplicity**: Fixed number of queues, no dynamic queue creation
5. **Production-Ready**: Works on VPS without Docker/Kubernetes

