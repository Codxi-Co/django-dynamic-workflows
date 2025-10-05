"""Tests for django_workflow_engine utility functions."""

from django.contrib.auth import get_user_model

import pytest

from django_workflow_engine.models import Pipeline, Stage, WorkFlow, WorkflowAttachment
from django_workflow_engine.utils import (
    build_approval_steps,
    get_next_workflow_stage,
    get_user_for_approval,
    get_workflow_first_stage,
    get_workflow_stage_approvers,
)

User = get_user_model()


@pytest.mark.django_db
class TestGetUserForApproval:
    """Tests for get_user_for_approval utility function."""

    def test_returns_provided_user_when_given(self):
        """Should return the provided user as highest priority."""
        user1 = User.objects.create_user(username="user1", email="user1@test.com")
        user2 = User.objects.create_user(username="user2", email="user2@test.com")

        # Create a mock object with created_by
        class MockObj:
            created_by = user2
            _meta = type("Meta", (), {"label": "MockObj", "pk": 1})()

        mock_obj = MockObj()
        mock_obj.pk = 1

        result = get_user_for_approval(mock_obj, user=user1)
        assert result == user1, "Should return provided user as highest priority"

    def test_falls_back_to_created_by(self):
        """Should fallback to obj.created_by when user not provided."""
        user = User.objects.create_user(username="creator", email="creator@test.com")

        class MockObj:
            created_by = user
            _meta = type("Meta", (), {"label": "MockObj"})()
            pk = 1

        mock_obj = MockObj()

        result = get_user_for_approval(mock_obj, user=None)
        assert result == user, "Should fallback to created_by"

    def test_falls_back_to_started_by(self):
        """Should fallback to obj.started_by when created_by not available."""
        user = User.objects.create_user(username="starter", email="starter@test.com")

        class MockObj:
            created_by = None
            started_by = user
            _meta = type("Meta", (), {"label": "MockObj"})()
            pk = 1

        mock_obj = MockObj()

        result = get_user_for_approval(mock_obj, user=None)
        assert result == user, "Should fallback to started_by"

    def test_falls_back_to_attachment_started_by(self):
        """Should fallback to attachment.started_by when obj fields not available."""
        user = User.objects.create_user(
            username="attachment_starter", email="attachment@test.com"
        )

        class MockObj:
            created_by = None
            _meta = type("Meta", (), {"label": "MockObj"})()
            pk = 1

        class MockAttachment:
            started_by = user

        mock_obj = MockObj()
        mock_attachment = MockAttachment()

        result = get_user_for_approval(mock_obj, user=None, attachment=mock_attachment)
        assert result == user, "Should fallback to attachment.started_by"

    def test_returns_none_when_no_user_found(self):
        """Should return None and log warning when no user can be found."""

        class MockObj:
            created_by = None
            _meta = type("Meta", (), {"label": "MockObj"})()
            pk = 1

        mock_obj = MockObj()

        result = get_user_for_approval(mock_obj, user=None)
        assert result is None, "Should return None when no user found"


@pytest.mark.django_db
class TestBuildApprovalSteps:
    """Tests for build_approval_steps utility function."""

    def test_returns_empty_list_when_user_is_none(self):
        """Should return empty list when user is None to prevent cascading errors."""
        company_user = User.objects.create_user(
            username="company", email="company@test.com"
        )
        workflow = WorkFlow.objects.create(
            company=company_user, name_en="Test Workflow", name_ar="Test Workflow"
        )
        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            name_ar="Test Pipeline",
        )
        stage = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Test Stage",
            name_ar="Test Stage",
            stage_info={"approvals": [{"approval_type": "self-approved"}]},
        )

        result = build_approval_steps(stage, created_by_user=None)
        assert result == [], "Should return empty list when user is None"

    def test_builds_self_approval_step(self):
        """Should build approval step for self-approval type."""
        user = User.objects.create_user(username="testuser", email="test@test.com")
        company_user = User.objects.create_user(
            username="company", email="company@test.com"
        )

        workflow = WorkFlow.objects.create(
            company=company_user, name_en="Test Workflow", name_ar="Test Workflow"
        )
        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            name_ar="Test Pipeline",
        )
        stage = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Test Stage",
            name_ar="Test Stage",
            stage_info={"approvals": [{"approval_type": "self-approved"}]},
        )

        steps = build_approval_steps(stage, user)

        assert len(steps) == 1, "Should create one approval step"
        assert steps[0]["assigned_to"] == user, "Should assign to provided user"
        assert steps[0]["step"] == 1, "Should set step number"

    def test_builds_user_specific_approval_step(self):
        """Should build approval step for user-specific approval."""
        user1 = User.objects.create_user(username="user1", email="user1@test.com")
        user2 = User.objects.create_user(username="user2", email="user2@test.com")
        company_user = User.objects.create_user(
            username="company", email="company@test.com"
        )

        workflow = WorkFlow.objects.create(
            company=company_user, name_en="Test Workflow", name_ar="Test Workflow"
        )
        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            name_ar="Test Pipeline",
        )
        stage = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Test Stage",
            name_ar="Test Stage",
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": user2.id}]
            },
        )

        steps = build_approval_steps(stage, user1)

        assert len(steps) == 1, "Should create one approval step"
        assert steps[0]["assigned_to"] == user2, "Should assign to specified user"

    def test_includes_extra_fields_with_stage_id(self):
        """Should include extra_fields with stage_id in each step."""
        user = User.objects.create_user(username="testuser", email="test@test.com")
        company_user = User.objects.create_user(
            username="company", email="company@test.com"
        )

        workflow = WorkFlow.objects.create(
            company=company_user, name_en="Test Workflow", name_ar="Test Workflow"
        )
        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            name_ar="Test Pipeline",
        )
        stage = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Test Stage",
            name_ar="Test Stage",
            stage_info={"approvals": [{"approval_type": "self-approved"}]},
        )

        steps = build_approval_steps(stage, user)

        assert "extra_fields" in steps[0], "Should include extra_fields"
        assert (
            steps[0]["extra_fields"]["stage_id"] == stage.id
        ), "Should include stage_id"

    def test_builds_multiple_approval_steps(self):
        """Should build multiple approval steps when multiple approvals configured."""
        user1 = User.objects.create_user(username="user1", email="user1@test.com")
        user2 = User.objects.create_user(username="user2", email="user2@test.com")
        user3 = User.objects.create_user(username="user3", email="user3@test.com")
        company_user = User.objects.create_user(
            username="company", email="company@test.com"
        )

        workflow = WorkFlow.objects.create(
            company=company_user, name_en="Test Workflow", name_ar="Test Workflow"
        )
        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            name_ar="Test Pipeline",
        )
        stage = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Test Stage",
            name_ar="Test Stage",
            stage_info={
                "approvals": [
                    {"approval_type": "user", "approval_user": user2.id},
                    {"approval_type": "user", "approval_user": user3.id},
                ]
            },
        )

        steps = build_approval_steps(stage, user1)

        assert len(steps) == 2, "Should create two approval steps"
        assert steps[0]["step"] == 1, "First step should be numbered 1"
        assert steps[1]["step"] == 2, "Second step should be numbered 2"
        assert steps[0]["assigned_to"] == user2, "First step should assign to user2"
        assert steps[1]["assigned_to"] == user3, "Second step should assign to user3"


@pytest.mark.django_db
class TestGetWorkflowStageApprovers:
    """Tests for get_workflow_stage_approvers utility function."""

    def test_returns_self_approval_when_no_stage_info(self):
        """Should return self-approval default when stage has no stage_info."""
        user = User.objects.create_user(username="testuser", email="test@test.com")
        company_user = User.objects.create_user(
            username="company", email="company@test.com"
        )

        workflow = WorkFlow.objects.create(
            company=company_user, name_en="Test Workflow", name_ar="Test Workflow"
        )
        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            name_ar="Test Pipeline",
        )
        stage = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Test Stage",
            name_ar="Test Stage",
            stage_info=None,  # No stage_info
        )

        approvers = get_workflow_stage_approvers(stage, user)

        assert len(approvers) == 1, "Should return one default approver"
        assert approvers[0]["approval_user"] == user, "Should use created_by_user"
        assert (
            approvers[0]["approval_type"] == "self-approved"
        ), "Should be self-approval"

    def test_returns_self_approval_when_no_approvals_configured(self):
        """Should return self-approval when approvals list is empty."""
        user = User.objects.create_user(username="testuser", email="test@test.com")
        company_user = User.objects.create_user(
            username="company", email="company@test.com"
        )

        workflow = WorkFlow.objects.create(
            company=company_user, name_en="Test Workflow", name_ar="Test Workflow"
        )
        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            name_ar="Test Pipeline",
        )
        stage = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Test Stage",
            name_ar="Test Stage",
            stage_info={"approvals": []},  # Empty approvals
        )

        approvers = get_workflow_stage_approvers(stage, user)

        assert len(approvers) == 1, "Should return one default approver"
        assert (
            approvers[0]["approval_type"] == "self-approved"
        ), "Should be self-approval"

    def test_returns_configured_approvals(self):
        """Should return configured approvals from stage_info."""
        user = User.objects.create_user(username="testuser", email="test@test.com")
        company_user = User.objects.create_user(
            username="company", email="company@test.com"
        )

        workflow = WorkFlow.objects.create(
            company=company_user, name_en="Test Workflow", name_ar="Test Workflow"
        )
        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            name_ar="Test Pipeline",
        )

        approvals_config = [
            {"approval_type": "user", "approval_user": user.id},
            {"approval_type": "role", "user_role": 1},
        ]

        stage = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Test Stage",
            name_ar="Test Stage",
            stage_info={"approvals": approvals_config},
        )

        approvers = get_workflow_stage_approvers(stage, user)

        assert len(approvers) == 2, "Should return configured approvals"
        assert approvers[0]["approval_type"] == "user", "First should be user type"
        assert approvers[1]["approval_type"] == "role", "Second should be role type"


@pytest.mark.django_db
class TestGetNextWorkflowStage:
    """Tests for get_next_workflow_stage function."""

    def test_returns_none_for_none_current_stage(self):
        """Should return None when current_stage is None."""
        result = get_next_workflow_stage(None)
        assert result is None

    def test_returns_next_stage_in_same_pipeline(self):
        """Should return next stage in same pipeline when available."""
        user = User.objects.create_user(username="testuser", email="test@test.com")
        workflow = WorkFlow.objects.create(
            company=user, name_en="Test Workflow", name_ar="Test Workflow"
        )
        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=user,
            name_en="Pipeline",
            name_ar="Pipeline",
            order=0,
        )

        stage1 = Stage.objects.create(
            pipeline=pipeline,
            company=user,
            name_en="Stage 1",
            name_ar="Stage 1",
            order=0,
            is_active=True,
        )
        stage2 = Stage.objects.create(
            pipeline=pipeline,
            company=user,
            name_en="Stage 2",
            name_ar="Stage 2",
            order=1,
            is_active=True,
        )

        next_stage = get_next_workflow_stage(stage1)

        assert next_stage == stage2
        assert next_stage.pipeline == pipeline

    def test_returns_first_stage_of_next_pipeline(self):
        """Should return first stage of next pipeline when current pipeline is complete."""
        user = User.objects.create_user(username="testuser", email="test@test.com")
        workflow = WorkFlow.objects.create(
            company=user, name_en="Test Workflow", name_ar="Test Workflow"
        )

        # Pipeline 1
        pipeline1 = Pipeline.objects.create(
            workflow=workflow,
            company=user,
            name_en="Pipeline 1",
            name_ar="Pipeline 1",
            order=0,
        )
        stage1 = Stage.objects.create(
            pipeline=pipeline1,
            company=user,
            name_en="Stage 1",
            name_ar="Stage 1",
            order=0,
            is_active=True,
        )

        # Pipeline 2
        pipeline2 = Pipeline.objects.create(
            workflow=workflow,
            company=user,
            name_en="Pipeline 2",
            name_ar="Pipeline 2",
            order=1,
        )
        stage2 = Stage.objects.create(
            pipeline=pipeline2,
            company=user,
            name_en="Stage 2",
            name_ar="Stage 2",
            order=0,
            is_active=True,
        )

        # Get next stage after last stage of pipeline1
        next_stage = get_next_workflow_stage(stage1)

        assert next_stage == stage2
        assert next_stage.pipeline == pipeline2

    def test_returns_none_at_end_of_workflow(self):
        """Should return None when at last stage of last pipeline."""
        user = User.objects.create_user(username="testuser", email="test@test.com")
        workflow = WorkFlow.objects.create(
            company=user, name_en="Test Workflow", name_ar="Test Workflow"
        )
        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=user,
            name_en="Pipeline",
            name_ar="Pipeline",
            order=0,
        )
        final_stage = Stage.objects.create(
            pipeline=pipeline,
            company=user,
            name_en="Final Stage",
            name_ar="Final Stage",
            order=0,
            is_active=True,
        )

        next_stage = get_next_workflow_stage(final_stage)

        assert next_stage is None

    def test_returns_none_when_next_pipeline_has_no_stages(self):
        """Should return None when next pipeline exists but has no stages."""
        user = User.objects.create_user(username="testuser", email="test@test.com")
        workflow = WorkFlow.objects.create(
            company=user, name_en="Test Workflow", name_ar="Test Workflow"
        )

        # Pipeline 1 with a stage
        pipeline1 = Pipeline.objects.create(
            workflow=workflow,
            company=user,
            name_en="Pipeline 1",
            name_ar="Pipeline 1",
            order=0,
        )
        stage1 = Stage.objects.create(
            pipeline=pipeline1,
            company=user,
            name_en="Stage 1",
            name_ar="Stage 1",
            order=0,
            is_active=True,
        )

        # Pipeline 2 with NO stages
        pipeline2 = Pipeline.objects.create(
            workflow=workflow,
            company=user,
            name_en="Pipeline 2",
            name_ar="Pipeline 2",
            order=1,
        )

        next_stage = get_next_workflow_stage(stage1)

        assert next_stage is None


@pytest.mark.django_db
class TestGetWorkflowFirstStage:
    """Tests for get_workflow_first_stage function."""

    def test_returns_first_stage_of_first_pipeline(self):
        """Should return first stage of first pipeline."""
        user = User.objects.create_user(username="testuser", email="test@test.com")
        workflow = WorkFlow.objects.create(
            company=user, name_en="Test Workflow", name_ar="Test Workflow"
        )

        # First pipeline
        pipeline1 = Pipeline.objects.create(
            workflow=workflow,
            company=user,
            name_en="Pipeline 1",
            name_ar="Pipeline 1",
            order=0,
        )
        first_stage = Stage.objects.create(
            pipeline=pipeline1,
            company=user,
            name_en="First Stage",
            name_ar="First Stage",
            order=0,
            is_active=True,
        )
        Stage.objects.create(
            pipeline=pipeline1,
            company=user,
            name_en="Second Stage",
            name_ar="Second Stage",
            order=1,
            is_active=True,
        )

        # Second pipeline (should be ignored)
        pipeline2 = Pipeline.objects.create(
            workflow=workflow,
            company=user,
            name_en="Pipeline 2",
            name_ar="Pipeline 2",
            order=1,
        )
        Stage.objects.create(
            pipeline=pipeline2,
            company=user,
            name_en="Stage in Pipeline 2",
            name_ar="Stage in Pipeline 2",
            order=0,
            is_active=True,
        )

        result = get_workflow_first_stage(workflow)

        assert result == first_stage
        assert result.pipeline == pipeline1

    def test_returns_none_when_no_pipelines(self):
        """Should return None when workflow has no pipelines."""
        user = User.objects.create_user(username="testuser", email="test@test.com")
        workflow = WorkFlow.objects.create(
            company=user, name_en="Empty Workflow", name_ar="Empty Workflow"
        )

        result = get_workflow_first_stage(workflow)

        assert result is None

    def test_returns_none_when_first_pipeline_has_no_stages(self):
        """Should return None when first pipeline has no stages."""
        user = User.objects.create_user(username="testuser", email="test@test.com")
        workflow = WorkFlow.objects.create(
            company=user, name_en="Test Workflow", name_ar="Test Workflow"
        )
        Pipeline.objects.create(
            workflow=workflow,
            company=user,
            name_en="Empty Pipeline",
            name_ar="Empty Pipeline",
            order=0,
        )

        result = get_workflow_first_stage(workflow)

        assert result is None
