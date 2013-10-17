#!/usr/bin/env python

import mkt
from mkt.developers.forms import ban_unrated_game
from mkt.webapps.models import AddonExcludedRegion as AER, Webapp


def run():
    """
    Backfill Webapp Geodata by inferring regional popularity from
    AddonExcludedRegion objects (or lack thereof).
    Remove AddonExcludedRegion objects, except for unrated games.
    """

    pks = AER.objects.values_list('addon', flat=True).distinct()

    for pk in pks:
        app = Webapp.objects.get(id=pk)

        # If this app was excluded in every region except one,
        # let's consider it regionally popular in that particular region.
        region_ids = app.get_region_ids()
        if len(region_ids) == 1:
            geodata = {}
            region = mkt.regions.REGIONS_CHOICES_ID_DICT[region_ids[0]].slug
            geodata['popular_region'] = region
            app.geodata.update(**geodata)

    # Remove all existing exclusions, since all apps are public in every
    # region by default. If developers want to hard-restrict their apps
    # they can now do that.
    AER.objects.all().delete()

    # Let's still ban unrated games until the IARC migration happens.
    for pk in pks:
        app = Webapp.objects.get(id=pk)
        ban_unrated_game(app)
