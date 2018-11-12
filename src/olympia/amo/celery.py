"""Loads and instantiates Celery, registers our tasks, and performs any other
necessary Celery-related setup. Also provides Celery-related utility methods,
in particular exposing a shortcut to the @task decorator.

Please note that this module should not import model-related code because
Django may not be properly set-up during import time (e.g if this module
is directly being run/imported by Celery)
"""
from __future__ import absolute_import

from django.conf import settings

from celery import Celery, group
from celery.signals import task_failure
from kombu import serialization
from post_request_task.task import (
    PostRequestTask, _start_queuing_tasks, _send_tasks_and_stop_queuing)
from raven import Client
from raven.contrib.celery import register_logger_signal, register_signal

import olympia.core.logger


log = olympia.core.logger.getLogger('z.task')


class AMOTask(PostRequestTask):
    """A custom celery Task base class that inherits from `PostRequestTask`
    to delay tasks and adds a special hack to still perform a serialization
    roundtrip in eager mode, to mimic what happens in production in tests.

    The serialization is applied both to apply_async() and apply() to work
    around the fact that celery groups have their own apply_async() method that
    directly calls apply() on each task in eager mode.

    Note that we should never somehow be using eager mode with actual workers,
    that would cause them to try to serialize data that has already been
    serialized...
    """
    abstract = True

    def _serialize_args_and_kwargs_for_eager_mode(
            self, args=None, kwargs=None, **options):
        producer = options.get('producer')
        with app.producer_or_acquire(producer) as eager_producer:
            serializer = options.get(
                'serializer', eager_producer.serializer
            )
            body = args, kwargs
            content_type, content_encoding, data = serialization.dumps(
                body, serializer
            )
            args, kwargs = serialization.loads(
                data, content_type, content_encoding
            )
        return args, kwargs

    def apply_async(self, args=None, kwargs=None, **options):
        if app.conf.task_always_eager:
            args, kwargs = self._serialize_args_and_kwargs_for_eager_mode(
                args=args, kwargs=kwargs, **options)

        return super(AMOTask, self).apply_async(
            args=args, kwargs=kwargs, **options)

    def apply(self, args=None, kwargs=None, **options):
        if app.conf.task_always_eager:
            args, kwargs = self._serialize_args_and_kwargs_for_eager_mode(
                args=args, kwargs=kwargs, **options)

        return super(AMOTask, self).apply(args=args, kwargs=kwargs, **options)


app = Celery('olympia', task_cls=AMOTask)
task = app.task

app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Hook up Sentry in celery.
raven_client = Client(settings.RAVEN_CONFIG['dsn'])

# register a custom filter to filter out duplicate logs
register_logger_signal(raven_client)

# hook into the Celery error handler
register_signal(raven_client)

# After upgrading raven we can specify loglevel=logging.INFO to override
# the default (which is ERROR).
register_logger_signal(raven_client)


@task_failure.connect
def process_failure_signal(exception, traceback, sender, task_id,
                           signal, args, kwargs, einfo, **kw):
    """Catch any task failure signals from within our worker processes and log
    them as exceptions, so they appear in Sentry and ordinary logging
    output."""

    exc_info = (type(exception), exception, traceback)
    log.error(
        u'Celery TASK exception: {0.__name__}: {1}'.format(*exc_info),
        exc_info=exc_info,
        extra={
            'data': {
                'task_id': task_id,
                'sender': sender,
                'args': args,
                'kwargs': kwargs
            }
        })


def create_chunked_tasks_signatures(
        task, items, chunk_size, task_args=None, task_kwargs=None):
    """
    Splits a task depending on a list of items into a bunch of tasks of the
    specified chunk_size, passing a chunked queryset and optional additional
    arguments to each.

    Return the group of task signatures without executing it."""
    from olympia.amo.utils import chunked
    if task_args is None:
        task_args = ()
    if task_kwargs is None:
        task_kwargs = {}

    return group([
        task.si(chunk, *task_args, **task_kwargs)
        for chunk in chunked(items, chunk_size)
    ])


def pause_all_tasks():
    _start_queuing_tasks()


def resume_all_tasks():
    _send_tasks_and_stop_queuing()
