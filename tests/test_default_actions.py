"""Test cases for default workflow actions (deprecated - stubs only)."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from django_workflow_engine.default_actions import (
    default_send_email_after_approve,
    default_send_email_after_delegate,
    default_send_email_after_move_pipeline,
    default_send_email_after_move_stage,
    default_send_email_after_reject,
    default_send_email_after_resubmission,
    default_send_email_on_workflow_complete,
    default_send_email_on_workflow_start,
)

User = get_user_model()


class DefaultActionsTest(TestCase):
    """Test that default actions are deprecated stubs that return False."""

    def test_default_send_email_after_approve_returns_false(self):
        """Verify deprecated function returns False."""
        result = default_send_email_after_approve()
        self.assertFalse(result)

    def test_default_send_email_after_reject_returns_false(self):
        """Verify deprecated function returns False."""
        result = default_send_email_after_reject()
        self.assertFalse(result)

    def test_default_send_email_after_resubmission_returns_false(self):
        """Verify deprecated function returns False."""
        result = default_send_email_after_resubmission()
        self.assertFalse(result)

    def test_default_send_email_after_delegate_returns_false(self):
        """Verify deprecated function returns False."""
        result = default_send_email_after_delegate()
        self.assertFalse(result)

    def test_default_send_email_after_move_stage_returns_false(self):
        """Verify deprecated function returns False."""
        result = default_send_email_after_move_stage()
        self.assertFalse(result)

    def test_default_send_email_after_move_pipeline_returns_false(self):
        """Verify deprecated function returns False."""
        result = default_send_email_after_move_pipeline()
        self.assertFalse(result)

    def test_default_send_email_on_workflow_start_returns_false(self):
        """Verify deprecated function returns False."""
        result = default_send_email_on_workflow_start()
        self.assertFalse(result)

    def test_default_send_email_on_workflow_complete_returns_false(self):
        """Verify deprecated function returns False."""
        result = default_send_email_on_workflow_complete()
        self.assertFalse(result)
