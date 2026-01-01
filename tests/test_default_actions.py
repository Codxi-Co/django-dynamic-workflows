"""Test cases for default workflow actions."""

from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

import pytest
from approval_workflow.models import ApprovalInstance

from django_workflow_engine.choices import WorkflowAttachmentStatus, WorkflowStatus
from django_workflow_engine.default_actions import (
    _send_email,
    default_send_email_after_approve,
    default_send_email_after_delegate,
    default_send_email_after_move_pipeline,
    default_send_email_after_move_stage,
    default_send_email_after_reject,
    default_send_email_after_resubmission,
    default_send_email_on_workflow_complete,
    default_send_email_on_workflow_start,
)
from django_workflow_engine.models import Pipeline, Stage, WorkFlow, WorkflowAttachment
from django_workflow_engine.services import attach_workflow_to_object
from sandbox.testapp.models import Company, Department

User = get_user_model()


class DefaultActionsTest(TestCase):
    """Test cases for default action functions."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        # Create a company user that represents the organization
        self.company_user = User.objects.create_user(
            username="testcompany", email="company@example.com", password="testpass123"
        )
        self.company = Company.objects.create(name="Test Company")
        self.department = Department.objects.create(
            name="Test Department", company=self.company
        )
        self.department2 = Department.objects.create(
            name="Second Department", company=self.company
        )

        # Create workflow structure with company_user instead of company
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
        # Set department using GenericForeignKey
        self.pipeline.department = self.department
        self.pipeline.save()

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

        # Create workflow attachment
        self.attachment = attach_workflow_to_object(
            obj=self.user, workflow=self.workflow, user=self.user, auto_start=False
        )
        self.attachment.current_stage = self.stage
        self.attachment.current_pipeline = self.pipeline
        self.attachment.save()

    @patch("django_workflow_engine.default_actions._send_email")
    def test_default_send_email_after_approve(self, mock_send_email):
        """Test default approve email action."""
        mock_send_email.return_value = True

        context = {
            "attachment": self.attachment,
            "obj": self.user,
            "current_stage": self.stage,
            "user": self.user,
        }

        result = default_send_email_after_approve(**context)

        self.assertTrue(result)
        mock_send_email.assert_called_once()

        # Check email content
        call_args = mock_send_email.call_args
        recipients, subject, message, context_arg = call_args[0]

        self.assertIn(self.user.email, recipients)
        self.assertIn("Approval Completed", subject)
        self.assertIn(self.stage.name_en, message)

    @patch("django_workflow_engine.default_actions._send_email")
    def test_default_send_email_after_reject(self, mock_send_email):
        """Test default reject email action."""
        mock_send_email.return_value = True

        context = {
            "attachment": self.attachment,
            "obj": self.user,
            "current_stage": self.stage,
            "reason": "Not meeting requirements",
            "user": self.user,
        }

        result = default_send_email_after_reject(**context)

        self.assertTrue(result)
        mock_send_email.assert_called_once()

        # Check email content
        call_args = mock_send_email.call_args
        recipients, subject, message, context_arg = call_args[0]

        self.assertIn(self.user.email, recipients)
        self.assertIn("Workflow Rejected", subject)
        self.assertIn("Not meeting requirements", message)

    @patch("django_workflow_engine.default_actions._send_email")
    def test_default_send_email_after_resubmission(self, mock_send_email):
        """Test default resubmission email action."""
        mock_send_email.return_value = True

        stage2 = Stage.objects.create(
            pipeline=self.pipeline,
            company=self.company_user,
            name_en="Review Stage",
            name_ar="مرحلة المراجعة",
            created_by=self.user,
            order=1,
        )

        context = {
            "attachment": self.attachment,
            "obj": self.user,
            "target_stage": stage2,
            "reason": "Please review documentation",
            "user": self.user,
        }

        result = default_send_email_after_resubmission(**context)

        self.assertTrue(result)
        mock_send_email.assert_called_once()

        # Check email content
        call_args = mock_send_email.call_args
        recipients, subject, message, context_arg = call_args[0]

        self.assertIn(self.user.email, recipients)
        self.assertIn("Resubmission Requested", subject)
        self.assertIn(stage2.name_en, message)

    @patch("django_workflow_engine.default_actions._send_email")
    def test_default_send_email_after_delegate(self, mock_send_email):
        """Test default delegation email action."""
        mock_send_email.return_value = True

        delegate_user = User.objects.create_user(
            username="delegate", email="delegate@example.com", password="testpass123"
        )

        context = {
            "attachment": self.attachment,
            "obj": self.user,
            "current_stage": self.stage,
            "delegate_to": delegate_user,
            "user": self.user,
            "reason": "You have more expertise",
        }

        result = default_send_email_after_delegate(**context)

        self.assertTrue(result)
        mock_send_email.assert_called_once()

        # Check email content
        call_args = mock_send_email.call_args
        recipients, subject, message, context_arg = call_args[0]

        self.assertIn(delegate_user.email, recipients)
        self.assertIn("Approval Delegated", subject)
        self.assertIn("You have more expertise", message)

    @patch("django_workflow_engine.default_actions._send_email")
    def test_default_send_email_after_move_stage(self, mock_send_email):
        """Test default stage move email action."""
        mock_send_email.return_value = True

        stage2 = Stage.objects.create(
            pipeline=self.pipeline,
            company=self.company_user,
            name_en="Next Stage",
            name_ar="المرحلة التالية",
            created_by=self.user,
            order=1,
        )

        context = {
            "attachment": self.attachment,
            "obj": self.user,
            "from_stage": self.stage,
            "to_stage": stage2,
        }

        result = default_send_email_after_move_stage(**context)

        self.assertTrue(result)
        mock_send_email.assert_called_once()

        # Check email content
        call_args = mock_send_email.call_args
        recipients, subject, message, context_arg = call_args[0]

        self.assertIn(self.user.email, recipients)
        self.assertIn("Workflow Progress", subject)
        self.assertIn(stage2.name_en, message)

    @patch("django_workflow_engine.default_actions._send_email")
    def test_default_send_email_after_move_pipeline(self, mock_send_email):
        """Test default pipeline move email action."""
        mock_send_email.return_value = True

        pipeline2 = Pipeline.objects.create(
            workflow=self.workflow,
            company=self.company_user,
            name_en="Second Pipeline",
            name_ar="الخط الثاني",
            created_by=self.user,
            order=1,
        )

        context = {
            "attachment": self.attachment,
            "obj": self.user,
            "from_pipeline": self.pipeline,
            "to_pipeline": pipeline2,
        }

        result = default_send_email_after_move_pipeline(**context)

        self.assertTrue(result)
        mock_send_email.assert_called_once()

        # Check email content
        call_args = mock_send_email.call_args
        recipients, subject, message, context_arg = call_args[0]

        self.assertIn(self.user.email, recipients)
        self.assertIn("moved to a new pipeline", message)
        self.assertIn(pipeline2.name_en, message)

    @patch("django_workflow_engine.default_actions._send_email")
    def test_default_send_email_on_workflow_start(self, mock_send_email):
        """Test default workflow start email action."""
        mock_send_email.return_value = True

        context = {
            "attachment": self.attachment,
            "obj": self.user,
            "workflow": self.workflow,
            "initial_stage": self.stage,
        }

        result = default_send_email_on_workflow_start(**context)

        self.assertTrue(result)
        mock_send_email.assert_called_once()

        # Check email content
        call_args = mock_send_email.call_args
        recipients, subject, message, context_arg = call_args[0]

        self.assertIn(self.user.email, recipients)
        self.assertIn("Workflow Started", subject)
        self.assertIn(self.workflow.name_en, message)

    @patch("django_workflow_engine.default_actions._send_email")
    def test_default_send_email_on_workflow_complete(self, mock_send_email):
        """Test default workflow complete email action."""
        mock_send_email.return_value = True
        self.attachment.status = WorkflowAttachmentStatus.COMPLETED
        self.attachment.save()

        context = {
            "attachment": self.attachment,
            "obj": self.user,
            "workflow": self.workflow,
        }

        result = default_send_email_on_workflow_complete(**context)

        self.assertTrue(result)
        mock_send_email.assert_called_once()

        # Check email content
        call_args = mock_send_email.call_args
        recipients, subject, message, context_arg = call_args[0]

        self.assertIn(self.user.email, recipients)
        self.assertIn("Workflow Completed", subject)
        self.assertIn(self.workflow.name_en, message)

    def test_action_with_missing_context(self):
        """Test action behavior with missing required context."""
        # Missing attachment
        context = {"obj": self.user, "current_stage": self.stage, "user": self.user}

        result = default_send_email_after_approve(**context)
        self.assertFalse(result)

        # Missing object
        context = {
            "attachment": self.attachment,
            "current_stage": self.stage,
            "user": self.user,
        }

        result = default_send_email_after_approve(**context)
        self.assertFalse(result)

    def test_action_with_no_email_recipients(self):
        """Test action behavior when no email recipients are found."""
        # Create user without email
        user_no_email = User.objects.create_user(
            username="noemail", password="testpass123"
        )

        attachment = attach_workflow_to_object(
            obj=user_no_email,
            workflow=self.workflow,
            user=user_no_email,
            auto_start=False,
        )

        context = {
            "attachment": attachment,
            "obj": user_no_email,
            "current_stage": self.stage,
            "user": user_no_email,
        }

        result = default_send_email_after_approve(**context)
        self.assertFalse(result)

    @patch("django.conf.settings.WORKFLOW_DISABLE_EMAILS", False, create=True)
    @patch("django_workflow_engine.default_actions._try_async_email")
    @patch("django.core.mail.send_mail")
    def test_send_email_function(self, mock_send_mail, mock_async_email):
        """Test the internal _send_email function."""
        mock_async_email.return_value = False  # No async email available
        mock_send_mail.return_value = True

        recipients = ["test1@example.com", "test2@example.com"]
        subject = "Test Subject"
        message = "Test message"
        context = {}

        result = _send_email(recipients, subject, message, context)

        self.assertTrue(result)
        mock_send_mail.assert_called_once_with(
            subject=subject,
            message=message,
            from_email="noreply@example.com",  # Default from settings
            recipient_list=recipients,
            fail_silently=True,  # Changed to True for non-blocking behavior
        )

    @patch("django.conf.settings.WORKFLOW_DISABLE_EMAILS", False, create=True)
    @patch("django_workflow_engine.default_actions._try_async_email")
    @patch("django.core.mail.send_mail")
    def test_send_email_function_failure(self, mock_send_mail, mock_async_email):
        """Test _send_email function when email sending fails."""
        mock_async_email.return_value = False  # No async email available
        mock_send_mail.side_effect = Exception("SMTP Error")

        recipients = ["test@example.com"]
        subject = "Test Subject"
        message = "Test message"
        context = {}

        result = _send_email(recipients, subject, message, context)

        self.assertFalse(result)

    @patch("django.conf.settings.WORKFLOW_DISABLE_EMAILS", False, create=True)
    @patch("django_workflow_engine.default_actions._try_async_email")
    def test_send_email_with_async(self, mock_async_email):
        """Test _send_email function with async email enabled."""
        mock_async_email.return_value = True  # Async email succeeded

        recipients = ["test@example.com"]
        subject = "Test Subject"
        message = "Test message"
        context = {}

        result = _send_email(recipients, subject, message, context)

        self.assertTrue(result)
        mock_async_email.assert_called_once_with(recipients, subject, message)

    @patch("django_workflow_engine.default_actions._try_async_email")
    @patch("django.conf.settings.WORKFLOW_DISABLE_EMAILS", True, create=True)
    def test_send_email_disabled(self, mock_async_email):
        """Test _send_email function when emails are disabled."""
        recipients = ["test@example.com"]
        subject = "Test Subject"
        message = "Test message"
        context = {}

        result = _send_email(recipients, subject, message, context)

        # Should return True but not actually send
        self.assertTrue(result)
        # Async email should not be attempted
        mock_async_email.assert_not_called()

    def test_user_with_started_by_different_from_created_by(self):
        """Test email recipients when started_by is different from created_by."""
        # Create another user who starts the workflow
        starter_user = User.objects.create_user(
            username="starter", email="starter@example.com", password="testpass123"
        )

        # Create an object with created_by field (use the workflow itself as test object)
        test_obj = self.workflow

        # Update attachment to have different started_by
        self.attachment.started_by = starter_user
        self.attachment.save()

        with patch(
            "django_workflow_engine.default_actions._send_email"
        ) as mock_send_email:
            mock_send_email.return_value = True

            context = {
                "attachment": self.attachment,
                "obj": test_obj,  # Use workflow which has created_by
                "current_stage": self.stage,
                "user": self.user,
            }

            result = default_send_email_after_approve(**context)

            self.assertTrue(result)

            # Check that both creator and starter emails are included
            call_args = mock_send_email.call_args
            recipients = call_args[0][0]

            self.assertIn(self.user.email, recipients)  # Creator (from obj.created_by)
            self.assertIn(
                starter_user.email, recipients
            )  # Starter (from attachment.started_by)


@pytest.mark.django_db
class TestDefaultActionsIntegration:
    """Integration tests for default actions with django-approval-workflow."""

    def test_default_actions_with_approval_instance(self):
        """Test default actions receiving approval instance context."""
        user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # Create a company user that represents the organization
        company_user = User.objects.create_user(
            username="testcompany", email="company@example.com", password="testpass123"
        )
        company = Company.objects.create(name="Test Company")
        department = Department.objects.create(name="Test Department", company=company)

        workflow = WorkFlow.objects.create(
            company=company_user,
            name_en="Test Workflow",
            name_ar="سير عمل تجريبي",
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
        # Set department using GenericForeignKey
        pipeline.department = department
        pipeline.save()

        stage = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Test Stage",
            name_ar="مرحلة تجريبية",
            is_active=True,
            created_by=user,
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": user.id}]
            },
        )

        # Update workflow active status
        workflow.update_active_status()

        attachment = attach_workflow_to_object(
            obj=user, workflow=workflow, user=user, auto_start=False
        )
        attachment.current_stage = stage
        attachment.current_pipeline = pipeline
        attachment.save()

        # Create approval instance
        content_type = ContentType.objects.get_for_model(User)
        from approval_workflow.models import ApprovalFlow

        approval_flow = ApprovalFlow.objects.create(
            content_type=content_type, object_id=str(user.pk)
        )

        approval_instance = ApprovalInstance.objects.create(
            flow=approval_flow,
            step_number=1,
            assigned_to=user,
            action_user=user,
            comment="Approved by integration test",
        )

        with patch(
            "django_workflow_engine.default_actions._send_email"
        ) as mock_send_email:
            mock_send_email.return_value = True

            context = {
                "attachment": attachment,
                "obj": user,
                "current_stage": stage,
                "user": user,
                "approval_instance": approval_instance,
            }

            result = default_send_email_after_approve(**context)

            assert result is True
            mock_send_email.assert_called_once()

            # Verify email content includes approval information
            call_args = mock_send_email.call_args
            recipients, subject, message, context_arg = call_args[0]

            assert user.email in recipients
            assert "Approval Completed" in subject
