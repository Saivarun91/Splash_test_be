import os
from celery import Celery
from kombu import Queue
from celery.signals import task_prerun, task_postrun, task_failure

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


# ============================================================================
# Celery Signal Handlers for Queue Load Tracking
# ============================================================================

@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **kwds):
    """
    Called when a task is about to start execution.
    Updates queue counters: pending -= 1, running += 1
    """
    try:
        # Get queue name from task request
        if task and hasattr(task, 'request') and hasattr(task.request, 'delivery_info'):
            delivery_info = task.request.delivery_info
            # routing_key contains the queue name for direct exchanges
            queue_name = delivery_info.get('routing_key')
            
            if queue_name and queue_name.startswith('queue_'):
                from probackendapp.queue_load_manager import (
                    decrement_pending,
                    increment_running
                )
                decrement_pending(queue_name)
                increment_running(queue_name)
    except Exception as e:
        # Log but don't fail the task if counter update fails
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to update queue counters in task_prerun: {e}")


@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **kwds):
    """
    Called when a task finishes successfully.
    Updates queue counters: running -= 1
    """
    try:
        # Get queue name from task request
        if task and hasattr(task, 'request') and hasattr(task.request, 'delivery_info'):
            delivery_info = task.request.delivery_info
            queue_name = delivery_info.get('routing_key')
            
            if queue_name and queue_name.startswith('queue_'):
                from probackendapp.queue_load_manager import decrement_running
                decrement_running(queue_name)
    except Exception as e:
        # Log but don't fail the task if counter update fails
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to update queue counters in task_postrun: {e}")


@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, traceback=None, einfo=None, **kwds):
    """
    Called when a task fails.
    Updates queue counters: running -= 1
    """
    try:
        # Get the task instance from current_task context
        from celery import current_task
        task = current_task.request if current_task else None
        
        if task and hasattr(task, 'delivery_info'):
            delivery_info = task.delivery_info
            queue_name = delivery_info.get('routing_key')
            
            if queue_name and queue_name.startswith('queue_'):
                from probackendapp.queue_load_manager import decrement_running
                decrement_running(queue_name)
    except Exception as e:
        # Log but don't fail the task if counter update fails
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to update queue counters in task_failure: {e}")
