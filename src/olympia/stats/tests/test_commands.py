import json
import os
import shutil
from datetime import date, timedelta

from nose.tools import eq_

from django.conf import settings
from django.core import management

import amo.search
from olympia.amo.tests import TestCase
from addons.models import Addon, Persona
from stats.management.commands.download_counts_from_file import is_valid_source
from stats.management.commands.update_counts_from_file import Command
from stats.models import DownloadCount, ThemeUpdateCount, UpdateCount
from zadmin.models import DownloadSource


hive_folder = os.path.join(settings.ROOT, 'apps/stats/fixtures/files')


class FixturesFolderMixin(object):
    # You have to define these two values in your subclasses.
    date = 'YYYY-MM-DD'
    source_folder = 'dummy'

    def clean_up_files(self):
        dirpath = os.path.join(hive_folder, self.date)
        if os.path.isdir(dirpath):
            for name in os.listdir(dirpath):
                os.unlink(os.path.join(dirpath, name))
            os.rmdir(dirpath)

    def setUp(self):
        super(FixturesFolderMixin, self).setUp()
        self.clean_up_files()
        shutil.copytree(os.path.join(hive_folder, self.source_folder),
                        os.path.join(hive_folder, self.date))

    def tearDown(self):
        self.clean_up_files()
        super(FixturesFolderMixin, self).tearDown()


class TestADICommand(FixturesFolderMixin, TestCase):
    fixtures = ('base/addon_3615', 'base/featured', 'addons/persona',
                'base/appversion.json')
    date = '2014-07-10'
    source_folder = 'src'

    def setUp(self):
        super(TestADICommand, self).setUp()
        self.command = Command()

    def test_update_counts_from_file(self):
        management.call_command('update_counts_from_file', hive_folder,
                                date=self.date)
        eq_(UpdateCount.objects.all().count(), 1)
        update_count = UpdateCount.objects.last()
        eq_(update_count.count, 5)
        eq_(update_count.date, date(2014, 7, 10))
        eq_(update_count.versions, {u'3.8': 2, u'3.7': 3})
        eq_(update_count.statuses, {u'userEnabled': 5})
        application = u'{ec8030f7-c20a-464f-9b0e-13a3a9e97384}'
        eq_(update_count.applications[application], {u'3.6': 18})
        eq_(update_count.oses, {u'WINNT': 5})
        eq_(update_count.locales, {u'en-us': 1, u'en-US': 4})

    def test_update_version(self):
        # Initialize the known addons and their versions.
        self.command.addons_versions = {3615: ['3.5', '3.6']}
        uc = UpdateCount(addon_id=3615)
        self.command.update_version(uc, '3.6', 123)
        assert uc.versions == {'3.6': 123}
        # Test very long version:
        self.command.update_version(uc, '1' * 33, 1)
        assert uc.versions == {'3.6': 123, '1' * 32: 1}  # Trimmed.

    def test_update_status(self):
        uc = UpdateCount(addon_id=3615)
        self.command.update_status(uc, 'foobar', 123)  # Non-existent status.
        assert not uc.statuses
        self.command.update_status(uc, 'userEnabled', 123)
        assert uc.statuses == {'userEnabled': 123}

    def test_update_app(self):
        firefox_guid = '{ec8030f7-c20a-464f-9b0e-13a3a9e97384}'
        uc = UpdateCount(addon_id=3615)
        self.command.update_app(uc, 'foobar', '1.0', 123)  # Non-existent app.
        assert not uc.applications
        # Malformed versions.
        self.command.update_app(uc, firefox_guid, '3.0.1.2', 123)
        self.command.update_app(uc, firefox_guid, '3.0123', 123)
        self.command.update_app(uc, firefox_guid, '3.0c2', 123)
        self.command.update_app(uc, firefox_guid, 'a.b.c', 123)
        assert not uc.applications
        # Well formed versions.
        self.command.update_app(uc, firefox_guid, '1.0', 123)
        self.command.update_app(uc, firefox_guid, '1.0.1', 124)
        self.command.update_app(uc, firefox_guid, '1.0a1', 125)
        self.command.update_app(uc, firefox_guid, '1.0b2', 126)
        assert uc.applications == {firefox_guid: {
            '1.0': 123,
            '1.0.1': 124,
            '1.0a1': 125,
            '1.0b2': 126}}

    def test_update_os(self):
        uc = UpdateCount(addon_id=3615)
        self.command.update_os(uc, 'foobar', 123)  # Non-existent OS.
        assert not uc.oses
        self.command.update_os(uc, 'WINNT', 123)
        assert uc.oses == {'WINNT': 123}

    def test_update_locale(self):
        current_locales = [  # Taken from the language pack index.
            'ach', 'af', 'ak', 'an', 'ar', 'as', 'ast', 'ast-ES', 'az',
            'bb-BK', 'be', 'bg', 'bn-BD', 'bn-IN', 'br', 'bs', 'ca',
            'ca-valencia', 'cs', 'csb', 'cy', 'cy-GB', 'da', 'de', 'dsb', 'el',
            'en-GB', 'en-ZA', 'eo', 'es-AR', 'es-CL', 'es-ES', 'es-MX', 'et',
            'eu', 'fa', 'ff', 'fi', 'fj-FJ', 'fr', 'fur-IT', 'fy-NL', 'ga-IE',
            'gd', 'gl', 'gu-IN', 'he', 'hi', 'hi-IN', 'hr', 'hsb', 'hu',
            'hy-AM', 'id', 'is', 'it', 'ja', 'kk', 'km', 'kn', 'ko', 'ku',
            'lg', 'lij', 'lt', 'lv', 'mai', 'mg', 'mk', 'ml', 'mr', 'ms',
            'nb-NO', 'nl', 'nn-NO', 'nr', 'nso', 'or', 'pa-IN', 'pl', 'pt-BR',
            'pt-PT', 'rm', 'ro', 'ru', 'si', 'sk', 'sl', 'son', 'sq', 'sr',
            'ss', 'st', 'sv-SE', 'sw', 'sw-TZ', 'ta', 'ta-IN', 'ta-LK', 'te',
            'th', 'tn', 'tr', 'ts', 'uk', 've', 'vi', 'wa', 'wo-SN', 'xh',
            'zap-MX-diiste', 'zh-CN', 'zh-TW', 'zu']
        uc = UpdateCount(addon_id=3615)
        self.command.update_locale(uc, 'foobar', 123)  # Non-existent locale.
        assert not uc.locales
        for locale in current_locales:
            self.command.update_locale(uc, locale, 1)
        assert len(uc.locales) == len(current_locales)

    def test_trim_field(self):
        uc = UpdateCount(addon_id=3615, count=1, date='2015-01-11')
        self.command.trim_field(uc.versions)  # Empty field.
        assert not uc.versions

        uc.versions = {'3.6': 123, '3.7': 321}
        self.command.trim_field(uc.versions)  # Small enough to fit in the db.
        assert uc.versions == {'3.6': 123, '3.7': 321}  # Unchanged.

        very_long_key = 'x' * (2 ** 16)
        uc.versions[very_long_key] = 1
        self.command.trim_field(uc.versions)  # Too big, must be trimmed.
        assert uc.versions == {'3.6': 123, '3.7': 321}  # Keep the most used.

        uc.versions[very_long_key] = 1000  # Most used.
        self.command.trim_field(uc.versions)  # Too big, must be trimmed.
        # Nothing left: least used removed, but still too big, so all the keys
        # were removed.
        assert uc.versions == {}

        # Make sure we can store a very large field in the database.
        long_key = 'x' * 65528  # This makes the dict barely fit in the db.
        uc.versions[long_key] = 1
        assert len(json.dumps(uc.versions)) == (2 ** 16) - 1
        uc.save()
        uc = UpdateCount.objects.get(pk=uc.pk)  # Reload
        # Fits in the database, so no truncation.
        assert len(json.dumps(uc.versions)) == (2 ** 16) - 1

    def test_download_counts_from_file(self):
        # Create the necessary "valid download sources" entries.
        DownloadSource.objects.create(name='search', type='full')
        DownloadSource.objects.create(name='coll', type='prefix')

        management.call_command('download_counts_from_file', hive_folder,
                                date=self.date)
        eq_(DownloadCount.objects.all().count(), 1)
        download_count = DownloadCount.objects.last()
        eq_(download_count.count, 2)
        eq_(download_count.date, date(2014, 7, 10))
        eq_(download_count.sources, {u'search': 1, u'collection': 1})

    def test_theme_update_counts_from_file(self):
        management.call_command('theme_update_counts_from_file', hive_folder,
                                date=self.date)
        eq_(ThemeUpdateCount.objects.all().count(), 2)
        eq_(ThemeUpdateCount.objects.get(addon_id=3615).count, 2)
        # Persona 813 has addon id 15663: we need the count to be the sum of
        # the "old" request on the persona_id 813 (only the one with the source
        # "gp") and the "new" request on the addon_id 15663.
        eq_(ThemeUpdateCount.objects.get(addon_id=15663).count, 15)

    def test_update_theme_popularity_movers(self):
        # Create ThemeUpdateCount entries for the persona 559 with addon_id
        # 15663 and the persona 575 with addon_id 15679 for the last 28 days.
        # We start from the previous day, as the theme_update_counts_from_*
        # scripts are gathering data for the day before.
        yesterday = date.today() - timedelta(days=1)
        for i in range(28):
            d = yesterday - timedelta(days=i)
            ThemeUpdateCount.objects.create(addon_id=15663, count=i, date=d)
            ThemeUpdateCount.objects.create(addon_id=15679,
                                            count=i * 100, date=d)
        # Compute the popularity and movers.
        management.call_command('update_theme_popularity_movers')
        p1 = Persona.objects.get(pk=559)
        p2 = Persona.objects.get(pk=575)

        # The popularity is the average over the last 7 days, and as we created
        # entries with one more user per day in the past (or 100 more), the
        # calculation is "sum(range(7)) / 7" (or "sum(range(7)) * 100 / 7").
        eq_(p1.popularity, 3)  # sum(range(7)) / 7
        eq_(p2.popularity, 300)  # sum(range(7)) * 100 / 7

        # Three weeks avg (sum(range(21)) / 21) = 10 so (3 - 10) / 10.
        # The movers is computed with the following formula:
        # previous_3_weeks: the average over the 21 days before the last 7 days
        # movers: (popularity - previous_3_weeks) / previous_3_weeks
        # The calculation for the previous_3_weeks is:
        # previous_3_weeks: (sum(range(28) - sum(range(7))) * 100 / 21 == 1700.
        eq_(p1.movers, 0.0)  # Because the popularity is <= 100.
        # We round the results to cope with floating point imprecision.
        eq_(round(p2.movers, 5), round((300.0 - 1700) / 1700, 5))

    def test_is_valid_source(self):
        assert is_valid_source('foo',
                               fulls=['foo', 'bar'],
                               prefixes=['baz', 'cruux'])
        assert not is_valid_source('foob',
                                   fulls=['foo', 'bar'],
                                   prefixes=['baz', 'cruux'])
        assert is_valid_source('foobaz',
                               fulls=['foo', 'bar'],
                               prefixes=['baz', 'cruux'])
        assert not is_valid_source('ba',
                                   fulls=['foo', 'bar'],
                                   prefixes=['baz', 'cruux'])


class TestThemeADICommand(FixturesFolderMixin, TestCase):
    date = '2014-11-06'
    fixtures = ['base/appversion.json']
    source_folder = '1093699'

    def test_update_counts_from_file_bug_1093699(self):
        Addon.objects.create(guid='{fe9e9f88-42f0-40dc-970b-4b0e6b7a3d0b}',
                             type=amo.ADDON_THEME)
        management.call_command('update_counts_from_file', hive_folder,
                                date=self.date)
        eq_(UpdateCount.objects.all().count(), 1)
        uc = UpdateCount.objects.last()
        eq_(uc.count, 1320)
        eq_(uc.date, date(2014, 11, 06))
        eq_(uc.versions,
            {u'1.7.16': 1, u'userEnabled': 3, u'1.7.13': 2, u'1.7.11': 3,
             u'1.6.0': 1, u'1.7.14': 1304, u'1.7.6': 6})
        eq_(uc.statuses,
            {u'Unknown': 3, u'userEnabled': 1259, u'userDisabled': 58})
        eq_(uc.oses, {u'WINNT': 1122, u'Darwin': 114, u'Linux': 84})
        eq_(uc.locales[u'es-ES'], 20)
        eq_(uc.applications[u'{92650c4d-4b8e-4d2a-b7eb-24ecf4f6b63a}'],
            {u'2.0': 3})
