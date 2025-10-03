"""Performance test for workflow attachment.

This test ensures that attach_workflow_to_object completes within 200ms
for a typical workflow with 3 pipelines and 5 stages each.

Run this test with:
    pytest tests/test_workflow_attach_performance.py -v -s
"""

import time

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from django_workflow_engine.choices import ApprovalTypes, WorkflowStatus
from django_workflow_engine.models import Pipeline, Stage, WorkFlow
from django_workflow_engine.services import attach_workflow_to_object
from sandbox.testapp.models import Company, Department, WorkflowTestModel

User = get_user_model()


class WorkflowAttachmentPerformanceTest(TestCase):
    """Test workflow attachment performance to ensure it meets 200ms target."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for the entire test class."""
        cls.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        import uuid

        unique_id = str(uuid.uuid4())[:8]
        cls.company_user = User.objects.create_user(
            username=f"testcompany{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )
        cls.company = Company.objects.create(name="Test Company")
        cls.department = Department.objects.create(
            name="Test Department", company=cls.company
        )

        # Create a typical workflow with 3 pipelines × 5 stages = 15 stages
        cls.workflow = WorkFlow.objects.create(
            company=cls.company_user,
            name_en="Purchase Approval Workflow",
            name_ar="سير عمل الموافقة على الشراء",
            status=WorkflowStatus.ACTIVE,
            created_by=cls.user,
        )

        # Create 3 pipelines
        for p in range(3):
            pipeline = Pipeline.objects.create(
                workflow=cls.workflow,
                company=cls.company_user,
                name_en=f"Pipeline {p + 1}",
                name_ar=f"خط أنابيب {p + 1}",
                department=cls.department,
                created_by=cls.user,
                order=p,
            )

            # Create 5 stages per pipeline
            for s in range(5):
                stage = Stage(
                    pipeline=pipeline,
                    company=cls.company_user,
                    name_en=f"Stage {s + 1}",
                    name_ar=f"المرحلة {s + 1}",
                    created_by=cls.user,
                    order=s,
                    is_active=True,
                    stage_info={
                        "approvals": [
                            {
                                "approval_type": ApprovalTypes.USER,
                                "approval_user": cls.user.id,
                            }
                        ],
                        "color": "#3498db",
                    },
                )
                stage.save(
                    skip_workflow_update=True
                )  # Skip workflow update during bulk creation

        # Update workflow active status once at the end
        cls.workflow.update_active_status()

    def test_attach_workflow_performance_200ms(self):
        """
        Test that attach_workflow_to_object completes within 200ms.

        This is the main performance test that ensures workflow attachment
        (including cloning and starting) completes within the 200ms target.
        """
        # Create a test object
        test_object = WorkflowTestModel.objects.create(
            name="Test Workflow Object",
            description="Test Description",
            amount=1000.00,
            created_by=self.user,
        )

        # Measure attach_workflow_to_object performance
        start = time.time()
        attachment = attach_workflow_to_object(
            test_object,
            self.workflow,
            user=self.user,
            auto_start=True,  # This includes starting the workflow
        )
        elapsed_ms = (time.time() - start) * 1000

        # Print detailed timing
        print(f"\n{'='*60}")
        print(f"WORKFLOW ATTACHMENT PERFORMANCE TEST:")
        print(f"  Workflow: {self.workflow.name_en}")
        print(f"  Pipelines: {self.workflow.pipelines.count()}")
        print(
            f"  Total Stages: {sum(p.stages.count() for p in self.workflow.pipelines.all())}"
        )
        print(f"  Time Taken: {elapsed_ms:.2f}ms")
        print(f"  Target: 200ms")
        print(f"  Status: {'✓ PASS' if elapsed_ms <= 200 else '✗ FAIL'}")
        print(f"{'='*60}\n")

        # Assertions
        self.assertIsNotNone(attachment)
        self.assertEqual(attachment.workflow.pipelines.count(), 3)
        self.assertTrue(
            elapsed_ms <= 200,
            f"Workflow attachment took {elapsed_ms:.2f}ms, exceeds 200ms target",
        )

    def test_clone_performance(self):
        """
        Test that workflow.clone() completes efficiently.

        This test specifically measures the cloning performance to ensure
        bulk_create optimization is working correctly.
        """
        # Measure clone performance
        start = time.time()
        cloned_workflow = self.workflow.clone()
        elapsed_ms = (time.time() - start) * 1000

        # Print detailed timing
        print(f"\n{'='*60}")
        print(f"WORKFLOW CLONE PERFORMANCE TEST:")
        print(f"  Original Workflow ID: {self.workflow.id}")
        print(f"  Cloned Workflow ID: {cloned_workflow.id}")
        print(f"  Pipelines: {cloned_workflow.pipelines.count()}")
        print(
            f"  Total Stages: {sum(p.stages.count() for p in cloned_workflow.pipelines.all())}"
        )
        print(f"  Time Taken: {elapsed_ms:.2f}ms")
        print(f"  Target: 100ms (cloning only)")
        print(f"  Status: {'✓ PASS' if elapsed_ms <= 100 else '✗ FAIL'}")
        print(f"{'='*60}\n")

        # Assertions
        self.assertIsNotNone(cloned_workflow)
        self.assertNotEqual(cloned_workflow.id, self.workflow.id)
        self.assertEqual(cloned_workflow.pipelines.count(), 3)
        self.assertEqual(
            sum(p.stages.count() for p in cloned_workflow.pipelines.all()), 15
        )
        self.assertTrue(
            elapsed_ms <= 100,
            f"Workflow cloning took {elapsed_ms:.2f}ms, exceeds 100ms target",
        )

    def test_attach_workflow_without_auto_start(self):
        """
        Test workflow attachment without auto-start.

        This measures just the attachment and cloning, without starting.
        """
        test_object = WorkflowTestModel.objects.create(
            name="Test Workflow Object 2",
            description="Test Description",
            amount=2000.00,
            created_by=self.user,
        )

        # Measure attach without auto-start
        start = time.time()
        attachment = attach_workflow_to_object(
            test_object,
            self.workflow,
            user=self.user,
            auto_start=False,  # Don't start workflow
        )
        elapsed_ms = (time.time() - start) * 1000

        # Print detailed timing
        print(f"\n{'='*60}")
        print(f"WORKFLOW ATTACHMENT (NO AUTO-START) PERFORMANCE TEST:")
        print(f"  Time Taken: {elapsed_ms:.2f}ms")
        print(f"  Target: 150ms (attachment without starting)")
        print(f"  Status: {'✓ PASS' if elapsed_ms <= 150 else '✗ FAIL'}")
        print(f"{'='*60}\n")

        # Assertions
        self.assertIsNotNone(attachment)
        self.assertTrue(
            elapsed_ms <= 150,
            f"Workflow attachment (no start) took {elapsed_ms:.2f}ms, exceeds 150ms target",
        )

    def test_large_workflow_performance(self):
        """
        Test performance with a larger workflow (5 pipelines × 10 stages = 50 stages).

        This ensures the optimization scales well with larger workflows.
        """
        # Create a larger workflow
        large_workflow = WorkFlow.objects.create(
            company=self.company_user,
            name_en="Large Workflow",
            name_ar="سير عمل كبير",
            status=WorkflowStatus.ACTIVE,
            created_by=self.user,
        )

        # Create 5 pipelines with 10 stages each
        for p in range(5):
            pipeline = Pipeline.objects.create(
                workflow=large_workflow,
                company=self.company_user,
                name_en=f"Pipeline {p + 1}",
                name_ar=f"خط أنابيب {p + 1}",
                department=self.department,
                created_by=self.user,
                order=p,
            )

            # Create 10 stages per pipeline
            for s in range(10):
                stage = Stage(
                    pipeline=pipeline,
                    company=self.company_user,
                    name_en=f"Stage {s + 1}",
                    name_ar=f"المرحلة {s + 1}",
                    created_by=self.user,
                    order=s,
                    is_active=True,
                    stage_info={
                        "approvals": [
                            {
                                "approval_type": ApprovalTypes.USER,
                                "approval_user": self.user.id,
                            }
                        ]
                    },
                )
                stage.save(skip_workflow_update=True)

        large_workflow.update_active_status()

        # Create test object
        test_object = WorkflowTestModel.objects.create(
            name="Large Workflow Test",
            description="Test Description",
            amount=5000.00,
            created_by=self.user,
        )

        # Measure performance
        start = time.time()
        attachment = attach_workflow_to_object(
            test_object,
            large_workflow,
            user=self.user,
            auto_start=True,
        )
        elapsed_ms = (time.time() - start) * 1000

        # Print detailed timing
        print(f"\n{'='*60}")
        print(f"LARGE WORKFLOW ATTACHMENT PERFORMANCE TEST:")
        print(f"  Pipelines: {large_workflow.pipelines.count()}")
        print(
            f"  Total Stages: {sum(p.stages.count() for p in large_workflow.pipelines.all())}"
        )
        print(f"  Time Taken: {elapsed_ms:.2f}ms")
        print(f"  Target: 500ms (larger workflow)")
        print(f"  Status: {'✓ PASS' if elapsed_ms <= 500 else '✗ FAIL'}")
        print(f"{'='*60}\n")

        # Assertions for larger workflow
        self.assertIsNotNone(attachment)
        self.assertTrue(
            elapsed_ms <= 500,
            f"Large workflow attachment took {elapsed_ms:.2f}ms, exceeds 500ms target",
        )
