#!/usr/bin/env python

import mkt
from mkt.webapps.models import Georestrictions, Webapp


def run():
    for app in Webapp.with_deleted.no_cache():
        g, created = Georestrictions.objects.get_or_create(addon=app)

        old_restrictions = g.to_dict()
        new_restrictions = dict((k, True) for k in old_restrictions)

        for region in app.addonexcludedregion.values_list('region', flat=True):
            slug = mkt.regions.REGIONS_CHOICES_ID_DICT.get(region).slug
            new_restrictions['region_' + slug] = False

        if old_restrictions != new_restrictions:
            app.georestrictions.update(**new_restrictions)
