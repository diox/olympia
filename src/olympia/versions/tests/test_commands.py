import csv
import os
import tempfile
from datetime import datetime

from django.core.management import call_command
from django.core.management.base import CommandError

from olympia import amo
from olympia.amo.tests import TestCase, addon_factory
from olympia.applications.models import AppVersion
from olympia.constants.promoted import LINE, RECOMMENDED
from olympia.files.models import File
from olympia.versions.management.commands.prepare_android_general_availability import (
    Command as PrepareAndroidGeneralAvailabilityCommand,
)
from olympia.versions.models import ApplicationsVersions


class TestPrepareAndroidGeneralAvailabilityCommand(TestCase):
    def setUp(self):
        self.min_version_fenix_testing_set = AppVersion.objects.get_or_create(
            application=amo.ANDROID.id,
            version=amo.MIN_VERSION_FENIX_GENERAL_AVAILABILITY,
        )[0]
        self.min_version_fenix_actual_ga = AppVersion.objects.get_or_create(
            application=amo.ANDROID.id, version='120.0'
        )[0]
        self.min_version_fenix = AppVersion.objects.get_or_create(
            application=amo.ANDROID.id, version=amo.MIN_VERSION_FENIX
        )[0]
        self.max_version_fennec = AppVersion.objects.get_or_create(
            application=amo.ANDROID.id, version='68.*'
        )[0]
        self.max_version_fenix = AppVersion.objects.get_or_create(
            application=amo.ANDROID.id, version=amo.DEFAULT_WEBEXT_MAX_VERSION
        )[0]

    def _create_csv(self, contents):
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.csv', delete=False
        ) as csv_file:
            self.addCleanup(os.remove, csv_file.name)
            writer = csv.writer(csv_file)
            writer.writerows(contents)
        return csv_file.name

    def test_missing_csv_paths(self):
        csv_file1 = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        self.addCleanup(os.remove, csv_file1.name)
        csv_file2 = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        self.addCleanup(os.remove, csv_file2.name)
        with self.assertRaises(CommandError):
            call_command('prepare_android_general_availability')
        with self.assertRaises(CommandError):
            call_command(
                'prepare_android_general_availability',
                f'--known-working={csv_file1.name}.csv',
            )
        with self.assertRaises(CommandError):
            call_command(
                'prepare_android_general_availability',
                f'--known-broken={csv_file2.name}',
            )
        call_command(
            'prepare_android_general_availability',
            f'--known-broken={csv_file2.name}',
            f'--known-working={csv_file1.name}',
        )

    def test_init_csv_parsing(self):
        file_working_name = self._create_csv(
            [['addon_id'], ['123456789'], ['4815162342'], ['007'], ['42']]
        )
        file_broken_name = self._create_csv(
            [['addon_id'], ['0987654321'], ['1123581321'], ['009']]
        )
        command = PrepareAndroidGeneralAvailabilityCommand()
        command.init_csv_data(
            {'known_working': file_working_name, 'known_broken': file_broken_name}
        )
        assert command.known_working_ids == [123456789, 4815162342, 7, 42]
        assert command.known_broken_ids == [987654321, 1123581321, 9]

    def test_full(self):
        promoted_set_addons = [
            addon_factory(
                name='Recommended for Android',
                version_kw={
                    'application': amo.ANDROID.id,
                    'min_app_version': '48.0',
                    'max_app_version': '*',
                },
                promoted=RECOMMENDED,
            ),
            addon_factory(
                name='Line for all',
                version_kw={
                    'application': amo.ANDROID.id,
                    'min_app_version': '48.0',
                    'max_app_version': '*',
                },
                promoted=LINE,
            ),
        ]
        # As set up both promoted add-ons are promoted for both applications,
        # ensure one is only for Android.
        promoted_set_addons[0].promotedaddon.update(application_id=amo.ANDROID.id)
        testing_set_addons = [
            addon_factory(
                name='In testing set', version_kw={'application': amo.ANDROID.id}
            ),  # Part of the testing set
            addon_factory(
                name='In testing set no existing compat'
            ),  # Part of the testing set without existing compat
        ]
        ga_set_addons = [
            addon_factory(
                name='In GA set recent and compatible',
                version_kw={
                    'application': amo.ANDROID.id,
                    'min_app_version': '48.0',
                    'max_app_version': '*',
                },
            ),  # Recent enough and marked as compatible
        ]
        broken = [
            addon_factory(
                name='In the broken list',
                version_kw={
                    'application': amo.ANDROID.id,
                    'min_app_version': '48.0',
                    'max_app_version': '*',
                },
            ),  # Recent but will be part of the explicitly broken list in csv
        ]
        fennec_set_addons = [
            addon_factory(
                name='In Fennec set because old',
                version_kw={
                    'created': datetime(2019, 12, 31),
                    'application': amo.ANDROID.id,
                    'min_app_version': '48.0',
                    'max_app_version': '*',
                },
            ),  # Too old to be part of the GA set
            addon_factory(
                name='In Fennec set because old, even if recommended for desktop',
                version_kw={
                    'created': datetime(2019, 12, 31),
                    'application': amo.ANDROID.id,
                    'min_app_version': '48.0',
                    'max_app_version': '*',
                },
                promoted=RECOMMENDED,
            ),  # Recommended but for Desktop (see below) and old
        ]
        fennec_set_addons[1].promotedaddon.update(application_id=amo.FIREFOX.id)
        file_working_name = self._create_csv(
            [['addon_id'], *[[str(addon.pk)] for addon in testing_set_addons]]
        )
        file_broken_name = self._create_csv(
            [['addon_id'], *[[str(addon.pk)] for addon in broken]]
        )
        # ApplicationsVersions().save() will automatically correct
        # compatibility and set strict compatibility if needed, so we do a
        # mass-update for all we've created so far to mimic the state the
        # add-ons we want to migrate would be in in prod.
        ApplicationsVersions.objects.filter(application=amo.ANDROID.id).update(
            min=AppVersion.objects.get(application=amo.ANDROID.id, version='48.0'),
        )
        File.objects.all().update(strict_compatibility=False)
        drop_set_addons = [
            addon_factory(
                name='In drop set because minimum is weird',
                version_kw={
                    'created': datetime(2019, 12, 31),
                    'application': amo.ANDROID.id,
                    'min_app_version': '90.0',
                    'max_app_version': '*',
                },
            ),  # Old but minimum version higher than Fenix (see below)
        ]
        ApplicationsVersions.objects.filter(
            version=drop_set_addons[0].current_version
        ).update(min=AppVersion.objects.get(application=amo.ANDROID.id, version='90.0'))
        not_compatible_addons = [
            addon_factory(
                name='Not compatible with Android and not in tested set'
            ),  # Not marked as compatible with Android
        ]
        untouched_addons = [
            addon_factory(
                name='Not an extension',
                type=amo.ADDON_LPAPP,
                version_kw={
                    'application': amo.ANDROID.id,
                    'min_app_version': '48.0',
                    'max_app_version': '*',
                },
            ),  # Not an extension, untouched
        ]
        # Add add-on already compatible with testing version to the testing
        # set, we'll want to check its compatibility is still set to the right
        # version (we shouldn't have touched it).
        testing_set_addons.append(
            addon_factory(
                name='Already set to compatible with 119',
                version_kw={
                    'application': amo.ANDROID.id,
                    'min_app_version': self.min_version_fenix_testing_set.version,
                    'max_app_version': '*',
                    'compat_originated_from': amo.APPVERSIONS_ORIGINATED_FROM_DEVELOPER,
                },
            )
        )
        # Same with the ga set.
        ga_set_addons.append(
            addon_factory(
                name='Already set to compatible with 120',
                version_kw={
                    'application': amo.ANDROID.id,
                    'min_app_version': self.min_version_fenix_actual_ga.version,
                    'max_app_version': '*',
                    'compat_originated_from': amo.APPVERSIONS_ORIGINATED_FROM_DEVELOPER,
                },
            )
        )

        call_command(
            'prepare_android_general_availability',
            f'--known-working={file_working_name}',
            f'--known-broken={file_broken_name}',
        )

        # "Promoted" add-ons for Android shouldn't have been touched.
        for addon in promoted_set_addons:
            if hasattr(addon.current_version, '_compatible_apps'):
                del addon.current_version._compatible_apps
            assert amo.ANDROID in addon.current_version.compatible_apps
            assert (
                addon.current_version.compatible_apps[amo.ANDROID].min.version == '48.0'
            )
            assert addon.current_version.compatible_apps[amo.ANDROID].max.version == '*'
            assert (
                addon.current_version.compatible_apps[amo.ANDROID].originated_from
                == amo.APPVERSIONS_ORIGINATED_FROM_UNKNOWN
            )
            assert not addon.current_version.file.reload().strict_compatibility

        # "Testing set" add-ons should be compatible with min 119.a1.
        for addon in testing_set_addons:
            if hasattr(addon.current_version, '_compatible_apps'):
                del addon.current_version._compatible_apps
            assert amo.ANDROID in addon.current_version.compatible_apps
            assert (
                addon.current_version.compatible_apps[amo.ANDROID].min.version
                == '119.0a1'
            )
            assert addon.current_version.compatible_apps[amo.ANDROID].max.version == '*'
            assert addon.current_version.compatible_apps[
                amo.ANDROID
            ].originated_from in (
                amo.APPVERSIONS_ORIGINATED_FROM_MIGRATION,
                amo.APPVERSIONS_ORIGINATED_FROM_DEVELOPER,
            )
            assert not addon.current_version.file.reload().strict_compatibility

        # "GA set" add-ons should be compatible with min 120.
        for addon in ga_set_addons:
            if hasattr(addon.current_version, '_compatible_apps'):
                del addon.current_version._compatible_apps
            assert amo.ANDROID in addon.current_version.compatible_apps
            assert (
                addon.current_version.compatible_apps[amo.ANDROID].min.version
                == '120.0'
            )
            assert addon.current_version.compatible_apps[amo.ANDROID].max.version == '*'
            assert addon.current_version.compatible_apps[
                amo.ANDROID
            ].originated_from in (
                amo.APPVERSIONS_ORIGINATED_FROM_MIGRATION,
                amo.APPVERSIONS_ORIGINATED_FROM_DEVELOPER,
            )
            assert not addon.current_version.file.reload().strict_compatibility

        # "Fennec set" add-ons should be compatible with max 68.* with strict
        # compatibility set.
        for addon in fennec_set_addons:
            if hasattr(addon.current_version, '_compatible_apps'):
                del addon.current_version._compatible_apps
            assert amo.ANDROID in addon.current_version.compatible_apps
            assert (
                addon.current_version.compatible_apps[amo.ANDROID].min.version == '48.0'
            )
            assert (
                addon.current_version.compatible_apps[amo.ANDROID].max.version == '68.*'
            )
            assert addon.current_version.compatible_apps[
                amo.ANDROID
            ].originated_from in (
                amo.APPVERSIONS_ORIGINATED_FROM_MIGRATION,
                amo.APPVERSIONS_ORIGINATED_FROM_DEVELOPER,
            )
            assert addon.current_version.file.reload().strict_compatibility

        # "Drop set" add-ons have wonky compatibility that should be dropped
        # entirely.
        for addon in drop_set_addons:
            if hasattr(addon.current_version, '_compatible_apps'):
                del addon.current_version._compatible_apps
            assert amo.ANDROID not in addon.current_version.compatible_apps

        # "Incompatible add-ons" shouldn't have been touched, nothing to do.
        for addon in not_compatible_addons:
            if hasattr(addon.current_version, '_compatible_apps'):
                del addon.current_version._compatible_apps
            assert amo.ANDROID not in addon.current_version.compatible_apps
            assert amo.FIREFOX in addon.current_version.compatible_apps

        # "Untouched add-ons" shouldn't have been touched, even if they were
        # already compatible.
        for addon in untouched_addons:
            if hasattr(addon.current_version, '_compatible_apps'):
                del addon.current_version._compatible_apps
            assert amo.ANDROID in addon.current_version.compatible_apps
            assert (
                addon.current_version.compatible_apps[amo.ANDROID].min.version == '48.0'
            )
            assert addon.current_version.compatible_apps[amo.ANDROID].max.version == '*'
            assert (
                addon.current_version.compatible_apps[amo.ANDROID].originated_from
                == amo.APPVERSIONS_ORIGINATED_FROM_UNKNOWN
            )
            assert not addon.current_version.file.reload().strict_compatibility
