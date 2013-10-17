#!/usr/bin/env python

import amo

import mkt
from mkt.webapps.models import AddonExcludedRegion as AER, Webapp


def run():
    """
    Backfill Webapp Geodata by inferring regional popularity from
    AddonExcludedRegion objects (or lack thereof).
    Remove AddonExcludedRegion objects, except for unrated games.
    """

    paid_types = amo.ADDON_PREMIUMS + (amo.ADDON_FREE_INAPP,)
    pks = (AER.objects.exclude(addon__premium_type__in=paid_types)
           .values_list('addon', flat=True).distinct())

    games_cat = Webapp.category('games')
    content_region_ids = [x.id for x
                          in mkt.regions.ALL_REGIONS_WITH_CONTENT_RATINGS]

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

        for exclusion in app.addonexcludedregion.all():
            # If this region exclusion is for a content rating, keep it.
            if (games_cat and exclusion.region in content_region_ids and
                app.listed_in(category='games') and
                app.listed_in(region=region) and
                not app.content_ratings_in(region)):
                continue

            print 'Removing %s' % exclusion

            # Remove all other existing exclusions, since all apps are public
            # in every region by default. If developers want to hard-restrict
            # their apps they can now do that.
            exclusion.delete()
