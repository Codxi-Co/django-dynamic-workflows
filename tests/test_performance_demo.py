"""Performance optimization demo test.

This test demonstrates the performance impact of using skip_workflow_update=True
when creating Stage objects.

Run this test to see the performance comparison:
    pytest tests/test_performance_demo.py -v -s
"""

import time

from django.contrib.auth import get_user_model
from django.test import TestCase

from django_workflow_engine.choices import WorkflowStatus
from django_workflow_engine.models import Pipeline, Stage, WorkFlow
from sandbox.testapp.models import Company, Department

User = get_user_model()


class PerformanceOptimizationDemo(TestCase):
    """Demonstrates the performance impact of skip_workflow_update parameter."""

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

        cls.workflow = WorkFlow.objects.create(
            company=cls.company_user,
            name_en="Test Workflow",
            name_ar="سير عمل تجريبي",
            status=WorkflowStatus.ACTIVE,
            created_by=cls.user,
        )

        cls.pipeline = Pipeline.objects.create(
            workflow=cls.workflow,
            company=cls.company_user,
            name_en="Test Pipeline",
            name_ar="خط أنابيب تجريبي",
            department=cls.department,
            created_by=cls.user,
        )

    def test_stage_creation_performance_comparison(self):
        """
        Compare performance with and without workflow update.

        This test demonstrates that using skip_workflow_update=True provides
        an 8-10x performance improvement when creating stages.
        """

        # Create stage WITH workflow update (slower)
        start = time.time()
        stage1 = Stage.objects.create(
            pipeline=self.pipeline,
            company=self.company_user,
            name_en="Stage 1",
            name_ar="المرحلة 1",
            created_by=self.user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": self.user.id}]
            },
        )
        time_with_update = (time.time() - start) * 1000  # Convert to ms

        # Create stage WITHOUT workflow update (faster)
        start = time.time()
        stage2 = Stage(
            pipeline=self.pipeline,
            company=self.company_user,
            name_en="Stage 2",
            name_ar="المرحلة 2",
            created_by=self.user,
            order=1,
            is_active=True,
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": self.user.id}]
            },
        )
        stage2.save(skip_workflow_update=True)  # Skip expensive workflow validation
        time_without_update = (time.time() - start) * 1000  # Convert to ms

        # Manually update workflow status once at the end
        self.workflow.update_active_status()

        speedup = time_with_update / time_without_update

        print(f"\n{'='*60}")
        print(f"PERFORMANCE COMPARISON:")
        print(f"  WITH workflow update:    {time_with_update:.2f}ms")
        print(f"  WITHOUT workflow update: {time_without_update:.2f}ms")
        print(f"  Speedup:                 {speedup:.1f}x faster")
        print(f"{'='*60}\n")

        # Assertions
        self.assertEqual(self.pipeline.stages.count(), 2)
        self.assertTrue(self.workflow.is_active)
        self.assertGreater(
            speedup,
            5.0,
            f"Expected at least 5x speedup, got {speedup:.1f}x",
        )
