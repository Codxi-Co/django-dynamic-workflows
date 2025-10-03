"""Detailed performance test for workflow attachment with step-by-step timing.

This test measures each step in the workflow attachment process to identify bottlenecks.

Run this test with:
    pytest tests/test_workflow_attach_detailed_performance.py -v -s
"""

import time
from contextlib import contextmanager

from django.contrib.auth import get_user_model
from django.test import TestCase

from django_workflow_engine.choices import ApprovalTypes, WorkflowStatus
from django_workflow_engine.models import Pipeline, Stage, WorkFlow
from django_workflow_engine.services import attach_workflow_to_object
from sandbox.testapp.models import Company, Department, WorkflowTestModel

User = get_user_model()


@contextmanager
def timer(name):
    """Context manager to measure execution time."""
    start = time.time()
    yield
    elapsed_ms = (time.time() - start) * 1000
    print(f"  {name}: {elapsed_ms:.2f}ms")


class DetailedWorkflowPerformanceTest(TestCase):
    """Test to identify performance bottlenecks in workflow attachment."""

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
                stage.save(skip_workflow_update=True)

        cls.workflow.update_active_status()

    def test_detailed_workflow_attachment_timing(self):
        """
        Test workflow attachment with detailed step-by-step timing.

        This helps identify which part of the process is slow.
        """
        from django.db import connection
        from django.test.utils import override_settings

        print(f"\n{'='*60}")
        print("DETAILED WORKFLOW ATTACHMENT PERFORMANCE TEST")
        print(f"{'='*60}")

        # Create test object
        test_object = WorkflowTestModel.objects.create(
            name="Test Workflow Object",
            description="Test Description",
            amount=1000.00,
            created_by=self.user,
        )

        # Track query count
        query_count_start = len(connection.queries)

        # Measure total time
        total_start = time.time()

        # Step 1: Prefetch and clone
        with timer("Step 1: Workflow validation"):
            if not self.workflow.is_active:
                raise ValueError("Workflow is not active")

        with timer("Step 2: Prefetch workflow data"):
            from django.contrib.contenttypes.models import ContentType

            workflow_with_relations = WorkFlow.objects.prefetch_related(
                "pipelines__stages"
            ).get(id=self.workflow.id)

        with timer("Step 3: Clone workflow"):
            workflow_to_use = workflow_with_relations.clone()

        with timer("Step 4: Get content type"):
            content_type = ContentType.objects.get_for_model(test_object)

        with timer("Step 5: Create workflow attachment"):
            from django_workflow_engine.models import WorkflowAttachment

            attachment, created = WorkflowAttachment.objects.get_or_create(
                content_type=content_type,
                object_id=str(test_object.pk),
                defaults={
                    "workflow": workflow_to_use,
                    "metadata": {},
                    "started_by": self.user,
                },
            )

        # Step 6: Start workflow
        with timer("Step 6: Get first pipeline and stage"):
            first_pipeline = workflow_to_use.pipelines.order_by("order").first()
            first_stage = first_pipeline.stages.order_by("order").first()

        with timer("Step 7: Update attachment status"):
            from django.utils import timezone

            from django_workflow_engine.choices import WorkflowAttachmentStatus

            attachment.status = WorkflowAttachmentStatus.IN_PROGRESS
            attachment.current_stage = first_stage
            attachment.current_pipeline = first_pipeline
            attachment.started_at = timezone.now()
            attachment.started_by = self.user
            attachment.save()

        with timer("Step 8: Build approval steps"):
            from django_workflow_engine.utils import build_approval_steps

            steps = build_approval_steps(first_stage, self.user)

        with timer("Step 9: Start approval flow"):
            if steps:
                from approval_workflow.services import start_flow

                start_flow(test_object, steps)

        total_elapsed = (time.time() - total_start) * 1000
        query_count = len(connection.queries) - query_count_start

        print(f"\nTotal Time: {total_elapsed:.2f}ms")
        print(f"Total Queries: {query_count}")
        print(
            f"Average per Query: {total_elapsed/query_count if query_count > 0 else 0:.2f}ms"
        )
        print(f"\nTarget: 200ms")
        print(f"Status: {'✓ PASS' if total_elapsed <= 200 else '✗ FAIL'}")
        print(f"{'='*60}\n")

        # Print all queries if slow
        if total_elapsed > 200:
            print("\nSLOW QUERIES:")
            for i, query in enumerate(connection.queries[query_count_start:], 1):
                print(f"\n  Query {i} ({query['time']}s):")
                print(f"    {query['sql'][:200]}...")

        self.assertTrue(
            total_elapsed <= 200,
            f"Workflow attachment took {total_elapsed:.2f}ms, exceeds 200ms target",
        )
