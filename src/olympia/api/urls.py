from django.conf import settings
from django.conf.urls import include, patterns, url
from django.db.transaction import non_atomic_requests

import waffle

from olympia.addons.urls import ADDON_ID
from olympia.api import views, views_drf

API_CACHE_TIMEOUT = getattr(settings, 'API_CACHE_TIMEOUT', 500)


# Wrap class views in a lambda call so we get an fresh instance of the class
# for thread-safety.
def class_view(cls):
    return lambda *args, **kw: cls()(*args, **kw)


# Regular expressions that we use in our urls.
type_regexp = '/(?P<addon_type>[^/]*)'
limit_regexp = '/(?P<limit>\d*)'
platform_regexp = '/(?P<platform>\w*)'
version_regexp = '/(?P<version>[^/]*)'
compat_mode = '(?:/(?P<compat_mode>(?:strict|normal|ignore)))?'


def build_urls(base, appendages):
    """
    Many of our urls build off each other:
    e.g.
    /search/:query
    /search/:query/:type
    .
    .
    /search/:query/:type/:limit/:platform/:version
    /search/:query/:type/:limit/:platform/:version/:compatMode
    """
    urls = [base]
    for i in range(len(appendages)):
        urls.append(base + ''.join(appendages[:i + 1]))

    return urls


base_search_regexp = r'search/(?P<query>[^/]+)'
appendages = [type_regexp, limit_regexp, platform_regexp, version_regexp,
              compat_mode]
search_regexps = build_urls(base_search_regexp, appendages)

base_list_regexp = r'list'
appendages.insert(0, '/(?P<list_type>[^/]+)')
list_regexps = build_urls(base_list_regexp, appendages)


class SwitchToDRF(object):
    """
    Waffle switch to move from Piston to DRF.
    """
    def __init__(self, resource_name):
        self.resource_name = resource_name

    @non_atomic_requests
    def __call__(self, *args, **kwargs):
        if waffle.switch_is_active('drf'):
            view_name = self.resource_name + 'View'
            return getattr(views_drf, view_name).as_view()(*args, **kwargs)
        else:
            return (class_view(getattr(views, self.resource_name + 'View'))
                    (*args, **kwargs))


api_patterns = patterns(
    '',
    # Addon_details
    url('addon/%s$' % ADDON_ID, SwitchToDRF('AddonDetail'),
        name='api.addon_detail'),
    url(r'^get_language_packs$', SwitchToDRF('Language'),
        name='api.language'),)

for regexp in search_regexps:
    api_patterns += patterns(
        '',
        url(regexp + '/?$', SwitchToDRF('Search'), name='api.search'))

for regexp in list_regexps:
    api_patterns += patterns(
        '',
        url(regexp + '/?$', SwitchToDRF('List'), name='api.list'))

urlpatterns = patterns(
    '',
    # Redirect api requests without versions
    url('^((?:addon|search|list)/.*)$', views.redirect_view),

    # Piston
    url(r'^1.5/search_suggestions/', views.search_suggestions),
    # Append api_version to the real api views
    url(r'^(?P<api_version>\d+|\d+.\d+)/search/guid:(?P<guids>.*)',
        views.guid_search),
    url(r'^(?P<api_version>\d+|\d+.\d+)/', include(api_patterns)),
    url(r'^v3/accounts/', include('olympia.accounts.urls')),
    url(r'^v3/', include('olympia.signing.urls')),
    url(r'^v3/statistics/', include('olympia.stats.api_urls')),
)
