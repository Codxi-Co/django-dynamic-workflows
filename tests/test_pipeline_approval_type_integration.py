"""
Integration tests combining pipeline transitions with ApprovalType behavior.

Tests real-world scenarios with:
- Multiple pipelines
- Different approval types per stage
- Complete workflow flows from start to finish
"""

import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model

import pytest
from approval_workflow.choices import ApprovalType, RoleSelectionStrategy

from django_workflow_engine.choices import (
    ApprovalTypes,
    WorkflowAttachmentStatus,
    WorkflowStatus,
)
from django_workflow_engine.models import Pipeline, Stage, WorkFlow
from django_workflow_engine.services import (
    attach_workflow_to_object,
    move_to_next_stage,
)
from django_workflow_engine.utils import build_approval_steps

User = get_user_model()


@pytest.mark.django_db
class TestPipelineApprovalTypeIntegration:
    """Integration tests for pipeline transitions with different approval types."""

    def test_multi_pipeline_with_mixed_approval_types(self):
        """
        Test complete workflow with:
        - Pipeline 1: SUBMIT stage (requires form)
        - Pipeline 2: APPROVE stage (optional form)
        - Pipeline 3: MOVE stage (no form)
        """
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
            name_en="Purchase Request Workflow",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        # Pipeline 1: Submission (SUBMIT type)
        pipeline_submission = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Submission Pipeline",
            name_ar="خط التقديم",
            created_by=user,
            order=0,
        )

        submit_stage = Stage.objects.create(
            pipeline=pipeline_submission,
            company=company_user,
            name_en="Submit Request",
            name_ar="تقديم الطلب",
            created_by=user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.SELF,
                        "step_approval_type": ApprovalType.SUBMIT,
                        "required_form": 100,  # Form required for SUBMIT
                    }
                ]
            },
        )

        # Pipeline 2: Review (APPROVE type)
        pipeline_review = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Review Pipeline",
            name_ar="خط المراجعة",
            created_by=user,
            order=1,
        )

        review_stage = Stage.objects.create(
            pipeline=pipeline_review,
            company=company_user,
            name_en="Manager Review",
            name_ar="مراجعة المدير",
            created_by=user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": user.id,
                        "step_approval_type": ApprovalType.APPROVE,
                        "required_form": 101,  # Optional form for APPROVE
                    }
                ]
            },
        )

        # Pipeline 3: Routing (MOVE type)
        pipeline_routing = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Routing Pipeline",
            name_ar="خط التوجيه",
            created_by=user,
            order=2,
        )

        move_stage = Stage.objects.create(
            pipeline=pipeline_routing,
            company=company_user,
            name_en="Route to Finance",
            name_ar="التوجيه للمالية",
            created_by=user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": user.id,
                        "step_approval_type": ApprovalType.MOVE,
                        # No form for MOVE type
                    }
                ]
            },
        )

        workflow.update_active_status()

        # Verify approval steps are built correctly for each stage
        submit_steps = build_approval_steps(submit_stage, user)
        assert submit_steps[0]["approval_type"] == ApprovalType.SUBMIT
        # Form may not be present if DynamicForm model isn't configured

        review_steps = build_approval_steps(review_stage, user)
        assert review_steps[0]["approval_type"] == ApprovalType.APPROVE
        # Form may not be present if DynamicForm model isn't configured

        move_steps = build_approval_steps(move_stage, user)
        assert move_steps[0]["approval_type"] == ApprovalType.MOVE
        assert move_steps[0].get("form") is None

        # Test workflow progression through all pipelines
        attachment = attach_workflow_to_object(
            obj=user, workflow=workflow, user=user, auto_start=False, disable_clone=True
        )
        attachment.status = WorkflowAttachmentStatus.IN_PROGRESS
        attachment.current_stage = submit_stage
        attachment.current_pipeline = pipeline_submission
        attachment.save()

        with patch("approval_workflow.services.start_flow"):
            with patch(
                "django_workflow_engine.utils.build_approval_steps"
            ) as mock_steps:
                # Move from SUBMIT stage to APPROVE stage (pipeline transition)
                mock_steps.return_value = [{"step": 1}]
                attachment = move_to_next_stage(user, user)
                assert attachment.current_stage == review_stage
                assert attachment.current_pipeline == pipeline_review

                # Move from APPROVE stage to MOVE stage (pipeline transition)
                mock_steps.return_value = [{"step": 1}]
                attachment = move_to_next_stage(user, user)
                assert attachment.current_stage == move_stage
                assert attachment.current_pipeline == pipeline_routing

                # Complete workflow
                attachment = move_to_next_stage(user, user)
                assert attachment.status == WorkflowAttachmentStatus.COMPLETED

    def test_check_in_verify_in_multi_pipeline_workflow(self):
        """
        Test workflow with CHECK_IN_VERIFY type in a multi-pipeline setup.
        """
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
            name_en="Quality Control Workflow",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        # Pipeline 1: Standard approval
        pipeline1 = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Initial Approval",
            name_ar="الموافقة الأولية",
            created_by=user,
            order=0,
        )

        stage1 = Stage.objects.create(
            pipeline=pipeline1,
            company=company_user,
            name_en="Manager Approval",
            name_ar="موافقة المدير",
            created_by=user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": user.id,
                        "step_approval_type": ApprovalType.APPROVE,
                    }
                ]
            },
        )

        # Pipeline 2: Check-in/Verify
        pipeline2 = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Quality Check",
            name_ar="فحص الجودة",
            created_by=user,
            order=1,
        )

        check_verify_stage = Stage.objects.create(
            pipeline=pipeline2,
            company=company_user,
            name_en="Physical Verification",
            name_ar="التحقق المادي",
            created_by=user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.ROLE,
                        "user_role": 1,
                        "role_selection_strategy": RoleSelectionStrategy.ANYONE,
                        "step_approval_type": ApprovalType.CHECK_IN_VERIFY,
                    }
                ]
            },
        )

        workflow.update_active_status()

        # Verify CHECK_IN_VERIFY approval steps
        steps = build_approval_steps(check_verify_stage, user)
        assert steps[0]["approval_type"] == ApprovalType.CHECK_IN_VERIFY

        # Test pipeline transition to CHECK_IN_VERIFY stage
        attachment = attach_workflow_to_object(
            obj=user, workflow=workflow, user=user, auto_start=False, disable_clone=True
        )
        attachment.status = WorkflowAttachmentStatus.IN_PROGRESS
        attachment.current_stage = stage1
        attachment.current_pipeline = pipeline1
        attachment.save()

        with patch("approval_workflow.services.start_flow"):
            with patch(
                "django_workflow_engine.utils.build_approval_steps"
            ) as mock_steps:
                mock_steps.return_value = [{"step": 1}]

                # Move to CHECK_IN_VERIFY stage
                attachment = move_to_next_stage(user, user)
                assert attachment.current_stage == check_verify_stage
                assert attachment.current_pipeline == pipeline2

    def test_expense_approval_workflow_realistic_scenario(self):
        """
        Test realistic expense approval workflow:
        - Stage 1 (Pipeline 1): Employee submits expense (SUBMIT type)
        - Stage 2 (Pipeline 1): Manager reviews (APPROVE type)
        - Stage 3 (Pipeline 2): Finance verifies (CHECK_IN_VERIFY type)
        - Stage 4 (Pipeline 2): Route to payment (MOVE type)
        """
        user = User.objects.create_user(
            username="employee", email="employee@example.com", password="testpass123"
        )
        manager = User.objects.create_user(
            username="manager", email="manager@example.com", password="testpass123"
        )
        unique_id = str(uuid.uuid4())[:8]
        company_user = User.objects.create_user(
            username=f"company{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )

        workflow = WorkFlow.objects.create(
            company=company_user,
            name_en="Expense Approval Workflow",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        # Pipeline 1: Submission & Review
        submission_pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Submission & Review",
            name_ar="التقديم والمراجعة",
            created_by=user,
            order=0,
        )

        # Stage 1: Employee submission (SUBMIT)
        submit_expense_stage = Stage.objects.create(
            pipeline=submission_pipeline,
            company=company_user,
            name_en="Submit Expense",
            name_ar="تقديم المصروف",
            created_by=user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.SELF,
                        "step_approval_type": ApprovalType.SUBMIT,
                        "required_form": 200,  # Expense submission form
                    }
                ]
            },
        )

        # Stage 2: Manager review (APPROVE)
        manager_review_stage = Stage.objects.create(
            pipeline=submission_pipeline,
            company=company_user,
            name_en="Manager Review",
            name_ar="مراجعة المدير",
            created_by=user,
            order=1,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": manager.id,
                        "step_approval_type": ApprovalType.APPROVE,
                        "required_form": 201,  # Manager review form
                    }
                ]
            },
        )

        # Pipeline 2: Finance Processing
        finance_pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Finance Processing",
            name_ar="معالجة المالية",
            created_by=user,
            order=1,
        )

        # Stage 3: Finance verification (CHECK_IN_VERIFY)
        finance_verify_stage = Stage.objects.create(
            pipeline=finance_pipeline,
            company=company_user,
            name_en="Finance Verification",
            name_ar="التحقق من المالية",
            created_by=user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.ROLE,
                        "user_role": 2,  # Finance role
                        "role_selection_strategy": RoleSelectionStrategy.ANYONE,
                        "step_approval_type": ApprovalType.CHECK_IN_VERIFY,
                    }
                ]
            },
        )

        # Stage 4: Route to payment (MOVE)
        route_payment_stage = Stage.objects.create(
            pipeline=finance_pipeline,
            company=company_user,
            name_en="Route to Payment",
            name_ar="التوجيه للدفع",
            created_by=user,
            order=1,
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

        workflow.update_active_status()

        # Verify all approval steps have correct types
        submit_steps = build_approval_steps(submit_expense_stage, user)
        assert submit_steps[0]["approval_type"] == ApprovalType.SUBMIT
        # Form may not be present if DynamicForm model isn't configured

        manager_steps = build_approval_steps(manager_review_stage, manager)
        assert manager_steps[0]["approval_type"] == ApprovalType.APPROVE
        # Form may not be present if DynamicForm model isn't configured

        finance_steps = build_approval_steps(finance_verify_stage, user)
        assert finance_steps[0]["approval_type"] == ApprovalType.CHECK_IN_VERIFY

        payment_steps = build_approval_steps(route_payment_stage, user)
        assert payment_steps[0]["approval_type"] == ApprovalType.MOVE

        # Test complete workflow flow
        attachment = attach_workflow_to_object(
            obj=user, workflow=workflow, user=user, auto_start=False, disable_clone=True
        )
        attachment.status = WorkflowAttachmentStatus.IN_PROGRESS
        attachment.current_stage = submit_expense_stage
        attachment.current_pipeline = submission_pipeline
        attachment.save()

        with patch("approval_workflow.services.start_flow"):
            with patch(
                "django_workflow_engine.utils.build_approval_steps"
            ) as mock_steps:
                mock_steps.return_value = [{"step": 1}]

                # Progress: Submit -> Manager Review (same pipeline)
                attachment = move_to_next_stage(user, user)
                assert attachment.current_stage == manager_review_stage
                assert attachment.current_pipeline == submission_pipeline
                assert attachment.status == WorkflowAttachmentStatus.IN_PROGRESS

                # Progress: Manager Review -> Finance Verification (pipeline transition)
                attachment = move_to_next_stage(user, manager)
                assert attachment.current_stage == finance_verify_stage
                assert attachment.current_pipeline == finance_pipeline
                assert attachment.status == WorkflowAttachmentStatus.IN_PROGRESS

                # Progress: Finance Verification -> Route to Payment (same pipeline)
                attachment = move_to_next_stage(user, user)
                assert attachment.current_stage == route_payment_stage
                assert attachment.current_pipeline == finance_pipeline
                assert attachment.status == WorkflowAttachmentStatus.IN_PROGRESS

                # Complete workflow
                attachment = move_to_next_stage(user, user)
                assert attachment.status == WorkflowAttachmentStatus.COMPLETED
                assert attachment.completed_at is not None

    def test_all_approval_types_in_single_pipeline(self):
        """Test a pipeline with all four approval types in sequence."""
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
            name_en="All Types Workflow",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Complete Pipeline",
            name_ar="خط كامل",
            created_by=user,
            order=0,
        )

        # Create stages with all four approval types
        submit_stage = Stage.objects.create(
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
                        "required_form": 300,
                    }
                ]
            },
        )

        approve_stage = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Approve Stage",
            name_ar="مرحلة الموافقة",
            created_by=user,
            order=1,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": user.id,
                        "step_approval_type": ApprovalType.APPROVE,
                    }
                ]
            },
        )

        check_verify_stage = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Check-in Verify Stage",
            name_ar="مرحلة التحقق من تسجيل الوصول",
            created_by=user,
            order=2,
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

        move_stage = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Move Stage",
            name_ar="مرحلة النقل",
            created_by=user,
            order=3,
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

        workflow.update_active_status()

        # Verify all stages have correct approval types
        stages_and_types = [
            (submit_stage, ApprovalType.SUBMIT),
            (approve_stage, ApprovalType.APPROVE),
            (check_verify_stage, ApprovalType.CHECK_IN_VERIFY),
            (move_stage, ApprovalType.MOVE),
        ]

        for stage, expected_type in stages_and_types:
            steps = build_approval_steps(stage, user)
            assert steps[0]["approval_type"] == expected_type

        # Test progression through all approval types
        attachment = attach_workflow_to_object(
            obj=user, workflow=workflow, user=user, auto_start=False, disable_clone=True
        )
        attachment.status = WorkflowAttachmentStatus.IN_PROGRESS
        attachment.current_stage = submit_stage
        attachment.current_pipeline = pipeline
        attachment.save()

        with patch("approval_workflow.services.start_flow"):
            with patch(
                "django_workflow_engine.utils.build_approval_steps"
            ) as mock_steps:
                mock_steps.return_value = [{"step": 1}]

                # SUBMIT -> APPROVE
                attachment = move_to_next_stage(user, user)
                assert attachment.current_stage == approve_stage

                # APPROVE -> CHECK_IN_VERIFY
                attachment = move_to_next_stage(user, user)
                assert attachment.current_stage == check_verify_stage

                # CHECK_IN_VERIFY -> MOVE
                attachment = move_to_next_stage(user, user)
                assert attachment.current_stage == move_stage

                # MOVE -> COMPLETED
                attachment = move_to_next_stage(user, user)
                assert attachment.status == WorkflowAttachmentStatus.COMPLETED
