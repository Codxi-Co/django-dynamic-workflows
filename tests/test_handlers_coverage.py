"""Comprehensive tests for handlers.py to increase coverage."""

from unittest.mock import MagicMock, Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType

import pytest

from django_workflow_engine.choices import (
    ActionType,
    WorkflowAttachmentStatus,
    WorkflowStatus,
)
from django_workflow_engine.handlers import (
    ApprovalStepBuilder,
    BaseApprovalHandler,
    WorkflowApprovalHandler,
    WorkflowProgressManager,
    get_handler_for_instance,
    get_workflow_handler_for_object,
)
from django_workflow_engine.models import Pipeline, Stage, WorkFlow, WorkflowAttachment

User = get_user_model()


@pytest.mark.django_db
class TestBaseApprovalHandler:
    """Tests for BaseApprovalHandler."""

    def test_before_approve(self):
        """Test before_approve hook method."""
        handler = BaseApprovalHandler()
        mock_instance = Mock()
        mock_instance.flow.id = 1
        mock_instance.step_number = 1

        # Should execute without error
        handler.before_approve(mock_instance)

    def test_after_approve(self):
        """Test after_approve hook method."""
        handler = BaseApprovalHandler()
        mock_instance = Mock()
        mock_instance.flow.id = 1
        mock_instance.step_number = 1

        handler.after_approve(mock_instance)

    def test_on_final_approve(self):
        """Test on_final_approve hook method."""
        handler = BaseApprovalHandler()
        mock_instance = Mock()
        mock_instance.flow.id = 1
        mock_instance.step_number = 1

        handler.on_final_approve(mock_instance)

    def test_before_reject(self):
        """Test before_reject hook method."""
        handler = BaseApprovalHandler()
        mock_instance = Mock()
        mock_instance.flow.id = 1
        mock_instance.step_number = 1

        handler.before_reject(mock_instance)

    def test_after_reject(self):
        """Test after_reject hook method."""
        handler = BaseApprovalHandler()
        mock_instance = Mock()
        mock_instance.flow.id = 1
        mock_instance.step_number = 1

        handler.after_reject(mock_instance)

    def test_after_resubmission(self):
        """Test after_resubmission hook method."""
        handler = BaseApprovalHandler()
        mock_instance = Mock()
        mock_instance.flow.id = 1
        mock_instance.step_number = 1

        handler.after_resubmission(mock_instance)

    def test_after_delegate(self):
        """Test after_delegate hook method."""
        handler = BaseApprovalHandler()
        mock_instance = Mock()
        mock_instance.flow.id = 1
        mock_instance.step_number = 1

        handler.after_delegate(mock_instance)


@pytest.mark.django_db
class TestGetHandlerForInstance:
    """Tests for get_handler_for_instance function."""

    def test_get_handler_no_target_object(self):
        """Test get_handler_for_instance with no target object."""
        mock_instance = Mock()
        mock_instance.flow.target = None

        result = get_handler_for_instance(mock_instance)

        assert result is None

    def test_get_handler_with_workflow_attachment(self):
        """Test get_handler_for_instance returns WorkflowApprovalHandler."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")
        content_type = ContentType.objects.get_for_model(User)
        WorkflowAttachment.objects.create(
            workflow=workflow, content_type=content_type, object_id=str(user.pk)
        )

        mock_instance = Mock()
        mock_instance.flow.target = user

        handler = get_handler_for_instance(mock_instance)

        assert handler is not None
        assert isinstance(handler, WorkflowApprovalHandler)

    def test_get_handler_without_workflow_attachment(self):
        """Test get_handler_for_instance without workflow attachment."""
        user = User.objects.create_user(username="test2", email="test2@test.com")

        mock_instance = Mock()
        mock_instance.flow.target = user

        handler = get_handler_for_instance(mock_instance)

        # Should return None for objects without workflow attachment
        assert handler is None


@pytest.mark.django_db
class TestApprovalStepBuilder:
    """Tests for ApprovalStepBuilder."""

    def test_build_steps(self):
        """Test building approval steps from stage."""
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
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": user.id}]
            },
            is_active=True,
        )

        builder = ApprovalStepBuilder(stage, user)
        steps = builder.build_steps()

        assert isinstance(steps, list)


@pytest.mark.django_db
class TestWorkflowApprovalHandler:
    """Tests for WorkflowApprovalHandler."""

    def test_init(self):
        """Test handler initialization."""
        user = User.objects.create_user(username="test", email="test@test.com")
        handler = WorkflowApprovalHandler(user)

        assert handler.instance == user

    def test_after_approve(self):
        """Test after_approve method."""
        user = User.objects.create_user(username="test", email="test@test.com")
        handler = WorkflowApprovalHandler(user)
        mock_instance = Mock()

        # Should execute without error
        handler.after_approve(mock_instance)

    @patch("django_workflow_engine.services.move_to_next_stage")
    @patch("django_workflow_engine.services.trigger_workflow_event")
    def test_on_final_approve(self, mock_trigger, mock_move):
        """Test on_final_approve progresses workflow."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")
        content_type = ContentType.objects.get_for_model(User)
        attachment = WorkflowAttachment.objects.create(
            workflow=workflow,
            content_type=content_type,
            object_id=str(user.pk),
            status=WorkflowAttachmentStatus.IN_PROGRESS,
        )

        mock_move.return_value = attachment

        handler = WorkflowApprovalHandler(user)
        mock_approval = Mock()
        mock_approval.action_user = user

        handler.on_final_approve(mock_approval)

        # Verify move_to_next_stage was called
        mock_move.assert_called_once_with(user)
        # Verify trigger_workflow_event was called
        assert mock_trigger.called

    @patch("django_workflow_engine.services.reject_workflow_stage")
    @patch("django_workflow_engine.services.trigger_workflow_event")
    def test_after_reject(self, mock_trigger, mock_reject):
        """Test after_reject handles rejection."""
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
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": user.id}]
            },
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

        handler = WorkflowApprovalHandler(user)
        mock_approval = Mock()
        mock_approval.comment = "Test rejection"
        mock_approval.action_user = user

        handler.after_reject(mock_approval)

        # Verify reject_workflow_stage was called
        assert mock_reject.called

    @patch("django_workflow_engine.services.trigger_workflow_event")
    def test_after_resubmission(self, mock_trigger):
        """Test after_resubmission handles resubmission."""
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
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": user.id}]
            },
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

        handler = WorkflowApprovalHandler(user)
        mock_approval = Mock()
        mock_approval.comment = "Please resubmit"
        mock_approval.action_user = user
        mock_approval.extra_fields = {"resubmission_stage_id": stage.id}

        handler.after_resubmission(mock_approval)

        # Verify attachment was updated
        attachment.refresh_from_db()
        assert attachment.current_stage == stage

    @patch("django_workflow_engine.services.trigger_workflow_event")
    def test_after_delegate(self, mock_trigger):
        """Test after_delegate handles delegation."""
        user = User.objects.create_user(username="test", email="test@test.com")
        delegate = User.objects.create_user(
            username="delegate", email="delegate@test.com"
        )
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")
        content_type = ContentType.objects.get_for_model(User)
        attachment = WorkflowAttachment.objects.create(
            workflow=workflow,
            content_type=content_type,
            object_id=str(user.pk),
            status=WorkflowAttachmentStatus.IN_PROGRESS,
        )

        handler = WorkflowApprovalHandler(user)
        mock_approval = Mock()
        mock_approval.assigned_to = delegate
        mock_approval.comment = "Delegating to you"
        mock_approval.action_user = user

        handler.after_delegate(mock_approval)

        # Verify trigger_workflow_event was called
        assert mock_trigger.called


@pytest.mark.django_db
class TestGetWorkflowHandlerForObject:
    """Tests for get_workflow_handler_for_object."""

    def test_get_handler_with_attachment(self):
        """Test getting handler for object with workflow attachment."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(company=user, name_en="Test", name_ar="Test")
        content_type = ContentType.objects.get_for_model(User)
        WorkflowAttachment.objects.create(
            workflow=workflow, content_type=content_type, object_id=str(user.pk)
        )

        handler = get_workflow_handler_for_object(user)

        assert handler is not None
        assert isinstance(handler, WorkflowApprovalHandler)

    def test_get_handler_without_attachment(self):
        """Test getting handler for object without workflow attachment."""
        user = User.objects.create_user(username="test2", email="test2@test.com")

        handler = get_workflow_handler_for_object(user)

        assert handler is None


@pytest.mark.django_db
class TestWorkflowProgressManager:
    """Tests for WorkflowProgressManager."""

    def test_init_with_handler(self):
        """Test initialization with explicit handler."""
        user = User.objects.create_user(username="test", email="test@test.com")
        handler = WorkflowApprovalHandler(user)

        manager = WorkflowProgressManager(user, workflow_handler=handler)

        assert manager.obj == user
        assert manager.workflow_handler == handler

    def test_init_without_handler(self):
        """Test initialization without explicit handler."""
        user = User.objects.create_user(username="test", email="test@test.com")

        manager = WorkflowProgressManager(user)

        assert manager.obj == user

    @patch("django_workflow_engine.services.attach_workflow_to_object")
    def test_attach_and_start_workflow(self, mock_attach):
        """Test attaching and starting workflow."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(
            company=user,
            name_en="Test",
            name_ar="Test",
            status=WorkflowStatus.ACTIVE,
            is_active=True,
        )

        mock_attachment = Mock()
        mock_attach.return_value = mock_attachment

        manager = WorkflowProgressManager(user)
        result = manager.attach_and_start_workflow(workflow, user, {"key": "value"})

        mock_attach.assert_called_once_with(
            obj=user,
            workflow=workflow,
            user=user,
            auto_start=True,
            metadata={"key": "value"},
        )
        assert result == mock_attachment

    def test_get_current_status_with_attachment(self):
        """Test getting current workflow status."""
        user = User.objects.create_user(username="test", email="test@test.com")
        workflow = WorkFlow.objects.create(
            company=user, name_en="Test Workflow", name_ar="Test"
        )
        pipeline = Pipeline.objects.create(
            workflow=workflow, company=user, name_en="Pipeline", name_ar="Pipeline"
        )
        stage = Stage.objects.create(
            pipeline=pipeline,
            company=user,
            name_en="Stage",
            name_ar="Stage",
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": user.id}]
            },
            is_active=True,
        )
        content_type = ContentType.objects.get_for_model(User)
        attachment = WorkflowAttachment.objects.create(
            workflow=workflow,
            content_type=content_type,
            object_id=str(user.pk),
            status=WorkflowAttachmentStatus.IN_PROGRESS,
            current_stage=stage,
            current_pipeline=pipeline,
        )

        manager = WorkflowProgressManager(user)
        status = manager.get_current_status()

        assert status is not None
        assert status["workflow"] == "Test Workflow"
        assert status["status"] == WorkflowAttachmentStatus.IN_PROGRESS
        assert status["current_stage"] == "Stage"
        assert status["current_pipeline"] == "Pipeline"

    def test_get_current_status_without_attachment(self):
        """Test getting status for object without attachment."""
        user = User.objects.create_user(username="test", email="test@test.com")

        manager = WorkflowProgressManager(user)
        status = manager.get_current_status()

        assert status is None
