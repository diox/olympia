from django.contrib import admin
from django.contrib.messages.storage import default_storage as default_messages_storage
from django.test import RequestFactory

from olympia import core
from olympia.amo.tests import TestCase, addon_factory, user_factory, version_factory
from olympia.reviewers.admin import NeedsHumanReviewAdmin
from olympia.reviewers.models import NeedsHumanReview


class TestNeedsHumanReviewAdmin(TestCase):
    def test_deactivate_selected_action(self):
        request = RequestFactory().get('/')
        request.user = user_factory()
        self.grant_permission(request.user, '*:*')
        core.set_user(request.user)
        request._messages = default_messages_storage(request)

        addon = addon_factory()
        v1 = version_factory(addon=addon)
        v2 = version_factory(addon=addon)
        nhr0 = NeedsHumanReview.objects.create(
            version=v1, reason=NeedsHumanReview.REASON_UNKNOWN
        )
        nhr1 = NeedsHumanReview.objects.create(
            version=v1, reason=NeedsHumanReview.REASON_MANUALLY_SET_BY_REVIEWER
        )
        nhr2 = NeedsHumanReview.objects.create(
            version=v2, reason=NeedsHumanReview.REASON_MANUALLY_SET_BY_REVIEWER
        )
        assert v1.due_date
        assert v2.due_date

        qs = NeedsHumanReview.objects.filter(pk__in=(nhr1.pk, nhr2.pk))
        nhr_admin = NeedsHumanReviewAdmin(NeedsHumanReview, admin.site)

        nhr_admin.deactivate_selected(request, qs)

        nhr0.reload()
        assert nhr0.is_active  # not part of the queryset, so it's untouched.

        nhr1.reload()
        v1.reload()
        assert not nhr1.is_active
        assert v1.due_date  # Because it has another NeedsHumanReview

        nhr2.reload()
        v2.reload()
        assert not nhr2.is_active
        assert not v2.due_date  # No longer has any reason to have a due date.

    def test_activate_selected_action(self):
        request = RequestFactory().get('/')
        request.user = user_factory()
        self.grant_permission(request.user, '*:*')
        core.set_user(request.user)
        request._messages = default_messages_storage(request)

        addon = addon_factory()
        v1 = version_factory(addon=addon)
        v2 = version_factory(addon=addon)
        nhr0 = NeedsHumanReview.objects.create(
            version=v1, reason=NeedsHumanReview.REASON_UNKNOWN, is_active=False
        )
        nhr1 = NeedsHumanReview.objects.create(
            version=v1,
            reason=NeedsHumanReview.REASON_MANUALLY_SET_BY_REVIEWER,
            is_active=False,
        )
        nhr2 = NeedsHumanReview.objects.create(
            version=v2,
            reason=NeedsHumanReview.REASON_MANUALLY_SET_BY_REVIEWER,
            is_active=False,
        )
        assert not v1.due_date
        assert not v2.due_date

        qs = NeedsHumanReview.objects.filter(pk__in=(nhr1.pk, nhr2.pk))
        nhr_admin = NeedsHumanReviewAdmin(NeedsHumanReview, admin.site)

        nhr_admin.activate_selected(request, qs)

        nhr0.reload()
        assert not nhr0.is_active  # not part of the queryset, so it's untouched.

        nhr1.reload()
        v1.reload()
        assert nhr1.is_active
        assert v1.due_date

        nhr2.reload()
        v2.reload()
        assert nhr2.is_active
        assert v2.due_date
