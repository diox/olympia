import mock
from nose.tools import eq_

import amo.tests

import mkt
from mkt.developers.cron import exclude_new_region, send_new_region_emails


class TestSendNewRegionEmails(amo.tests.WebappTestCase):

    @mock.patch('mkt.developers.cron._region_email')
    def test_called(self, _region_email_mock):
        send_new_region_emails([mkt.regions.UK])
        eq_(list(_region_email_mock.call_args_list[0][0][0]),
            [self.app.id])

    @mock.patch('mkt.developers.cron._region_email')
    def test_not_called_with_exclusions(self, _region_email_mock):
        self.app.addonexcludedregion.create(
            region=mkt.regions.UK.id)
        send_new_region_emails([mkt.regions.UK])
        eq_(list(_region_email_mock.call_args_list[0][0][0]), [])


class TestExcludeNewRegion(amo.tests.WebappTestCase):

    @mock.patch('mkt.developers.cron._region_exclude')
    def test_called(self, _region_exclude_mock):
        exclude_new_region([mkt.regions.UK])
        eq_(list(_region_exclude_mock.call_args_list[0][0][0]), [self.app.id])

    @mock.patch('mkt.developers.cron._region_exclude')
    def test_not_called_with_exclusions(self, _region_exclude_mock):
        self.app.addonexcludedregion.create(
            region=mkt.regions.UK.id)
        exclude_new_region([mkt.regions.UK])
        eq_(list(_region_exclude_mock.call_args_list[0][0][0]), [])
