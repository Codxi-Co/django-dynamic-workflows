"""
Test cases for workflow fixes:
1. Form enrichment with answer keys and nested forms
2. Pipeline movement and synchronization
3. Workflow completion status
"""

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory

import pytest
from approval_workflow.choices import ApprovalStatus

from django_workflow_engine.choices import WorkflowAttachmentStatus
from django_workflow_engine.models import Pipeline, Stage, WorkFlow, WorkflowAttachment
from django_workflow_engine.serializers import WorkflowApprovalSerializer
from django_workflow_engine.services import (
    attach_workflow_to_object,
    move_to_next_stage,
    start_workflow_for_object,
)
from django_workflow_engine.utils import enrich_answers, flatten_form_info
from sandbox.testapp.models import WorkflowTestModel

User = get_user_model()


@pytest.fixture
def company_user(db):
    """Create a company user for tests."""
    return User.objects.create_user(
        username="testcompany",
        email="company@example.com",
        password="testpass123",
    )


@pytest.mark.django_db
class TestFormEnrichment:
    """Test form data enrichment with answer keys."""

    def test_flatten_simple_form(self):
        """Test flattening a simple form without nesting."""
        form_info = [
            {"field_name": "name", "field_type": "TEXT"},
            {"field_name": "budget", "field_type": "NUMBER"},
        ]
        submitted_data = {"name": "Project Alpha", "budget": 50000}

        flattened = flatten_form_info(form_info, submitted_data)

        assert len(flattened) == 2
        assert flattened[0]["field_name"] == "name"
        assert flattened[1]["field_name"] == "budget"

    def test_flatten_nested_form_with_dropdown_trigger(self):
        """Test flattening nested forms triggered by dropdown selection."""
        form_info = [
            {
                "field_name": "department",
                "field_type": "DROP_DOWN",
                "extra_info": {
                    "choice_form": {
                        "choice": "IT",
                        "form": {
                            "field_name": "it_budget",
                            "field_type": "NUMBER",
                        },
                    }
                },
            }
        ]
        submitted_data = {"department": "IT", "it_budget": 50000}

        flattened = flatten_form_info(form_info, submitted_data)

        assert len(flattened) == 2  # Both parent and nested field
        assert flattened[0]["field_name"] == "department"
        assert flattened[1]["field_name"] == "it_budget"

    def test_flatten_nested_form_not_triggered(self):
        """Test that nested forms are not included when trigger condition not met."""
        form_info = [
            {
                "field_name": "department",
                "field_type": "DROP_DOWN",
                "extra_info": {
                    "choice_form": {
                        "choice": "IT",
                        "form": {
                            "field_name": "it_budget",
                            "field_type": "NUMBER",
                        },
                    }
                },
            }
        ]
        submitted_data = {"department": "HR"}  # Different choice, doesn't trigger

        flattened = flatten_form_info(form_info, submitted_data)

        assert len(flattened) == 1  # Only parent field
        assert flattened[0]["field_name"] == "department"

    def test_flatten_nested_form_with_multi_choice_trigger(self):
        """Test flattening nested forms triggered by multi-choice selection."""
        form_info = [
            {
                "field_name": "features",
                "field_type": "MULTI_CHOICE",
                "extra_info": {
                    "choice_form": {
                        "choice": "premium",
                        "form": {
                            "field_name": "premium_level",
                            "field_type": "NUMBER",
                        },
                    }
                },
            }
        ]
        submitted_data = {"features": ["basic", "premium"], "premium_level": 3}

        flattened = flatten_form_info(form_info, submitted_data)

        assert len(flattened) == 2  # Both parent and nested field
        assert flattened[1]["field_name"] == "premium_level"

    def test_enrich_answers_basic(self):
        """Test basic answer enrichment."""
        form_info = [
            {"field_name": "name", "field_type": "TEXT"},
            {"field_name": "budget", "field_type": "NUMBER"},
        ]
        answers = {"name": "Project Alpha", "budget": 50000}

        enriched = enrich_answers(form_info, answers, save_files=False)

        assert len(enriched) == 2
        assert enriched[0]["field_name"] == "name"
        assert enriched[0]["answer"] == "Project Alpha"
        assert enriched[1]["field_name"] == "budget"
        assert enriched[1]["answer"] == 50000

    def test_enrich_answers_with_file_upload(self):
        """Test answer enrichment with file upload."""
        form_info = [
            {"field_name": "document", "field_type": "FILE"},
        ]

        # Create a mock uploaded file
        test_file = SimpleUploadedFile(
            "test.txt", b"test content", content_type="text/plain"
        )
        answers = {"document": test_file}

        # Create a mock request
        factory = RequestFactory()
        request = factory.post("/")
        request.META["HTTP_HOST"] = "testserver"

        # Test without saving files to avoid creating test files in workflows directory
        enriched = enrich_answers(
            form_info, answers, request=request, object_id=1, save_files=False
        )

        assert len(enriched) == 1
        assert enriched[0]["field_name"] == "document"
        # The answer should be the uploaded file object when save_files=False
        assert isinstance(enriched[0]["answer"], SimpleUploadedFile)
        assert enriched[0]["answer"].name == "test.txt"

    def test_enrich_answers_skips_missing_fields(self):
        """Test that enrichment skips fields not in answers."""
        form_info = [
            {"field_name": "name", "field_type": "TEXT"},
            {"field_name": "optional", "field_type": "TEXT"},
        ]
        answers = {"name": "Project Alpha"}  # optional field not provided

        enriched = enrich_answers(form_info, answers, save_files=False)

        assert len(enriched) == 1  # Only name is included
        assert enriched[0]["field_name"] == "name"


@pytest.mark.django_db
class TestProgressCalculation:
    """Test workflow progress percentage calculation."""

    @pytest.fixture
    def workflow_with_stages(self, company_user):
        """Create a workflow with 4 stages for progress testing."""
        workflow = WorkFlow.objects.create(
            name_en="Progress Test Workflow",
            name_ar="سير عمل اختبار التقدم",
            company=company_user,
            created_by=company_user,
            status="active",
            is_active=True,
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            name_en="Test Pipeline",
            name_ar="خط الاختبار",
            company=company_user,
            order=0,
        )

        for i in range(4):
            Stage.objects.create(
                pipeline=pipeline,
                name_en=f"Stage {i+1}",
                name_ar=f"المرحلة {i+1}",
                company=company_user,
                order=i,
                is_active=True,
                stage_info={
                    "approvals": [
                        {"approval_type": "self", "approval_user": company_user.id}
                    ],
                },
            )

        workflow.update_active_status()
        workflow.is_active = True
        workflow.save()

        return workflow

    def test_progress_calculation_at_completion(
        self, company_user, workflow_with_stages
    ):
        """Test that progress is 100% when workflow is completed."""
        test_obj = WorkflowTestModel.objects.create(
            name="Test Object",
            created_by=company_user,
        )

        # Attach workflow
        attachment = attach_workflow_to_object(
            test_obj, workflow_with_stages, user=company_user, auto_start=False
        )

        # Set status to completed
        attachment.status = "completed"
        attachment.current_stage = None
        attachment.current_pipeline = None
        attachment.save()

        # Check progress is 100%
        assert attachment.progress_percentage == 100

    def test_progress_calculation_midway(self, company_user, workflow_with_stages):
        """Test that progress is calculated correctly at mid-workflow."""
        test_obj = WorkflowTestModel.objects.create(
            name="Test Object",
            created_by=company_user,
        )

        # Attach workflow
        attachment = attach_workflow_to_object(
            test_obj, workflow_with_stages, user=company_user, auto_start=True
        )

        # Manually set to stage 1 if not started
        if not attachment.current_stage:
            stages = list(
                attachment.workflow.pipelines.first().stages.all().order_by("order")
            )
            attachment.current_stage = stages[0]
            attachment.current_pipeline = attachment.workflow.pipelines.first()
            attachment.status = "in_progress"
            attachment.save()

        # Should be at stage 1 of 4 (25%)
        assert attachment.progress_percentage == 25

        # Move to stage 2
        stages = list(
            attachment.workflow.pipelines.first().stages.all().order_by("order")
        )
        attachment.current_stage = stages[1]
        attachment.save()

        # Should be at stage 2 of 4 (50%)
        assert attachment.progress_percentage == 50

    def test_progress_with_multiple_pipelines(self, company_user):
        """Test progress calculation with 2 pipelines."""
        # Create workflow with 2 pipelines
        workflow = WorkFlow.objects.create(
            name_en="Multi-Pipeline Progress Test",
            name_ar="اختبار تقدم متعدد المسارات",
            company=company_user,
            created_by=company_user,
            status="active",
            is_active=True,
        )

        # Pipeline 1 with 2 stages
        pipeline1 = Pipeline.objects.create(
            workflow=workflow,
            name_en="Pipeline 1",
            name_ar="المسار 1",
            company=company_user,
            order=0,
        )

        Stage.objects.create(
            pipeline=pipeline1,
            name_en="P1 Stage 1",
            name_ar="المرحلة 1",
            company=company_user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [
                    {"approval_type": "self", "approval_user": company_user.id}
                ],
            },
        )

        Stage.objects.create(
            pipeline=pipeline1,
            name_en="P1 Stage 2",
            name_ar="المرحلة 2",
            company=company_user,
            order=1,
            is_active=True,
            stage_info={
                "approvals": [
                    {"approval_type": "self", "approval_user": company_user.id}
                ],
            },
        )

        # Pipeline 2 with 2 stages
        pipeline2 = Pipeline.objects.create(
            workflow=workflow,
            name_en="Pipeline 2",
            name_ar="المسار 2",
            company=company_user,
            order=1,
        )

        Stage.objects.create(
            pipeline=pipeline2,
            name_en="P2 Stage 1",
            name_ar="المرحلة 3",
            company=company_user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [
                    {"approval_type": "self", "approval_user": company_user.id}
                ],
            },
        )

        Stage.objects.create(
            pipeline=pipeline2,
            name_en="P2 Stage 2",
            name_ar="المرحلة 4",
            company=company_user,
            order=1,
            is_active=True,
            stage_info={
                "approvals": [
                    {"approval_type": "self", "approval_user": company_user.id}
                ],
            },
        )

        workflow.update_active_status()
        workflow.is_active = True
        workflow.save()

        # Create test object and attach workflow
        test_obj = WorkflowTestModel.objects.create(
            name="Test Object",
            created_by=company_user,
        )

        attachment = attach_workflow_to_object(
            test_obj, workflow, user=company_user, auto_start=False
        )

        # Get stages from cloned workflow
        cloned_pipelines = list(attachment.workflow.pipelines.all().order_by("order"))
        p1_stages = list(cloned_pipelines[0].stages.all().order_by("order"))
        p2_stages = list(cloned_pipelines[1].stages.all().order_by("order"))

        # Test at Pipeline 1, Stage 1 (1 of 4 = 25%)
        attachment.current_stage = p1_stages[0]
        attachment.current_pipeline = cloned_pipelines[0]
        attachment.status = "in_progress"
        attachment.save()
        assert attachment.progress_percentage == 25

        # Test at Pipeline 1, Stage 2 (2 of 4 = 50%)
        attachment.current_stage = p1_stages[1]
        attachment.save()
        assert attachment.progress_percentage == 50

        # Test at Pipeline 2, Stage 1 (3 of 4 = 75%)
        attachment.current_stage = p2_stages[0]
        attachment.current_pipeline = cloned_pipelines[1]
        attachment.save()
        assert attachment.progress_percentage == 75

        # Test at Pipeline 2, Stage 2 (4 of 4 = 100%)
        attachment.current_stage = p2_stages[1]
        attachment.save()
        assert attachment.progress_percentage == 100

        # Test completed state
        attachment.status = "completed"
        attachment.current_stage = None
        attachment.current_pipeline = None
        attachment.save()
        assert attachment.progress_percentage == 100


@pytest.mark.django_db
class TestPipelineMovement:
    """Test pipeline movement and synchronization."""

    @pytest.fixture
    def workflow_with_two_pipelines(self, company_user):
        """Create a workflow with 2 pipelines, each with 2 stages."""
        workflow = WorkFlow.objects.create(
            name_en="Multi-Pipeline Workflow",
            name_ar="سير عمل متعدد المسارات",
            company=company_user,
            created_by=company_user,
            status="active",
        )

        # Pipeline 1
        pipeline1 = Pipeline.objects.create(
            workflow=workflow,
            name_en="Pipeline 1",
            name_ar="المسار 1",
            company=company_user,
            order=0,
        )

        stage1_1 = Stage.objects.create(
            pipeline=pipeline1,
            name_en="Stage 1.1",
            name_ar="المرحلة 1.1",
            company=company_user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [
                    {"approval_type": "self", "approval_user": company_user.id}
                ],
            },
        )

        stage1_2 = Stage.objects.create(
            pipeline=pipeline1,
            name_en="Stage 1.2",
            name_ar="المرحلة 1.2",
            company=company_user,
            order=1,
            is_active=True,
            stage_info={
                "approvals": [
                    {"approval_type": "self", "approval_user": company_user.id}
                ],
            },
        )

        # Pipeline 2
        pipeline2 = Pipeline.objects.create(
            workflow=workflow,
            name_en="Pipeline 2",
            name_ar="المسار 2",
            company=company_user,
            order=1,
        )

        stage2_1 = Stage.objects.create(
            pipeline=pipeline2,
            name_en="Stage 2.1",
            name_ar="المرحلة 2.1",
            company=company_user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [
                    {"approval_type": "self", "approval_user": company_user.id}
                ],
            },
        )

        stage2_2 = Stage.objects.create(
            pipeline=pipeline2,
            name_en="Stage 2.2",
            name_ar="المرحلة 2.2",
            company=company_user,
            order=1,
            is_active=True,
            stage_info={
                "approvals": [
                    {"approval_type": "self", "approval_user": company_user.id}
                ],
            },
        )

        workflow.update_active_status()

        # Ensure workflow is active
        workflow.is_active = True
        workflow.save()

        return {
            "workflow": workflow,
            "pipeline1": pipeline1,
            "pipeline2": pipeline2,
            "stage1_1": stage1_1,
            "stage1_2": stage1_2,
            "stage2_1": stage2_1,
            "stage2_2": stage2_2,
        }

    def test_pipeline_sync_on_save(self, company_user, workflow_with_two_pipelines):
        """Test that current_pipeline is automatically synced with current_stage."""
        test_obj = WorkflowTestModel.objects.create(
            name="Test Object",
            created_by=company_user,
        )

        workflow = workflow_with_two_pipelines["workflow"]
        stage1_1 = workflow_with_two_pipelines["stage1_1"]
        pipeline1 = workflow_with_two_pipelines["pipeline1"]

        # Attach workflow
        attachment = attach_workflow_to_object(
            test_obj, workflow, user=company_user, auto_start=False
        )

        # Manually set current_stage without setting current_pipeline
        attachment.current_stage = stage1_1
        attachment.current_pipeline = None
        attachment.save()

        # Reload from database
        attachment.refresh_from_db()

        # current_pipeline should be auto-synced
        assert attachment.current_pipeline is not None
        assert attachment.current_pipeline.id == pipeline1.id

    def test_move_within_same_pipeline(self, company_user, workflow_with_two_pipelines):
        """Test moving from one stage to another within the same pipeline."""
        test_obj = WorkflowTestModel.objects.create(
            name="Test Object",
            created_by=company_user,
        )

        workflow = workflow_with_two_pipelines["workflow"]

        # Attach workflow
        attachment = attach_workflow_to_object(
            test_obj, workflow, user=company_user, auto_start=False
        )

        # Get the actual pipelines and stages from the workflow
        pipelines = workflow.pipelines.order_by("order").all()
        pipeline1 = pipelines[0]

        stages_p1 = pipeline1.stages.order_by("order").all()
        stage1_1 = stages_p1[0]
        stage1_2 = stages_p1[1]

        # Manually start the workflow
        start_workflow_for_object(test_obj, user=company_user)
        attachment.refresh_from_db()

        # Should start at stage 1.1
        assert attachment.current_stage is not None
        assert attachment.current_stage.order == stage1_1.order
        assert attachment.current_pipeline.order == pipeline1.order

        # Get next stage
        next_stage = attachment.next_stage
        assert next_stage is not None
        assert next_stage.order == stage1_2.order

    def test_move_across_pipelines(self, company_user, workflow_with_two_pipelines):
        """Test moving from last stage of pipeline 1 to first stage of pipeline 2."""
        test_obj = WorkflowTestModel.objects.create(
            name="Test Object",
            created_by=company_user,
        )

        workflow = workflow_with_two_pipelines["workflow"]

        # Attach and start workflow
        attachment = attach_workflow_to_object(
            test_obj, workflow, user=company_user, auto_start=False
        )

        # Get the actual pipelines and stages from the attached workflow
        pipelines = workflow.pipelines.order_by("order").all()
        pipeline1 = pipelines[0]
        pipeline2 = pipelines[1]

        stage1_2 = pipeline1.stages.order_by("order").last()
        stage2_1 = pipeline2.stages.order_by("order").first()

        # Manually set to last stage of pipeline 1
        attachment.current_stage = stage1_2
        attachment.current_pipeline = pipeline1
        attachment.status = WorkflowAttachmentStatus.IN_PROGRESS
        attachment.save()

        # Get next stage
        next_stage = attachment.next_stage

        # Should be first stage of pipeline 2
        assert next_stage is not None
        assert next_stage.order == stage2_1.order
        assert next_stage.pipeline.order == pipeline2.order

    def test_pipeline_movement_with_approval_flow(self, company_user):
        """Test movement between pipelines using ONLY WorkflowApprovalSerializer.

        This test demonstrates automatic workflow progression:
        1. Use WorkflowApprovalSerializer to approve each stage
        2. Workflow progresses AUTOMATICALLY via handlers (no manual move_to_next_stage!)
        3. Verify pipeline transitions happen correctly

        This is how developers should use the workflow engine - just approve with
        the serializer and the workflow progresses automatically.
        """
        from approval_workflow.choices import ApprovalStatus
        from approval_workflow.models import ApprovalFlow, ApprovalInstance

        # Create workflow with 2 pipelines, 2 stages each
        workflow = WorkFlow.objects.create(
            name_en="Multi-Pipeline Workflow",
            name_ar="سير عمل متعدد المسارات",
            company=company_user,
            created_by=company_user,
            status="active",
        )

        # Pipeline 1: Finance
        pipeline1 = Pipeline.objects.create(
            workflow=workflow,
            name_en="Finance Pipeline",
            name_ar="مسار المالية",
            company=company_user,
            order=0,
        )

        stage1_1 = Stage.objects.create(
            pipeline=pipeline1,
            name_en="Finance Review",
            name_ar="مراجعة مالية",
            company=company_user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [
                    {"approval_type": "user", "approval_user": company_user.id}
                ],
            },
        )

        stage1_2 = Stage.objects.create(
            pipeline=pipeline1,
            name_en="Finance Approval",
            name_ar="موافقة مالية",
            company=company_user,
            order=1,
            is_active=True,
            stage_info={
                "approvals": [
                    {"approval_type": "user", "approval_user": company_user.id}
                ],
            },
        )

        # Pipeline 2: Management
        pipeline2 = Pipeline.objects.create(
            workflow=workflow,
            name_en="Management Pipeline",
            name_ar="مسار الإدارة",
            company=company_user,
            order=1,
        )

        stage2_1 = Stage.objects.create(
            pipeline=pipeline2,
            name_en="Manager Review",
            name_ar="مراجعة المدير",
            company=company_user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [
                    {"approval_type": "user", "approval_user": company_user.id}
                ],
            },
        )

        stage2_2 = Stage.objects.create(
            pipeline=pipeline2,
            name_en="Executive Approval",
            name_ar="موافقة تنفيذية",
            company=company_user,
            order=1,
            is_active=True,
            stage_info={
                "approvals": [
                    {"approval_type": "user", "approval_user": company_user.id}
                ],
            },
        )

        workflow.update_active_status()
        workflow.is_active = True
        workflow.save()

        # Create test object
        test_obj = WorkflowTestModel.objects.create(
            name="Test Object",
            created_by=company_user,
        )

        # Attach and start workflow
        attachment = attach_workflow_to_object(
            test_obj, workflow, user=company_user, auto_start=True
        )

        # Verify we're in Pipeline 1, Stage 1
        attachment.refresh_from_db()

        # Get the cloned workflow's pipelines and stages
        cloned_workflow = attachment.workflow
        cloned_pipelines = list(cloned_workflow.pipelines.order_by("order"))
        cloned_pipeline1 = cloned_pipelines[0]
        cloned_pipeline2 = cloned_pipelines[1]

        cloned_stages_p1 = list(cloned_pipeline1.stages.order_by("order"))
        cloned_stage1_1 = cloned_stages_p1[0]
        cloned_stage1_2 = cloned_stages_p1[1]

        cloned_stages_p2 = list(cloned_pipeline2.stages.order_by("order"))
        cloned_stage2_1 = cloned_stages_p2[0]
        cloned_stage2_2 = cloned_stages_p2[1]

        assert attachment.current_pipeline.id == cloned_pipeline1.id
        assert attachment.current_stage.id == cloned_stage1_1.id
        assert attachment.status == "in_progress"
        assert attachment.progress_percentage == 25  # 1/4 stages

        # Create mock request
        factory = RequestFactory()
        request = factory.post("/")
        request.user = company_user

        # ===== APPROVE STAGE 1.1 (Finance Review) =====
        content_type = ContentType.objects.get_for_model(WorkflowTestModel)
        approval_flow = ApprovalFlow.objects.get(
            content_type=content_type,
            object_id=test_obj.pk,
        )

        current_approval = ApprovalInstance.objects.get(
            flow=approval_flow,
            status=ApprovalStatus.CURRENT,
        )
        assert current_approval.assigned_to.id == company_user.id

        serializer = WorkflowApprovalSerializer(
            instance=test_obj,
            data={"action": ApprovalStatus.APPROVED},
            context={"request": request},
        )
        assert serializer.is_valid()
        serializer.save()

        # Workflow should progress AUTOMATICALLY via handler!
        attachment.refresh_from_db()
        assert attachment.current_pipeline.id == cloned_pipeline1.id
        assert attachment.current_stage.id == cloned_stage1_2.id
        assert attachment.status == "in_progress"
        assert attachment.progress_percentage == 50  # 2/4 stages

        # ===== APPROVE STAGE 1.2 (Finance Approval) =====
        current_approval = ApprovalInstance.objects.get(
            flow=approval_flow,
            status=ApprovalStatus.CURRENT,
        )

        serializer = WorkflowApprovalSerializer(
            instance=test_obj,
            data={"action": ApprovalStatus.APPROVED},
            context={"request": request},
        )
        assert serializer.is_valid()
        serializer.save()

        # ===== VERIFY PIPELINE TRANSITION (happens automatically!) =====
        attachment.refresh_from_db()
        assert (
            attachment.current_pipeline.id == cloned_pipeline2.id
        )  # Moved to Pipeline 2!
        assert attachment.current_stage.id == cloned_stage2_1.id
        assert attachment.status == "in_progress"
        assert attachment.progress_percentage == 75  # 3/4 stages

        # ===== APPROVE STAGE 2.1 (Manager Review) =====
        current_approval = ApprovalInstance.objects.get(
            flow=approval_flow,
            status=ApprovalStatus.CURRENT,
        )

        serializer = WorkflowApprovalSerializer(
            instance=test_obj,
            data={"action": ApprovalStatus.APPROVED},
            context={"request": request},
        )
        assert serializer.is_valid()
        serializer.save()

        # Workflow progresses automatically
        attachment.refresh_from_db()
        assert attachment.current_pipeline.id == cloned_pipeline2.id
        assert attachment.current_stage.id == cloned_stage2_2.id
        assert attachment.status == "in_progress"
        assert attachment.progress_percentage == 100  # 4/4 stages

        # ===== APPROVE FINAL STAGE 2.2 (Executive Approval) =====
        current_approval = ApprovalInstance.objects.get(
            flow=approval_flow,
            status=ApprovalStatus.CURRENT,
        )

        serializer = WorkflowApprovalSerializer(
            instance=test_obj,
            data={"action": ApprovalStatus.APPROVED},
            context={"request": request},
        )
        assert serializer.is_valid()
        serializer.save()

        # ===== VERIFY WORKFLOW COMPLETION (happens automatically!) =====
        attachment.refresh_from_db()
        assert attachment.status == "completed"
        assert attachment.progress_percentage == 100
        assert attachment.completed_at is not None


@pytest.mark.django_db
class TestWorkflowCompletion:
    """Test workflow completion when all stages are approved."""

    @pytest.fixture
    def workflow_with_one_pipeline(self, company_user):
        """Create a workflow with 1 pipeline and 2 stages."""
        workflow = WorkFlow.objects.create(
            name_en="Single Pipeline Workflow",
            name_ar="سير عمل أحادي المسار",
            company=company_user,
            created_by=company_user,
            status="active",
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            name_en="Pipeline 1",
            name_ar="المسار 1",
            company=company_user,
            order=0,
        )

        stage1 = Stage.objects.create(
            pipeline=pipeline,
            name_en="Stage 1",
            name_ar="المرحلة 1",
            company=company_user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [
                    {"approval_type": "self", "approval_user": company_user.id}
                ],
            },
        )

        stage2 = Stage.objects.create(
            pipeline=pipeline,
            name_en="Stage 2",
            name_ar="المرحلة 2",
            company=company_user,
            order=1,
            is_active=True,
            stage_info={
                "approvals": [
                    {"approval_type": "self", "approval_user": company_user.id}
                ],
            },
        )

        workflow.update_active_status()

        # Ensure workflow is active
        workflow.is_active = True
        workflow.save()

        return {
            "workflow": workflow,
            "pipeline": pipeline,
            "stage1": stage1,
            "stage2": stage2,
        }

    def test_next_stage_returns_none_at_end(
        self, company_user, workflow_with_one_pipeline
    ):
        """Test that next_stage returns None when at the last stage of the last pipeline."""
        test_obj = WorkflowTestModel.objects.create(
            name="Test Object",
            created_by=company_user,
        )

        workflow = workflow_with_one_pipeline["workflow"]
        stage2 = workflow_with_one_pipeline["stage2"]
        pipeline = workflow_with_one_pipeline["pipeline"]

        # Attach workflow
        attachment = attach_workflow_to_object(
            test_obj, workflow, user=company_user, auto_start=False
        )

        # Set to last stage
        attachment.current_stage = stage2
        attachment.current_pipeline = pipeline
        attachment.status = WorkflowAttachmentStatus.IN_PROGRESS
        attachment.save()

        # Get next stage
        next_stage = attachment.next_stage

        # Should be None (no more stages)
        assert next_stage is None

    def test_workflow_completes_after_last_stage(
        self, company_user, workflow_with_one_pipeline
    ):
        """Test that workflow status changes to COMPLETED after the last stage is approved."""
        test_obj = WorkflowTestModel.objects.create(
            name="Test Object",
            created_by=company_user,
        )

        workflow = workflow_with_one_pipeline["workflow"]
        stage2 = workflow_with_one_pipeline["stage2"]
        pipeline = workflow_with_one_pipeline["pipeline"]

        # Attach workflow
        attachment = attach_workflow_to_object(
            test_obj, workflow, user=company_user, auto_start=False
        )

        # Set to last stage with IN_PROGRESS status
        attachment.current_stage = stage2
        attachment.current_pipeline = pipeline
        attachment.status = WorkflowAttachmentStatus.IN_PROGRESS
        attachment.save()

        # Move to next stage (should complete the workflow)
        updated_attachment = move_to_next_stage(test_obj, user=company_user)

        # Workflow should be completed
        assert updated_attachment.status == WorkflowAttachmentStatus.COMPLETED
        assert updated_attachment.current_stage is None
        assert updated_attachment.current_pipeline is None
        assert updated_attachment.completed_at is not None


@pytest.mark.django_db
class TestFormEnrichmentIntegration:
    """Test form enrichment integration with workflow approval serializer."""

    @pytest.fixture
    def workflow_with_form(self, company_user):
        """Create a workflow with a stage that has a form with nested fields."""
        workflow = WorkFlow.objects.create(
            name_en="Form Workflow",
            name_ar="سير عمل النموذج",
            company=company_user,
            created_by=company_user,
            status="active",
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            name_en="Pipeline 1",
            name_ar="المسار 1",
            company=company_user,
            order=0,
        )

        # Create stage with nested form
        stage = Stage.objects.create(
            pipeline=pipeline,
            name_en="Form Stage",
            name_ar="مرحلة النموذج",
            company=company_user,
            order=0,
            is_active=True,
            form_info=[
                {"field_name": "name", "field_type": "TEXT"},
                {"field_name": "budget", "field_type": "NUMBER"},
                {
                    "field_name": "department",
                    "field_type": "DROP_DOWN",
                    "extra_info": {
                        "choice_form": {
                            "choice": "IT",
                            "form": {
                                "field_name": "it_details",
                                "field_type": "TEXT",
                            },
                        }
                    },
                },
            ],
            stage_info={
                "approvals": [
                    {"approval_type": "self", "approval_user": company_user.id}
                ],
            },
        )

        workflow.update_active_status()

        # Ensure workflow is active
        workflow.is_active = True
        workflow.save()

        return {
            "workflow": workflow,
            "pipeline": pipeline,
            "stage": stage,
        }

    def test_serializer_enriches_form_data(self, company_user, workflow_with_form):
        """Test that WorkflowApprovalSerializer enriches form data with answer keys."""
        test_obj = WorkflowTestModel.objects.create(
            name="Test Object",
            created_by=company_user,
        )

        workflow = workflow_with_form["workflow"]
        stage = workflow_with_form["stage"]

        # Attach and start workflow
        attachment = attach_workflow_to_object(
            test_obj, workflow, user=company_user, auto_start=False
        )
        attachment.current_stage = stage
        attachment.status = WorkflowAttachmentStatus.IN_PROGRESS
        attachment.save()

        # Create mock request
        factory = RequestFactory()
        request = factory.post("/")
        request.user = company_user

        # Create serializer with form data
        form_data = {
            "name": "Project Alpha",
            "budget": 50000,
            "department": "IT",
            "it_details": "Extra IT information",
        }

        serializer = WorkflowApprovalSerializer(
            instance=test_obj,
            data={
                "action": ApprovalStatus.APPROVED,
                "form_data": form_data,
            },
            context={"request": request},
        )

        # Create a mock approval object with form
        from unittest.mock import Mock

        mock_form = Mock()
        mock_form.form_info = stage.form_info  # Use form_info from stage
        mock_form.id = 1

        mock_approval = Mock()
        mock_approval.form = mock_form
        mock_approval.id = 1

        # Test the enrichment method directly with mock approval
        enriched = serializer._enrich_form_data(form_data, mock_approval)

        # Should have enriched all fields including nested ones
        assert isinstance(enriched, list)
        assert len(enriched) == 4  # All 4 fields (name, budget, department, it_details)

        # Check that each field has an "answer" key
        field_names = {field["field_name"] for field in enriched}
        assert "name" in field_names
        assert "budget" in field_names
        assert "department" in field_names
        assert "it_details" in field_names

        # Check that answers are present
        for field in enriched:
            assert "answer" in field
            assert field["answer"] == form_data[field["field_name"]]
