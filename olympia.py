"""Performs a number of path mutation and monkey patching operations which are
required for Olympia to start up correctly."""

import os
import sys


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")


def update_system_path():
    """Add our `apps` directory to the front of `sys.path` so our app modules
    are importable without the `apps.` prefix."""

    ROOT = os.path.dirname(os.path.abspath(__file__))
    # Insert the 'apps' folder to the front of sys.path so it takes precedence.
    sys.path.insert(0, os.path.join(ROOT, 'apps'))


def load_newrelic(self):
    """Init NewRelic, if we're configured to use it.

    Note that this get's called in zamboni.py once django
    is already setup. Thus we can safely import `django.conf.settings`
    """
    from django.conf import settings

    newrelic_ini = getattr(settings, 'NEWRELIC_INI', None)

    if newrelic_ini:
        import newrelic.agent
        try:
            newrelic.agent.initialize(newrelic_ini)
            return True
        except Exception:
            log.exception('Failed to load new relic config.')

    return False


update_system_path()
