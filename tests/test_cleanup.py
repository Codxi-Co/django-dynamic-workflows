"""Tests for workflow cleanup utilities - cleaning cloned actions, not attachments."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings
from django.utils import timezone

from django_workflow_engine.choices import WorkflowAttachmentStatus, WorkflowStatus
from django_workflow_engine.cleanup import (
    cleanup_completed_workflow_actions,
    cleanup_orphaned_workflow_actions,
    get_cleanup_statistics,
)
from django_workflow_engine.models import (
    Pipeline,
    Stage,
    WorkFlow,
    WorkflowAction,
    WorkflowAttachment,
)

User = get_user_model()


@override_settings(WORKFLOW_AUTO_CREATE_ACTIONS=False)
class WorkflowCleanupTest(TestCase):
    """Test cleanup of cloned workflow actions while preserving attachments."""

    def setUp(self):
        """Set up test data."""
        # Create user
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com"
        )

        # Create template workflow
        self.template_workflow = WorkFlow.objects.create(
            name_en="Template Workflow",
            name_ar="قالب سير العمل",
            status=WorkflowStatus.ACTIVE,
            is_active=True,
            is_hidden=False,  # Template workflow
            created_by=self.user,
        )

        # Create pipeline and stage
        self.pipeline = Pipeline.objects.create(
            workflow=self.template_workflow,
            name_en="Test Pipeline",
            name_ar="خط أنابيب الاختبار",
            order=1,
            created_by=self.user,
        )

        self.stage = Stage.objects.create(
            pipeline=self.pipeline,
            name_en="Test Stage",
            name_ar="مرحلة الاختبار",
            order=1,
            created_by=self.user,
        )

        # Add template actions
        self.template_action = WorkflowAction.objects.create(
            workflow=self.template_workflow,
            action_type="after_approve",
            function_path="test.handler",
        )

        # Get content type for user
        self.content_type = ContentType.objects.get_for_model(User)

        self.test_user_counter = 0

    def create_cloned_workflow_with_attachment(self, status, days_ago=0):
        """Create a cloned workflow with attachment and actions.

        NOTE: Creates attachment with IN_PROGRESS first to avoid auto-cleanup,
        then updates to the desired status if it's a final status.
        """
        # Clone the template workflow
        cloned_workflow = WorkFlow.objects.create(
            name_en=f"{self.template_workflow.name_en} (Cloned)",
            name_ar=f"{self.template_workflow.name_ar} (نسخة)",
            status=WorkflowStatus.ACTIVE,
            is_active=False,
            is_hidden=True,  # Cloned workflow
            cloned_from=self.template_workflow,
            created_by=self.user,
        )

        # Clone pipeline and stage
        cloned_pipeline = Pipeline.objects.create(
            workflow=cloned_workflow,
            name_en=self.pipeline.name_en,
            name_ar=self.pipeline.name_ar,
            order=self.pipeline.order,
            created_by=self.user,
        )

        cloned_stage = Stage.objects.create(
            pipeline=cloned_pipeline,
            name_en=self.stage.name_en,
            name_ar=self.stage.name_ar,
            order=self.stage.order,
            created_by=self.user,
        )

        # Clone actions
        cloned_action = WorkflowAction.objects.create(
            workflow=cloned_workflow,
            action_type=self.template_action.action_type,
            function_path=self.template_action.function_path,
        )

        # Create unique test user for attachment
        self.test_user_counter += 1
        test_user = User.objects.create_user(
            username=f"testuser{self.test_user_counter}",
            email=f"test{self.test_user_counter}@example.com",
        )

        # Create attachment with IN_PROGRESS first to avoid auto-cleanup
        attachment = WorkflowAttachment.objects.create(
            workflow=cloned_workflow,
            content_type=self.content_type,
            object_id=test_user.id,
            current_pipeline=cloned_pipeline,
            current_stage=cloned_stage,
            status=WorkflowAttachmentStatus.IN_PROGRESS,
        )

        # Modify timestamps if needed (before changing status)
        if days_ago > 0:
            past_date = timezone.now() - timedelta(days=days_ago)
            WorkflowAttachment.objects.filter(id=attachment.id).update(
                created_at=past_date, modified_at=past_date
            )
            attachment.refresh_from_db()

        # Now update to final status using direct SQL to bypass signal
        # This allows us to test manual cleanup separately from auto-cleanup
        if status != WorkflowAttachmentStatus.IN_PROGRESS:
            WorkflowAttachment.objects.filter(id=attachment.id).update(status=status)
            attachment.refresh_from_db()

        return cloned_workflow, attachment, cloned_action

    def test_cleanup_cloned_actions_from_completed_workflows(self):
        """Test that cloned actions are deleted but attachments are kept."""
        # Create cloned workflows
        cloned1, attach1, action1 = self.create_cloned_workflow_with_attachment(
            WorkflowAttachmentStatus.COMPLETED, days_ago=35
        )
        cloned2, attach2, action2 = self.create_cloned_workflow_with_attachment(
            WorkflowAttachmentStatus.REJECTED, days_ago=35
        )
        cloned3, attach3, action3 = self.create_cloned_workflow_with_attachment(
            WorkflowAttachmentStatus.IN_PROGRESS, days_ago=35
        )

        # Verify initial state
        self.assertEqual(WorkflowAction.objects.count(), 4)  # 1 template + 3 cloned
        self.assertEqual(WorkflowAttachment.objects.count(), 3)

        # Dry run
        result = cleanup_completed_workflow_actions(older_than_days=30, dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["actions_deleted"], 2)  # From completed and rejected
        self.assertEqual(result["workflows_processed"], 2)

        # Verify nothing deleted yet
        self.assertEqual(WorkflowAction.objects.count(), 4)

        # Actual cleanup
        result = cleanup_completed_workflow_actions(older_than_days=30)
        self.assertFalse(result["dry_run"])
        self.assertEqual(result["actions_deleted"], 2)
        self.assertEqual(result["workflows_processed"], 2)

        # Verify cloned actions deleted, template action kept
        self.assertEqual(
            WorkflowAction.objects.count(), 2
        )  # Template + in_progress cloned
        self.assertTrue(
            WorkflowAction.objects.filter(id=self.template_action.id).exists()
        )
        self.assertTrue(WorkflowAction.objects.filter(id=action3.id).exists())
        self.assertFalse(WorkflowAction.objects.filter(id=action1.id).exists())
        self.assertFalse(WorkflowAction.objects.filter(id=action2.id).exists())

        # Verify ALL attachments are kept
        self.assertEqual(WorkflowAttachment.objects.count(), 3)
        self.assertTrue(WorkflowAttachment.objects.filter(id=attach1.id).exists())
        self.assertTrue(WorkflowAttachment.objects.filter(id=attach2.id).exists())
        self.assertTrue(WorkflowAttachment.objects.filter(id=attach3.id).exists())

    def test_cleanup_respects_age_filter(self):
        """Test that cleanup respects the age filter."""
        # Create old and recent completed workflows
        old_cloned, old_attach, old_action = (
            self.create_cloned_workflow_with_attachment(
                WorkflowAttachmentStatus.COMPLETED, days_ago=35
            )
        )
        recent_cloned, recent_attach, recent_action = (
            self.create_cloned_workflow_with_attachment(
                WorkflowAttachmentStatus.COMPLETED, days_ago=5
            )
        )

        # Cleanup only older than 30 days
        result = cleanup_completed_workflow_actions(older_than_days=30)
        self.assertEqual(result["actions_deleted"], 1)

        # Verify old action deleted, recent kept
        self.assertFalse(WorkflowAction.objects.filter(id=old_action.id).exists())
        self.assertTrue(WorkflowAction.objects.filter(id=recent_action.id).exists())

        # Verify both attachments kept
        self.assertTrue(WorkflowAttachment.objects.filter(id=old_attach.id).exists())
        self.assertTrue(WorkflowAttachment.objects.filter(id=recent_attach.id).exists())

    def test_template_actions_never_deleted(self):
        """Test that template workflow actions are never deleted."""
        # Create completed cloned workflow
        cloned, attach, cloned_action = self.create_cloned_workflow_with_attachment(
            WorkflowAttachmentStatus.COMPLETED, days_ago=100
        )

        # Cleanup
        result = cleanup_completed_workflow_actions(older_than_days=0)

        # Template action must still exist
        self.assertTrue(
            WorkflowAction.objects.filter(id=self.template_action.id).exists()
        )
        self.assertEqual(self.template_action.workflow.is_hidden, False)

        # Cloned action should be deleted
        self.assertFalse(WorkflowAction.objects.filter(id=cloned_action.id).exists())

    def test_get_cleanup_statistics(self):
        """Test statistics show cloned workflows and actions correctly."""
        # Create some workflows
        cloned1, attach1, action1 = self.create_cloned_workflow_with_attachment(
            WorkflowAttachmentStatus.COMPLETED, days_ago=35
        )
        cloned2, attach2, action2 = self.create_cloned_workflow_with_attachment(
            WorkflowAttachmentStatus.COMPLETED, days_ago=95
        )
        cloned3, attach3, action3 = self.create_cloned_workflow_with_attachment(
            WorkflowAttachmentStatus.IN_PROGRESS
        )

        stats = get_cleanup_statistics()

        # Attachments
        self.assertEqual(stats["total_attachments"], 3)
        self.assertEqual(stats["completed_attachments"], 2)
        self.assertEqual(stats["in_progress_attachments"], 1)

        # Cloned workflows
        self.assertEqual(stats["cloned_workflows"]["total"], 3)
        self.assertEqual(stats["cloned_workflows"]["with_completed_attachments"], 2)

        # Cloned actions
        self.assertEqual(stats["cloned_actions"]["total"], 3)
        self.assertEqual(stats["cloned_actions"]["from_completed_workflows"], 2)

        # Template action not counted in cloned
        self.assertEqual(stats["total_actions"], 4)  # 1 template + 3 cloned


class CleanupEdgeCasesTest(TestCase):
    """Test edge cases for cleanup utilities."""

    def test_cleanup_with_no_data(self):
        """Test cleanup when there's no data."""
        result = cleanup_completed_workflow_actions()
        self.assertEqual(result["actions_deleted"], 0)
        self.assertEqual(result["workflows_processed"], 0)

    def test_cleanup_statistics_with_no_data(self):
        """Test statistics when there's no data."""
        stats = get_cleanup_statistics()
        self.assertEqual(stats["total_attachments"], 0)
        self.assertEqual(stats["total_actions"], 0)
        self.assertEqual(stats["cloned_workflows"]["total"], 0)


@override_settings(WORKFLOW_AUTO_CREATE_ACTIONS=False)
class AutoCleanupSignalTest(TestCase):
    """Test automatic cleanup signal when workflows complete."""

    def setUp(self):
        """Set up test data."""
        # Create user
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com"
        )

        # Create template workflow
        self.template_workflow = WorkFlow.objects.create(
            name_en="Template Workflow",
            name_ar="قالب سير العمل",
            status=WorkflowStatus.ACTIVE,
            is_active=True,
            is_hidden=False,  # Template workflow
            created_by=self.user,
        )

        # Create pipeline and stage
        self.pipeline = Pipeline.objects.create(
            workflow=self.template_workflow,
            name_en="Test Pipeline",
            name_ar="خط أنابيب الاختبار",
            order=1,
            created_by=self.user,
        )

        self.stage = Stage.objects.create(
            pipeline=self.pipeline,
            name_en="Test Stage",
            name_ar="مرحلة الاختبار",
            order=1,
            created_by=self.user,
        )

        # Add template actions
        self.template_action = WorkflowAction.objects.create(
            workflow=self.template_workflow,
            action_type="after_approve",
            function_path="test.handler",
        )

        # Get content type for user
        self.content_type = ContentType.objects.get_for_model(User)

    def create_cloned_workflow_with_attachment(self):
        """Create a cloned workflow with attachment and actions."""
        # Clone the template workflow
        cloned_workflow = WorkFlow.objects.create(
            name_en=f"{self.template_workflow.name_en} (Cloned)",
            name_ar=f"{self.template_workflow.name_ar} (نسخة)",
            status=WorkflowStatus.ACTIVE,
            is_active=False,
            is_hidden=True,  # Cloned workflow
            cloned_from=self.template_workflow,
            created_by=self.user,
        )

        # Clone pipeline and stage
        cloned_pipeline = Pipeline.objects.create(
            workflow=cloned_workflow,
            name_en=self.pipeline.name_en,
            name_ar=self.pipeline.name_ar,
            order=self.pipeline.order,
            created_by=self.user,
        )

        cloned_stage = Stage.objects.create(
            pipeline=cloned_pipeline,
            name_en=self.stage.name_en,
            name_ar=self.stage.name_ar,
            order=self.stage.order,
            created_by=self.user,
        )

        # Clone actions
        cloned_action = WorkflowAction.objects.create(
            workflow=cloned_workflow,
            action_type=self.template_action.action_type,
            function_path=self.template_action.function_path,
        )

        # Create test user for attachment
        test_user = User.objects.create_user(
            username=f"testuser_{cloned_workflow.id}",
            email=f"test_{cloned_workflow.id}@example.com",
        )

        # Create attachment with IN_PROGRESS status initially
        attachment = WorkflowAttachment.objects.create(
            workflow=cloned_workflow,
            content_type=self.content_type,
            object_id=test_user.id,
            current_pipeline=cloned_pipeline,
            current_stage=cloned_stage,
            status=WorkflowAttachmentStatus.IN_PROGRESS,
        )

        return cloned_workflow, attachment, cloned_action

    def test_auto_cleanup_on_completed_status(self):
        """Test that cloned actions are auto-deleted when status changes to COMPLETED."""
        cloned_workflow, attachment, cloned_action = (
            self.create_cloned_workflow_with_attachment()
        )

        # Verify initial state
        self.assertEqual(WorkflowAction.objects.count(), 2)  # Template + cloned
        self.assertTrue(WorkflowAction.objects.filter(id=cloned_action.id).exists())

        # Change status to COMPLETED - should trigger auto-cleanup
        attachment.status = WorkflowAttachmentStatus.COMPLETED
        attachment.save()

        # Verify cloned action was deleted automatically
        self.assertEqual(WorkflowAction.objects.count(), 1)  # Only template remains
        self.assertFalse(WorkflowAction.objects.filter(id=cloned_action.id).exists())
        self.assertTrue(
            WorkflowAction.objects.filter(id=self.template_action.id).exists()
        )

        # Verify attachment is still kept for history
        self.assertTrue(WorkflowAttachment.objects.filter(id=attachment.id).exists())

    def test_auto_cleanup_on_rejected_status(self):
        """Test that cloned actions are auto-deleted when status changes to REJECTED."""
        cloned_workflow, attachment, cloned_action = (
            self.create_cloned_workflow_with_attachment()
        )

        # Verify initial state
        self.assertEqual(WorkflowAction.objects.count(), 2)
        self.assertTrue(WorkflowAction.objects.filter(id=cloned_action.id).exists())

        # Change status to REJECTED - should trigger auto-cleanup
        attachment.status = WorkflowAttachmentStatus.REJECTED
        attachment.save()

        # Verify cloned action was deleted automatically
        self.assertEqual(WorkflowAction.objects.count(), 1)
        self.assertFalse(WorkflowAction.objects.filter(id=cloned_action.id).exists())

        # Verify attachment is kept
        self.assertTrue(WorkflowAttachment.objects.filter(id=attachment.id).exists())

    def test_no_cleanup_on_in_progress_status(self):
        """Test that actions are NOT deleted when status is IN_PROGRESS."""
        cloned_workflow, attachment, cloned_action = (
            self.create_cloned_workflow_with_attachment()
        )

        # Status is already IN_PROGRESS, verify no cleanup
        self.assertEqual(WorkflowAction.objects.count(), 2)
        self.assertTrue(WorkflowAction.objects.filter(id=cloned_action.id).exists())

        # Update something else (not status) to trigger save
        attachment.save()

        # Verify actions are NOT deleted
        self.assertEqual(WorkflowAction.objects.count(), 2)
        self.assertTrue(WorkflowAction.objects.filter(id=cloned_action.id).exists())

    def test_template_actions_never_auto_deleted(self):
        """Test that template workflow actions are never auto-deleted."""
        cloned_workflow, attachment, cloned_action = (
            self.create_cloned_workflow_with_attachment()
        )

        # Change to completed
        attachment.status = WorkflowAttachmentStatus.COMPLETED
        attachment.save()

        # Template action must still exist
        self.assertTrue(
            WorkflowAction.objects.filter(id=self.template_action.id).exists()
        )

    def test_multiple_workflows_auto_cleanup_independently(self):
        """Test that multiple workflows clean up independently."""
        # Create two cloned workflows
        cloned1, attach1, action1 = self.create_cloned_workflow_with_attachment()
        cloned2, attach2, action2 = self.create_cloned_workflow_with_attachment()

        # Verify initial state: 1 template + 2 cloned = 3 actions
        self.assertEqual(WorkflowAction.objects.count(), 3)

        # Complete first workflow
        attach1.status = WorkflowAttachmentStatus.COMPLETED
        attach1.save()

        # Verify only first cloned action deleted
        self.assertEqual(WorkflowAction.objects.count(), 2)  # Template + action2
        self.assertFalse(WorkflowAction.objects.filter(id=action1.id).exists())
        self.assertTrue(WorkflowAction.objects.filter(id=action2.id).exists())

        # Complete second workflow
        attach2.status = WorkflowAttachmentStatus.COMPLETED
        attach2.save()

        # Verify second cloned action deleted
        self.assertEqual(WorkflowAction.objects.count(), 1)  # Only template
        self.assertFalse(WorkflowAction.objects.filter(id=action2.id).exists())

        # Both attachments still exist
        self.assertTrue(WorkflowAttachment.objects.filter(id=attach1.id).exists())
        self.assertTrue(WorkflowAttachment.objects.filter(id=attach2.id).exists())
