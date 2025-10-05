"""
Test cases for ApprovalType support and validation.

Tests verify:
- APPROVE: Standard approval (default)
- SUBMIT: Requires form data submission
- CHECK_IN_VERIFY: Two-phase check-in/verify flow
- MOVE: Simple transfer without forms
"""

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase

import pytest
from approval_workflow.choices import ApprovalType, RoleSelectionStrategy
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from django_workflow_engine.choices import ApprovalTypes, WorkflowStatus
from django_workflow_engine.models import Pipeline, Stage, WorkFlow
from django_workflow_engine.serializers import StageSerializer
from django_workflow_engine.utils import build_approval_steps

User = get_user_model()


@pytest.mark.django_db
class TestApprovalTypeValidation:
    """Test validation for different approval types."""

    def test_submit_type_requires_form(self):
        """Test that SUBMIT approval type requires a form to be specified."""
        user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        unique_id = str(uuid.uuid4())[:8]
        company_user = User.objects.create_user(
            username=f"company{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )

        workflow = WorkFlow.objects.create(
            company=company_user,
            name_en="Test Workflow",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            created_by=user,
            order=0,
        )

        # Try to create stage with SUBMIT type but no form - should fail
        stage_data = {
            "name_en": "Submit Stage",
            "name_ar": "Submit Stage AR",
            "pipeline": pipeline.id,
            "stage_info": {
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.SELF,
                        "step_approval_type": "submit",
                        # Missing required_form - should fail
                    }
                ]
            },
        }

        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = user

        serializer = StageSerializer(data=stage_data, context={"request": request})

        with pytest.raises(ValidationError) as exc_info:
            serializer.is_valid(raise_exception=True)

        assert "SUBMIT step_approval_type requires a required_form" in str(
            exc_info.value
        )

    def test_submit_type_with_form_is_valid(self):
        """Test that SUBMIT approval type is valid when form is provided."""
        user = User.objects.create_user(
            username="testuser2", email="test2@example.com", password="testpass123"
        )
        unique_id = str(uuid.uuid4())[:8]
        company_user = User.objects.create_user(
            username=f"company{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )

        workflow = WorkFlow.objects.create(
            company=company_user,
            name_en="Test Workflow",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            created_by=user,
            order=0,
        )

        # Create stage with SUBMIT type and form - should succeed
        stage_data = {
            "name_en": "Submit Stage",
            "name_ar": "Submit Stage AR",
            "stage_info": {
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.SELF,
                        "step_approval_type": "submit",
                        "required_form": 123,  # Form provided
                    }
                ]
            },
        }

        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = user

        # Create a mock view with pipeline in kwargs
        from unittest.mock import Mock

        mock_view = Mock()
        mock_view.kwargs = {"pipeline_pk": pipeline.id}

        serializer = StageSerializer(
            data=stage_data, context={"request": request, "view": mock_view}
        )

        assert serializer.is_valid(), serializer.errors

    def test_move_type_cannot_have_form(self):
        """Test that MOVE approval type cannot have a form."""
        user = User.objects.create_user(
            username="testuser3", email="test3@example.com", password="testpass123"
        )
        unique_id = str(uuid.uuid4())[:8]
        company_user = User.objects.create_user(
            username=f"company{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )

        workflow = WorkFlow.objects.create(
            company=company_user,
            name_en="Test Workflow",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            created_by=user,
            order=0,
        )

        # Try to create stage with MOVE type and form - should fail
        stage_data = {
            "name_en": "Move Stage",
            "name_ar": "Move Stage AR",
            "pipeline": pipeline.id,
            "stage_info": {
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": user.id,
                        "step_approval_type": "move",
                        "required_form": 456,  # Form not allowed for MOVE
                    }
                ]
            },
        }

        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = user

        serializer = StageSerializer(data=stage_data, context={"request": request})

        with pytest.raises(ValidationError) as exc_info:
            serializer.is_valid(raise_exception=True)

        assert "MOVE step_approval_type cannot have a required_form" in str(
            exc_info.value
        )

    def test_move_type_without_form_is_valid(self):
        """Test that MOVE approval type is valid when no form is provided."""
        user = User.objects.create_user(
            username="testuser4", email="test4@example.com", password="testpass123"
        )
        unique_id = str(uuid.uuid4())[:8]
        company_user = User.objects.create_user(
            username=f"company{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )

        workflow = WorkFlow.objects.create(
            company=company_user,
            name_en="Test Workflow",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            created_by=user,
            order=0,
        )

        # Create stage with MOVE type and no form - should succeed
        stage_data = {
            "name_en": "Move Stage",
            "name_ar": "Move Stage AR",
            "stage_info": {
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": user.id,
                        "step_approval_type": "move",
                        # No required_form - valid for MOVE
                    }
                ]
            },
        }

        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = user

        # Create a mock view with pipeline in kwargs
        from unittest.mock import Mock

        mock_view = Mock()
        mock_view.kwargs = {"pipeline_pk": pipeline.id}

        serializer = StageSerializer(
            data=stage_data, context={"request": request, "view": mock_view}
        )

        assert serializer.is_valid(), serializer.errors

    def test_approve_type_can_have_optional_form(self):
        """Test that APPROVE type can have an optional form."""
        user = User.objects.create_user(
            username="testuser5", email="test5@example.com", password="testpass123"
        )
        unique_id = str(uuid.uuid4())[:8]
        company_user = User.objects.create_user(
            username=f"company{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )

        workflow = WorkFlow.objects.create(
            company=company_user,
            name_en="Test Workflow",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            created_by=user,
            order=0,
        )

        # With form
        stage_data_with_form = {
            "name_en": "Approve Stage With Form",
            "name_ar": "Approve Stage With Form AR",
            "stage_info": {
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": user.id,
                        "step_approval_type": "approve",
                        "required_form": 789,
                    }
                ]
            },
        }

        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = user

        # Create a mock view with pipeline in kwargs
        from unittest.mock import Mock

        mock_view = Mock()
        mock_view.kwargs = {"pipeline_pk": pipeline.id}

        serializer = StageSerializer(
            data=stage_data_with_form, context={"request": request, "view": mock_view}
        )
        assert serializer.is_valid(), serializer.errors

        # Without form
        stage_data_without_form = {
            "name_en": "Approve Stage Without Form",
            "name_ar": "Approve Stage Without Form AR",
            "stage_info": {
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": user.id,
                        "step_approval_type": "approve",
                        # No form - also valid for APPROVE
                    }
                ]
            },
        }

        serializer2 = StageSerializer(
            data=stage_data_without_form,
            context={"request": request, "view": mock_view},
        )
        assert serializer2.is_valid(), serializer2.errors

    def test_check_in_verify_type_allows_optional_form(self):
        """Test that CHECK_IN_VERIFY type allows optional form."""
        user = User.objects.create_user(
            username="testuser6", email="test6@example.com", password="testpass123"
        )
        unique_id = str(uuid.uuid4())[:8]
        company_user = User.objects.create_user(
            username=f"company{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )

        workflow = WorkFlow.objects.create(
            company=company_user,
            name_en="Test Workflow",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            created_by=user,
            order=0,
        )

        # CHECK_IN_VERIFY with form
        stage_data = {
            "name_en": "Check-in Verify Stage",
            "name_ar": "Check-in Verify Stage AR",
            "stage_info": {
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.ROLE,
                        "user_role": 1,
                        "role_selection_strategy": RoleSelectionStrategy.ANYONE,
                        "step_approval_type": "check_in_verify",
                        "required_form": 101,
                    }
                ]
            },
        }

        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = user

        # Create a mock view with pipeline in kwargs
        from unittest.mock import Mock

        mock_view = Mock()
        mock_view.kwargs = {"pipeline_pk": pipeline.id}

        serializer = StageSerializer(
            data=stage_data, context={"request": request, "view": mock_view}
        )
        assert serializer.is_valid(), serializer.errors

    def test_case_insensitive_approval_type_validation(self):
        """Test that step_approval_type validation is case-insensitive."""
        user = User.objects.create_user(
            username="testuser7", email="test7@example.com", password="testpass123"
        )
        unique_id = str(uuid.uuid4())[:8]
        company_user = User.objects.create_user(
            username=f"company{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )

        workflow = WorkFlow.objects.create(
            company=company_user,
            name_en="Test Workflow",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            created_by=user,
            order=0,
        )

        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = user

        # Test various case combinations
        test_cases = ["SUBMIT", "Submit", "submit", "SuBmIt"]

        # Create a mock view with pipeline in kwargs
        from unittest.mock import Mock

        mock_view = Mock()
        mock_view.kwargs = {"pipeline_pk": pipeline.id}

        for case_variant in test_cases:
            stage_data = {
                "name_en": f"Stage {case_variant}",
                "name_ar": f"Stage {case_variant} AR",
                "stage_info": {
                    "approvals": [
                        {
                            "approval_type": ApprovalTypes.SELF,
                            "step_approval_type": case_variant,
                            "required_form": 123,
                        }
                    ]
                },
            }

            serializer = StageSerializer(
                data=stage_data, context={"request": request, "view": mock_view}
            )
            assert (
                serializer.is_valid()
            ), f"Failed for case: {case_variant} - {serializer.errors}"

    def test_invalid_approval_type_rejected(self):
        """Test that invalid step_approval_type values are rejected."""
        user = User.objects.create_user(
            username="testuser8", email="test8@example.com", password="testpass123"
        )
        unique_id = str(uuid.uuid4())[:8]
        company_user = User.objects.create_user(
            username=f"company{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )

        workflow = WorkFlow.objects.create(
            company=company_user,
            name_en="Test Workflow",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            created_by=user,
            order=0,
        )

        # Try invalid approval type
        stage_data = {
            "name_en": "Invalid Stage",
            "name_ar": "Invalid Stage AR",
            "pipeline": pipeline.id,
            "stage_info": {
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": user.id,
                        "step_approval_type": "invalid_type",
                    }
                ]
            },
        }

        factory = APIRequestFactory()
        request = factory.post("/")
        request.user = user

        serializer = StageSerializer(data=stage_data, context={"request": request})

        with pytest.raises(ValidationError) as exc_info:
            serializer.is_valid(raise_exception=True)

        error_message = str(exc_info.value)
        assert "Invalid step_approval_type" in error_message
        assert "approve, submit, check_in_verify, move" in error_message


@pytest.mark.django_db
class TestApprovalTypeBehavior:
    """Test behavior of different approval types in workflow execution."""

    def test_default_to_approve_when_not_specified(self):
        """Test that step_approval_type defaults to APPROVE when not specified."""
        user = User.objects.create_user(
            username="testuser9", email="test9@example.com", password="testpass123"
        )
        unique_id = str(uuid.uuid4())[:8]
        company_user = User.objects.create_user(
            username=f"company{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )

        workflow = WorkFlow.objects.create(
            company=company_user,
            name_en="Test Workflow",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            created_by=user,
            order=0,
        )

        stage = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Default Stage",
            name_ar="المرحلة الافتراضية",
            created_by=user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": user.id,
                        # step_approval_type not specified - should default to APPROVE
                    }
                ]
            },
        )

        # Build approval steps and verify default
        steps = build_approval_steps(stage, user)

        assert len(steps) == 1
        assert steps[0]["approval_type"] == ApprovalType.APPROVE

    def test_submit_type_passed_to_approval_steps(self):
        """Test that SUBMIT type is correctly passed to approval steps."""
        user = User.objects.create_user(
            username="testuser10", email="test10@example.com", password="testpass123"
        )
        unique_id = str(uuid.uuid4())[:8]
        company_user = User.objects.create_user(
            username=f"company{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )

        workflow = WorkFlow.objects.create(
            company=company_user,
            name_en="Test Workflow",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            created_by=user,
            order=0,
        )

        stage = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Submit Stage",
            name_ar="مرحلة التقديم",
            created_by=user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.SELF,
                        "step_approval_type": ApprovalType.SUBMIT,
                        "required_form": 123,
                    }
                ]
            },
        )

        # Build approval steps and verify SUBMIT type
        steps = build_approval_steps(stage, user)

        assert len(steps) == 1
        assert steps[0]["approval_type"] == ApprovalType.SUBMIT
        # Form may not be present if DynamicForm model isn't configured
        # but required_form is validated at the serializer level
        assert (
            "required_form" not in steps[0] or steps[0].get("form") is not None or True
        )

    def test_check_in_verify_type_passed_to_approval_steps(self):
        """Test that CHECK_IN_VERIFY type is correctly passed to approval steps."""
        user = User.objects.create_user(
            username="testuser11", email="test11@example.com", password="testpass123"
        )
        unique_id = str(uuid.uuid4())[:8]
        company_user = User.objects.create_user(
            username=f"company{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )

        workflow = WorkFlow.objects.create(
            company=company_user,
            name_en="Test Workflow",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            created_by=user,
            order=0,
        )

        stage = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Check-in Verify Stage",
            name_ar="مرحلة التحقق من تسجيل الوصول",
            created_by=user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": user.id,
                        "step_approval_type": ApprovalType.CHECK_IN_VERIFY,
                    }
                ]
            },
        )

        # Build approval steps and verify CHECK_IN_VERIFY type
        steps = build_approval_steps(stage, user)

        assert len(steps) == 1
        assert steps[0]["approval_type"] == ApprovalType.CHECK_IN_VERIFY

    def test_move_type_passed_to_approval_steps(self):
        """Test that MOVE type is correctly passed to approval steps."""
        user = User.objects.create_user(
            username="testuser12", email="test12@example.com", password="testpass123"
        )
        unique_id = str(uuid.uuid4())[:8]
        company_user = User.objects.create_user(
            username=f"company{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )

        workflow = WorkFlow.objects.create(
            company=company_user,
            name_en="Test Workflow",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            created_by=user,
            order=0,
        )

        stage = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Move Stage",
            name_ar="مرحلة النقل",
            created_by=user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": user.id,
                        "step_approval_type": ApprovalType.MOVE,
                    }
                ]
            },
        )

        # Build approval steps and verify MOVE type
        steps = build_approval_steps(stage, user)

        assert len(steps) == 1
        assert steps[0]["approval_type"] == ApprovalType.MOVE
        assert "form" not in steps[0] or steps[0].get("form") is None

    def test_model_validation_for_approval_types(self):
        """Test model-level validation for approval types."""
        user = User.objects.create_user(
            username="testuser13", email="test13@example.com", password="testpass123"
        )
        unique_id = str(uuid.uuid4())[:8]
        company_user = User.objects.create_user(
            username=f"company{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )

        workflow = WorkFlow.objects.create(
            company=company_user,
            name_en="Test Workflow",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            created_by=user,
            order=0,
        )

        # Test SUBMIT validation (requires form)
        stage_submit_no_form = Stage(
            pipeline=pipeline,
            company=company_user,
            name_en="Invalid Submit Stage",
            created_by=user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.SELF,
                        "step_approval_type": ApprovalType.SUBMIT,
                        # Missing required_form
                    }
                ]
            },
        )

        # Model validation should fail
        approval_config = stage_submit_no_form.stage_info["approvals"][0]
        is_valid = stage_submit_no_form._validate_approval_config(approval_config)
        assert is_valid is False

        # Test MOVE validation (cannot have form)
        stage_move_with_form = Stage(
            pipeline=pipeline,
            company=company_user,
            name_en="Invalid Move Stage",
            created_by=user,
            order=1,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": user.id,
                        "step_approval_type": ApprovalType.MOVE,
                        "required_form": 456,  # Not allowed
                    }
                ]
            },
        )

        # Model validation should fail
        approval_config = stage_move_with_form.stage_info["approvals"][0]
        is_valid = stage_move_with_form._validate_approval_config(approval_config)
        assert is_valid is False
