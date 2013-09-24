from celery.task.sets import TaskSet
import cronjobs

from amo.utils import chunked

import mkt
from mkt.developers.tasks import region_email, region_exclude
from mkt.webapps.models import get_excluded_in, Webapp


def _region_email(ids, regions):
    ts = [region_email.subtask(args=[chunk, regions])
          for chunk in chunked(ids, 100)]
    TaskSet(ts).apply_async()


@cronjobs.register
def send_new_region_emails(regions):
    """Email app developers notifying them of new regions added."""
    excluded = get_excluded_in([r.slug for r in regions])
    ids = Webapp.objects.exclude(id__in=excluded).values_list('id', flat=True)
    _region_email(ids, regions)


def _region_exclude(ids, regions):
    ts = [region_exclude.subtask(args=[chunk, regions])
          for chunk in chunked(ids, 100)]
    TaskSet(ts).apply_async()


@cronjobs.register
def exclude_new_region(regions):
    """
    Update regional blacklist for app developers who opted out of being
    automatically added to new regions.
    """
    _region_exclude(get_excluded_in(mkt.regions.WORLDWIDE.slug), regions)
