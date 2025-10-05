"""
Test cases for pipeline transitions and stage movements.

Tests verify that workflows properly transition between pipelines
when all stages in a pipeline are completed.
"""

import uuid
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

import pytest
from approval_workflow.choices import ApprovalStatus, RoleSelectionStrategy
from approval_workflow.models import ApprovalFlow, ApprovalInstance

from django_workflow_engine.choices import (
    ActionType,
    ApprovalTypes,
    WorkflowAttachmentStatus,
    WorkflowStatus,
)
from django_workflow_engine.models import Pipeline, Stage, WorkFlow, WorkflowAttachment
from django_workflow_engine.services import (
    attach_workflow_to_object,
    move_to_next_stage,
    start_workflow_for_object,
    trigger_workflow_event,
)
from sandbox.testapp.models import Company, Department

User = get_user_model()


@pytest.mark.django_db
class TestPipelineTransitions:
    """Test pipeline transition logic."""

    def test_single_pipeline_stage_progression(self):
        """Test basic stage progression within a single pipeline."""
        # Setup
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
            name_en="Single Pipeline Workflow",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Main Pipeline",
            name_ar="خط أنابيب رئيسي",
            created_by=user,
            order=0,
        )

        stage1 = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Stage 1",
            name_ar="المرحلة 1",
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
            name_en="Stage 2",
            name_ar="المرحلة 2",
            created_by=user,
            order=1,
            is_active=True,
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": user.id}]
            },
        )

        stage3 = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Stage 3",
            name_ar="المرحلة 3",
            created_by=user,
            order=2,
            is_active=True,
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": user.id}]
            },
        )

        workflow.update_active_status()

        # Attach workflow
        attachment = attach_workflow_to_object(
            obj=user, workflow=workflow, user=user, auto_start=False, disable_clone=True
        )
        attachment.status = WorkflowAttachmentStatus.IN_PROGRESS
        attachment.current_stage = stage1
        attachment.current_pipeline = pipeline
        attachment.save()

        # Test progression: Stage 1 -> Stage 2
        with patch("approval_workflow.services.start_flow"):
            with patch(
                "django_workflow_engine.utils.build_approval_steps"
            ) as mock_steps:
                mock_steps.return_value = [{"step": 1}]

                updated_attachment = move_to_next_stage(user, user)

                assert updated_attachment.current_stage == stage2
                assert updated_attachment.current_pipeline == pipeline
                assert updated_attachment.status == WorkflowAttachmentStatus.IN_PROGRESS

        # Test progression: Stage 2 -> Stage 3
        with patch("approval_workflow.services.start_flow"):
            with patch(
                "django_workflow_engine.utils.build_approval_steps"
            ) as mock_steps:
                mock_steps.return_value = [{"step": 1}]

                updated_attachment = move_to_next_stage(user, user)

                assert updated_attachment.current_stage == stage3
                assert updated_attachment.current_pipeline == pipeline
                assert updated_attachment.status == WorkflowAttachmentStatus.IN_PROGRESS

    def test_multi_pipeline_transition(self):
        """Test transition from last stage of Pipeline A to first stage of Pipeline B."""
        # Setup
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
            name_en="Multi Pipeline Workflow",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        # Pipeline A - HR Review
        pipeline_a = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="HR Review Pipeline",
            name_ar="خط مراجعة الموارد البشرية",
            created_by=user,
            order=0,
        )

        hr_stage1 = Stage.objects.create(
            pipeline=pipeline_a,
            company=company_user,
            name_en="HR Initial Review",
            name_ar="المراجعة الأولية للموارد البشرية",
            created_by=user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": user.id}]
            },
        )

        hr_stage2 = Stage.objects.create(
            pipeline=pipeline_a,
            company=company_user,
            name_en="HR Final Approval",
            name_ar="الموافقة النهائية للموارد البشرية",
            created_by=user,
            order=1,
            is_active=True,
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": user.id}]
            },
        )

        # Pipeline B - Finance Review
        pipeline_b = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Finance Review Pipeline",
            name_ar="خط مراجعة المالية",
            created_by=user,
            order=1,
        )

        finance_stage1 = Stage.objects.create(
            pipeline=pipeline_b,
            company=company_user,
            name_en="Finance Review",
            name_ar="مراجعة المالية",
            created_by=user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": user.id}]
            },
        )

        finance_stage2 = Stage.objects.create(
            pipeline=pipeline_b,
            company=company_user,
            name_en="Finance Final Approval",
            name_ar="الموافقة النهائية للمالية",
            created_by=user,
            order=1,
            is_active=True,
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": user.id}]
            },
        )

        workflow.update_active_status()

        # Attach workflow
        attachment = attach_workflow_to_object(
            obj=user, workflow=workflow, user=user, auto_start=False, disable_clone=True
        )
        attachment.status = WorkflowAttachmentStatus.IN_PROGRESS
        attachment.current_stage = hr_stage1
        attachment.current_pipeline = pipeline_a
        attachment.save()

        # Move from HR Stage 1 to HR Stage 2 (within same pipeline)
        with patch("approval_workflow.services.start_flow"):
            with patch(
                "django_workflow_engine.utils.build_approval_steps"
            ) as mock_steps:
                mock_steps.return_value = [{"step": 1}]

                updated_attachment = move_to_next_stage(user, user)

                assert updated_attachment.current_stage == hr_stage2
                assert updated_attachment.current_pipeline == pipeline_a

        # CRITICAL TEST: Move from HR Stage 2 (last in Pipeline A) to Finance Stage 1 (first in Pipeline B)
        with patch("approval_workflow.services.start_flow"):
            with patch(
                "django_workflow_engine.utils.build_approval_steps"
            ) as mock_steps:
                with patch(
                    "django_workflow_engine.services.trigger_workflow_event"
                ) as mock_trigger:
                    mock_steps.return_value = [{"step": 1}]

                    updated_attachment = move_to_next_stage(user, user)

                    # Verify pipeline transition
                    assert updated_attachment.current_stage == finance_stage1
                    assert updated_attachment.current_pipeline == pipeline_b
                    assert (
                        updated_attachment.status
                        == WorkflowAttachmentStatus.IN_PROGRESS
                    )

                    # Verify AFTER_MOVE_PIPELINE event was triggered
                    move_pipeline_calls = [
                        call
                        for call in mock_trigger.call_args_list
                        if len(call[0]) > 1
                        and call[0][1] == ActionType.AFTER_MOVE_PIPELINE
                    ]
                    assert (
                        len(move_pipeline_calls) > 0
                    ), "AFTER_MOVE_PIPELINE event should be triggered"

    def test_pipeline_transition_triggers_correct_events(self):
        """Test that pipeline transitions trigger AFTER_MOVE_PIPELINE and AFTER_MOVE_STAGE events."""
        # Setup
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
            name_en="Event Testing Workflow",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        # First Pipeline
        pipeline1 = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Pipeline 1",
            name_ar="خط أنابيب 1",
            created_by=user,
            order=0,
        )

        stage1 = Stage.objects.create(
            pipeline=pipeline1,
            company=company_user,
            name_en="Stage 1",
            name_ar="المرحلة 1",
            created_by=user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": user.id}]
            },
        )

        # Second Pipeline
        pipeline2 = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Pipeline 2",
            name_ar="خط أنابيب 2",
            created_by=user,
            order=1,
        )

        stage2 = Stage.objects.create(
            pipeline=pipeline2,
            company=company_user,
            name_en="Stage 2",
            name_ar="المرحلة 2",
            created_by=user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": user.id}]
            },
        )

        workflow.update_active_status()

        # Attach and set to last stage of pipeline1
        attachment = attach_workflow_to_object(
            obj=user, workflow=workflow, user=user, auto_start=False, disable_clone=True
        )
        attachment.status = WorkflowAttachmentStatus.IN_PROGRESS
        attachment.current_stage = stage1
        attachment.current_pipeline = pipeline1
        attachment.save()

        # Move to next pipeline
        with patch("approval_workflow.services.start_flow"):
            with patch(
                "django_workflow_engine.utils.build_approval_steps"
            ) as mock_steps:
                with patch(
                    "django_workflow_engine.services.trigger_workflow_event"
                ) as mock_trigger:
                    mock_steps.return_value = [{"step": 1}]

                    move_to_next_stage(user, user)

                    # Verify both events were triggered
                    triggered_events = [
                        call[0][1] for call in mock_trigger.call_args_list
                    ]

                    assert (
                        ActionType.AFTER_MOVE_PIPELINE in triggered_events
                    ), "Should trigger AFTER_MOVE_PIPELINE"
                    assert (
                        ActionType.AFTER_MOVE_STAGE in triggered_events
                    ), "Should trigger AFTER_MOVE_STAGE"

    def test_last_stage_of_last_pipeline_completes_workflow(self):
        """Test that completing the last stage of the last pipeline marks workflow as completed."""
        # Setup
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
            name_en="Completion Test Workflow",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Final Pipeline",
            name_ar="خط أنابيب نهائي",
            created_by=user,
            order=0,
        )

        final_stage = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Final Stage",
            name_ar="المرحلة النهائية",
            created_by=user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": user.id}]
            },
        )

        workflow.update_active_status()

        # Attach and set to final stage
        attachment = attach_workflow_to_object(
            obj=user, workflow=workflow, user=user, auto_start=False, disable_clone=True
        )
        attachment.status = WorkflowAttachmentStatus.IN_PROGRESS
        attachment.current_stage = final_stage
        attachment.current_pipeline = pipeline
        attachment.save()

        # Move past final stage
        with patch(
            "django_workflow_engine.services.trigger_workflow_event"
        ) as mock_trigger:
            updated_attachment = move_to_next_stage(user, user)

            # Verify workflow is completed
            assert updated_attachment.status == WorkflowAttachmentStatus.COMPLETED
            assert updated_attachment.completed_at is not None
            assert updated_attachment.current_stage is None
            assert updated_attachment.current_pipeline is None

            # Verify ON_WORKFLOW_COMPLETE event was triggered
            triggered_events = [call[0][1] for call in mock_trigger.call_args_list]
            assert ActionType.ON_WORKFLOW_COMPLETE in triggered_events

    def test_three_pipeline_sequential_transition(self):
        """Test sequential transitions across three pipelines."""
        # Setup
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
            name_en="Three Pipeline Workflow",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        # Create 3 pipelines with 1 stage each
        pipelines = []
        stages = []
        for i in range(3):
            pipeline = Pipeline.objects.create(
                workflow=workflow,
                company=company_user,
                name_en=f"Pipeline {i+1}",
                name_ar=f"خط أنابيب {i+1}",
                created_by=user,
                order=i,
            )
            pipelines.append(pipeline)

            stage = Stage.objects.create(
                pipeline=pipeline,
                company=company_user,
                name_en=f"Stage {i+1}",
                name_ar=f"المرحلة {i+1}",
                created_by=user,
                order=0,
                is_active=True,
                stage_info={
                    "approvals": [{"approval_type": "user", "approval_user": user.id}]
                },
            )
            stages.append(stage)

        workflow.update_active_status()

        # Start at Pipeline 1
        attachment = attach_workflow_to_object(
            obj=user, workflow=workflow, user=user, auto_start=False, disable_clone=True
        )
        attachment.status = WorkflowAttachmentStatus.IN_PROGRESS
        attachment.current_stage = stages[0]
        attachment.current_pipeline = pipelines[0]
        attachment.save()

        # Move through all pipelines
        with patch("approval_workflow.services.start_flow"):
            with patch(
                "django_workflow_engine.utils.build_approval_steps"
            ) as mock_steps:
                mock_steps.return_value = [{"step": 1}]

                # Pipeline 1 -> Pipeline 2
                updated_attachment = move_to_next_stage(user, user)
                assert updated_attachment.current_pipeline == pipelines[1]
                assert updated_attachment.current_stage == stages[1]

                # Pipeline 2 -> Pipeline 3
                updated_attachment = move_to_next_stage(user, user)
                assert updated_attachment.current_pipeline == pipelines[2]
                assert updated_attachment.current_stage == stages[2]

                # Pipeline 3 -> Completed
                updated_attachment = move_to_next_stage(user, user)
                assert updated_attachment.status == WorkflowAttachmentStatus.COMPLETED
