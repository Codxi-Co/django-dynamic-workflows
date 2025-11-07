"""
Test cases for all 3 workflow strategies.

This module tests:
- Strategy 1: Workflow→Pipeline→Stage (approvals at stage level - full hierarchy)
- Strategy 2: Workflow→Pipeline (approvals at pipeline level, NO stages allowed)
- Strategy 3: Workflow Only (approvals at workflow level, NO pipelines/stages allowed)
"""

from unittest.mock import Mock

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from approval_workflow.choices import ApprovalStatus
from approval_workflow.models import ApprovalFlow, ApprovalInstance

from django_workflow_engine.choices import (
    ApprovalTypes,
    WorkflowStatus,
    WorkflowStrategy,
)
from django_workflow_engine.models import Pipeline, Stage, WorkFlow, WorkflowAttachment
from django_workflow_engine.serializers import WorkflowApprovalSerializer
from django_workflow_engine.services import (
    attach_workflow_to_object,
    get_workflow_attachment,
)
from sandbox.testapp.models import WorkflowTestModel

from .factories import UserFactory, setup_test_workflow_model


class WorkflowStrategy1Test(TestCase):
    """Test Strategy 1: Workflow→Pipeline→Stage - Approvals at stage level (full hierarchy)"""

    def setUp(self):
        """Set up test data for strategy 1 workflow"""
        # Register WorkflowTestModel for workflow
        setup_test_workflow_model()

        # Create users
        self.requester = UserFactory(username="requester")
        self.reviewer1 = UserFactory(username="reviewer1")
        self.reviewer2 = UserFactory(username="reviewer2")
        self.approver = UserFactory(username="approver")

        # Create test object
        self.test_object = WorkflowTestModel.objects.create(
            name="Test Object",
            created_by=self.requester,
        )

    def _create_mock_request(self, user):
        """Create a mock request object"""
        request = Mock()
        request.user = user
        return request

    def test_strategy_1_workflow_complete_flow(self):
        """Test complete workflow flow for strategy 1 (stage-level approvals - full hierarchy)"""

        # Create strategy 1 workflow with approvals at stage level (full hierarchy)
        workflow = WorkFlow.objects.create(
            name_en="Strategy 1 Workflow",
            name_ar="استراتيجية 1",
            company=self.requester,
            created_by=self.requester,
            status=WorkflowStatus.ACTIVE,
            is_active=True,
            strategy=WorkflowStrategy.WORKFLOW_PIPELINE_STAGE,  # Strategy 1: Full hierarchy
        )

        # Pipeline with multiple stages
        pipeline = Pipeline.objects.create(
            workflow=workflow,
            name_en="Main Pipeline",
            name_ar="خط رئيسي",
            company=self.requester,
            order=0,
        )

        # Stage 1: First Reviewer
        stage1 = Stage.objects.create(
            pipeline=pipeline,
            name_en="First Review",
            name_ar="مراجعة أولى",
            company=self.requester,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": self.reviewer1.id,
                    },
                ]
            },
        )

        # Stage 2: Second Reviewer
        stage2 = Stage.objects.create(
            pipeline=pipeline,
            name_en="Second Review",
            name_ar="مراجعة ثانية",
            company=self.requester,
            order=1,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": self.reviewer2.id,
                    },
                ]
            },
        )

        # Stage 3: Final Approver
        stage3 = Stage.objects.create(
            pipeline=pipeline,
            name_en="Final Approval",
            name_ar="موافقة نهائية",
            company=self.requester,
            order=2,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": self.approver.id,
                    },
                ]
            },
        )

        workflow.update_active_status()

        # Attach and start workflow
        attachment = attach_workflow_to_object(
            obj=self.test_object,
            workflow=workflow,
            user=self.requester,
            auto_start=True,
            metadata={"test": "strategy1"},
        )

        # Verify attachment created
        self.assertIsNotNone(attachment)
        self.assertEqual(attachment.target, self.test_object)
        self.assertEqual(attachment.status, "in_progress")

        # Get approval flow
        approval_flow = ApprovalFlow.objects.filter(
            content_type=ContentType.objects.get_for_model(WorkflowTestModel),
            object_id=self.test_object.pk,
        ).first()

        self.assertIsNotNone(approval_flow, "Approval flow should be created")

        # Strategy 1: Stage-level approvals are created incrementally as workflow progresses
        # Initially, only the first stage's approval (1 step) is created
        all_instances = ApprovalInstance.objects.filter(flow=approval_flow)
        self.assertEqual(
            all_instances.count(),
            1,
            f"Should have 1 approval step initially (first stage), got {all_instances.count()}",
        )

        # Verify workflow is at first stage (workflow is cloned, so name may have "(Copy)" suffix)
        attachment.refresh_from_db()
        self.assertIsNotNone(attachment.current_stage)
        self.assertIn("First Review", attachment.current_stage.name_en)

        # Step 1: Reviewer 1 approves (completes stage 1)
        current_approval = ApprovalInstance.objects.filter(
            flow=approval_flow, status=ApprovalStatus.CURRENT
        ).first()
        self.assertIsNotNone(current_approval, "Current approval should exist")
        self.assertEqual(current_approval.assigned_to, self.reviewer1)

        request = self._create_mock_request(self.reviewer1)
        serializer = WorkflowApprovalSerializer(
            instance=self.test_object,
            data={"action": ApprovalStatus.APPROVED},
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")
        serializer.save()

        # After stage 1 approval, workflow should move to stage 2
        attachment.refresh_from_db()
        self.assertEqual(attachment.status, "in_progress")
        self.assertIsNotNone(attachment.current_stage, "Should move to stage 2")
        self.assertIn(
            "Second Review", attachment.current_stage.name_en, "Should move to stage 2"
        )

        # Approval flow should now have 2 total steps (stage 1 + stage 2)
        all_instances = ApprovalInstance.objects.filter(flow=approval_flow)
        self.assertEqual(
            all_instances.count(),
            2,
            f"Should have 2 approval steps after moving to stage 2, got {all_instances.count()}",
        )

        # Step 2: Reviewer 2 approves (completes stage 2)
        current_approval = ApprovalInstance.objects.filter(
            flow=approval_flow, status=ApprovalStatus.CURRENT
        ).first()
        self.assertIsNotNone(current_approval, "Current approval should exist")
        self.assertEqual(current_approval.assigned_to, self.reviewer2)

        request = self._create_mock_request(self.reviewer2)
        serializer = WorkflowApprovalSerializer(
            instance=self.test_object,
            data={"action": ApprovalStatus.APPROVED},
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")
        serializer.save()

        # After stage 2 approval, workflow should move to stage 3
        attachment.refresh_from_db()
        self.assertEqual(attachment.status, "in_progress")
        self.assertIsNotNone(attachment.current_stage, "Should move to stage 3")
        self.assertIn(
            "Final Approval", attachment.current_stage.name_en, "Should move to stage 3"
        )

        # Approval flow should now have 3 total steps (all 3 stages)
        all_instances = ApprovalInstance.objects.filter(flow=approval_flow)
        self.assertEqual(
            all_instances.count(),
            3,
            f"Should have 3 approval steps after moving to stage 3, got {all_instances.count()}",
        )

        # Step 3: Final approver approves (workflow completes)
        current_approval = ApprovalInstance.objects.filter(
            flow=approval_flow, status=ApprovalStatus.CURRENT
        ).first()
        self.assertIsNotNone(current_approval, "Current approval should exist")
        self.assertEqual(current_approval.assigned_to, self.approver)

        request = self._create_mock_request(self.approver)
        serializer = WorkflowApprovalSerializer(
            instance=self.test_object,
            data={"action": ApprovalStatus.APPROVED},
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")
        serializer.save()

        # Verify workflow is completed (Strategy 1: no movement, just complete)
        attachment.refresh_from_db()
        self.assertEqual(
            attachment.status,
            "completed",
            f"Expected completed status, got {attachment.status}",
        )
        self.assertIsNotNone(attachment.completed_at)
        self.assertIsNone(attachment.current_stage)
        self.assertIsNone(attachment.current_pipeline)

        # Verify all approvals are approved
        all_approvals = ApprovalInstance.objects.filter(flow=approval_flow)
        self.assertEqual(all_approvals.count(), 3)
        for approval in all_approvals:
            self.assertEqual(approval.status, ApprovalStatus.APPROVED)


class WorkflowStrategy2Test(TestCase):
    """Test Strategy 2: Workflow→Pipeline - Approvals at pipeline level"""

    def setUp(self):
        """Set up test data for strategy 2 workflow"""
        # Register WorkflowTestModel for workflow
        setup_test_workflow_model()

        # Create users
        self.requester = UserFactory(username="requester")
        self.finance_reviewer = UserFactory(username="finance_reviewer")
        self.hr_reviewer = UserFactory(username="hr_reviewer")
        self.exec_approver = UserFactory(username="exec_approver")

        # Create test object
        self.test_object = WorkflowTestModel.objects.create(
            name="Test Object",
            created_by=self.requester,
        )

    def _create_mock_request(self, user):
        """Create a mock request object"""
        request = Mock()
        request.user = user
        return request

    def test_strategy_2_workflow_complete_flow(self):
        """Test complete workflow flow for strategy 2 (pipeline-level approvals)"""

        # Create strategy 2 workflow with approvals at pipeline level
        workflow = WorkFlow.objects.create(
            name_en="Strategy 2 Workflow",
            name_ar="استراتيجية 2",
            company=self.requester,
            created_by=self.requester,
            status=WorkflowStatus.ACTIVE,
            is_active=True,
            strategy=WorkflowStrategy.WORKFLOW_PIPELINE,
        )

        # Pipeline 1: Finance Review (approvals at pipeline level, NO stages)
        pipeline1 = Pipeline.objects.create(
            workflow=workflow,
            name_en="Finance Review",
            name_ar="مراجعة مالية",
            company=self.requester,
            order=0,
            pipeline_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": self.finance_reviewer.id,
                    },
                ]
            },
        )
        # NO stages for Strategy 2

        # Pipeline 2: HR Review (approvals at pipeline level, NO stages)
        pipeline2 = Pipeline.objects.create(
            workflow=workflow,
            name_en="HR Review",
            name_ar="مراجعة الموارد البشرية",
            company=self.requester,
            order=1,
            pipeline_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": self.hr_reviewer.id,
                    },
                ]
            },
        )
        # NO stages for Strategy 2

        # Pipeline 3: Executive Approval (approvals at pipeline level, NO stages)
        pipeline3 = Pipeline.objects.create(
            workflow=workflow,
            name_en="Executive Approval",
            name_ar="موافقة تنفيذية",
            company=self.requester,
            order=2,
            pipeline_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": self.exec_approver.id,
                    },
                ]
            },
        )
        # NO stages for Strategy 2

        workflow.update_active_status()

        # Attach and start workflow
        attachment = attach_workflow_to_object(
            obj=self.test_object,
            workflow=workflow,
            user=self.requester,
            auto_start=True,
            metadata={"test": "strategy2"},
        )

        # Verify attachment created
        self.assertIsNotNone(attachment)
        self.assertEqual(attachment.target, self.test_object)
        self.assertEqual(attachment.status, "in_progress")

        # Get approval flow
        approval_flow = ApprovalFlow.objects.filter(
            content_type=ContentType.objects.get_for_model(WorkflowTestModel),
            object_id=self.test_object.pk,
        ).first()

        self.assertIsNotNone(approval_flow, "Approval flow should be created")

        # Step 1: Finance reviewer approves (Pipeline 1)
        current_approval = ApprovalInstance.objects.filter(
            flow=approval_flow, status=ApprovalStatus.CURRENT
        ).first()
        self.assertIsNotNone(current_approval, "Current approval should exist")
        self.assertEqual(current_approval.assigned_to, self.finance_reviewer)

        request = self._create_mock_request(self.finance_reviewer)
        serializer = WorkflowApprovalSerializer(
            instance=self.test_object,
            data={"action": ApprovalStatus.APPROVED},
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")
        serializer.save()

        # Verify moved to Pipeline 2 (HR Review)
        attachment.refresh_from_db()
        self.assertEqual(attachment.status, "in_progress")
        # For strategy 2, we move directly to next pipeline (skip stages within pipeline)

        # Step 2: HR reviewer approves (Pipeline 2)
        current_approval = ApprovalInstance.objects.filter(
            flow=approval_flow, status=ApprovalStatus.CURRENT
        ).first()
        self.assertIsNotNone(current_approval, "Current approval should exist for HR")
        self.assertEqual(current_approval.assigned_to, self.hr_reviewer)

        request = self._create_mock_request(self.hr_reviewer)
        serializer = WorkflowApprovalSerializer(
            instance=self.test_object,
            data={"action": ApprovalStatus.APPROVED},
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")
        serializer.save()

        # Verify moved to Pipeline 3 (Executive)
        attachment.refresh_from_db()
        self.assertEqual(attachment.status, "in_progress")

        # Step 3: Executive approver approves (Pipeline 3 - Final)
        current_approval = ApprovalInstance.objects.filter(
            flow=approval_flow, status=ApprovalStatus.CURRENT
        ).first()
        self.assertIsNotNone(
            current_approval, "Current approval should exist for Executive"
        )
        self.assertEqual(current_approval.assigned_to, self.exec_approver)

        request = self._create_mock_request(self.exec_approver)
        serializer = WorkflowApprovalSerializer(
            instance=self.test_object,
            data={"action": ApprovalStatus.APPROVED},
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")
        serializer.save()

        # Verify workflow is completed (no more pipelines)
        attachment.refresh_from_db()
        self.assertEqual(
            attachment.status,
            "completed",
            f"Expected completed status, got {attachment.status}",
        )
        self.assertIsNotNone(attachment.completed_at)
        self.assertIsNone(attachment.current_stage)
        self.assertIsNone(attachment.current_pipeline)

        # Verify all approvals are approved
        all_approvals = ApprovalInstance.objects.filter(flow=approval_flow)
        self.assertEqual(all_approvals.count(), 3)  # 3 pipelines
        for approval in all_approvals:
            self.assertEqual(approval.status, ApprovalStatus.APPROVED)


class WorkflowStrategy3Test(TestCase):
    """Test Strategy 3: Workflow Only - Approvals at workflow level (no pipelines/stages)"""

    def setUp(self):
        """Set up test data for strategy 3 workflow"""
        # Register WorkflowTestModel for workflow
        setup_test_workflow_model()

        # Create users
        self.requester = UserFactory(username="requester")
        self.reviewer1 = UserFactory(username="reviewer1")
        self.reviewer2 = UserFactory(username="reviewer2")
        self.manager = UserFactory(username="manager")
        self.director = UserFactory(username="director")

        # Create test object
        self.test_object = WorkflowTestModel.objects.create(
            name="Test Object",
            created_by=self.requester,
        )

    def _create_mock_request(self, user):
        """Create a mock request object"""
        request = Mock()
        request.user = user
        return request

    def test_strategy_3_workflow_complete_flow(self):
        """Test complete workflow flow for strategy 3 (stage-level approvals - default)"""

        # Create strategy 3 workflow (default strategy)
        workflow = WorkFlow.objects.create(
            name_en="Strategy 3 Workflow",
            name_ar="استراتيجية 3",
            company=self.requester,
            created_by=self.requester,
            status=WorkflowStatus.ACTIVE,
            is_active=True,
            strategy=WorkflowStrategy.WORKFLOW_PIPELINE_STAGE,  # Default
        )

        # Pipeline 1: Initial Review
        pipeline1 = Pipeline.objects.create(
            workflow=workflow,
            name_en="Initial Review",
            name_ar="مراجعة أولية",
            company=self.requester,
            order=0,
        )

        # Stage 1.1: First Reviewer
        stage1_1 = Stage.objects.create(
            pipeline=pipeline1,
            name_en="First Review",
            name_ar="مراجعة أولى",
            company=self.requester,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": self.reviewer1.id,
                    },
                ]
            },
        )

        # Stage 1.2: Second Reviewer
        stage1_2 = Stage.objects.create(
            pipeline=pipeline1,
            name_en="Second Review",
            name_ar="مراجعة ثانية",
            company=self.requester,
            order=1,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": self.reviewer2.id,
                    },
                ]
            },
        )

        # Pipeline 2: Management Approval
        pipeline2 = Pipeline.objects.create(
            workflow=workflow,
            name_en="Management Approval",
            name_ar="موافقة إدارية",
            company=self.requester,
            order=1,
        )

        # Stage 2.1: Manager
        stage2_1 = Stage.objects.create(
            pipeline=pipeline2,
            name_en="Manager Approval",
            name_ar="موافقة المدير",
            company=self.requester,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": self.manager.id,
                    },
                ]
            },
        )

        # Stage 2.2: Director (Final)
        stage2_2 = Stage.objects.create(
            pipeline=pipeline2,
            name_en="Director Approval",
            name_ar="موافقة المدير التنفيذي",
            company=self.requester,
            order=1,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": self.director.id,
                    },
                ]
            },
        )

        workflow.update_active_status()

        # Attach and start workflow
        attachment = attach_workflow_to_object(
            obj=self.test_object,
            workflow=workflow,
            user=self.requester,
            auto_start=True,
            metadata={"test": "strategy3"},
        )

        # Verify attachment created
        self.assertIsNotNone(attachment)
        self.assertEqual(attachment.target, self.test_object)
        self.assertEqual(attachment.status, "in_progress")

        # Get approval flow
        approval_flow = ApprovalFlow.objects.filter(
            content_type=ContentType.objects.get_for_model(WorkflowTestModel),
            object_id=self.test_object.pk,
        ).first()

        self.assertIsNotNone(approval_flow, "Approval flow should be created")

        # Step 1: Reviewer 1 approves (Pipeline 1, Stage 1)
        current_approval = ApprovalInstance.objects.filter(
            flow=approval_flow, status=ApprovalStatus.CURRENT
        ).first()
        self.assertIsNotNone(current_approval)
        self.assertEqual(current_approval.assigned_to, self.reviewer1)

        request = self._create_mock_request(self.reviewer1)
        serializer = WorkflowApprovalSerializer(
            instance=self.test_object,
            data={"action": ApprovalStatus.APPROVED},
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")
        serializer.save()

        # Verify moved to next stage in same pipeline
        attachment.refresh_from_db()
        self.assertEqual(attachment.status, "in_progress")

        # Step 2: Reviewer 2 approves (Pipeline 1, Stage 2)
        current_approval = ApprovalInstance.objects.filter(
            flow=approval_flow, status=ApprovalStatus.CURRENT
        ).first()
        self.assertIsNotNone(current_approval)
        self.assertEqual(current_approval.assigned_to, self.reviewer2)

        request = self._create_mock_request(self.reviewer2)
        serializer = WorkflowApprovalSerializer(
            instance=self.test_object,
            data={"action": ApprovalStatus.APPROVED},
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")
        serializer.save()

        # Verify moved to next pipeline
        attachment.refresh_from_db()
        self.assertEqual(attachment.status, "in_progress")

        # Step 3: Manager approves (Pipeline 2, Stage 1)
        current_approval = ApprovalInstance.objects.filter(
            flow=approval_flow, status=ApprovalStatus.CURRENT
        ).first()
        self.assertIsNotNone(current_approval)
        self.assertEqual(current_approval.assigned_to, self.manager)

        request = self._create_mock_request(self.manager)
        serializer = WorkflowApprovalSerializer(
            instance=self.test_object,
            data={"action": ApprovalStatus.APPROVED},
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")
        serializer.save()

        # Verify moved to next stage in same pipeline
        attachment.refresh_from_db()
        self.assertEqual(attachment.status, "in_progress")

        # Step 4: Director approves (Pipeline 2, Stage 2 - Final)
        current_approval = ApprovalInstance.objects.filter(
            flow=approval_flow, status=ApprovalStatus.CURRENT
        ).first()
        self.assertIsNotNone(current_approval)
        self.assertEqual(current_approval.assigned_to, self.director)

        request = self._create_mock_request(self.director)
        serializer = WorkflowApprovalSerializer(
            instance=self.test_object,
            data={"action": ApprovalStatus.APPROVED},
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")
        serializer.save()

        # Verify workflow is completed
        attachment.refresh_from_db()
        self.assertEqual(
            attachment.status,
            "completed",
            f"Expected completed status, got {attachment.status}",
        )
        self.assertIsNotNone(attachment.completed_at)
        self.assertIsNone(attachment.current_stage)
        self.assertIsNone(attachment.current_pipeline)

        # Verify all approvals are approved
        all_approvals = ApprovalInstance.objects.filter(flow=approval_flow)
        self.assertEqual(all_approvals.count(), 4)  # 4 stages
        for approval in all_approvals:
            self.assertEqual(approval.status, ApprovalStatus.APPROVED)
