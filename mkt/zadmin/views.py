import datetime

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse

import jingo
from elasticutils.contrib.django import S

import amo
from access import acl
from addons.models import Category
from amo.decorators import any_permission_required, json_view, write
from amo.urlresolvers import reverse
from amo.utils import chunked
from zadmin.decorators import admin_required

import mkt
from mkt.webapps.models import Webapp, WebappIndexer
from mkt.webapps.utils import get_attr_lang
from mkt.webapps.tasks import update_manifests
from mkt.zadmin.models import (FeaturedApp, FeaturedAppCarrier,
                               FeaturedAppRegion)


@transaction.commit_on_success
@write
@any_permission_required([('Admin', '%'),
                          ('FeaturedApps', '%')])
def featured_apps_admin(request):
    return jingo.render(request, 'zadmin/featuredapp.html')


@any_permission_required([('Admin', '%'),
                          ('FeaturedApps', '%')])
def featured_apps_ajax(request):
    cat_slug = None
    if request.method == 'GET':
        cat_slug = request.GET.get('category')
    elif request.method == 'POST':
        if not acl.action_allowed(request, 'FeaturedApps', 'Edit'):
            raise PermissionDenied
        cat_slug = request.POST.get('category')
        deleteid = request.POST.get('delete')
        if deleteid:
            delete_apps = FeaturedApp.objects.no_cache().filter(
                app__id=int(deleteid))
            if not cat_slug:
                delete_apps = delete_apps.filter(category__isnull=True)
            else:
                delete_apps = delete_apps.filter(category__slug=cat_slug)
            delete_apps.delete()
        appid = request.POST.get('add')
        if appid:
            category = None
            if cat_slug:
                try:
                    category = Category.objects.get(slug=cat_slug,
                                                    type=amo.ADDON_WEBAPP)
                except (Category.DoesNotExist,
                        Category.MultipleObjectsReturned):
                    pass
            app, created = FeaturedApp.objects.no_cache().get_or_create(
                category=category, app_id=int(appid))
            if created:
                FeaturedAppRegion.objects.create(
                    featured_app=app, region=mkt.regions.WORLDWIDE.id)

    apps = []
    apps_regions_carriers = []
    if cat_slug:
        apps = FeaturedApp.objects.filter(category__slug=cat_slug)
    else:
        apps = FeaturedApp.objects.filter(category=None)

    for app in apps:
        regions = app.regions.values_list('region', flat=True)
        excluded_regions = app.app.get_excluded_region_ids()
        carriers = app.carriers.values_list('carrier', flat=True)
        apps_regions_carriers.append((app, regions, excluded_regions,
                                      carriers))

    return jingo.render(request, 'zadmin/featured_apps_ajax.html',
                        {'apps_regions_carriers': apps_regions_carriers,
                         'regions': mkt.regions.REGIONS_CHOICES,
                         'carriers': mkt.constants.CARRIER_SLUGS})


@any_permission_required([('Admin', '%'),
                          ('FeaturedApps', 'Edit')])
def set_attrs_ajax(request):
    regions = request.POST.getlist('region[]')
    carriers = set(request.POST.getlist('carrier[]'))
    startdate = request.POST.get('startdate', None)
    enddate = request.POST.get('enddate', None)

    app = request.POST.get('app', None)
    if not app:
        return HttpResponse()
    fa = FeaturedApp.objects.no_cache().get(pk=app)
    if regions or carriers:
        regions = set(int(r) for r in regions)
        fa.regions.exclude(region__in=regions).delete()
        to_create = regions - set(fa.regions.filter(region__in=regions)
                                  .values_list('region', flat=True))
        excluded_regions = fa.app.get_excluded_region_ids()
        for i in to_create:
            if i not in excluded_regions:
                FeaturedAppRegion.objects.create(featured_app=fa, region=i)

        fa.carriers.exclude(carrier__in=carriers).delete()
        to_create = carriers - set(fa.carriers.filter(carrier__in=carriers)
                                   .values_list('carrier', flat=True))
        for c in to_create:
            FeaturedAppCarrier.objects.create(featured_app=fa, carrier=c)

    if startdate:
        fa.start_date = datetime.datetime.strptime(startdate, '%Y-%m-%d')
    else:
        fa.start_date = None
    if enddate:
        fa.end_date = datetime.datetime.strptime(enddate, '%Y-%m-%d')
    else:
        fa.end_date = None
    fa.save()
    return HttpResponse()


@any_permission_required([('Admin', '%'),
                          ('FeaturedApps', '%')])
def featured_categories_ajax(request):
    cats = Category.objects.filter(type=amo.ADDON_WEBAPP)
    return jingo.render(request, 'zadmin/featured_categories_ajax.html', {
        'homecount': FeaturedApp.objects.no_cache().filter(
            category=None).count(),
        'categories': [{
            'name': cat.name,
            'id': cat.slug,
            'count': FeaturedApp.objects.no_cache().filter(
                category=cat).count()
        } for cat in cats]})


@admin_required(reviewers=True)
def manifest_revalidation(request):
    if request.method == 'POST':
        # collect the apps to revalidate
        qs = Q(is_packaged=False, status=amo.STATUS_PUBLIC,
               disabled_by_user=False)
        webapp_pks = Webapp.objects.filter(qs).values_list('pk', flat=True)

        for pks in chunked(webapp_pks, 100):
            update_manifests.delay(list(pks), check_hash=False)

        amo.messages.success(request, "Manifest revalidation queued")

    return jingo.render(request, 'zadmin/manifest.html')


@any_permission_required([('Admin', '%'),
                          ('FeaturedApps', '%')])
@json_view
def featured_suggestions(request):
    q = request.GET.get('q', u'').lower().strip()
    cat_slug = request.GET.get('category')

    filters = {
        'type': amo.ADDON_WEBAPP,
        'status': amo.STATUS_PUBLIC,
        'is_disabled': False,
    }
    if cat_slug:
        filters.update({'category': cat_slug})

    search_fields = ['app_slug', 'name']
    # If search looks like an ID, also search the ID field.
    if q.isdigit():
        qs = search_fields.append('id')

    # Do a search based on the query string.
    qs = S(WebappIndexer).filter(**filters).query(
        should=True, **dict(('{0}__prefix'.format(f), w)
                            for f in search_fields for w in q.split()))

    fields = ['id', 'app_slug', 'default_locale']
    for analyzer in amo.SEARCH_ANALYZER_MAP:
        if (not settings.ES_USE_PLUGINS and
            analyzer in amo.SEARCH_ANALYZER_PLUGINS):
            continue
        fields.append('name_{0}'.format(analyzer))

    qs = qs.values_dict(*fields)

    results = []
    for app in qs[:20]:
        results.append({
            'id': app._id,
            'name': get_attr_lang(app, 'name', app['default_locale']),
            'url': reverse('detail', args=[app['app_slug']]),
        })

    return results
