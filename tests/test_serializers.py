"""Test cases for workflow serializers."""

import uuid
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

import pytest
from approval_workflow.choices import ApprovalStatus
from approval_workflow.models import ApprovalFlow, ApprovalInstance

from django_workflow_engine.choices import WorkflowAttachmentStatus, WorkflowStatus
from django_workflow_engine.models import Pipeline, Stage, WorkFlow
from django_workflow_engine.serializers import WorkflowApprovalSerializer
from django_workflow_engine.services import attach_workflow_to_object
from sandbox.testapp.models import Company, Department

User = get_user_model()


class WorkflowApprovalSerializerTest(TestCase):
    """Test cases for WorkflowApprovalSerializer."""

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
        )

        self.stage2 = Stage.objects.create(
            pipeline=self.pipeline,
            company=self.company_user,
            name_en="Stage 2",
            name_ar="المرحلة 2",
            created_by=self.user,
            order=1,
            is_active=True,
        )

        # Create workflow attachment
        self.attachment = attach_workflow_to_object(
            obj=self.user, workflow=self.workflow, user=self.user, auto_start=False
        )
        # Get the cloned stages from the cloned workflow
        cloned_pipeline = self.attachment.workflow.pipelines.first()
        cloned_stage1 = cloned_pipeline.stages.get(order=0)

        self.attachment.current_stage = cloned_stage1
        self.attachment.current_pipeline = cloned_pipeline
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
            status=ApprovalStatus.CURRENT,
            assigned_to=self.user,
            action_user=self.user,
            comment="Test approval",
        )

        # Create mock request
        self.mock_request = Mock()
        self.mock_request.user = self.user

    def test_approval_serializer_validation(self):
        """Test serializer validation for approval action."""
        data = {
            "action": ApprovalStatus.APPROVED,
            "form_data": {"comment": "Looks good"},
        }

        serializer = WorkflowApprovalSerializer(
            data=data, object_instance=self.user, context={"request": self.mock_request}
        )

        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["action"], ApprovalStatus.APPROVED)
        self.assertEqual(
            serializer.validated_data["form_data"]["comment"], "Looks good"
        )

    def test_rejection_serializer_validation(self):
        """Test serializer validation for rejection action."""
        data = {
            "action": ApprovalStatus.REJECTED,
            "reason": "Missing required documentation",
        }

        serializer = WorkflowApprovalSerializer(
            data=data, object_instance=self.user, context={"request": self.mock_request}
        )

        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["action"], ApprovalStatus.REJECTED)
        self.assertEqual(
            serializer.validated_data["reason"], "Missing required documentation"
        )

    def test_resubmission_serializer_validation(self):
        """Test serializer validation for resubmission action."""
        # Use the cloned stage ID
        cloned_stage1 = self.attachment.current_stage
        data = {
            "action": ApprovalStatus.NEEDS_RESUBMISSION,
            "stage_id": cloned_stage1.id,
            "reason": "Please update the documentation",
        }

        serializer = WorkflowApprovalSerializer(
            data=data, object_instance=self.user, context={"request": self.mock_request}
        )

        self.assertTrue(serializer.is_valid())
        self.assertEqual(
            serializer.validated_data["action"], ApprovalStatus.NEEDS_RESUBMISSION
        )
        self.assertEqual(serializer.validated_data["stage_id"], cloned_stage1.id)

    def test_delegation_serializer_validation(self):
        """Test serializer validation for delegation action."""
        delegate_user = User.objects.create_user(
            username="delegate", email="delegate@example.com", password="testpass123"
        )

        data = {
            "action": ApprovalStatus.DELEGATED,
            "user_id": delegate_user.id,
            "reason": "You have more expertise in this area",
        }

        serializer = WorkflowApprovalSerializer(
            data=data, object_instance=self.user, context={"request": self.mock_request}
        )

        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["action"], ApprovalStatus.DELEGATED)
        self.assertEqual(serializer.validated_data["user_id"], delegate_user.id)

    def test_invalid_action_validation(self):
        """Test serializer validation with invalid action."""
        data = {
            "action": "invalid_action",
        }

        serializer = WorkflowApprovalSerializer(
            data=data, object_instance=self.user, context={"request": self.mock_request}
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("action", serializer.errors)

    def test_resubmission_without_stage_id(self):
        """Test resubmission validation without stage_id."""
        data = {
            "action": ApprovalStatus.NEEDS_RESUBMISSION,
            "reason": "Please update",
        }

        serializer = WorkflowApprovalSerializer(
            data=data, object_instance=self.user, context={"request": self.mock_request}
        )

        # Should still be valid - stage_id is optional
        self.assertTrue(serializer.is_valid())

    def test_delegation_without_user_id(self):
        """Test delegation validation without user_id."""
        data = {
            "action": ApprovalStatus.DELEGATED,
            "reason": "Need expert review",
        }

        serializer = WorkflowApprovalSerializer(
            data=data, object_instance=self.user, context={"request": self.mock_request}
        )

        # Should still be valid - user_id is optional
        self.assertTrue(serializer.is_valid())

    @patch("django_workflow_engine.serializers.advance_flow")
    def test_serializer_save_method(self, mock_advance_flow):
        """Test serializer save method calls advance_flow."""
        # Setup mock
        mock_advance_flow.return_value = self.user

        data = {
            "action": ApprovalStatus.APPROVED,
            "form_data": {"comment": "Approved"},
        }

        serializer = WorkflowApprovalSerializer(
            data=data, object_instance=self.user, context={"request": self.mock_request}
        )

        self.assertTrue(serializer.is_valid())

        # Call save
        result = serializer.save()

        # Verify advance_flow was called
        mock_advance_flow.assert_called_once_with(
            instance=self.user,
            action=ApprovalStatus.APPROVED,
            user=self.mock_request.user,
            comment="",
            form_data={"comment": "Approved"},
            delegate_to=None,
            resubmission_steps=None,
        )
        self.assertEqual(result, self.user)

    def test_serializer_with_form_data(self):
        """Test serializer with complex form data."""
        form_data = {
            "comment": "This is a detailed comment",
            "priority": "high",
            "department": "engineering",
            "estimated_hours": 40,
            "attachments": ["file1.pdf", "file2.docx"],
        }

        data = {
            "action": ApprovalStatus.APPROVED,
            "form_data": form_data,
        }

        serializer = WorkflowApprovalSerializer(
            data=data, object_instance=self.user, context={"request": self.mock_request}
        )

        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["form_data"], form_data)

    def test_serializer_without_object_instance(self):
        """Test serializer behavior without object_instance."""
        data = {
            "action": ApprovalStatus.APPROVED,
        }

        serializer = WorkflowApprovalSerializer(
            data=data, context={"request": self.mock_request}
        )

        # Should require object_instance for workflow approval
        self.assertFalse(serializer.is_valid())
        self.assertIn("action", serializer.errors)
        self.assertIn(
            "Object instance is required", str(serializer.errors["action"][0])
        )

    def test_serializer_without_request_context(self):
        """Test serializer behavior without request in context."""
        data = {
            "action": ApprovalStatus.APPROVED,
        }

        serializer = WorkflowApprovalSerializer(
            data=data, object_instance=self.user, context={}
        )

        # Should still validate data structure
        self.assertTrue(serializer.is_valid())

    def test_serializer_with_empty_form_data(self):
        """Test serializer with empty form_data."""
        data = {
            "action": ApprovalStatus.APPROVED,
            "form_data": {},
        }

        serializer = WorkflowApprovalSerializer(
            data=data, object_instance=self.user, context={"request": self.mock_request}
        )

        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["form_data"], {})

    def test_serializer_with_reason_and_form_data(self):
        """Test serializer with both reason and form_data."""
        data = {
            "action": ApprovalStatus.REJECTED,
            "reason": "Does not meet requirements",
            "form_data": {
                "comment": "Additional details in form",
                "reviewer": "John Doe",
            },
        }

        serializer = WorkflowApprovalSerializer(
            data=data, object_instance=self.user, context={"request": self.mock_request}
        )

        self.assertTrue(serializer.is_valid())
        self.assertEqual(
            serializer.validated_data["reason"], "Does not meet requirements"
        )
        self.assertEqual(
            serializer.validated_data["form_data"]["comment"],
            "Additional details in form",
        )


@pytest.mark.django_db
class TestSerializerIntegrationWithApprovalWorkflow:
    """Integration tests between serializer and approval workflow."""

    def test_serializer_with_real_approval_workflow(self):
        """Test serializer integration with actual approval workflow components."""
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

        stage = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Review Stage",
            name_ar="مرحلة المراجعة",
            created_by=user,
            is_active=True,
        )

        # Create workflow attachment
        attachment = attach_workflow_to_object(
            obj=user, workflow=workflow, user=user, auto_start=False
        )
        attachment.current_stage = stage
        attachment.current_pipeline = pipeline
        attachment.status = WorkflowAttachmentStatus.IN_PROGRESS
        attachment.save()

        # Update workflow active status
        workflow.update_active_status()

        # Create approval flow for integration
        content_type = ContentType.objects.get_for_model(User)
        from approval_workflow.models import ApprovalFlow

        approval_flow = ApprovalFlow.objects.create(
            content_type=content_type, object_id=str(user.pk)
        )

        # Create approval instance
        approval_instance = ApprovalInstance.objects.create(
            flow=approval_flow,
            step_number=1,
            status=ApprovalStatus.CURRENT,
            assigned_to=user,
            action_user=user,
            comment="Integration test setup",
        )

        # Test serializer with approval data
        mock_request = Mock()
        mock_request.user = user

        data = {
            "action": ApprovalStatus.APPROVED,
            "form_data": {
                "comment": "Integration test approval",
                "integration_test": True,
            },
        }

        serializer = WorkflowApprovalSerializer(
            data=data, object_instance=user, context={"request": mock_request}
        )

        assert serializer.is_valid()
        assert serializer.validated_data["action"] == ApprovalStatus.APPROVED
        assert serializer.validated_data["form_data"]["integration_test"] is True

        # The actual save would integrate with approval workflow
        # but we'll mock it to avoid complexity in test setup
        with patch(
            "django_workflow_engine.serializers.advance_flow"
        ) as mock_advance_flow:
            mock_advance_flow.return_value = user
            result = serializer.save()
            assert result == user

    def test_serializer_validation_with_workflow_states(self):
        """Test serializer validation considering workflow states."""
        user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # Test different workflow states
        valid_states = [WorkflowAttachmentStatus.IN_PROGRESS]
        invalid_states = [
            WorkflowAttachmentStatus.NOT_STARTED,
            WorkflowAttachmentStatus.COMPLETED,
            WorkflowAttachmentStatus.REJECTED,
            WorkflowAttachmentStatus.CANCELLED,
        ]

        # Test valid states (should pass validation)
        for state in valid_states:
            with patch(
                "django_workflow_engine.serializers.get_workflow_attachment"
            ) as mock_get:
                with patch(
                    "django_workflow_engine.serializers.get_current_approval_for_object"
                ) as mock_approval:
                    mock_attachment = Mock()
                    mock_attachment.status = state
                    mock_get.return_value = mock_attachment
                    mock_approval.return_value = Mock()  # Mock current approval exists

                    mock_request = Mock()
                    mock_request.user = user

                    data = {
                        "action": ApprovalStatus.APPROVED,
                        "form_data": {"state_test": str(state)},
                    }

                    serializer = WorkflowApprovalSerializer(
                        data=data,
                        object_instance=user,
                        context={"request": mock_request},
                    )

                    # Should be valid for in-progress workflows
                    assert serializer.is_valid(), f"Expected {state} to be valid"

        # Test invalid states (should fail validation)
        for state in invalid_states:
            with patch(
                "django_workflow_engine.serializers.get_workflow_attachment"
            ) as mock_get:
                mock_attachment = Mock()
                mock_attachment.status = state
                mock_get.return_value = mock_attachment

                mock_request = Mock()
                mock_request.user = user

                data = {
                    "action": ApprovalStatus.APPROVED,
                    "form_data": {"state_test": str(state)},
                }

                serializer = WorkflowApprovalSerializer(
                    data=data, object_instance=user, context={"request": mock_request}
                )

                # Should fail validation for non-in-progress workflows
                assert not serializer.is_valid(), f"Expected {state} to be invalid"
                assert "action" in serializer.errors
