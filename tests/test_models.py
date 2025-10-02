"""Test cases for workflow engine models."""

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase

import pytest
from approval_workflow.models import ApprovalFlow

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
from sandbox.testapp.models import Company, Department

User = get_user_model()


class WorkFlowModelTest(TestCase):
    """Test cases for WorkFlow model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        # Create a company user that represents the organization
        import uuid

        unique_id = str(uuid.uuid4())[:8]
        self.company_user = User.objects.create_user(
            username=f"testcompany{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )
        # Create a real company for testing
        # Create a company user that represents the organization
        import uuid

        unique_id = str(uuid.uuid4())[:8]
        self.company_user = User.objects.create_user(
            username=f"testcompany{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )
        self.company = Company.objects.create(name="Test Company")
        self.department = Department.objects.create(
            name="Test Department", company=self.company
        )

    def test_workflow_creation(self):
        """Test creating a workflow."""
        workflow = WorkFlow.objects.create(
            company=self.company_user,
            name_en="Test Workflow",
            name_ar="سير عمل تجريبي",
            description="Test workflow description",
            status=WorkflowStatus.ACTIVE,
            created_by=self.user,
        )

        self.assertEqual(workflow.name_en, "Test Workflow")
        self.assertEqual(workflow.status, WorkflowStatus.ACTIVE)
        self.assertFalse(workflow.is_active)  # No pipelines yet

    def test_workflow_is_active_with_pipelines(self):
        """Test workflow is_active property with complete pipelines."""
        workflow = WorkFlow.objects.create(
            company=self.company_user,
            name_en="Test Workflow",
            name_ar="سير عمل تجريبي",
            status=WorkflowStatus.ACTIVE,
            created_by=self.user,
        )

        # Create pipeline with stages
        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=self.company_user,
            name_en="Test Pipeline",
            name_ar="خط أنابيب تجريبي",
            department=self.department,
            created_by=self.user,
        )

        stage = Stage(
            pipeline=pipeline,
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
        stage.save(skip_workflow_update=True)

        # Manually update workflow status
        workflow.update_active_status()
        workflow.refresh_from_db()
        self.assertTrue(workflow.is_active)


class PipelineModelTest(TestCase):
    """Test cases for Pipeline model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        # Create a company user that represents the organization
        import uuid

        unique_id = str(uuid.uuid4())[:8]
        self.company_user = User.objects.create_user(
            username=f"testcompany{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )
        self.company = Company.objects.create(name="Test Company")
        self.department = Department.objects.create(
            name="Test Department", company=self.company
        )

        self.workflow = WorkFlow.objects.create(
            company=self.company_user,
            name_en="Test Workflow",
            name_ar="سير عمل تجريبي",
            status=WorkflowStatus.ACTIVE,
            created_by=self.user,
        )

    def test_pipeline_creation(self):
        """Test creating a pipeline."""
        pipeline = Pipeline.objects.create(
            workflow=self.workflow,
            company=self.company_user,
            name_en="Test Pipeline",
            name_ar="خط أنابيب تجريبي",
            department=self.department,
            created_by=self.user,
            order=0,
        )

        self.assertEqual(pipeline.name_en, "Test Pipeline")
        self.assertEqual(pipeline.workflow, self.workflow)
        self.assertEqual(pipeline.order, 0)

    def test_pipeline_stage_creation(self):
        """Test creating stages for a pipeline."""
        pipeline = Pipeline.objects.create(
            workflow=self.workflow,
            company=self.company_user,
            name_en="Test Pipeline",
            name_ar="خط أنابيب تجريبي",
            department=self.department,
            created_by=self.user,
        )

        stage1 = Stage.objects.create(
            pipeline=pipeline,
            company=self.company_user,
            name_en="Stage 1",
            name_ar="المرحلة 1",
            created_by=self.user,
            order=0,
        )

        stage2 = Stage.objects.create(
            pipeline=pipeline,
            company=self.company_user,
            name_en="Stage 2",
            name_ar="المرحلة 2",
            created_by=self.user,
            order=1,
        )

        self.assertEqual(pipeline.stages.count(), 2)
        self.assertEqual(stage1.order, 0)
        self.assertEqual(stage2.order, 1)


class WorkflowActionModelTest(TestCase):
    """Test cases for WorkflowAction model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        # Create a company user that represents the organization
        import uuid

        unique_id = str(uuid.uuid4())[:8]
        self.company_user = User.objects.create_user(
            username=f"testcompany{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )
        self.company = Company.objects.create(name="Test Company")
        self.department = Department.objects.create(
            name="Test Department", company=self.company
        )

        self.workflow = WorkFlow.objects.create(
            company=self.company_user,
            name_en="Test Workflow",
            name_ar="سير عمل تجريبي",
            status=WorkflowStatus.ACTIVE,
            created_by=self.user,
        )

        self.pipeline = Pipeline.objects.create(
            workflow=self.workflow,
            company=self.company_user,
            name_en="Test Pipeline",
            name_ar="خط أنابيب تجريبي",
            department=self.department,
            created_by=self.user,
        )

        self.stage = Stage.objects.create(
            pipeline=self.pipeline,
            company=self.company_user,
            name_en="Test Stage",
            name_ar="مرحلة تجريبية",
            created_by=self.user,
        )

    def test_workflow_action_creation(self):
        """Test creating workflow-level action."""
        action = WorkflowAction.objects.create(
            workflow=self.workflow,
            action_type=ActionType.AFTER_APPROVE,
            function_path="django_workflow_engine.default_actions.default_send_email_after_approve",
            is_active=True,
            order=0,
        )

        self.assertEqual(action.action_type, ActionType.AFTER_APPROVE)
        self.assertEqual(action.scope_level, "workflow")
        self.assertEqual(action.scope_object, self.workflow)

    def test_stage_action_creation(self):
        """Test creating stage-level action."""
        action = WorkflowAction.objects.create(
            stage=self.stage,
            action_type=ActionType.AFTER_APPROVE,
            function_path="myapp.custom_actions.custom_approval_action",
            is_active=True,
            order=0,
            parameters={"custom_param": "value"},
        )

        self.assertEqual(action.scope_level, "stage")
        self.assertEqual(action.scope_object, self.stage)
        self.assertEqual(action.parameters["custom_param"], "value")

    def test_action_scope_validation(self):
        """Test that exactly one scope must be set."""
        # Test creating action with no scope (should fail validation)
        action = WorkflowAction(
            action_type=ActionType.AFTER_APPROVE,
            function_path="test.function",
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            action.clean()

        # Test creating action with multiple scopes (should fail validation)
        action = WorkflowAction(
            workflow=self.workflow,
            stage=self.stage,  # Multiple scopes
            action_type=ActionType.AFTER_APPROVE,
            function_path="test.function",
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            action.clean()


class WorkflowAttachmentModelTest(TestCase):
    """Test cases for WorkflowAttachment model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        # Create a company user that represents the organization
        import uuid

        unique_id = str(uuid.uuid4())[:8]
        self.company_user = User.objects.create_user(
            username=f"testcompany{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )
        self.company = Company.objects.create(name="Test Company")
        self.department = Department.objects.create(
            name="Test Department", company=self.company
        )

        self.workflow = WorkFlow.objects.create(
            company=self.company_user,
            name_en="Test Workflow",
            name_ar="سير عمل تجريبي",
            status=WorkflowStatus.ACTIVE,
            created_by=self.user,
        )

        self.pipeline = Pipeline.objects.create(
            workflow=self.workflow,
            company=self.company_user,
            name_en="Test Pipeline",
            name_ar="خط أنابيب تجريبي",
            department=self.department,
            created_by=self.user,
        )

        self.stage = Stage.objects.create(
            pipeline=self.pipeline,
            company=self.company_user,
            name_en="Test Stage",
            name_ar="مرحلة تجريبية",
            created_by=self.user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": self.user.id}]
            },
        )

    def test_workflow_attachment_creation(self):
        """Test creating workflow attachment to user model."""
        content_type = ContentType.objects.get_for_model(User)

        attachment = WorkflowAttachment.objects.create(
            workflow=self.workflow,
            content_type=content_type,
            object_id=str(self.user.pk),
            status=WorkflowAttachmentStatus.NOT_STARTED,
            started_by=self.user,
            metadata={"test": "data"},
        )

        self.assertEqual(attachment.target, self.user)
        self.assertEqual(attachment.status, WorkflowAttachmentStatus.NOT_STARTED)
        self.assertEqual(attachment.metadata["test"], "data")

    def test_workflow_attachment_progress(self):
        """Test workflow attachment progress calculation."""
        # Create second stage
        Stage.objects.create(
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

        content_type = ContentType.objects.get_for_model(User)

        attachment = WorkflowAttachment.objects.create(
            workflow=self.workflow,
            content_type=content_type,
            object_id=str(self.user.pk),
            current_stage=self.stage,
            current_pipeline=self.pipeline,
            status=WorkflowAttachmentStatus.IN_PROGRESS,
            started_by=self.user,
        )

        # Should be 50% (1 of 2 stages)
        self.assertEqual(attachment.progress_percentage, 50)

    def test_next_stage_calculation(self):
        """Test next stage calculation."""
        stage2 = Stage.objects.create(
            pipeline=self.pipeline,
            company=self.company_user,
            name_en="Stage 2",
            name_ar="المرحلة 2",
            created_by=self.user,
            order=1,
        )

        content_type = ContentType.objects.get_for_model(User)

        attachment = WorkflowAttachment.objects.create(
            workflow=self.workflow,
            content_type=content_type,
            object_id=str(self.user.pk),
            current_stage=self.stage,
            current_pipeline=self.pipeline,
            status=WorkflowAttachmentStatus.IN_PROGRESS,
            started_by=self.user,
        )

        self.assertEqual(attachment.next_stage, stage2)


class WorkflowConfigurationModelTest(TestCase):
    """Test cases for WorkflowConfiguration model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_workflow_configuration_creation(self):
        """Test creating workflow configuration for a model."""
        content_type = ContentType.objects.get_for_model(User)

        config = WorkflowConfiguration.objects.create(
            content_type=content_type,
            is_enabled=True,
            auto_start_workflow=True,
            status_field="workflow_status",
            stage_field="current_stage",
        )

        self.assertEqual(config.content_type, content_type)
        self.assertTrue(config.is_enabled)
        self.assertTrue(config.auto_start_workflow)
        self.assertEqual(config.status_field, "workflow_status")


class WorkflowCloneHiddenFieldTest(TestCase):
    """Test cases for is_hidden field on WorkFlow, Pipeline, and Stage models."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        import uuid

        unique_id = str(uuid.uuid4())[:8]
        self.company_user = User.objects.create_user(
            username=f"testcompany{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )
        self.company = Company.objects.create(name="Test Company")
        self.department = Department.objects.create(
            name="Test Department", company=self.company
        )

    def test_main_workflow_is_not_hidden_and_cloned_is_hidden(self):
        """Test that main workflows have is_hidden=False and cloned workflows have is_hidden=True."""
        # Create main workflow with pipelines and stages
        main_workflow = WorkFlow.objects.create(
            company=self.company_user,
            name_en="Main Workflow",
            name_ar="سير العمل الرئيسي",
            status=WorkflowStatus.ACTIVE,
            created_by=self.user,
        )

        main_pipeline = Pipeline.objects.create(
            workflow=main_workflow,
            company=self.company_user,
            name_en="Main Pipeline",
            name_ar="خط أنابيب رئيسي",
            department=self.department,
            created_by=self.user,
            order=0,
        )

        main_stage = Stage.objects.create(
            pipeline=main_pipeline,
            company=self.company_user,
            name_en="Main Stage",
            name_ar="المرحلة الرئيسية",
            created_by=self.user,
            order=0,
            is_active=True,
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": self.user.id}]
            },
        )

        # Verify main objects have is_hidden=False
        self.assertFalse(
            main_workflow.is_hidden, "Main workflow should have is_hidden=False"
        )
        self.assertFalse(
            main_pipeline.is_hidden, "Main pipeline should have is_hidden=False"
        )
        self.assertFalse(main_stage.is_hidden, "Main stage should have is_hidden=False")

        # Clone the workflow
        cloned_workflow = main_workflow.clone()

        # Verify cloned workflow has is_hidden=True
        self.assertTrue(
            cloned_workflow.is_hidden, "Cloned workflow should have is_hidden=True"
        )

        # Get cloned pipeline and stage
        cloned_pipeline = cloned_workflow.pipelines.first()
        cloned_stage = cloned_pipeline.stages.first()

        # Verify cloned pipeline and stage have is_hidden=True
        self.assertTrue(
            cloned_pipeline.is_hidden, "Cloned pipeline should have is_hidden=True"
        )
        self.assertTrue(
            cloned_stage.is_hidden, "Cloned stage should have is_hidden=True"
        )

        # Verify cloned_from relationships
        self.assertEqual(cloned_workflow.cloned_from, main_workflow)
        self.assertEqual(cloned_pipeline.cloned_from, main_pipeline)
        self.assertEqual(cloned_stage.cloned_from, main_stage)


@pytest.mark.django_db
class TestApprovalWorkflowIntegration:
    """Test integration with django-approval-workflow package."""

    def test_approval_flow_creation(self):
        """Test that approval flows can be created for workflow attachments."""
        user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # Create approval flow for the user object
        content_type = ContentType.objects.get_for_model(User)

        approval_flow = ApprovalFlow.objects.create(
            content_type=content_type, object_id=str(user.pk)
        )

        assert approval_flow.target == user
        assert approval_flow.content_type == content_type
