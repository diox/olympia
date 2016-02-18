"""
API views
"""
import hashlib
import itertools
import random
import urllib

from django.core.cache import cache
from django.db.transaction import non_atomic_requests
from django.http import HttpResponse, HttpResponsePermanentRedirect
from django.shortcuts import render
from django.template.context import get_standard_processors
from django.utils import translation
from django.utils.encoding import smart_str

import commonware.log
import jingo
import waffle
from tower import ugettext_lazy

from olympia import amo, api
from olympia.addons.models import Addon, CompatOverride
from olympia.amo.decorators import json_view
from olympia.amo.urlresolvers import get_url_prefix
from olympia.search.views import AddonSuggestionsAjax, PersonaSuggestionsAjax
from olympia.versions.compare import version_int


ERROR = 'error'
OUT_OF_DATE = ugettext_lazy(
    u"The API version, {0:.1f}, you are using is not valid.  "
    u"Please upgrade to the current version {1:.1f} API.")
SEARCHABLE_STATUSES = (amo.STATUS_PUBLIC, amo.STATUS_LITE,
                       amo.STATUS_LITE_AND_NOMINATED)

xml_env = jingo.env.overlay()
old_finalize = xml_env.finalize
xml_env.finalize = lambda x: amo.helpers.strip_controls(old_finalize(x))


# Hard limit of 30.  The buffer is to try for locale-specific add-ons.
MAX_LIMIT, BUFFER = 30, 10

# "New" is arbitrarily defined as 10 days old.
NEW_DAYS = 10

log = commonware.log.getLogger('z.api')


def partition(seq, key):
    """Group a sequence based into buckets by key(x)."""
    groups = itertools.groupby(sorted(seq, key=key), key=key)
    return ((k, list(v)) for k, v in groups)


def render_xml_to_string(request, template, context={}):
    if not jingo._helpers_loaded:
        jingo.load_helpers()

    for processor in get_standard_processors():
        context.update(processor(request))

    template = xml_env.get_template(template)
    return template.render(context)


@non_atomic_requests
def render_xml(request, template, context={}, **kwargs):
    """Safely renders xml, stripping out nasty control characters."""
    rendered = render_xml_to_string(request, template, context)

    if 'content_type' not in kwargs:
        kwargs['content_type'] = 'text/xml'

    return HttpResponse(rendered, **kwargs)


@non_atomic_requests
def handler403(request):
    context = {'error_level': ERROR, 'msg': 'Not allowed'}
    return render_xml(request, 'api/message.xml', context, status=403)


@non_atomic_requests
def handler404(request):
    context = {'error_level': ERROR, 'msg': 'Not Found'}
    return render_xml(request, 'api/message.xml', context, status=404)


@non_atomic_requests
def handler500(request):
    context = {'error_level': ERROR, 'msg': 'Server Error'}
    return render_xml(request, 'api/message.xml', context, status=500)


def validate_api_version(version):
    """
    We want to be able to deprecate old versions of the API, therefore we check
    for a minimum API version before continuing.
    """
    if float(version) < api.MIN_VERSION:
        return False

    if float(version) > api.MAX_VERSION:
        return False

    return True


def addon_filter(addons, addon_type, limit, app, platform, version,
                 compat_mode='strict', shuffle=True):
    """
    Filter addons by type, application, app version, and platform.

    Add-ons that support the current locale will be sorted to front of list.
    Shuffling will be applied to the add-ons supporting the locale and the
    others separately.

    Doing this in the database takes too long, so we in code and wrap it in
    generous caching.
    """
    APP = app

    if addon_type.upper() != 'ALL':
        try:
            addon_type = int(addon_type)
            if addon_type:
                addons = [a for a in addons if a.type == addon_type]
        except ValueError:
            # `addon_type` is ALL or a type id.  Otherwise we ignore it.
            pass

    # Take out personas since they don't have versions.
    groups = dict(partition(addons,
                            lambda x: x.type == amo.ADDON_PERSONA))
    personas, addons = groups.get(True, []), groups.get(False, [])

    platform = platform.lower()
    if platform != 'all' and platform in amo.PLATFORM_DICT:
        def f(ps):
            return pid in ps or amo.PLATFORM_ALL in ps

        pid = amo.PLATFORM_DICT[platform]
        addons = [a for a in addons
                  if f(a.current_version.supported_platforms)]

    if version is not None:
        vint = version_int(version)

        def f_strict(app):
            return app.min.version_int <= vint <= app.max.version_int

        def f_ignore(app):
            return app.min.version_int <= vint

        xs = [(a, a.compatible_apps) for a in addons]

        # Iterate over addons, checking compatibility depending on compat_mode.
        addons = []
        for addon, apps in xs:
            app = apps.get(APP)
            if compat_mode == 'strict':
                if app and f_strict(app):
                    addons.append(addon)
            elif compat_mode == 'ignore':
                if app and f_ignore(app):
                    addons.append(addon)
            elif compat_mode == 'normal':
                # This does a db hit but it's cached. This handles the cases
                # for strict opt-in, binary components, and compat overrides.
                v = addon.compatible_version(APP.id, version, platform,
                                             compat_mode)
                if v:  # There's a compatible version.
                    addons.append(addon)

    # Put personas back in.
    addons.extend(personas)

    # We prefer add-ons that support the current locale.
    lang = translation.get_language()

    def partitioner(x):
        return x.description is not None and (x.description.locale == lang)

    groups = dict(partition(addons, partitioner))
    good, others = groups.get(True, []), groups.get(False, [])

    if shuffle:
        random.shuffle(good)
        random.shuffle(others)

    # If limit=0, we return all addons with `good` coming before `others`.
    # Otherwise pad `good` if less than the limit and return the limit.
    if limit > 0:
        if len(good) < limit:
            good.extend(others[:limit - len(good)])
        return good[:limit]
    else:
        good.extend(others)
        return good


@non_atomic_requests
def guid_search(request, api_version, guids):
    lang = request.LANG

    def guid_search_cache_key(guid):
        key = 'guid_search:%s:%s:%s' % (api_version, lang, guid)
        return hashlib.md5(smart_str(key)).hexdigest()

    guids = [g.strip() for g in guids.split(',')] if guids else []

    addons_xml = cache.get_many([guid_search_cache_key(g) for g in guids])
    dirty_keys = set()

    for g in guids:
        key = guid_search_cache_key(g)
        if key not in addons_xml:
            dirty_keys.add(key)
            try:
                addon = Addon.objects.get(guid=g, disabled_by_user=False,
                                          status__in=SEARCHABLE_STATUSES)

            except Addon.DoesNotExist:
                addons_xml[key] = ''

            else:
                addon_xml = render_xml_to_string(request,
                                                 'api/includes/addon.xml',
                                                 {'addon': addon,
                                                  'api_version': api_version,
                                                  'api': api})
                addons_xml[key] = addon_xml

    cache.set_many(dict((k, v) for k, v in addons_xml.iteritems()
                        if k in dirty_keys))

    compat = (CompatOverride.objects.filter(guid__in=guids)
              .transform(CompatOverride.transformer))

    addons_xml = [v for v in addons_xml.values() if v]
    return render_xml(request, 'api/search.xml',
                      {'addons_xml': addons_xml,
                       'total': len(addons_xml),
                       'compat': compat,
                       'api_version': api_version, 'api': api})


@json_view
@non_atomic_requests
def search_suggestions(request):
    if waffle.sample_is_active('autosuggest-throttle'):
        return HttpResponse(status=503)
    cat = request.GET.get('cat', 'all')
    suggesterClass = {
        'all': AddonSuggestionsAjax,
        'themes': PersonaSuggestionsAjax,
    }.get(cat, AddonSuggestionsAjax)
    items = suggesterClass(request, ratings=True).items
    for s in items:
        s['rating'] = float(s['rating'])
    return {'suggestions': items}


# pylint: disable-msg=W0613
@non_atomic_requests
def redirect_view(request, url):
    """
    Redirect all requests that come here to an API call with a view parameter.
    """
    dest = '/api/%.1f/%s' % (api.CURRENT_VERSION,
                             urllib.quote(url.encode('utf-8')))
    dest = get_url_prefix().fix(dest)

    return HttpResponsePermanentRedirect(dest)
