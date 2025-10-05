"""Comprehensive tests for models.py to increase coverage."""

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

import pytest

from django_workflow_engine.choices import (
    ActionType,
    ApprovalTypes,
    WorkflowAttachmentStatus,
    WorkflowStatus,
)
from django_workflow_engine.models import (
    Pipeline,
    Stage,
    WorkFlow,
    WorkflowAction,
    WorkflowAttachment,
    WorkflowConfiguration,
)

User = get_user_model()


@pytest.mark.django_db
class TestWorkFlowModel:
    """Tests for WorkFlow model methods."""

    def test_validate_completeness_no_pipelines(self):
        """Test validation fails when workflow has no pipelines."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(
            company=user, name_en="Test", name_ar="Test", status=WorkflowStatus.ACTIVE
        )

        is_valid, message = workflow.validate_completeness()

        assert is_valid is False
        assert "at least one pipeline" in message

    def test_validate_completeness_pipeline_no_stages(self):
        """Test validation fails when pipeline has no stages."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(
            company=user, name_en="Test", name_ar="Test", status=WorkflowStatus.ACTIVE
        )
        Pipeline.objects.create(
            workflow=workflow, company=user, name_en="Pipeline", name_ar="Pipeline"
        )

        is_valid, message = workflow.validate_completeness()

        assert is_valid is False
        assert "at least one stage" in message

    def test_validate_completeness_stage_not_complete(self):
        """Test validation fails when stage is not complete."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(
            company=user, name_en="Test", name_ar="Test", status=WorkflowStatus.ACTIVE
        )
        pipeline = Pipeline.objects.create(
            workflow=workflow, company=user, name_en="Pipeline", name_ar="Pipeline"
        )
        # Stage without approvals
        Stage.objects.create(
            pipeline=pipeline,
            company=user,
            name_en="Stage",
            name_ar="Stage",
            stage_info={},
            is_active=False,
        )

        is_valid, message = workflow.validate_completeness()

        assert is_valid is False
        assert "not properly configured" in message

    def test_validate_completeness_success(self):
        """Test validation succeeds when workflow is properly configured."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(
            company=user, name_en="Test", name_ar="Test", status=WorkflowStatus.ACTIVE
        )
        pipeline = Pipeline.objects.create(
            workflow=workflow, company=user, name_en="Pipeline", name_ar="Pipeline"
        )
        Stage.objects.create(
            pipeline=pipeline,
            company=user,
            name_en="Stage",
            name_ar="Stage",
            stage_info={"approvals": [{"approval_type": "self-approved"}]},
            is_active=True,
        )

        is_valid, message = workflow.validate_completeness()

        assert is_valid is True
        assert "complete and valid" in message

    def test_update_active_status(self):
        """Test update_active_status updates is_active correctly."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(
            company=user,
            name_en="Test",
            name_ar="Test",
            status=WorkflowStatus.ACTIVE,
            is_active=False,
        )
        pipeline = Pipeline.objects.create(
            workflow=workflow, company=user, name_en="Pipeline", name_ar="Pipeline"
        )
        Stage.objects.create(
            pipeline=pipeline,
            company=user,
            name_en="Stage",
            name_ar="Stage",
            stage_info={"approvals": [{"approval_type": "self-approved"}]},
            is_active=True,
        )

        is_active, message = workflow.update_active_status()

        assert is_active is True
        workflow.refresh_from_db()
        assert workflow.is_active is True

    def test_completion_status_property(self):
        """Test completion_status property returns correct data."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(
            company=user, name_en="Test", name_ar="Test", status=WorkflowStatus.ACTIVE
        )

        status = workflow.completion_status

        assert "is_complete" in status
        assert "message" in status
        assert "is_active" in status
        assert "can_be_activated" in status


@pytest.mark.django_db
class TestStageModel:
    """Tests for Stage model validation."""

    def test_is_complete_no_stage_info(self):
        """Test is_complete returns False when stage_info is missing."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")
        pipeline = Pipeline.objects.create(
            workflow=workflow, company=user, name_en="Pipeline", name_ar="Pipeline"
        )
        stage = Stage.objects.create(
            pipeline=pipeline,
            company=user,
            name_en="Stage",
            name_ar="Stage",
            stage_info=None,
        )

        assert stage.is_complete() is False

    def test_is_complete_no_approvals(self):
        """Test is_complete returns False when no approvals configured."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")
        pipeline = Pipeline.objects.create(
            workflow=workflow, company=user, name_en="Pipeline", name_ar="Pipeline"
        )
        stage = Stage.objects.create(
            pipeline=pipeline,
            company=user,
            name_en="Stage",
            name_ar="Stage",
            stage_info={"approvals": []},
            is_active=True,
        )

        assert stage.is_complete() is False

    def test_validate_approval_config_invalid_type(self):
        """Test _validate_approval_config with invalid approval type."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")
        pipeline = Pipeline.objects.create(
            workflow=workflow, company=user, name_en="Pipeline", name_ar="Pipeline"
        )
        stage = Stage.objects.create(
            pipeline=pipeline,
            company=user,
            name_en="Stage",
            name_ar="Stage",
            stage_info={"approvals": [{"approval_type": "invalid"}]},
        )

        is_valid = stage._validate_approval_config({"approval_type": "invalid"})

        assert is_valid is False

    def test_validate_approval_config_role_missing_user_role(self):
        """Test validation fails for ROLE type without user_role."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")
        pipeline = Pipeline.objects.create(
            workflow=workflow, company=user, name_en="Pipeline", name_ar="Pipeline"
        )
        stage = Stage(
            pipeline=pipeline,
            company=user,
            name_en="Stage",
            name_ar="Stage",
            stage_info={"approvals": [{"approval_type": ApprovalTypes.ROLE}]},
        )

        is_valid = stage._validate_approval_config(
            {"approval_type": ApprovalTypes.ROLE}
        )

        assert is_valid is False

    def test_validate_approval_config_user_missing_approval_user(self):
        """Test validation fails for USER type without approval_user."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")
        pipeline = Pipeline.objects.create(
            workflow=workflow, company=user, name_en="Pipeline", name_ar="Pipeline"
        )
        stage = Stage(
            pipeline=pipeline,
            company=user,
            name_en="Stage",
            name_ar="Stage",
            stage_info={"approvals": [{"approval_type": ApprovalTypes.USER}]},
        )

        is_valid = stage._validate_approval_config(
            {"approval_type": ApprovalTypes.USER}
        )

        assert is_valid is False


@pytest.mark.django_db
class TestWorkflowAttachmentModel:
    """Tests for WorkflowAttachment model."""

    def test_progress_percentage_not_started(self):
        """Test progress_percentage returns 0 when not started."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")
        content_type = ContentType.objects.get_for_model(User)

        attachment = WorkflowAttachment.objects.create(
            workflow=workflow,
            content_type=content_type,
            object_id=str(user.pk),
            status=WorkflowAttachmentStatus.NOT_STARTED,
        )

        assert attachment.progress_percentage == 0

    def test_progress_percentage_completed(self):
        """Test progress_percentage returns 100 when completed."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")
        pipeline = Pipeline.objects.create(
            workflow=workflow, company=user, name_en="Pipeline", name_ar="Pipeline"
        )
        stage = Stage.objects.create(
            pipeline=pipeline,
            company=user,
            name_en="Stage",
            name_ar="Stage",
            is_active=True,
        )
        content_type = ContentType.objects.get_for_model(User)

        attachment = WorkflowAttachment.objects.create(
            workflow=workflow,
            content_type=content_type,
            object_id=str(user.pk),
            status=WorkflowAttachmentStatus.COMPLETED,
            current_stage=stage,
            current_pipeline=pipeline,
        )

        assert attachment.progress_percentage == 100

    def test_progress_percentage_rejected(self):
        """Test progress_percentage returns 0 when rejected."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")
        content_type = ContentType.objects.get_for_model(User)

        attachment = WorkflowAttachment.objects.create(
            workflow=workflow,
            content_type=content_type,
            object_id=str(user.pk),
            status=WorkflowAttachmentStatus.REJECTED,
        )

        assert attachment.progress_percentage == 0

    def test_next_stage_no_current_stage(self):
        """Test next_stage returns first stage when no current stage."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")
        pipeline = Pipeline.objects.create(
            workflow=workflow, company=user, name_en="Pipeline", name_ar="Pipeline"
        )
        stage = Stage.objects.create(
            pipeline=pipeline,
            company=user,
            name_en="Stage",
            name_ar="Stage",
            stage_info={"approvals": [{"approval_type": "self-approved"}]},
            is_active=True,
        )
        content_type = ContentType.objects.get_for_model(User)

        attachment = WorkflowAttachment.objects.create(
            workflow=workflow,
            content_type=content_type,
            object_id=str(user.pk),
        )

        assert attachment.next_stage == stage

    def test_get_progress_info(self):
        """Test get_progress_info returns complete information."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")
        pipeline = Pipeline.objects.create(
            workflow=workflow, company=user, name_en="Pipeline", name_ar="Pipeline"
        )
        stage = Stage.objects.create(
            pipeline=pipeline,
            company=user,
            name_en="Stage",
            name_ar="Stage",
            stage_info={"approvals": [{"approval_type": "self-approved"}]},
            is_active=True,
        )
        content_type = ContentType.objects.get_for_model(User)

        attachment = WorkflowAttachment.objects.create(
            workflow=workflow,
            content_type=content_type,
            object_id=str(user.pk),
            current_stage=stage,
            current_pipeline=pipeline,
            status=WorkflowAttachmentStatus.IN_PROGRESS,
        )

        info = attachment.get_progress_info()

        assert "current_stage" in info
        assert "current_pipeline" in info
        assert "status" in info
        assert "progress_percentage" in info
        assert info["current_stage"] == "Stage"


@pytest.mark.django_db
class TestWorkflowActionModel:
    """Tests for WorkflowAction model."""

    def test_clean_no_scope(self):
        """Test clean raises ValidationError when no scope is set."""
        user = User.objects.create_user(username="test", email="test@test.com")

        action = WorkflowAction(
            action_type=ActionType.AFTER_APPROVE,
            function_path="test.function",
        )

        with pytest.raises(ValidationError) as exc_info:
            action.clean()

        assert "Exactly one of workflow, pipeline, or stage must be set" in str(
            exc_info.value
        )

    def test_clean_multiple_scopes(self):
        """Test clean raises ValidationError when multiple scopes are set."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")
        pipeline = Pipeline.objects.create(
            workflow=workflow, company=user, name_en="Pipeline", name_ar="Pipeline"
        )

        action = WorkflowAction(
            action_type=ActionType.AFTER_APPROVE,
            function_path="test.function",
            workflow=workflow,
            pipeline=pipeline,  # Two scopes - invalid
        )

        with pytest.raises(ValidationError) as exc_info:
            action.clean()

        assert "Exactly one of workflow, pipeline, or stage must be set" in str(
            exc_info.value
        )

    def test_scope_level_property(self):
        """Test scope_level property returns correct level."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")
        pipeline = Pipeline.objects.create(
            workflow=workflow, company=user, name_en="Pipeline", name_ar="Pipeline"
        )
        stage = Stage.objects.create(
            pipeline=pipeline,
            company=user,
            name_en="Stage",
            name_ar="Stage",
            stage_info={"approvals": [{"approval_type": "self-approved"}]},
            is_active=True,
        )

        # Test workflow level
        action1 = WorkflowAction(
            action_type=ActionType.AFTER_APPROVE,
            function_path="test.function",
            workflow=workflow,
        )
        assert action1.scope_level == "workflow"

        # Test pipeline level
        action2 = WorkflowAction(
            action_type=ActionType.AFTER_APPROVE,
            function_path="test.function",
            pipeline=pipeline,
        )
        assert action2.scope_level == "pipeline"

        # Test stage level
        action3 = WorkflowAction(
            action_type=ActionType.AFTER_APPROVE,
            function_path="test.function",
            stage=stage,
        )
        assert action3.scope_level == "stage"

    def test_scope_object_property(self):
        """Test scope_object property returns correct object."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")

        action = WorkflowAction(
            action_type=ActionType.AFTER_APPROVE,
            function_path="test.function",
            workflow=workflow,
        )

        assert action.scope_object == workflow


@pytest.mark.django_db
class TestPipelineModel:
    """Tests for Pipeline model."""

    def test_department_name_with_name_attribute(self):
        """Test department_name returns name from department object."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")

        # Create pipeline with department (using User as mock department)
        content_type = ContentType.objects.get_for_model(User)
        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=user,
            name_en="Pipeline",
            name_ar="Pipeline",
            department_content_type=content_type,
            department_id=user.id,
        )

        # User has username which will be used
        dept_name = pipeline.department_name
        assert dept_name is not None

    def test_department_name_no_department(self):
        """Test department_name returns None when no department."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")
        pipeline = Pipeline.objects.create(
            workflow=workflow, company=user, name_en="Pipeline", name_ar="Pipeline"
        )

        assert pipeline.department_name is None


@pytest.mark.django_db
class TestWorkflowConfiguration:
    """Tests for WorkflowConfiguration model."""

    def test_str_representation(self):
        """Test __str__ returns correct format."""
        user = User.objects.create_user(username="test", email="test@test.com")
        content_type = ContentType.objects.get_for_model(User)

        config = WorkflowConfiguration.objects.create(
            content_type=content_type, is_enabled=True
        )

        str_repr = str(config)
        assert "auth.user" in str_repr.lower() or "user" in str_repr.lower()
