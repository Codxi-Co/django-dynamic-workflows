"""Test cases for workflow handlers."""

import uuid
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

import pytest
from approval_workflow.choices import ApprovalStatus
from approval_workflow.models import ApprovalFlow, ApprovalInstance

from django_workflow_engine.choices import (
    ActionType,
    WorkflowAttachmentStatus,
    WorkflowStatus,
)
from django_workflow_engine.handlers import (
    BaseApprovalHandler,
    WorkflowApprovalHandler,
    get_handler_for_instance,
)
from django_workflow_engine.models import Pipeline, Stage, WorkFlow, WorkflowAttachment
from django_workflow_engine.services import attach_workflow_to_object
from sandbox.testapp.models import Company, Department

User = get_user_model()


class BaseApprovalHandlerTest(TestCase):
    """Test cases for BaseApprovalHandler."""

    def test_base_handler_methods(self):
        """Test that base handler methods exist and can be called."""
        handler = BaseApprovalHandler()

        # Create a mock approval instance
        mock_instance = Mock()
        mock_instance.flow.id = 1
        mock_instance.step_number = 1

        # All methods should exist and not raise errors
        handler.before_approve(mock_instance)
        handler.after_approve(mock_instance)
        handler.on_final_approve(mock_instance)
        handler.before_reject(mock_instance)
        handler.after_reject(mock_instance)
        handler.after_resubmission(mock_instance)
        handler.after_delegate(mock_instance)


class WorkflowApprovalHandlerTest(TestCase):
    """Test cases for WorkflowApprovalHandler."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        unique_id = str(uuid.uuid4())[:8]
        self.company_user = User.objects.create_user(
            username=f"testcompany{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )
        self.company = Company.objects.create(name="Test Company")
        self.department = Department.objects.create(
            name="Test Department", company=self.company
        )

        # Create workflow structure
        self.workflow = WorkFlow.objects.create(
            company=self.company_user,
            name_en="Test Workflow",
            name_ar="سير عمل تجريبي",
            status=WorkflowStatus.ACTIVE,
            created_by=self.user,
        )

        self.pipeline = Pipeline.objects.create(
            workflow=self.workflow,
            company=self.company_user,
            name_en="Test Pipeline",
            name_ar="خط أنابيب تجريبي",
            created_by=self.user,
        )

        self.stage1 = Stage.objects.create(
            pipeline=self.pipeline,
            company=self.company_user,
            name_en="Stage 1",
            name_ar="المرحلة 1",
            created_by=self.user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": self.user.id}]
            },
        )

        self.stage2 = Stage.objects.create(
            pipeline=self.pipeline,
            company=self.company_user,
            name_en="Stage 2",
            name_ar="المرحلة 2",
            created_by=self.user,
            order=1,
            is_active=True,
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": self.user.id}]
            },
        )

        # Create workflow attachment
        self.attachment = attach_workflow_to_object(
            obj=self.user, workflow=self.workflow, user=self.user, auto_start=False
        )
        self.attachment.current_stage = self.stage1
        self.attachment.current_pipeline = self.pipeline
        self.attachment.status = WorkflowAttachmentStatus.IN_PROGRESS
        self.attachment.save()

        # Update workflow active status
        self.workflow.update_active_status()

        # Create approval flow and instance
        content_type = ContentType.objects.get_for_model(User)
        self.approval_flow = ApprovalFlow.objects.create(
            content_type=content_type, object_id=str(self.user.pk)
        )

        self.approval_instance = ApprovalInstance.objects.create(
            flow=self.approval_flow,
            step_number=1,
            status=ApprovalStatus.APPROVED,
            assigned_to=self.user,
            action_user=self.user,
            comment="Test approval",
        )

    @patch("django_workflow_engine.services.trigger_workflow_event")
    @patch("django_workflow_engine.services.move_to_next_stage")
    def test_on_final_approve(self, mock_move_stage, mock_trigger_event):
        """Test final approval handler."""
        mock_move_stage.return_value = self.attachment

        handler = WorkflowApprovalHandler(self.user)
        handler.on_final_approve(self.approval_instance)

        # Should trigger approve actions
        mock_trigger_event.assert_called_once_with(
            self.attachment,
            ActionType.AFTER_APPROVE,
            approval_instance=self.approval_instance,
            user=self.user,
        )

        # Should move to next stage
        mock_move_stage.assert_called_once_with(self.user)

    def test_after_approve(self):
        """Test individual approval handler (should not trigger progression)."""
        handler = WorkflowApprovalHandler(self.user)

        # Should not raise any errors
        handler.after_approve(self.approval_instance)

    @patch("django_workflow_engine.services.trigger_workflow_event")
    @patch("django_workflow_engine.services.reject_workflow_stage")
    def test_after_reject(self, mock_reject_stage, mock_trigger_event):
        """Test rejection handler."""
        self.approval_instance.comment = "Rejected for testing"

        handler = WorkflowApprovalHandler(self.user)
        handler.after_reject(self.approval_instance)

        # Should trigger reject actions
        mock_trigger_event.assert_called_once_with(
            self.attachment,
            ActionType.AFTER_REJECT,
            approval_instance=self.approval_instance,
            reason="Rejected for testing",
            user=self.user,
        )

        # Should reject workflow stage
        mock_reject_stage.assert_called_once_with(
            obj=self.user, stage=self.stage1, reason="Rejected for testing"
        )

    @patch("django_workflow_engine.services.trigger_workflow_event")
    def test_after_resubmission(self, mock_trigger_event):
        """Test resubmission handler."""
        # Set up resubmission to stage 2
        self.approval_instance.extra_fields = {"resubmission_stage_id": self.stage2.id}
        self.approval_instance.comment = "Please resubmit"

        handler = WorkflowApprovalHandler(self.user)
        handler.after_resubmission(self.approval_instance)

        # Should update attachment to target stage
        self.attachment.refresh_from_db()
        self.assertEqual(self.attachment.current_stage, self.stage2)

        # Should trigger resubmission actions
        mock_trigger_event.assert_called_once()
        call_args = mock_trigger_event.call_args
        self.assertEqual(call_args[0][0], self.attachment)
        self.assertEqual(call_args[0][1], ActionType.AFTER_RESUBMISSION)

    def test_after_resubmission_invalid_stage(self):
        """Test resubmission with invalid stage ID."""
        # Set up resubmission to non-existent stage
        self.approval_instance.extra_fields = {"resubmission_stage_id": 99999}

        handler = WorkflowApprovalHandler(self.user)

        # Should not raise errors, but log error
        with patch("django_workflow_engine.handlers.logger") as mock_logger:
            handler.after_resubmission(self.approval_instance)
            # Should log error about stage not found
            mock_logger.error.assert_called()


class HandlerRegistrationTest(TestCase):
    """Test cases for handler registration and resolution."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        unique_id = str(uuid.uuid4())[:8]
        self.company_user = User.objects.create_user(
            username=f"testcompany{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )
        self.company = Company.objects.create(name="Test Company")
        self.department = Department.objects.create(
            name="Test Department", company=self.company
        )

        self.workflow = WorkFlow.objects.create(
            company=self.company_user,
            name_en="Test Workflow",
            name_ar="سير عمل تجريبي",
            status=WorkflowStatus.ACTIVE,
            created_by=self.user,
        )

        self.pipeline = Pipeline.objects.create(
            workflow=self.workflow,
            company=self.company_user,
            name_en="Test Pipeline",
            name_ar="خط أنابيب تجريبي",
            created_by=self.user,
        )

        self.stage = Stage.objects.create(
            pipeline=self.pipeline,
            company=self.company_user,
            name_en="Test Stage",
            name_ar="مرحلة تجريبية",
            is_active=True,
            created_by=self.user,
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": self.user.id}]
            },
        )

        # Update workflow active status
        self.workflow.update_active_status()

    def test_get_handler_for_instance_with_workflow_attachment(self):
        """Test getting handler for instance with workflow attachment."""
        # Create workflow attachment
        attachment = attach_workflow_to_object(
            obj=self.user, workflow=self.workflow, user=self.user, auto_start=False
        )

        # Create approval flow
        content_type = ContentType.objects.get_for_model(User)
        approval_flow = ApprovalFlow.objects.create(
            content_type=content_type, object_id=str(self.user.pk)
        )

        approval_instance = ApprovalInstance.objects.create(
            flow=approval_flow,
            step_number=1,
            status=ApprovalStatus.PENDING,
            assigned_to=self.user,
        )

        # Should return WorkflowApprovalHandler
        handler = get_handler_for_instance(approval_instance)
        self.assertIsInstance(handler, WorkflowApprovalHandler)
        self.assertEqual(handler.instance, self.user)

    def test_get_handler_for_instance_without_attachment(self):
        """Test getting handler for instance without workflow attachment."""
        # Create approval flow without workflow attachment
        content_type = ContentType.objects.get_for_model(User)
        approval_flow = ApprovalFlow.objects.create(
            content_type=content_type, object_id=str(self.user.pk)
        )

        approval_instance = ApprovalInstance.objects.create(
            flow=approval_flow,
            step_number=1,
            status=ApprovalStatus.PENDING,
            assigned_to=self.user,
        )

        # Should return None for objects without workflow attachment
        handler = get_handler_for_instance(approval_instance)
        self.assertIsNone(handler)

    def test_get_handler_for_instance_no_target(self):
        """Test getting handler for instance with no target object."""
        # Create approval flow without target
        approval_flow = ApprovalFlow.objects.create(
            content_type=ContentType.objects.get_for_model(User),
            object_id="999999",  # Non-existent object
        )

        approval_instance = ApprovalInstance.objects.create(
            flow=approval_flow,
            step_number=1,
            status=ApprovalStatus.PENDING,
            assigned_to=self.user,
        )

        # Should return None for instances with no target
        handler = get_handler_for_instance(approval_instance)
        self.assertIsNone(handler)


@pytest.mark.django_db
class TestHandlerIntegrationWithApprovalWorkflow:
    """Integration tests between handlers and approval workflow."""

    def test_complete_approval_workflow_integration(self):
        """Test complete integration from approval to workflow progression."""
        # Create user and workflow
        user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        unique_id = str(uuid.uuid4())[:8]
        company_user = User.objects.create_user(
            username=f"testcompany{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )
        company = Company.objects.create(name="Test Company")
        department = Department.objects.create(name="Test Department", company=company)

        workflow = WorkFlow.objects.create(
            company=company_user,
            name_en="Integration Test Workflow",
            name_ar="سير عمل اختبار التكامل",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            name_ar="خط أنابيب تجريبي",
            created_by=user,
        )

        stage1 = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Initial Review",
            name_ar="المراجعة الأولية",
            created_by=user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": user.id}]
            },
        )

        stage2 = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Final Approval",
            name_ar="الموافقة النهائية",
            created_by=user,
            order=1,
            is_active=True,
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": user.id}]
            },
        )

        # Attach workflow
        attachment = attach_workflow_to_object(
            obj=user, workflow=workflow, user=user, auto_start=False
        )
        attachment.current_stage = stage1
        attachment.current_pipeline = pipeline
        attachment.status = WorkflowAttachmentStatus.IN_PROGRESS
        attachment.save()

        # Update workflow active status
        workflow.update_active_status()

        # Create approval flow
        content_type = ContentType.objects.get_for_model(User)
        approval_flow = ApprovalFlow.objects.create(
            content_type=content_type, object_id=str(user.pk)
        )

        # Create approval instance for stage 1
        approval_instance = ApprovalInstance.objects.create(
            flow=approval_flow,
            step_number=1,
            status=ApprovalStatus.APPROVED,
            assigned_to=user,
            action_user=user,
            comment="Stage 1 approved",
        )

        # Test handler resolution
        handler = get_handler_for_instance(approval_instance)
        assert isinstance(handler, WorkflowApprovalHandler)
        assert handler.instance == user

        # Test final approval progression
        with patch("django_workflow_engine.services.move_to_next_stage") as mock_move:
            mock_move.return_value = attachment
            handler.on_final_approve(approval_instance)
            mock_move.assert_called_once_with(user)

        # Verify attachment state would be updated
        attachment.refresh_from_db()
        # Workflow should be cloned, not the original
        assert attachment.workflow != workflow
        assert attachment.workflow.cloned_from == workflow
