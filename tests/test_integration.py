"""Integration tests demonstrating complete workflow with django-approval-workflow."""

from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

import pytest
from approval_workflow.choices import ApprovalStatus, RoleSelectionStrategy
from approval_workflow.models import ApprovalFlow, ApprovalInstance
from approval_workflow.services import start_flow

from django_workflow_engine.choices import (
    ActionType,
    WorkflowAttachmentStatus,
    WorkflowStatus,
)
from django_workflow_engine.handlers import (
    WorkflowApprovalHandler,
    get_handler_for_instance,
)
from django_workflow_engine.models import (
    Pipeline,
    Stage,
    WorkFlow,
    WorkflowAction,
    WorkflowAttachment,
    WorkflowConfiguration,
)
from django_workflow_engine.serializers import WorkflowApprovalSerializer
from django_workflow_engine.services import (
    attach_workflow_to_object,
    register_model_for_workflow,
    start_workflow_for_object,
    trigger_workflow_event,
)
from sandbox.testapp.models import Company, Department

User = get_user_model()


@pytest.mark.django_db
class TestCompleteWorkflowIntegration:
    """Complete integration test using django-approval-workflow."""

    def test_complete_workflow_lifecycle(self):
        """Test complete workflow lifecycle from creation to completion."""
        # Setup users
        creator = User.objects.create_user(
            username="creator", email="creator@example.com", password="testpass123"
        )

        approver1 = User.objects.create_user(
            username="approver1", email="approver1@example.com", password="testpass123"
        )

        approver2 = User.objects.create_user(
            username="approver2", email="approver2@example.com", password="testpass123"
        )

        # Create a test model to attach workflow to
        test_object = creator  # Using User as test object

        # Step 1: Create workflow structure
        company = Company.objects.create(name="Test Company")
        hr_department = Department.objects.create(name="HR Department", company=company)
        finance_department = Department.objects.create(
            name="Finance Department", company=company
        )

        workflow = WorkFlow.objects.create(
            company=company,
            name_en="Document Approval Workflow",
            name_ar="سير عمل الموافقة على الوثائق",
            status=WorkflowStatus.ACTIVE,
            created_by=creator,
        )

        # Create two pipelines
        hr_pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company,
            name_en="HR Review",
            name_ar="مراجعة الموارد البشرية",
            department_id=hr_department.id,
            created_by=creator,
            order=0,
        )

        finance_pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company,
            name_en="Finance Approval",
            name_ar="موافقة المالية",
            department_id=finance_department.id,
            created_by=creator,
            order=1,
        )

        # Create stages for HR pipeline
        hr_stage1 = Stage.objects.create(
            pipeline=hr_pipeline,
            company=company,
            name_en="Initial HR Review",
            name_ar="المراجعة الأولية للموارد البشرية",
            created_by=creator,
            order=0,
            is_active=True,
            # Configure approval requirements for this stage
            stage_info={
                "approval_config": {
                    "required_approvals": 1,
                    "approvers": [approver1.id],
                    "role_selection_strategy": RoleSelectionStrategy.CONSENSUS,
                }
            },
        )

        hr_stage2 = Stage.objects.create(
            pipeline=hr_pipeline,
            company=company,
            name_en="HR Manager Approval",
            name_ar="موافقة مدير الموارد البشرية",
            created_by=creator,
            order=1,
            is_active=True,
            stage_info={
                "approval_config": {
                    "required_approvals": 1,
                    "approvers": [approver2.id],
                    "role_selection_strategy": RoleSelectionStrategy.CONSENSUS,
                }
            },
        )

        # Create stage for Finance pipeline
        finance_stage = Stage.objects.create(
            pipeline=finance_pipeline,
            company=company,
            name_en="Finance Review",
            name_ar="مراجعة المالية",
            created_by=creator,
            order=0,
            is_active=True,
            stage_info={
                "approval_config": {
                    "required_approvals": 1,
                    "approvers": [approver2.id],
                    "role_selection_strategy": RoleSelectionStrategy.CONSENSUS,
                }
            },
        )

        # Update workflow active status
        workflow.update_active_status()

        # Step 2: Configure workflow actions
        # Add email action for approval events
        WorkflowAction.objects.create(
            workflow=workflow,
            action_type=ActionType.AFTER_APPROVE,
            function_path="django_workflow_engine.default_actions.default_send_email_after_approve",
            is_active=True,
            order=0,
            parameters={"custom_subject": "Document Approved"},
        )

        WorkflowAction.objects.create(
            stage=hr_stage1,  # Stage-specific action (higher priority)
            action_type=ActionType.AFTER_APPROVE,
            function_path="tests.test_integration.custom_hr_approval_action",
            is_active=True,
            order=0,
            parameters={"hr_department": "Human Resources"},
        )

        # Step 3: Register model for workflow support
        register_model_for_workflow(
            model_class=User,
            auto_start=True,
            default_workflow=workflow,
            status_field="workflow_status",
            stage_field="current_stage",
        )

        # Step 4: Attach workflow to object
        attachment = attach_workflow_to_object(
            obj=test_object,
            workflow=workflow,
            user=creator,
            auto_start=False,  # We'll start manually
            metadata={"document_type": "employee_contract", "priority": "high"},
        )

        assert attachment.target == test_object
        assert attachment.workflow == workflow
        assert attachment.status == WorkflowAttachmentStatus.NOT_STARTED

        # Step 5: Start workflow (should create approval flow)
        with patch(
            "django_workflow_engine.utils.build_approval_steps"
        ) as mock_build_steps:
            # Mock approval steps for first stage
            mock_build_steps.return_value = [
                {
                    "step": 1,
                    "assigned_to": approver1,
                    "required_approvals": 1,
                    "role_selection_strategy": RoleSelectionStrategy.CONSENSUS,
                    "step_number": 1,
                    "sla_duration": None,
                    "allow_higher_level": False,
                    "extra_fields": {"stage_id": hr_stage1.id},
                }
            ]

            # Start workflow
            updated_attachment = start_workflow_for_object(test_object, creator)

            assert updated_attachment.status == WorkflowAttachmentStatus.IN_PROGRESS
            assert updated_attachment.current_stage == hr_stage1
            assert updated_attachment.current_pipeline == hr_pipeline
            assert updated_attachment.started_by == creator

        # Step 6: Verify approval flow was created
        content_type = ContentType.objects.get_for_model(User)
        approval_flow = ApprovalFlow.objects.get(
            content_type=content_type, object_id=str(test_object.pk)
        )
        assert approval_flow.target == test_object

        # Create approval instance for testing (normally created by approval workflow)
        approval_instance = ApprovalInstance.objects.create(
            flow=approval_flow,
            step_number=1,
            status=ApprovalStatus.PENDING,
            assigned_to=approver1,
            extra_fields={"stage_id": hr_stage1.id},
        )

        # Step 7: Test handler resolution
        handler = get_handler_for_instance(approval_instance)
        assert isinstance(handler, WorkflowApprovalHandler)
        assert handler.instance == test_object

        # Step 8: Test approval action using serializer
        mock_request = Mock()
        mock_request.user = approver1

        approval_data = {
            "action": ApprovalStatus.APPROVED,
            "form_data": {
                "comment": "Initial HR review passed",
                "reviewed_by": approver1.username,
            },
        }

        serializer = WorkflowApprovalSerializer(
            data=approval_data,
            object_instance=test_object,
            context={"request": mock_request},
        )

        assert serializer.is_valid()

        # Step 9: Process approval (would trigger workflow progression)
        approval_instance.status = ApprovalStatus.APPROVED
        approval_instance.action_user = approver1
        approval_instance.comment = "Initial HR review passed"
        approval_instance.save()

        # Test final approval handler
        with patch("django_workflow_engine.services.move_to_next_stage") as mock_move:
            with patch(
                "django_workflow_engine.services.trigger_workflow_event"
            ) as mock_trigger:
                # Simulate final approval
                updated_attachment.current_stage = hr_stage2
                mock_move.return_value = updated_attachment

                handler.on_final_approve(approval_instance)

                # Verify actions were triggered
                mock_trigger.assert_called_with(
                    updated_attachment,
                    ActionType.AFTER_APPROVE,
                    approval_instance=approval_instance,
                    user=approver1,
                )

                # Verify stage progression
                mock_move.assert_called_once_with(test_object)

        # Step 10: Test workflow action execution
        with patch(
            "django_workflow_engine.services.execute_action_function"
        ) as mock_execute:
            mock_execute.return_value = True

            results = trigger_workflow_event(
                attachment,
                ActionType.AFTER_APPROVE,
                approval_instance=approval_instance,
                user=approver1,
            )

            assert len(results) > 0  # Should have executed actions
            mock_execute.assert_called()

        # Step 11: Test rejection scenario
        rejection_data = {
            "action": ApprovalStatus.REJECTED,
            "reason": "Missing required documentation",
        }

        rejection_serializer = WorkflowApprovalSerializer(
            data=rejection_data,
            object_instance=test_object,
            context={"request": mock_request},
        )

        assert rejection_serializer.is_valid()

        # Test rejection handler
        approval_instance.status = ApprovalStatus.REJECTED
        approval_instance.comment = "Missing required documentation"

        with patch(
            "django_workflow_engine.services.reject_workflow_stage"
        ) as mock_reject:
            with patch(
                "django_workflow_engine.services.trigger_workflow_event"
            ) as mock_trigger:
                handler.after_reject(approval_instance)

                mock_trigger.assert_called_with(
                    attachment,
                    ActionType.AFTER_REJECT,
                    approval_instance=approval_instance,
                    reason="Missing required documentation",
                    user=approver1,
                )

                mock_reject.assert_called_with(
                    obj=test_object,
                    stage=hr_stage1,
                    reason="Missing required documentation",
                )

        # Step 12: Test resubmission scenario
        resubmission_data = {
            "action": ApprovalStatus.NEEDS_RESUBMISSION,
            "stage_id": hr_stage1.id,
            "reason": "Please update document format",
        }

        resubmission_serializer = WorkflowApprovalSerializer(
            data=resubmission_data,
            object_instance=test_object,
            context={"request": mock_request},
        )

        assert resubmission_serializer.is_valid()

        # Test resubmission handler
        approval_instance.extra_fields = {"resubmission_stage_id": hr_stage1.id}
        approval_instance.comment = "Please update document format"

        with patch(
            "django_workflow_engine.services.trigger_workflow_event"
        ) as mock_trigger:
            handler.after_resubmission(approval_instance)

            # Verify attachment was updated
            attachment.refresh_from_db()
            assert attachment.current_stage == hr_stage1

            # Verify resubmission action was triggered
            mock_trigger.assert_called()

        # Step 13: Test delegation
        delegate_user = User.objects.create_user(
            username="delegate", email="delegate@example.com", password="testpass123"
        )

        delegation_data = {
            "action": ApprovalStatus.DELEGATED,
            "user_id": delegate_user.id,
            "reason": "Delegating to subject matter expert",
        }

        delegation_serializer = WorkflowApprovalSerializer(
            data=delegation_data,
            object_instance=test_object,
            context={"request": mock_request},
        )

        assert delegation_serializer.is_valid()

        # Verify workflow configuration is accessible
        config = WorkflowConfiguration.objects.get(content_type=content_type)
        assert config.is_enabled
        assert config.default_workflow == workflow

    def test_workflow_with_custom_actions(self):
        """Test workflow with custom action functions."""
        # Create minimal workflow for custom action testing
        user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        company = Company.objects.create(name="Test Company")
        department = Department.objects.create(name="Test Department", company=company)

        workflow = WorkFlow.objects.create(
            company=company,
            name_en="Custom Action Workflow",
            name_ar="سير عمل الإجراءات المخصصة",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company,
            name_en="Test Pipeline",
            name_ar="خط أنابيب تجريبي",
            department_id=department.id,
            created_by=user,
        )

        stage = Stage.objects.create(
            pipeline=pipeline,
            company=company,
            name_en="Test Stage",
            name_ar="مرحلة تجريبية",
            created_by=user,
            is_active=True,
        )

        # Create custom action
        custom_action = WorkflowAction.objects.create(
            stage=stage,
            action_type=ActionType.AFTER_APPROVE,
            function_path="tests.test_integration.custom_test_action",
            is_active=True,
            order=0,
            parameters={"custom_message": "Custom action executed", "test_mode": True},
        )

        # Update workflow active status
        workflow.update_active_status()

        attachment = attach_workflow_to_object(
            obj=user, workflow=workflow, user=user, auto_start=False
        )
        attachment.current_stage = stage
        attachment.current_pipeline = pipeline
        attachment.save()

        # Test action execution
        with patch(
            "django_workflow_engine.services.execute_action_function"
        ) as mock_execute:
            mock_execute.return_value = "Custom action result"

            results = trigger_workflow_event(
                attachment,
                ActionType.AFTER_APPROVE,
                user=user,
                test_context="integration_test",
            )

            assert len(results) == 1
            assert results[0] == "Custom action result"

            # Verify function was called with correct parameters
            call_args = mock_execute.call_args
            assert (
                call_args[1]["function_path"]
                == "tests.test_integration.custom_test_action"
            )
            assert (
                call_args[1]["parameters"]["custom_message"] == "Custom action executed"
            )
            assert call_args[1]["context"]["test_context"] == "integration_test"


# Mock custom action functions for testing
def custom_hr_approval_action(**context):
    """Mock custom HR approval action."""
    attachment = context.get("attachment")
    user = context.get("user")
    hr_department = context.get("hr_department", "HR")

    return {
        "action": "hr_approval_processed",
        "department": hr_department,
        "user": user.username if user else None,
        "object_id": attachment.object_id if attachment else None,
    }


def custom_test_action(**context):
    """Mock custom test action."""
    custom_message = context.get("custom_message", "Default message")
    test_mode = context.get("test_mode", False)

    if test_mode:
        return f"TEST: {custom_message}"
    return custom_message


class WorkflowConfigurationIntegrationTest(TestCase):
    """Test workflow configuration integration."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_model_registration_workflow_integration(self):
        """Test model registration with django-approval-workflow integration."""
        company = Company.objects.create(name="Test Company")
        department = Department.objects.create(name="Test Department", company=company)

        workflow = WorkFlow.objects.create(
            company=company,
            name_en="Default User Workflow",
            name_ar="سير عمل المستخدم الافتراضي",
            status=WorkflowStatus.ACTIVE,
            created_by=self.user,
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company,
            name_en="User Processing",
            name_ar="معالجة المستخدم",
            department_id=department.id,
            created_by=self.user,
        )

        Stage.objects.create(
            pipeline=pipeline,
            company=company,
            name_en="User Verification",
            name_ar="التحقق من المستخدم",
            created_by=self.user,
            is_active=True,
        )

        # Update workflow active status
        workflow.update_active_status()

        # Register User model for workflow
        config = register_model_for_workflow(
            model_class=User,
            auto_start=True,
            default_workflow=workflow,
            status_field="workflow_status",
            stage_field="current_stage",
            pre_start_hook="myapp.hooks.pre_start_user_workflow",
            post_complete_hook="myapp.hooks.post_complete_user_workflow",
        )

        self.assertTrue(config.auto_start_workflow)
        self.assertEqual(config.default_workflow, workflow)
        self.assertEqual(config.status_field, "workflow_status")
        self.assertEqual(config.pre_start_hook, "myapp.hooks.pre_start_user_workflow")

        # Test that configuration is accessible
        content_type = ContentType.objects.get_for_model(User)
        found_config = WorkflowConfiguration.objects.get(content_type=content_type)
        self.assertEqual(found_config, config)
