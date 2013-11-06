import logging

from django.core.management.base import BaseCommand, CommandError

log = logging.getLogger('z.task')


class Command(BaseCommand):
    help = ('Exclude apps in a given region. Syntax: \n'
            '    ./manage.py exclude_region <region_slug>')

    def handle(self, *args, **options):
        # Avoid import error.
        from mkt.webapps.models import Webapp
        from mkt.webapps.utils import get_region

        try:
            region_slug = args[0]
        except IndexError:
            raise CommandError(self.help)

        region = get_region(region_slug)

        for app in Webapp.objects.all():
            aer, created = app.addonexcludedregion.get_or_create(
                region=region.id)
            if created:
                log.info('[App %s - %s] Excluded in region %r'
                         % (app.pk, app.slug, region.slug))
