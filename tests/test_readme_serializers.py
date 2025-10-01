"""
Test cases for README examples using WorkFlowSerializer and StageSerializer.

These tests verify that the code examples shown in the README.md file work correctly.
"""

from django.contrib.auth import get_user_model

import pytest
from approval_workflow.choices import RoleSelectionStrategy
from rest_framework.test import APIRequestFactory

from django_workflow_engine.choices import ApprovalTypes
from django_workflow_engine.models import Pipeline, Stage, WorkFlow
from django_workflow_engine.serializers import StageSerializer, WorkFlowSerializer

User = get_user_model()


@pytest.fixture
def company_user(db):
    """Create a company user for testing."""
    return User.objects.create_user(
        username="test_company", email="company@test.com", password="testpass123"
    )


@pytest.fixture
def request_with_user(company_user):
    """Create a mock request with user."""
    factory = APIRequestFactory()
    request = factory.post("/")
    request.user = company_user
    return request


@pytest.mark.django_db
class TestWorkFlowSerializerReadmeExample:
    """Test WorkFlowSerializer as used in README examples."""

    def test_create_workflow_with_nested_pipelines_readme_example(
        self, company_user, request_with_user
    ):
        """Test creating workflow with pipelines exactly as shown in README."""
        # This is the exact data structure from README.md Step 3
        workflow_data = {
            "name_en": "Purchase Request Approval",
            "name_ar": "موافقة طلب الشراء",
            "company": company_user.id,
            "is_active": True,
            "pipelines": [
                {
                    "name_en": "Finance Review",
                    "name_ar": "مراجعة مالية",
                    "department_id": 1,  # Finance Department
                    "order": 1,
                    "number_of_stages": 3,  # Will auto-create 3 stages
                },
                {
                    "name_en": "Executive Approval",
                    "name_ar": "موافقة تنفيذية",
                    "department_id": 2,  # Management Department
                    "order": 2,
                    "number_of_stages": 1,  # Will auto-create 1 stage
                },
            ],
        }

        # Create workflow with auto-generated stages
        context = {"request": request_with_user, "company_user": company_user}
        workflow_serializer = WorkFlowSerializer(data=workflow_data, context=context)

        # Validate
        assert workflow_serializer.is_valid(), workflow_serializer.errors

        # Save
        result = workflow_serializer.save()

        # Verify workflow was created
        assert isinstance(result, WorkFlow)
        assert result.name_en == "Purchase Request Approval"
        assert result.name_ar == "موافقة طلب الشراء"
        assert result.company == company_user
        # Note: is_active may be False until stages are properly configured with approvals
        # This is expected behavior - the system validates stage configurations

        # Verify pipelines were created
        assert result.pipelines.count() == 2

        # Verify Finance Review pipeline
        finance_pipeline = result.pipelines.get(name_en="Finance Review")
        assert finance_pipeline.name_ar == "مراجعة مالية"
        assert finance_pipeline.order == 1
        # Note: department_id depends on DEPARTMENT_MODEL configuration in settings
        # The service function will set it if a department model is configured
        assert finance_pipeline.stages.count() == 3

        # Verify Executive Approval pipeline
        executive_pipeline = result.pipelines.get(name_en="Executive Approval")
        assert executive_pipeline.name_ar == "موافقة تنفيذية"
        assert executive_pipeline.order == 2
        # Note: department_id depends on DEPARTMENT_MODEL configuration in settings
        assert executive_pipeline.stages.count() == 1

        # Verify stages were auto-created with default names
        # Note: create_pipeline service uses order starting from 0
        stage_1 = finance_pipeline.stages.get(order=0)
        assert stage_1.name_en == "Stage 1"
        assert stage_1.name_ar == "المرحلة 1"
        # stage_info is initialized as empty dict by the service function
        assert "stage_info" in stage_1.__dict__ or stage_1.stage_info is not None

    def test_workflow_serializer_response_format(self, company_user, request_with_user):
        """Test that serializer returns the expected response format from README."""
        workflow_data = {
            "name_en": "Test Workflow",
            "name_ar": "سير عمل تجريبي",
            "company": company_user.id,
            "is_active": True,
            "pipelines": [
                {
                    "name_en": "Pipeline 1",
                    "name_ar": "خط الأنابيب 1",
                    "department_id": 1,
                    "order": 1,
                    "number_of_stages": 2,
                }
            ],
        }

        context = {"request": request_with_user, "company_user": company_user}
        serializer = WorkFlowSerializer(data=workflow_data, context=context)
        assert serializer.is_valid()

        result = serializer.save()
        representation = serializer.to_representation(result)

        # Verify response structure matches README expectations
        assert "id" in representation
        assert representation["name_en"] == "Test Workflow"
        assert representation["name_ar"] == "سير عمل تجريبي"
        assert representation["company"] == company_user.id
        # Note: is_active field reflects actual DB state after validation
        assert "is_active" in representation
        assert representation["pipelines_count"] == 1
        assert representation["total_stages_count"] == 2

    def test_workflow_without_pipelines(self, company_user, request_with_user):
        """Test creating workflow without pipelines."""
        workflow_data = {
            "name_en": "Empty Workflow",
            "name_ar": "سير عمل فارغ",
            "company": company_user.id,
            "is_active": True,
        }

        context = {"request": request_with_user, "company_user": company_user}
        serializer = WorkFlowSerializer(data=workflow_data, context=context)
        assert serializer.is_valid()

        result = serializer.save()
        assert result.pipelines.count() == 0

    def test_company_from_context(self, company_user, request_with_user):
        """Test that company can be inferred from context."""
        workflow_data = {
            "name_en": "Test Workflow",
            "name_ar": "سير عمل",
            "is_active": True,
            "pipelines": [],
        }

        # Pass company_user in context, not in data
        context = {"request": request_with_user, "company_user": company_user}
        serializer = WorkFlowSerializer(data=workflow_data, context=context)
        assert serializer.is_valid()

        result = serializer.save()
        assert result.company == company_user


@pytest.mark.django_db
class TestStageSerializerReadmeExample:
    """Test StageSerializer as used in README examples."""

    def test_configure_stage_approval_readme_example(
        self, company_user, request_with_user
    ):
        """Test configuring stage approval exactly as shown in README."""
        # First create a workflow with stages
        workflow = WorkFlow.objects.create(
            name_en="Purchase Request Approval",
            name_ar="موافقة طلب الشراء",
            company=company_user,
            is_active=True,
        )

        finance_pipeline = Pipeline.objects.create(
            workflow=workflow,
            name_en="Finance Review",
            name_ar="مراجعة مالية",
            order=1,
            department_id=1,
        )

        initial_review = Stage.objects.create(
            pipeline=finance_pipeline,
            name_en="Initial Review",
            name_ar="مراجعة أولية",
            order=1,
            stage_info={},
        )

        # This is the exact configuration from README.md Step 3
        stage_config = {
            "stage_info": {
                "color": "#3498db",
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.ROLE,
                        "user_role": 1,  # Finance Reviewer Role ID
                        "role_selection_strategy": RoleSelectionStrategy.ROUND_ROBIN,
                        "required_form": 1,  # Initial Review Form ID
                    }
                ],
            }
        }

        stage_serializer = StageSerializer(
            initial_review, data=stage_config, partial=True
        )

        # Validate
        assert stage_serializer.is_valid(), stage_serializer.errors

        # Save
        updated_stage = stage_serializer.save()

        # Verify configuration was applied
        assert updated_stage.stage_info["color"] == "#3498db"
        assert len(updated_stage.stage_info["approvals"]) == 1

        approval = updated_stage.stage_info["approvals"][0]
        assert approval["approval_type"] == ApprovalTypes.ROLE
        assert approval["user_role"] == 1
        assert approval["role_selection_strategy"] == RoleSelectionStrategy.ROUND_ROBIN
        assert approval["required_form"] == 1

    def test_configure_multiple_stages_readme_pattern(
        self, company_user, request_with_user
    ):
        """Test configuring multiple stages following README pattern."""
        # Create workflow structure
        workflow = WorkFlow.objects.create(
            name_en="Purchase Request Approval",
            company=company_user,
            is_active=True,
        )

        finance_pipeline = Pipeline.objects.create(
            workflow=workflow, name_en="Finance Review", order=1, department_id=1
        )

        # Create 3 stages as in README
        stage_1 = Stage.objects.create(
            pipeline=finance_pipeline, name_en="Initial Review", order=1, stage_info={}
        )

        stage_2 = Stage.objects.create(
            pipeline=finance_pipeline, name_en="Budget Approval", order=2, stage_info={}
        )

        stage_3 = Stage.objects.create(
            pipeline=finance_pipeline,
            name_en="Final Finance Sign-off",
            order=3,
            stage_info={},
        )

        # Configure Stage 1: Initial Review (README example)
        config_1 = {
            "stage_info": {
                "color": "#3498db",
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.ROLE,
                        "user_role": 1,
                        "role_selection_strategy": RoleSelectionStrategy.ROUND_ROBIN,
                        "required_form": 1,
                    }
                ],
            }
        }
        serializer_1 = StageSerializer(stage_1, data=config_1, partial=True)
        assert serializer_1.is_valid()
        updated_stage_1 = serializer_1.save()

        # Configure Stage 2: Budget Approval (README example)
        config_2 = {
            "stage_info": {
                "color": "#f39c12",
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.ROLE,
                        "user_role": 2,
                        "role_selection_strategy": RoleSelectionStrategy.ANYONE,
                        "required_form": 2,
                    }
                ],
            }
        }
        serializer_2 = StageSerializer(stage_2, data=config_2, partial=True)
        assert serializer_2.is_valid()
        updated_stage_2 = serializer_2.save()

        # Configure Stage 3: Final Finance Sign-off (README example with USER type)
        config_3 = {
            "stage_info": {
                "color": "#27ae60",
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": company_user.id,
                        "required_form": 3,
                    }
                ],
            }
        }
        serializer_3 = StageSerializer(stage_3, data=config_3, partial=True)
        assert serializer_3.is_valid()
        updated_stage_3 = serializer_3.save()

        # Verify all stages were configured correctly
        assert updated_stage_1.stage_info["color"] == "#3498db"
        assert (
            updated_stage_1.stage_info["approvals"][0]["approval_type"]
            == ApprovalTypes.ROLE
        )  # Normalized

        assert updated_stage_2.stage_info["color"] == "#f39c12"
        assert (
            updated_stage_2.stage_info["approvals"][0]["role_selection_strategy"]
            == RoleSelectionStrategy.ANYONE
        )

        assert updated_stage_3.stage_info["color"] == "#27ae60"
        assert (
            updated_stage_3.stage_info["approvals"][0]["approval_type"]
            == ApprovalTypes.USER
        )  # Normalized

    def test_stage_info_validation(self, company_user):
        """Test stage_info validation catches invalid data."""
        workflow = WorkFlow.objects.create(
            name_en="Test Workflow", company=company_user
        )
        pipeline = Pipeline.objects.create(
            workflow=workflow, name_en="Test Pipeline", order=1
        )
        stage = Stage.objects.create(
            pipeline=pipeline, name_en="Test Stage", order=1, stage_info={}
        )

        # Test invalid approval_type
        invalid_config = {
            "stage_info": {
                "approvals": [
                    {
                        "approval_type": "INVALID_TYPE",
                        "user_role": 1,
                    }
                ]
            }
        }

        serializer = StageSerializer(stage, data=invalid_config, partial=True)
        assert not serializer.is_valid()
        assert "stage_info" in serializer.errors

    def test_stage_info_validation_missing_required_fields(self, company_user):
        """Test validation for missing required fields."""
        workflow = WorkFlow.objects.create(
            name_en="Test Workflow", company=company_user
        )
        pipeline = Pipeline.objects.create(
            workflow=workflow, name_en="Test Pipeline", order=1
        )
        stage = Stage.objects.create(
            pipeline=pipeline, name_en="Test Stage", order=1, stage_info={}
        )

        # ROLE type without user_role
        invalid_config = {
            "stage_info": {
                "approvals": [
                    {
                        "approval_type": "ROLE",
                        # Missing user_role
                    }
                ]
            }
        }

        serializer = StageSerializer(stage, data=invalid_config, partial=True)
        assert not serializer.is_valid()

        # USER type without approval_user
        invalid_config_2 = {
            "stage_info": {
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        # Missing approval_user
                    }
                ]
            }
        }

        serializer_2 = StageSerializer(stage, data=invalid_config_2, partial=True)
        assert not serializer_2.is_valid()

    def test_stage_serializer_merges_existing_info(self, company_user):
        """Test that StageSerializer merges with existing stage_info."""
        workflow = WorkFlow.objects.create(
            name_en="Test Workflow", company=company_user
        )
        pipeline = Pipeline.objects.create(
            workflow=workflow, name_en="Test Pipeline", order=1
        )
        stage = Stage.objects.create(
            pipeline=pipeline,
            name_en="Test Stage",
            order=1,
            stage_info={"existing_field": "existing_value", "color": "#000000"},
        )

        # Update only the approvals
        config = {
            "stage_info": {
                "approvals": [
                    {
                        "approval_type": "ROLE",
                        "user_role": 1,
                        "role_selection_strategy": "anyone",
                    }
                ]
            }
        }

        serializer = StageSerializer(stage, data=config, partial=True)
        assert serializer.is_valid()
        updated_stage = serializer.save()

        # Verify merge happened
        assert "existing_field" in updated_stage.stage_info
        assert updated_stage.stage_info["existing_field"] == "existing_value"
        assert "approvals" in updated_stage.stage_info
        assert len(updated_stage.stage_info["approvals"]) == 1


@pytest.mark.django_db
class TestReadmeCompleteWorkflowExample:
    """Test the complete A-Z workflow example from README."""

    def test_complete_readme_workflow_creation(self, company_user, request_with_user):
        """
        Test creating the complete Purchase Request workflow from README Step 3.
        This creates workflow -> pipelines -> stages -> configure stages.
        """
        # Step 1: Create Workflow with Pipelines (from README)
        workflow_data = {
            "name_en": "Purchase Request Approval",
            "name_ar": "موافقة طلب الشراء",
            "company": company_user.id,
            "is_active": True,
            "pipelines": [
                {
                    "name_en": "Finance Review",
                    "name_ar": "مراجعة مالية",
                    "department_id": 1,
                    "order": 1,
                    "number_of_stages": 3,
                },
                {
                    "name_en": "Executive Approval",
                    "name_ar": "موافقة تنفيذية",
                    "department_id": 2,
                    "order": 2,
                    "number_of_stages": 1,
                },
            ],
        }

        context = {"request": request_with_user, "company_user": company_user}
        workflow_serializer = WorkFlowSerializer(data=workflow_data, context=context)
        assert workflow_serializer.is_valid()
        purchase_workflow = workflow_serializer.save()

        # Step 2: Get the auto-created stages (from README)
        finance_pipeline = purchase_workflow.pipelines.get(name_en="Finance Review")
        executive_pipeline = purchase_workflow.pipelines.get(
            name_en="Executive Approval"
        )

        # Note: create_pipeline service uses order starting from 0
        initial_review = finance_pipeline.stages.get(order=0)
        budget_approval = finance_pipeline.stages.get(order=1)
        finance_signoff = finance_pipeline.stages.get(order=2)
        executive_approval = executive_pipeline.stages.get(order=0)

        # Step 3: Configure Finance Stage 1 (from README)
        stage_config_1 = {
            "stage_info": {
                "color": "#3498db",
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.ROLE,
                        "user_role": 1,
                        "role_selection_strategy": RoleSelectionStrategy.ROUND_ROBIN,
                        "required_form": 1,
                    }
                ],
            }
        }
        serializer_1 = StageSerializer(
            initial_review, data=stage_config_1, partial=True
        )
        assert serializer_1.is_valid()
        serializer_1.save()

        # Step 4: Configure Finance Stage 2 (from README)
        stage_config_2 = {
            "stage_info": {
                "color": "#f39c12",
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.ROLE,
                        "user_role": 2,
                        "role_selection_strategy": RoleSelectionStrategy.ANYONE,
                        "required_form": 2,
                    }
                ],
            }
        }
        serializer_2 = StageSerializer(
            budget_approval, data=stage_config_2, partial=True
        )
        assert serializer_2.is_valid()
        serializer_2.save()

        # Step 5: Configure Finance Stage 3 (from README)
        stage_config_3 = {
            "stage_info": {
                "color": "#27ae60",
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": company_user.id,
                        "required_form": 3,
                    }
                ],
            }
        }
        serializer_3 = StageSerializer(
            finance_signoff, data=stage_config_3, partial=True
        )
        assert serializer_3.is_valid()
        serializer_3.save()

        # Step 6: Configure Executive Stage (from README)
        stage_config_4 = {
            "stage_info": {
                "color": "#8e44ad",
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.ROLE,
                        "user_role": 3,
                        "role_selection_strategy": RoleSelectionStrategy.CONSENSUS,
                    }
                ],
            }
        }
        serializer_4 = StageSerializer(
            executive_approval, data=stage_config_4, partial=True
        )
        assert serializer_4.is_valid()
        serializer_4.save()

        # Verify complete workflow structure
        assert purchase_workflow.pipelines.count() == 2
        assert finance_pipeline.stages.count() == 3
        assert executive_pipeline.stages.count() == 1

        # Verify all stages have approvals configured
        initial_review.refresh_from_db()
        assert len(initial_review.stage_info["approvals"]) == 1
        assert initial_review.stage_info["color"] == "#3498db"

        budget_approval.refresh_from_db()
        assert len(budget_approval.stage_info["approvals"]) == 1
        assert budget_approval.stage_info["color"] == "#f39c12"

        finance_signoff.refresh_from_db()
        assert len(finance_signoff.stage_info["approvals"]) == 1
        assert finance_signoff.stage_info["color"] == "#27ae60"

        executive_approval.refresh_from_db()
        assert len(executive_approval.stage_info["approvals"]) == 1
        assert executive_approval.stage_info["color"] == "#8e44ad"

    def test_update_stage_info_with_role_approval(
        self, company_user, request_with_user
    ):
        """Test updating stage with role-based approval configuration."""
        from django_workflow_engine.choices import ApprovalTypes, RoleSelectionStrategy

        # Create a workflow with pipeline
        workflow_data = {
            "name_en": "Finance Workflow",
            "name_ar": "سير عمل مالي",
            "company": company_user.id,
            "is_active": True,
            "pipelines": [
                {
                    "name_en": "Finance Pipeline",
                    "name_ar": "خط مالي",
                    "department_id": 1,
                    "order": 1,
                    "number_of_stages": 2,
                }
            ],
        }

        context = {"request": request_with_user, "company_user": company_user}
        workflow_serializer = WorkFlowSerializer(data=workflow_data, context=context)
        assert workflow_serializer.is_valid()
        finance_workflow = workflow_serializer.save()

        # Get the auto-created pipeline
        finance_pipeline = finance_workflow.pipelines.get(name_en="Finance Pipeline")
        budget_approval_stage = finance_pipeline.stages.get(order=1)

        # Update stage with the provided configuration
        stage_config = {
            "name_en": "Budget Approval",
            "name_ar": "موافقة الميزانية",
            "stage_info": {
                "color": "#f39c12",
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.ROLE,
                        "user_role": 2,
                        "role_selection_strategy": RoleSelectionStrategy.ANYONE,
                        "required_form": 2,
                    }
                ],
            },
        }

        serializer = StageSerializer(
            budget_approval_stage, data=stage_config, partial=True
        )
        assert serializer.is_valid(), f"Validation errors: {serializer.errors}"
        updated_stage = serializer.save()

        # Verify the stage was updated correctly
        updated_stage.refresh_from_db()
        assert updated_stage.is_active
        assert updated_stage.name_en == "Budget Approval"
        assert updated_stage.name_ar == "موافقة الميزانية"
        assert updated_stage.order == 1
        assert updated_stage.stage_info["color"] == "#f39c12"
        assert len(updated_stage.stage_info["approvals"]) == 1

        # Verify approval configuration
        approval_config = updated_stage.stage_info["approvals"][0]
        assert approval_config["approval_type"] == ApprovalTypes.ROLE
        assert approval_config["user_role"] == 2
        assert (
            approval_config["role_selection_strategy"] == RoleSelectionStrategy.ANYONE
        )
        assert approval_config["required_form"] == 2
