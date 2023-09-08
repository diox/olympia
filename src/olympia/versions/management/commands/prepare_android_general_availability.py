import csv
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.db.transaction import atomic

import olympia.core.logger
from olympia import amo
from olympia.addons.models import Addon
from olympia.applications.models import AppVersion
from olympia.constants.promoted import LINE, RECOMMENDED
from olympia.files.models import File
from olympia.versions.models import ApplicationsVersions


log = olympia.core.logger.getLogger('z.versions.prepare_android_general_availability')


class Command(BaseCommand):
    """
    A command to prepare for general availability of extensions in Firefox for
    Android by updating compatibility information of various sets of
    ApplicationVersions in the database.

    Each "set" should be exclusive.
    This is a long migration - There are currently 1.8M rows in the
    applications_versions table for android (many not useful, as we create them
    for unlisted).
    """

    help = 'Update add-on versions compatibility information for Firefox for Android'

    def add_arguments(self, parser):
        parser.add_argument(
            '--known-working',
            action='store',
            dest='known_working',
            type=str,
            # nargs=1,
            help='Path to CSV containing add-on ids known to be working with Fenix.',
        )

        parser.add_argument(
            '--known-broken',
            action='store',
            dest='known_broken',
            type=str,
            # nargs=1,
            help='Path to CSV containing add-on ids known to be broken with Fenix.',
        )

    def read_csv(self, path):
        with open(path) as file_:
            csv_reader = csv.reader(file_)
            return [int(row[0]) for row in csv_reader if row[0] and row[0].isnumeric()]

    def update_testing_set(self):
        log.info('Preparing "Testing set" for Android general availability')
        # "Testing set": Those extensions need to have their Android min
        # compatibility set to 119.0, even if they didn't have Android
        # compatibility set already, so this is a Version queryset and not a
        # ApplicationsVersions, since we are going to potentially create the
        # missing ApplicationsVersions.
        addons_testing_set = Addon.objects.filter(pk__in=self.known_working_ids)
        for addon in addons_testing_set:
            with atomic():
                ApplicationsVersions.objects.update_or_create(
                    version=addon.current_version,
                    application=amo.ANDROID.id,
                    defaults={
                        'min': self.min_version_fenix_testing_set,
                        'max': self.max_version_fenix,
                        'originated_from': amo.APPVERSIONS_ORIGINATED_FROM_MIGRATION,
                    },
                )

    @atomic
    def update_ga_set(self):
        log.info('Preparing "GA set" for Android general availability')
        # "GA set": Those extensions need their existing Firefox for Android
        # min compatibility forcibly set to 120.0.
        general_availability_qs = self.base_general_availability_qs.exclude(
            version__addon_id__in=self.known_broken_ids
        ).filter(version__created__gte=self.cutoff_date)
        general_availability_qs.update(
            min=self.min_version_fenix_actual_ga,
            originated_from=amo.APPVERSIONS_ORIGINATED_FROM_MIGRATION,
        )

    @atomic
    def update_fennec_set(self):
        log.info('Preparing "Fennec set" for Android general availability')
        # "Fennec set": Those extensions need their existing Firefox for
        # Android *max* compatibility set to 68.* *and* get
        # strict_compatibility enabled.
        fennec_only_qs = self.base_rest_qs.filter(
            min__version_int__lte=self.max_version_fennec.version_int
        )
        # First mark them as strictly compatible - before altering their
        # compatibility, since this does a subquery that would no longer return
        # the right ones if it's executed after that.
        File.objects.filter(version__apps__in=fennec_only_qs).update(
            strict_compatibility=True
        )
        fennec_only_qs.update(
            max=self.max_version_fennec,
            originated_from=amo.APPVERSIONS_ORIGINATED_FROM_MIGRATION,
        )

    @atomic
    def update_drop_set(self):
        log.info('Preparing "Drop set" for Android general availability')
        # "Drop set": Those extensions were marked as compatible with Fenix
        # already but that's wrong. It's a small set, drop their Firefox for
        # Android compatibility entirely.
        drop_android_qs = self.base_rest_qs.filter(
            min__version_int__gt=self.max_version_fennec.version_int
        )
        drop_android_qs.delete()

    def init_csv_data(self, kwargs):
        # addon ids we want to have available for users to test in 119.
        self.known_working_ids = self.read_csv(kwargs['known_working'])

        # addon ids we already know are not working in Fenix.
        self.known_broken_ids = self.read_csv(kwargs['known_broken'])

    def init_querysets(self):
        self.promoted_groups_ids = (RECOMMENDED.id, LINE.id)

        # AppVersions we'll need.
        self.min_version_fenix_testing_set = AppVersion.objects.get(
            application=amo.ANDROID.id,
            version=amo.MIN_VERSION_FENIX_GENERAL_AVAILABILITY,
        )
        self.min_version_fenix_actual_ga = AppVersion.objects.get(
            application=amo.ANDROID.id, version='120.0'
        )
        self.min_version_fenix = AppVersion.objects.get(
            application=amo.ANDROID.id, version=amo.MIN_VERSION_FENIX
        )
        self.max_version_fennec = AppVersion.objects.get(
            application=amo.ANDROID.id, version='68.*'
        )
        self.max_version_fenix = AppVersion.objects.get(
            application=amo.ANDROID.id, version=amo.DEFAULT_WEBEXT_MAX_VERSION
        )

        # Version creation date before which we consider existing versions not
        # to be compatible with Fenix.
        self.cutoff_date = datetime(
            2020, 1, 1
        )  # FIXME will likely change before landing

        # "Promoted set": Extensions already recommended/line on Fenix.
        # We don't touch those, it's only for reference.
        # promoted_set = ApplicationsVersions.objects.filter(
        #     application=amo.ANDROID.id
        # ).filter(
        #     Q(version__addon__promotedaddon__application_id=amo.ANDROID.id)
        #     | Q(version__addon__promotedaddon__application_id=None),
        #     version__addon__promotedaddon__group_id__in=self.promoted_groups_ids
        # )
        # Base queryset for the rest of the add-ons. We know we can exclude the
        # recommended/line, the testing ids we are going to alter separately
        # and everything that is either already compatible with Fenix 119.0
        # Nightly and higher, or compatible with Fennec and lower. We also
        # don't want anything we've already migrated automatically.
        self.base_general_availability_qs = (
            ApplicationsVersions.objects.filter(application=amo.ANDROID.id)
            .filter(version__addon__type=amo.ADDON_EXTENSION)
            .filter(
                Q(version__addon__promotedaddon__isnull=True)
                | ~Q(
                    version__addon__promotedaddon__group_id__in=self.promoted_groups_ids
                )
                | Q(version__addon__promotedaddon__application_id=amo.FIREFOX.id)
            )
            .exclude(version__addon_id__in=self.known_working_ids)
            .exclude(
                min__version_int__gte=self.min_version_fenix_testing_set.version_int
            )
            .exclude(max__version_int__lt=self.max_version_fennec.version_int)
            .exclude(originated_from=amo.APPVERSIONS_ORIGINATED_FROM_MIGRATION)
        )
        # The rest are either from before the cutoff or were explicitly tested
        # and found not compatible already.
        self.base_rest_qs = self.base_general_availability_qs.filter(
            Q(version__created__lt=self.cutoff_date)
            | Q(version__addon__id__in=self.known_broken_ids)
        )

    def handle(self, *args, **kwargs):
        if not kwargs['known_working'] or not kwargs['known_broken']:
            raise CommandError('Need to pass --known-working and --known-broken')

        self.init_csv_data(kwargs)
        self.init_querysets()
        self.update_testing_set()
        self.update_ga_set()
        self.update_fennec_set()
        self.update_drop_set()
