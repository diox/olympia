import logging

from django.core.management.base import BaseCommand, CommandError

import amo
from addons.models import AddonCategory
import mkt

log = logging.getLogger('z.task')


class Command(BaseCommand):
    help = ('Exclude games in a given region. Syntax: \n'
            '    ./manage.py exclude_games <region>')

    def handle(self, *args, **options):
        # Avoid import error.
        from mkt.webapps.models import AddonExcludedRegion as AER

        try:
            region_id = args[0]
        except IndexError:
            raise CommandError(self.help)

        if region_id.isdigit():
            # We got an ID, so get the slug.
            region_slug = mkt.regions.REGIONS_CHOICES_ID_DICT[region_id].slug
        else:
            # We got a slug, so get the ID.
            region_slug = region_id
            region_id = mkt.regions.REGIONS_DICT[region_id].id

        games = AddonCategory.objects.filter(addon__type=amo.ADDON_WEBAPP,
            category__type=amo.ADDON_WEBAPP,
            category__slug='games').values_list('addon', flat=True)

        for app_pk in games:
            AER.objects.get_or_create(addon_id=app_pk, region=region_id)
            log.info('[App %s] Excluded in region %r' % (app_pk, region_slug))
