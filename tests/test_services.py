"""Test cases for workflow engine services."""

import uuid
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

import pytest
from approval_workflow.choices import ApprovalStatus
from approval_workflow.models import ApprovalFlow, ApprovalInstance

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
from django_workflow_engine.services import (
    attach_workflow_to_object,
    complete_workflow,
    create_pipeline,
    execute_action_function,
    get_actions_for_event,
    get_workflow_attachment,
    is_model_workflow_enabled,
    move_to_next_stage,
    register_model_for_workflow,
    reject_workflow_stage,
    set_pipeline_department,
    start_workflow_for_object,
    trigger_workflow_event,
)
from django_workflow_engine.utils import build_approval_steps
from sandbox.testapp.models import Company, Department

User = get_user_model()


class WorkflowServicesTest(TestCase):
    """Test cases for workflow services."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
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

        # Create complete workflow structure
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
            created_by=self.user,
            order=0,
        )

        self.stage1 = Stage.objects.create(
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

        self.stage2 = Stage.objects.create(
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

        # Update workflow active status
        self.workflow.update_active_status()

    def test_attach_workflow_to_object(self):
        """Test attaching workflow to an object with automatic cloning."""
        attachment = attach_workflow_to_object(
            obj=self.user,
            workflow=self.workflow,
            user=self.user,
            auto_start=False,
            metadata={"test": "data"},
        )

        self.assertEqual(attachment.target, self.user)
        # The attached workflow should be a clone, not the original
        self.assertNotEqual(attachment.workflow, self.workflow)
        self.assertEqual(attachment.workflow.cloned_from, self.workflow)
        self.assertEqual(attachment.workflow.name_en, "Test Workflow (Copy)")
        self.assertEqual(attachment.status, WorkflowAttachmentStatus.NOT_STARTED)
        self.assertEqual(attachment.metadata["test"], "data")

        # Verify the clone has the same structure as the original
        self.assertEqual(
            attachment.workflow.pipelines.count(), self.workflow.pipelines.count()
        )
        self.assertEqual(
            attachment.workflow.pipelines.first().stages.count(),
            self.workflow.pipelines.first().stages.count(),
        )

    @patch("approval_workflow.services.start_flow")
    @patch("django_workflow_engine.utils.build_approval_steps")
    def test_start_workflow_for_object(self, mock_build_steps, mock_start_flow):
        """Test starting workflow for an object."""
        # First attach the workflow
        attachment = attach_workflow_to_object(
            obj=self.user, workflow=self.workflow, user=self.user, auto_start=False
        )

        # Mock approval steps
        mock_build_steps.return_value = [{"step": 1}]

        # Start the workflow
        modified_attachment = start_workflow_for_object(self.user, self.user)

        self.assertEqual(
            modified_attachment.status, WorkflowAttachmentStatus.IN_PROGRESS
        )
        # Current stage and pipeline should be from the cloned workflow
        self.assertEqual(
            modified_attachment.current_stage.name_en, f"{self.stage1.name_en} (Copy)"
        )
        self.assertEqual(
            modified_attachment.current_pipeline.name_en,
            f"{self.pipeline.name_en} (Copy)",
        )
        # Verify they are cloned versions, not originals
        self.assertNotEqual(modified_attachment.current_stage, self.stage1)
        self.assertNotEqual(modified_attachment.current_pipeline, self.pipeline)
        self.assertIsNotNone(modified_attachment.started_at)

        # Verify approval flow was started
        mock_start_flow.assert_called_once()

    @patch("approval_workflow.services.start_flow")
    @patch("django_workflow_engine.utils.build_approval_steps")
    def test_move_to_next_stage(self, mock_build_steps, mock_start_flow):
        """Test moving to next stage in workflow."""
        # Setup attachment in progress
        attachment = attach_workflow_to_object(
            obj=self.user, workflow=self.workflow, user=self.user, auto_start=False
        )
        attachment.status = WorkflowAttachmentStatus.IN_PROGRESS
        attachment.current_stage = self.stage1
        attachment.current_pipeline = self.pipeline
        attachment.save()

        mock_build_steps.return_value = [{"step": 2}]

        # Move to next stage
        modified_attachment = move_to_next_stage(self.user, self.user)

        self.assertEqual(modified_attachment.current_stage, self.stage2)
        mock_start_flow.assert_called_once()

    def test_reject_workflow_stage(self):
        """Test rejecting workflow at current stage."""
        # Setup attachment in progress
        attachment = attach_workflow_to_object(
            obj=self.user, workflow=self.workflow, user=self.user, auto_start=False
        )
        attachment.status = WorkflowAttachmentStatus.IN_PROGRESS
        attachment.current_stage = self.stage1
        attachment.save()

        # Reject workflow
        modified_attachment = reject_workflow_stage(
            obj=self.user, stage=self.stage1, user=self.user, reason="Not approved"
        )

        self.assertEqual(modified_attachment.status, WorkflowAttachmentStatus.REJECTED)
        self.assertIsNotNone(modified_attachment.completed_at)
        self.assertEqual(
            modified_attachment.metadata["rejection_reason"], "Not approved"
        )

    def test_complete_workflow(self):
        """Test completing workflow."""
        # Setup attachment in progress
        attachment = attach_workflow_to_object(
            obj=self.user, workflow=self.workflow, user=self.user, auto_start=False
        )
        attachment.status = WorkflowAttachmentStatus.IN_PROGRESS
        attachment.save()

        # Complete workflow
        modified_attachment = complete_workflow(self.user, self.user)

        self.assertEqual(modified_attachment.status, WorkflowAttachmentStatus.COMPLETED)
        self.assertIsNotNone(modified_attachment.completed_at)

    def test_register_model_for_workflow(self):
        """Test registering model for workflow functionality."""
        config = register_model_for_workflow(
            model_class=User,
            auto_start=True,
            default_workflow=self.workflow,
            status_field="workflow_status",
            stage_field="current_stage",
        )

        self.assertTrue(config.auto_start_workflow)
        self.assertEqual(config.default_workflow, self.workflow)
        self.assertEqual(config.status_field, "workflow_status")

    def test_get_workflow_attachment(self):
        """Test getting workflow attachment for object."""
        # No attachment initially
        attachment = get_workflow_attachment(self.user)
        self.assertIsNone(attachment)

        # Create attachment
        created_attachment = attach_workflow_to_object(
            obj=self.user, workflow=self.workflow, user=self.user, auto_start=False
        )

        # Should find attachment
        found_attachment = get_workflow_attachment(self.user)
        self.assertEqual(found_attachment, created_attachment)

    def test_is_model_workflow_enabled(self):
        """Test checking if model is workflow enabled."""
        # Not enabled initially
        self.assertFalse(is_model_workflow_enabled(User))

        # Register model
        register_model_for_workflow(User, auto_start=True)

        # Should be enabled
        self.assertTrue(is_model_workflow_enabled(User))

    def test_create_pipeline_with_department(self):
        """Test creating pipeline with department_id sets department_generic_fk."""
        pipeline_data = {
            "name_en": "Test Pipeline with Department",
            "name_ar": "خط أنابيب مع القسم",
            "department_id": self.department.id,
            "number_of_stages": 2,
        }

        pipeline = create_pipeline(
            workflow=self.workflow,
            pipeline_data=pipeline_data,
            created_by=self.user,
        )

        # Verify pipeline was created
        self.assertIsNotNone(pipeline)
        self.assertEqual(pipeline.name_en, "Test Pipeline with Department")

        # Verify department generic foreign key is set
        self.assertIsNotNone(pipeline.department_content_type)
        self.assertIsNotNone(pipeline.department_id)
        self.assertEqual(pipeline.department_id, self.department.id)

        # Verify department property works
        self.assertEqual(pipeline.department, self.department)
        self.assertEqual(pipeline.department_name, self.department.name)

        # Verify stages were created
        self.assertEqual(pipeline.stages.count(), 2)

    def test_create_pipeline_without_department(self):
        """Test creating pipeline without department_id doesn't set department_generic_fk."""
        pipeline_data = {
            "name_en": "Test Pipeline without Department",
            "name_ar": "خط أنابيب بدون القسم",
            "number_of_stages": 1,
        }

        pipeline = create_pipeline(
            workflow=self.workflow,
            pipeline_data=pipeline_data,
            created_by=self.user,
        )

        # Verify pipeline was created
        self.assertIsNotNone(pipeline)

        # Verify department generic foreign key is not set
        self.assertIsNone(pipeline.department_content_type)
        self.assertIsNone(pipeline.department_id)
        self.assertIsNone(pipeline.department)

    def test_set_pipeline_department(self):
        """Test set_pipeline_department function sets department_generic_fk correctly."""
        # Create a pipeline without department
        pipeline = Pipeline.objects.create(
            workflow=self.workflow,
            company=self.company_user,
            name_en="Test Pipeline",
            name_ar="خط أنابيب",
            created_by=self.user,
            order=5,
        )

        # Initially no department
        self.assertIsNone(pipeline.department)

        # Set department using the service function
        set_pipeline_department(pipeline, self.department.id)
        pipeline.save()

        # Reload from database
        pipeline.refresh_from_db()

        # Verify department is set
        self.assertIsNotNone(pipeline.department_content_type)
        self.assertIsNotNone(pipeline.department_id)
        self.assertEqual(pipeline.department_id, self.department.id)
        self.assertEqual(pipeline.department, self.department)

    def test_build_approval_steps_role_based_no_assigned_to_conflict(self):
        """Test that build_approval_steps doesn't create both assigned_to and assigned_role for role-based approvals."""
        # Create a mock role model
        from django.contrib.auth.models import Group

        from approval_workflow.choices import RoleSelectionStrategy

        from django_workflow_engine.choices import ApprovalTypes

        role = Group.objects.create(name="Test Role")

        # Create a stage with role-based approval
        stage = Stage.objects.create(
            pipeline=self.pipeline,
            name_en="Role Approval Stage",
            name_ar="مرحلة الموافقة على الدور",
            order=3,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.ROLE,
                        "user_role": role.id,
                        "role_selection_strategy": RoleSelectionStrategy.ANYONE,
                    }
                ]
            },
        )

        # Build approval steps
        with self.settings(APPROVAL_ROLE_MODEL="auth.Group"):
            steps = build_approval_steps(stage, self.user)

        # Verify we have steps
        self.assertEqual(len(steps), 1)
        step = steps[0]

        # Critical assertion: role-based approval should NOT have assigned_to
        self.assertNotIn(
            "assigned_to",
            step,
            "Role-based approval step should not have 'assigned_to' key",
        )

        # Should have assigned_role
        self.assertIn(
            "assigned_role",
            step,
            "Role-based approval step should have 'assigned_role' key",
        )
        self.assertEqual(step["assigned_role"], role)

        # Should have role_selection_strategy
        self.assertIn("role_selection_strategy", step)
        self.assertEqual(step["role_selection_strategy"], RoleSelectionStrategy.ANYONE)

    def test_build_approval_steps_user_based_no_role_conflict(self):
        """Test that build_approval_steps doesn't create assigned_role for user-based approvals."""
        from django_workflow_engine.choices import ApprovalTypes

        # Create a stage with user-based approval
        stage = Stage.objects.create(
            pipeline=self.pipeline,
            name_en="User Approval Stage",
            name_ar="مرحلة موافقة المستخدم",
            order=4,
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

        # Build approval steps
        steps = build_approval_steps(stage, self.user)

        # Verify we have steps
        self.assertEqual(len(steps), 1)
        step = steps[0]

        # Critical assertion: user-based approval should NOT have assigned_role
        self.assertNotIn(
            "assigned_role",
            step,
            "User-based approval step should not have 'assigned_role' key",
        )

        # Should have assigned_to
        self.assertIn(
            "assigned_to",
            step,
            "User-based approval step should have 'assigned_to' key",
        )
        self.assertEqual(step["assigned_to"], self.user)

        # Should NOT have role_selection_strategy for user-based approval
        self.assertNotIn(
            "role_selection_strategy",
            step,
            "User-based approval step should not have 'role_selection_strategy' key",
        )

    def test_build_approval_steps_mixed_approvals_no_conflicts(self):
        """Test that build_approval_steps handles mixed approval types correctly."""
        from django.contrib.auth.models import Group

        from approval_workflow.choices import RoleSelectionStrategy

        from django_workflow_engine.choices import ApprovalTypes

        role = Group.objects.create(name="Test Role 2")
        another_user = User.objects.create_user(
            username="approver", email="approver@test.com", password="testpass123"
        )

        # Create a stage with mixed approval types
        stage = Stage.objects.create(
            pipeline=self.pipeline,
            name_en="Mixed Approval Stage",
            name_ar="مرحلة موافقة مختلطة",
            order=5,
            is_active=True,
            stage_info={
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.ROLE,
                        "user_role": role.id,
                        "role_selection_strategy": RoleSelectionStrategy.CONSENSUS,
                    },
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": another_user.id,
                    },
                    {
                        "approval_type": ApprovalTypes.SELF,
                        "approval_user": self.user.id,
                    },
                ]
            },
        )

        # Build approval steps
        with self.settings(APPROVAL_ROLE_MODEL="auth.Group"):
            steps = build_approval_steps(stage, self.user)

        # Verify we have 3 steps
        self.assertEqual(len(steps), 3)

        # Step 1: Role-based - should have assigned_role, NOT assigned_to
        step1 = steps[0]
        self.assertNotIn("assigned_to", step1)
        self.assertIn("assigned_role", step1)
        self.assertEqual(step1["assigned_role"], role)
        self.assertEqual(
            step1["role_selection_strategy"], RoleSelectionStrategy.CONSENSUS
        )

        # Step 2: User-based - should have assigned_to, NOT assigned_role
        step2 = steps[1]
        self.assertIn("assigned_to", step2)
        self.assertNotIn("assigned_role", step2)
        self.assertEqual(step2["assigned_to"], another_user)

        # Step 3: Self-approval - should have assigned_to, NOT assigned_role
        step3 = steps[2]
        self.assertIn("assigned_to", step3)
        self.assertNotIn("assigned_role", step3)
        self.assertEqual(step3["assigned_to"], self.user)


class WorkflowActionServicesTest(TestCase):
    """Test cases for workflow action services."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
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

        # Create workflow structure
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
            created_by=self.user,
            order=0,
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

        # Create workflow attachment
        self.attachment = attach_workflow_to_object(
            obj=self.user, workflow=self.workflow, user=self.user, auto_start=False
        )
        self.attachment.current_stage = self.stage
        self.attachment.current_pipeline = self.pipeline
        self.attachment.save()

        # Update workflow active status
        self.workflow.update_active_status()

    def test_get_actions_for_event_stage_level(self):
        """Test getting actions with stage-level priority."""
        # Create stage-level action
        stage_action = WorkflowAction.objects.create(
            stage=self.stage,
            action_type=ActionType.AFTER_APPROVE,
            function_path="test.stage_action",
            is_active=True,
            order=0,
        )

        # Create workflow-level action (lower priority)
        WorkflowAction.objects.create(
            workflow=self.workflow,
            action_type=ActionType.AFTER_APPROVE,
            function_path="test.workflow_action",
            is_active=True,
            order=0,
        )

        actions = get_actions_for_event(self.attachment, ActionType.AFTER_APPROVE)

        # Should return stage action (higher priority)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0], stage_action)

    def test_get_actions_for_event_inheritance(self):
        """Test action inheritance: Stage -> Pipeline -> Workflow -> Default."""
        # No stage action, should check pipeline level
        actions = get_actions_for_event(self.attachment, ActionType.AFTER_APPROVE)

        # Should create default action since no custom actions exist
        self.assertEqual(len(actions), 1)
        self.assertIn("default_send_email_after_approve", actions[0].function_path)

    def test_execute_action_function_success(self):
        """Test successful action function execution."""
        # Mock a simple function
        with patch("importlib.import_module") as mock_import:
            mock_module = Mock()
            mock_function = Mock(return_value="success")
            mock_module.test_function = mock_function
            mock_import.return_value = mock_module

            result = execute_action_function(
                function_path="test.module.test_function",
                context={"test": "data"},
                parameters={"param": "value"},
            )

            self.assertEqual(result, "success")
            mock_function.assert_called_once_with(test="data", param="value")

    def test_execute_action_function_import_error(self):
        """Test action function execution with import error."""
        result = execute_action_function(
            function_path="nonexistent.module.function", context={}, parameters={}
        )

        self.assertIsNone(result)

    @patch("django_workflow_engine.services.execute_action_function")
    def test_trigger_workflow_event(self, mock_execute):
        """Test triggering workflow event with actions."""
        # Create test action
        WorkflowAction.objects.create(
            stage=self.stage,
            action_type=ActionType.AFTER_APPROVE,
            function_path="test.action",
            is_active=True,
            order=0,
        )

        mock_execute.return_value = "executed"

        results = trigger_workflow_event(
            self.attachment, ActionType.AFTER_APPROVE, user=self.user
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], "executed")
        mock_execute.assert_called_once()


@pytest.mark.django_db
class TestApprovalWorkflowIntegration:
    """Test integration with django-approval-workflow package."""

    def test_workflow_approval_handler_integration(self):
        """Test that WorkflowApprovalHandler integrates with approval workflow."""
        from django_workflow_engine.handlers import WorkflowApprovalHandler

        user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # Create workflow structure
        unique_id = str(uuid.uuid4())[:8]
        company_user = User.objects.create_user(
            username=f"testcompany{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )
        company = Company.objects.create(name="Test Company")
        department = Department.objects.create(name="Test Department", company=company)
        workflow = WorkFlow.objects.create(
            company=company_user,
            name_en="Test Workflow",
            name_ar="سير عمل تجريبي",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            name_ar="خط أنابيب تجريبي",
            created_by=user,
        )

        stage = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Test Stage",
            name_ar="مرحلة تجريبية",
            created_by=user,
            is_active=True,
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": user.id}]
            },
        )

        # Create workflow attachment
        attachment = attach_workflow_to_object(
            obj=user, workflow=workflow, user=user, auto_start=False
        )
        attachment.current_stage = stage
        attachment.current_pipeline = pipeline
        attachment.status = WorkflowAttachmentStatus.IN_PROGRESS
        attachment.save()

        # Update workflow active status
        workflow.update_active_status()

        # Create approval instance
        content_type = ContentType.objects.get_for_model(User)
        approval_flow = ApprovalFlow.objects.create(
            content_type=content_type, object_id=str(user.pk)
        )

        approval_instance = ApprovalInstance.objects.create(
            flow=approval_flow,
            step_number=1,
            status=ApprovalStatus.APPROVED,
            assigned_to=user,
            action_user=user,
        )

        # Test handler
        handler = WorkflowApprovalHandler(user)

        # Test final approval (should trigger workflow progression)
        with patch("django_workflow_engine.services.move_to_next_stage") as mock_move:
            mock_move.return_value = attachment
            handler.on_final_approve(approval_instance)
            mock_move.assert_called_once_with(user)

        # Test rejection (should trigger rejection actions)
        with patch(
            "django_workflow_engine.services.reject_workflow_stage"
        ) as mock_reject:
            handler.after_reject(approval_instance)
            mock_reject.assert_called_once()

    def test_approval_serializer_integration(self):
        """Test WorkflowApprovalSerializer integration."""
        from django_workflow_engine.serializers import WorkflowApprovalSerializer

        user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # Create workflow and attachment
        unique_id = str(uuid.uuid4())[:8]
        company_user = User.objects.create_user(
            username=f"testcompany{unique_id}",
            email=f"company{unique_id}@example.com",
            password="testpass123",
        )
        company = Company.objects.create(name="Test Company")
        department = Department.objects.create(name="Test Department", company=company)

        workflow = WorkFlow.objects.create(
            company=company_user,
            name_en="Test Workflow",
            name_ar="سير عمل تجريبي",
            status=WorkflowStatus.ACTIVE,
            created_by=user,
        )

        pipeline = Pipeline.objects.create(
            workflow=workflow,
            company=company_user,
            name_en="Test Pipeline",
            name_ar="خط أنابيب تجريبي",
            created_by=user,
        )

        stage = Stage.objects.create(
            pipeline=pipeline,
            company=company_user,
            name_en="Test Stage",
            name_ar="مرحلة تجريبية",
            is_active=True,
            created_by=user,
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": user.id}]
            },
        )

        # Update workflow active status
        workflow.update_active_status()

        attachment = attach_workflow_to_object(
            obj=user, workflow=workflow, user=user, auto_start=False
        )

        # Set workflow to in_progress manually
        attachment.status = WorkflowAttachmentStatus.IN_PROGRESS
        attachment.current_stage = stage
        attachment.current_pipeline = pipeline
        attachment.save()

        # Create approval flow and instance for the test
        from django.contrib.contenttypes.models import ContentType

        content_type = ContentType.objects.get_for_model(User)
        approval_flow = ApprovalFlow.objects.create(
            content_type=content_type, object_id=str(user.pk)
        )
        approval_instance = ApprovalInstance.objects.create(
            flow=approval_flow,
            step_number=1,
            status=ApprovalStatus.CURRENT,
            assigned_to=user,
            action_user=user,
            comment="Test approval instance",
        )

        # Test approval serializer
        serializer = WorkflowApprovalSerializer(
            data={
                "action": ApprovalStatus.APPROVED,
                "form_data": {"comment": "Approved"},
            },
            instance=user,
            context={"request": type("Request", (), {"user": user})()},
        )

        if not serializer.is_valid():
            print(f"Serializer validation errors: {serializer.errors}")
        assert serializer.is_valid()

        # Test rejection
        serializer = WorkflowApprovalSerializer(
            data={
                "action": ApprovalStatus.REJECTED,
                "reason": "Not approved",
            },
            instance=user,
            context={"request": type("Request", (), {"user": user})()},
        )

        assert serializer.is_valid()
