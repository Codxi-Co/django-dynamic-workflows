"""Comprehensive tests for services.py to increase coverage."""

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType

import pytest

from django_workflow_engine.choices import (
    ActionType,
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
from django_workflow_engine.services import (
    attach_workflow_to_object,
    complete_workflow,
    create_pipeline,
    create_workflow,
    get_available_workflows_for_selection,
    get_detailed_workflow_data,
    get_workflow_attachment,
    move_to_next_stage,
    register_model_for_workflow,
    reject_workflow_stage,
    start_workflow_for_object,
    trigger_workflow_event,
)

User = get_user_model()


@pytest.mark.django_db
class TestWorkflowCreation:
    """Tests for workflow creation functions."""

    def test_create_workflow_with_pipelines(self):
        """Test creating workflow with pipelines and stages."""
        user = User.objects.create_user(username="test", email="test@test.com")

        pipelines_data = [
            {
                "name_en": "Pipeline 1",
                "name_ar": "خط 1",
                "order": 0,
                "number_of_stages": 2,
            }
        ]

        workflow = create_workflow(
            company=user,
            name_en="Test Workflow",
            name_ar="تدفق الاختبار",
            created_by=user,
            pipelines_data=pipelines_data,
        )

        assert workflow.name_en == "Test Workflow"
        assert workflow.pipelines.count() == 1
        pipeline = workflow.pipelines.first()
        assert pipeline.stages.count() == 2

    def test_create_pipeline_with_stages(self):
        """Test creating pipeline with auto-generated stages."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")

        pipeline_data = {
            "name_en": "Test Pipeline",
            "name_ar": "خط الاختبار",
            "number_of_stages": 3,
            "order": 0,
        }

        pipeline = create_pipeline(
            workflow=workflow, pipeline_data=pipeline_data, created_by=user
        )

        assert pipeline.name_en == "Test Pipeline"
        assert pipeline.stages.count() == 3


@pytest.mark.django_db
class TestWorkflowAttachment:
    """Tests for workflow attachment functions."""

    def test_attach_workflow_to_object_inactive_workflow(self):
        """Test attaching inactive workflow raises error."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(
            company=user,
            name_en="Test",
            name_ar="Test",
            status=WorkflowStatus.INACTIVE,
            is_active=False,
        )

        with pytest.raises(ValueError) as exc_info:
            attach_workflow_to_object(user, workflow, user)

        assert "not active" in str(exc_info.value)

    def test_attach_workflow_creates_attachment(self):
        """Test attaching workflow creates WorkflowAttachment."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(
            company=user,
            name_en="Test",
            name_ar="Test",
            status=WorkflowStatus.ACTIVE,
            is_active=True,
        )

        attachment = attach_workflow_to_object(
            user, workflow, user, auto_start=False, disable_clone=True
        )

        assert attachment is not None
        assert attachment.workflow == workflow
        assert attachment.status == WorkflowAttachmentStatus.NOT_STARTED

    def test_get_workflow_attachment(self):
        """Test getting workflow attachment for object."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")
        content_type = ContentType.objects.get_for_model(User)
        attachment = WorkflowAttachment.objects.create(
            workflow=workflow, content_type=content_type, object_id=str(user.pk)
        )

        result = get_workflow_attachment(user)

        assert result == attachment

    def test_get_workflow_attachment_not_found(self):
        """Test get_workflow_attachment returns None when not found."""
        user = User.objects.create_user(username="test", email="test@test.com")

        result = get_workflow_attachment(user)

        assert result is None


@pytest.mark.django_db
class TestWorkflowProgression:
    """Tests for workflow progression functions."""

    def test_start_workflow_already_started(self):
        """Test starting already started workflow raises error."""
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
            status=WorkflowAttachmentStatus.IN_PROGRESS,
        )

        with pytest.raises(ValueError) as exc_info:
            start_workflow_for_object(user, user)

        assert "already started" in str(exc_info.value).lower()

    def test_move_to_next_stage_not_in_progress(self):
        """Test move_to_next_stage fails when workflow not in progress."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")
        content_type = ContentType.objects.get_for_model(User)
        attachment = WorkflowAttachment.objects.create(
            workflow=workflow,
            content_type=content_type,
            object_id=str(user.pk),
            status=WorkflowAttachmentStatus.NOT_STARTED,
        )

        with pytest.raises(ValueError) as exc_info:
            move_to_next_stage(user, user)

        assert "not in progress" in str(exc_info.value).lower()

    def test_complete_workflow(self):
        """Test completing workflow updates status correctly."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")
        content_type = ContentType.objects.get_for_model(User)
        attachment = WorkflowAttachment.objects.create(
            workflow=workflow,
            content_type=content_type,
            object_id=str(user.pk),
            status=WorkflowAttachmentStatus.IN_PROGRESS,
        )

        result = complete_workflow(user, user)

        assert result.status == WorkflowAttachmentStatus.COMPLETED
        assert result.completed_at is not None
        assert result.current_stage is None
        assert result.current_pipeline is None

    def test_reject_workflow_stage(self):
        """Test rejecting workflow stage."""
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
            status=WorkflowAttachmentStatus.IN_PROGRESS,
            current_stage=stage,
        )

        result = reject_workflow_stage(user, stage, user, reason="Test rejection")

        assert result.status == WorkflowAttachmentStatus.REJECTED
        assert result.completed_at is not None


@pytest.mark.django_db
class TestWorkflowConfiguration:
    """Tests for workflow configuration functions."""

    def test_register_model_for_workflow(self):
        """Test registering model for workflow."""
        config = register_model_for_workflow(
            User, auto_start=True, status_field="status"
        )

        assert config is not None
        assert config.auto_start_workflow is True
        assert config.status_field == "status"

    def test_get_available_workflows_for_selection(self):
        """Test getting available workflows for selection."""
        user = User.objects.create_user(username="test", email="test@test.com")

        # Register User model for workflow
        register_model_for_workflow(User)

        workflow = WorkFlow.objects.create(
            company=user,
            name_en="Test Workflow",
            name_ar="تدفق الاختبار",
            status=WorkflowStatus.ACTIVE,
            is_active=True,
        )

        workflows = get_available_workflows_for_selection(User)

        assert isinstance(workflows, list)


@pytest.mark.django_db
class TestWorkflowActions:
    """Tests for workflow action functions."""

    def test_trigger_workflow_event_no_actions(self):
        """Test trigger_workflow_event with no actions configured."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")
        content_type = ContentType.objects.get_for_model(User)
        attachment = WorkflowAttachment.objects.create(
            workflow=workflow, content_type=content_type, object_id=str(user.pk)
        )

        # Should not raise error even with no actions
        results = trigger_workflow_event(
            attachment, ActionType.ON_WORKFLOW_START, user=user
        )

        assert isinstance(results, list)

    def test_trigger_workflow_event_with_invalid_function(self):
        """Test trigger_workflow_event with invalid function path."""
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
        )

        # Create action with invalid function path
        WorkflowAction.objects.create(
            action_type=ActionType.ON_WORKFLOW_START,
            function_path="invalid.module.function",
            stage=stage,
            is_active=True,
        )

        # Should handle error gracefully
        results = trigger_workflow_event(
            attachment, ActionType.ON_WORKFLOW_START, user=user
        )

        assert isinstance(results, list)


@pytest.mark.django_db
class TestWorkflowDetailedData:
    """Tests for workflow detailed data functions."""

    def test_get_detailed_workflow_data(self):
        """Test getting detailed workflow data."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")
        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=user,
            name_en="Pipeline",
            name_ar="Pipeline",
            order=0,
        )
        stage = Stage.objects.create(
            pipeline=pipeline,
            company=user,
            name_en="Stage",
            name_ar="Stage",
            stage_info={"approvals": [{"approval_type": "self-approved"}]},
            is_active=True,
            order=0,
        )

        data = get_detailed_workflow_data(workflow.id)

        assert data["id"] == workflow.id
        assert data["name_en"] == "Test"
        assert "pipelines" in data
        assert len(data["pipelines"]) == 1
        assert "stages" in data["pipelines"][0]
        assert len(data["pipelines"][0]["stages"]) == 1
