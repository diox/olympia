import json
import uuid
from datetime import datetime
from unittest import mock

from django.conf import settings

import responses

from olympia import amo
from olympia.activity.models import ActivityLog
from olympia.amo.tests import TestCase, addon_factory, block_factory, user_factory

from ..models import Block, BlocklistSubmission, BlockType, BlockVersion
from ..utils import datetime_to_ts, disable_versions_for_block, save_versions_to_blocks


def test_datetime_to_ts():
    now = datetime.now()
    assert datetime_to_ts(now) == int(now.timestamp() * 1000)


class TestSaveVersionsToBlocks(TestCase):
    def setUp(self):
        self.task_user = user_factory(pk=settings.TASK_USER_ID, display_name='Mozilla')
        responses.add_callback(
            responses.POST,
            f'{settings.CINDER_SERVER_URL}create_decision',
            callback=lambda r: (201, {}, json.dumps({'uuid': uuid.uuid4().hex})),
        )

    def test_metadata_updates(self):
        user_new = user_factory()
        addon = addon_factory()
        existing_block = Block.objects.create(
            guid=addon.guid,
            updated_by=self.task_user,
            reason='old reason',
            url='old url',
        )
        submission = BlocklistSubmission.objects.create(
            input_guids=addon.guid, reason='new reason', url=None, updated_by=user_new
        )
        save_versions_to_blocks([addon.guid], submission)

        existing_block.reload()
        assert existing_block.reason == 'new reason'
        assert existing_block.url == 'old url'
        assert existing_block.updated_by == user_new

    def test_log_entries_new_block(self):
        user_new = user_factory()
        addon = addon_factory()
        submission = BlocklistSubmission.objects.create(
            input_guids=addon.guid,
            reason='some reason',
            url=None,
            updated_by=user_new,
            disable_addon=True,
            changed_version_ids=[addon.current_version.pk],
            signoff_state=BlocklistSubmission.SIGNOFF_PUBLISHED,
        )
        ActivityLog.objects.all().delete()

        save_versions_to_blocks([addon.guid], submission)

        assert ActivityLog.objects.count() == 4
        assert list(
            ActivityLog.objects.order_by('pk').values_list('action', flat=True)
        ) == [
            amo.LOG.BLOCKLIST_BLOCK_ADDED.id,
            amo.LOG.BLOCKLIST_VERSION_BLOCKED.id,
            amo.LOG.CHANGE_STATUS.id,
            amo.LOG.REJECT_VERSION.id,
        ]

        activity = ActivityLog.objects.latest('pk')
        assert activity.action == amo.LOG.REJECT_VERSION.id
        assert activity.user == user_new
        assert activity.details['comments'] == 'some reason'
        assert activity.details['is_addon_being_blocked']
        assert activity.details['is_addon_being_disabled']

        activity = ActivityLog.objects.get(action=amo.LOG.BLOCKLIST_BLOCK_ADDED.id)
        assert activity.user == user_new
        assert activity.details == {
            'added_versions': [
                f'{addon.current_version.version}',
            ],
            'blocked_versions': [
                f'{addon.current_version.version}',
            ],
            'comments': '1 versions added to block; 1 total versions now blocked.',
            'guid': f'{addon.guid}',
            'reason': 'some reason',
            'signoff_state': 'Published',
            'soft': False,
            'url': '',
        }

        activity = ActivityLog.objects.get(action=amo.LOG.BLOCKLIST_VERSION_BLOCKED.id)
        assert activity.user == user_new
        assert not activity.details['soft']

    def test_log_soft_block(self):
        user_new = user_factory()
        addon = addon_factory()
        submission = BlocklistSubmission.objects.create(
            input_guids=addon.guid,
            reason='some reason',
            url=None,
            updated_by=user_new,
            disable_addon=True,
            block_type=BlockType.SOFT_BLOCKED,
            changed_version_ids=[addon.current_version.pk],
            signoff_state=BlocklistSubmission.SIGNOFF_PUBLISHED,
        )
        ActivityLog.objects.all().delete()

        save_versions_to_blocks([addon.guid], submission)

        assert ActivityLog.objects.count() == 4
        assert list(
            ActivityLog.objects.order_by('pk').values_list('action', flat=True)
        ) == [
            amo.LOG.BLOCKLIST_BLOCK_ADDED.id,
            amo.LOG.BLOCKLIST_VERSION_BLOCKED.id,
            amo.LOG.CHANGE_STATUS.id,
            amo.LOG.REJECT_VERSION.id,
        ]

        activity = ActivityLog.objects.latest('pk')
        assert activity.action == amo.LOG.REJECT_VERSION.id
        assert activity.user == user_new
        assert activity.details['comments'] == 'some reason'
        assert activity.details['is_addon_being_blocked']
        assert activity.details['is_addon_being_disabled']

        activity = ActivityLog.objects.get(action=amo.LOG.BLOCKLIST_BLOCK_ADDED.id)
        assert activity.user == user_new
        assert activity.details == {
            'added_versions': [
                f'{addon.current_version.version}',
            ],
            'blocked_versions': [
                f'{addon.current_version.version}',
            ],
            'comments': '1 versions added to block; 1 total versions now blocked.',
            'guid': f'{addon.guid}',
            'reason': 'some reason',
            'signoff_state': 'Published',
            'soft': True,
            'url': '',
        }

        activity = ActivityLog.objects.get(action=amo.LOG.BLOCKLIST_VERSION_BLOCKED.id)
        assert activity.user == user_new
        assert activity.details['soft']

    def test_no_empty_new_blocks(self):
        user_new = user_factory()
        addon = addon_factory()
        submission = BlocklistSubmission.objects.create(
            input_guids=addon.guid,
            reason='reason',
            url='url',
            updated_by=user_new,
            changed_version_ids=[],
        )
        save_versions_to_blocks([addon.guid], submission)

        assert not Block.objects.exists()

    def test_save_blocks_override_existing_block_type_soft_to_hard(self):
        user_new = user_factory()
        addon = addon_factory()
        block_factory(
            guid=addon.guid,
            updated_by=self.task_user,
            block_type=BlockType.SOFT_BLOCKED,
        )
        assert addon.current_version.blockversion.block_type == BlockType.SOFT_BLOCKED
        submission = BlocklistSubmission.objects.create(
            input_guids=addon.guid,
            reason='some reason',
            url=None,
            updated_by=user_new,
            block_type=BlockType.BLOCKED,  # Hard-block override.
            changed_version_ids=[addon.current_version.pk],
            signoff_state=BlocklistSubmission.SIGNOFF_PUBLISHED,
        )
        save_versions_to_blocks([addon.guid], submission)
        assert (
            addon.current_version.blockversion.reload().block_type == BlockType.BLOCKED
        )

    def test_save_blocks_override_existing_block_type_hard_to_soft(self):
        user_new = user_factory()
        addon = addon_factory()
        block_factory(guid=addon.guid, updated_by=self.task_user)
        assert addon.current_version.blockversion.block_type == BlockType.BLOCKED
        submission = BlocklistSubmission.objects.create(
            input_guids=addon.guid,
            reason='some reason',
            url=None,
            updated_by=user_new,
            block_type=BlockType.SOFT_BLOCKED,
            changed_version_ids=[addon.current_version.pk],
            signoff_state=BlocklistSubmission.SIGNOFF_PUBLISHED,
        )
        save_versions_to_blocks([addon.guid], submission)
        assert (
            addon.current_version.blockversion.reload().block_type
            == BlockType.SOFT_BLOCKED
        )

    @mock.patch('olympia.reviewers.utils.ReviewBase')
    def test_reviewbase_human_review_is_true_if_block_was_updated_by_human(
        self, review_base_mock
    ):
        user = user_factory()
        addon = addon_factory()
        submission = BlocklistSubmission.objects.create(
            input_guids=addon.guid,
            reason='some reason',
            url=None,
            updated_by=user,
            disable_addon=True,
            block_type=BlockVersion.BLOCK_TYPE_CHOICES.BLOCKED,
            changed_version_ids=[addon.current_version.pk],
            signoff_state=BlocklistSubmission.SIGNOFF_PUBLISHED,
        )
        block = block_factory(addon=addon, updated_by=submission.updated_by)
        disable_versions_for_block(block, submission)
        assert review_base_mock.call_args[0] == ()
        assert review_base_mock.call_args[1] == {
            'addon': addon,
            'version': None,
            'user': user,
            'review_type': 'pending',
            'human_review': True,  # True because user is a human
        }

    @mock.patch('olympia.reviewers.utils.ReviewBase')
    def test_reviewbase_human_review_is_false_if_block_was_updated_by_none(
        self, review_base_mock
    ):
        addon = addon_factory()
        submission = BlocklistSubmission.objects.create(
            input_guids=addon.guid,
            reason='some reason',
            url=None,
            updated_by=self.task_user,
            disable_addon=True,
            block_type=BlockVersion.BLOCK_TYPE_CHOICES.BLOCKED,
            changed_version_ids=[addon.current_version.pk],
            signoff_state=BlocklistSubmission.SIGNOFF_PUBLISHED,
        )
        block = block_factory(addon=addon, updated_by=submission.updated_by)
        # We can't save a block with updated_by = None, but check that we still
        # correctly fall back to the task user if somehow we have to deal with
        # a block in that state in disable_versions_for_block().
        block.updated_by = None
        disable_versions_for_block(block, submission)
        assert review_base_mock.call_args[0] == ()
        assert review_base_mock.call_args[1] == {
            'addon': addon,
            'version': None,
            'user': self.task_user,  # We fell back to the task user.
            'review_type': 'pending',
            'human_review': False,  # False because it's the task user.
        }

    @mock.patch('olympia.reviewers.utils.ReviewBase')
    def test_reviewbase_human_review_is_false_if_block_was_updated_by_task_user(
        self, review_base_mock
    ):
        addon = addon_factory()
        submission = BlocklistSubmission.objects.create(
            input_guids=addon.guid,
            reason='some reason',
            url=None,
            updated_by=self.task_user,
            disable_addon=True,
            block_type=BlockVersion.BLOCK_TYPE_CHOICES.BLOCKED,
            changed_version_ids=[addon.current_version.pk],
            signoff_state=BlocklistSubmission.SIGNOFF_PUBLISHED,
        )
        block = block_factory(addon=addon, updated_by=submission.updated_by)
        disable_versions_for_block(block, submission)
        assert review_base_mock.call_args[0] == ()
        assert review_base_mock.call_args[1] == {
            'addon': addon,
            'version': None,
            'user': self.task_user,
            'review_type': 'pending',
            'human_review': False,  # False because it's the task user.
        }
