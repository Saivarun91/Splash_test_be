import os
from celery import Celery
from kombu import Queue
from celery.signals import task_prerun, task_postrun, task_failure

# -------------------------------------------------------------------
# Django settings
# -------------------------------------------------------------------
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "imgbackend.settings")

app = Celery("imgbackend")
app.config_from_object("django.conf:settings", namespace="CELERY")

# -------------------------------------------------------------------
# QUEUE CONFIGURATION (20 queues)
# -------------------------------------------------------------------

NUM_QUEUES = 20

QUEUES = [
    Queue(
        name=f"queue_{i}",
        exchange="tasks",
        routing_key=f"queue_{i}",
    )
    for i in range(NUM_QUEUES)
]

app.conf.task_queues = QUEUES

# Default fallback queue
app.conf.task_default_queue = "queue_0"
app.conf.task_default_exchange = "tasks"
app.conf.task_default_exchange_type = "direct"
app.conf.task_default_routing_key = "queue_0"

# 🔑 CRITICAL: routing must be explicit
app.conf.task_routes = {
    "*": {
        "exchange": "tasks",
        "exchange_type": "direct",
        "routing_key": "queue_0",  # overridden by .set(queue=...)
    }
}

# Allow Celery to create queues dynamically if needed
app.conf.task_create_missing_queues = True

# Discover tasks from all installed apps
app.autodiscover_tasks()

# -------------------------------------------------------------------
# SIGNAL HANDLERS (QUEUE LOAD TRACKING)
# -------------------------------------------------------------------

@task_prerun.connect
def task_prerun_handler(
    sender=None, task_id=None, task=None, args=None, kwargs=None, **kwds
):
    """
    When a task STARTS:
    pending -= 1
    running += 1
    """
    try:
        if task and hasattr(task, "request"):
            delivery_info = task.request.delivery_info or {}
            queue_name = delivery_info.get("routing_key")

            if queue_name and queue_name.startswith("queue_"):
                from probackendapp.queue_load_manager import (
                    decrement_pending,
                    increment_running,
                )

                decrement_pending(queue_name)
                increment_running(queue_name)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"task_prerun queue counter update failed: {e}"
        )


@task_postrun.connect
def task_postrun_handler(
    sender=None,
    task_id=None,
    task=None,
    args=None,
    kwargs=None,
    retval=None,
    state=None,
    **kwds,
):
    """
    When a task FINISHES successfully:
    running -= 1
    """
    try:
        if task and hasattr(task, "request"):
            delivery_info = task.request.delivery_info or {}
            queue_name = delivery_info.get("routing_key")

            if queue_name and queue_name.startswith("queue_"):
                from probackendapp.queue_load_manager import decrement_running
                decrement_running(queue_name)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"task_postrun queue counter update failed: {e}"
        )


@task_failure.connect
def task_failure_handler(
    sender=None,
    task_id=None,
    exception=None,
    traceback=None,
    einfo=None,
    **kwds,
):
    """
    When a task FAILS:
    running -= 1
    """
    try:
        from celery import current_task

        task = current_task.request if current_task else None
        if task:
            delivery_info = task.delivery_info or {}
            queue_name = delivery_info.get("routing_key")

            if queue_name and queue_name.startswith("queue_"):
                from probackendapp.queue_load_manager import decrement_running
                decrement_running(queue_name)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"task_failure queue counter update failed: {e}"
        )
