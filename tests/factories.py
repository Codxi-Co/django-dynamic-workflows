"""
Factory classes for creating test data for django-workflow-engine
"""

from django.contrib.auth import get_user_model

import factory
from approval_workflow.choices import RoleSelectionStrategy
from factory.django import DjangoModelFactory

from django_workflow_engine.choices import ApprovalTypes
from django_workflow_engine.models import Pipeline, Stage, WorkFlow, WorkflowAttachment
from django_workflow_engine.services import register_model_for_workflow
from sandbox.testapp.models import Company, Department, WorkflowTestModel

User = get_user_model()


class CompanyFactory(DjangoModelFactory):
    """Factory for Company model"""

    class Meta:
        model = Company

    name = factory.Sequence(lambda n: f"Test Company {n}")


class DepartmentFactory(DjangoModelFactory):
    """Factory for Department model"""

    class Meta:
        model = Department

    name = factory.Sequence(lambda n: f"Department {n}")
    company = factory.SubFactory(CompanyFactory)


class UserFactory(DjangoModelFactory):
    """Factory for User model"""

    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@test.com")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")


class WorkFlowFactory(DjangoModelFactory):
    """Factory for WorkFlow model"""

    class Meta:
        model = WorkFlow

    name_en = factory.Sequence(lambda n: f"Workflow {n}")
    name_ar = factory.LazyAttribute(lambda obj: f"سير العمل {obj.name_en.split()[-1]}")
    company = factory.SubFactory(CompanyFactory)
    is_active = True
    description = factory.Faker("text", max_nb_chars=200)

    @classmethod
    def _after_postgeneration(cls, instance, create, results=None):
        """Override to prevent automatic save after postgeneration"""
        pass

    @factory.post_generation
    def slug(obj, create, extracted, **kwargs):
        """Generate a slug-like identifier for testing"""
        if create:
            obj.slug_identifier = f"workflow_{obj.id}"
            obj.save()


class PipelineFactory(DjangoModelFactory):
    """Factory for Pipeline model"""

    class Meta:
        model = Pipeline

    name_en = factory.Sequence(lambda n: f"Pipeline {n}")
    name_ar = factory.LazyAttribute(
        lambda obj: f"خط الأنابيب {obj.name_en.split()[-1]}"
    )
    workflow = factory.SubFactory(WorkFlowFactory)
    department = factory.SubFactory(DepartmentFactory)
    company = factory.SelfAttribute("workflow.company")
    order = factory.Sequence(lambda n: n)


class StageFactory(DjangoModelFactory):
    """Factory for Stage model"""

    class Meta:
        model = Stage

    name_en = factory.Sequence(lambda n: f"Stage {n}")
    name_ar = factory.LazyAttribute(lambda obj: f"مرحلة {obj.name_en.split()[-1]}")
    pipeline = factory.SubFactory(PipelineFactory)
    company = factory.SelfAttribute("pipeline.company")
    order = factory.Sequence(lambda n: n)
    is_active = True
    stage_info = factory.Dict({"color": "#3498db", "approvals": []})


class WorkflowTestModelFactory(DjangoModelFactory):
    """Factory for WorkflowTestModel"""

    class Meta:
        model = WorkflowTestModel

    name = factory.Sequence(lambda n: f"Test Object {n}")
    description = factory.Faker("text", max_nb_chars=200)
    status = "pending"
    amount = factory.Faker("pydecimal", left_digits=5, right_digits=2, positive=True)
    priority = factory.Iterator(["low", "normal", "high", "urgent"])
    created_by = factory.SubFactory(UserFactory)


class WorkflowAttachmentFactory(DjangoModelFactory):
    """Factory for WorkflowAttachment"""

    class Meta:
        model = WorkflowAttachment

    workflow = factory.SubFactory(WorkFlowFactory)
    started_by = factory.SubFactory(UserFactory)
    metadata = factory.Dict({"priority": "normal", "department": "test"})


class CompleteWorkflowFactory(WorkFlowFactory):
    """Factory that creates a complete workflow with pipelines and stages"""

    class Meta:
        model = WorkFlow

    @factory.post_generation
    def create_pipelines(obj, create, extracted, **kwargs):
        if not create:
            return

        # Create Finance Pipeline with 3 stages
        finance_pipeline = PipelineFactory(
            workflow=obj,
            name_en="Finance Review",
            name_ar="مراجعة مالية",
            order=1,
            department__name="Finance Department",
        )

        # Finance stages
        StageFactory(
            pipeline=finance_pipeline,
            name_en="Initial Review",
            name_ar="المراجعة الأولى",
            order=1,
            stage_info={
                "color": "#3498db",
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.ROLE,
                        "user_role": 1,
                        "role_selection_strategy": RoleSelectionStrategy.ROUND_ROBIN,
                        "required_form": 1,
                    }
                ],
            },
        )

        StageFactory(
            pipeline=finance_pipeline,
            name_en="Budget Approval",
            name_ar="موافقة الميزانية",
            order=2,
            stage_info={
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
        )

        StageFactory(
            pipeline=finance_pipeline,
            name_en="Final Finance Sign-off",
            name_ar="الموافقة المالية النهائية",
            order=3,
            stage_info={
                "color": "#27ae60",
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.USER,
                        "approval_user": 123,
                        "required_form": 3,
                    }
                ],
            },
        )

        # Create Management Pipeline with 1 stage
        management_pipeline = PipelineFactory(
            workflow=obj,
            name_en="Executive Approval",
            name_ar="موافقة تنفيذية",
            order=2,
            department__name="Management Department",
        )

        # Management stage
        StageFactory(
            pipeline=management_pipeline,
            name_en="Executive Approval",
            name_ar="الموافقة التنفيذية",
            order=1,
            stage_info={
                "color": "#8e44ad",
                "approvals": [
                    {
                        "approval_type": ApprovalTypes.ROLE,
                        "user_role": 3,
                        "role_selection_strategy": RoleSelectionStrategy.ANYONE,
                    }
                ],
            },
        )

        # Save the object to ensure all relationships are properly set
        obj.save()

    @classmethod
    def _after_postgeneration(cls, instance, create, results=None):
        """Override to prevent automatic save after postgeneration"""
        pass


def setup_test_workflow_model():
    """Helper function to register WorkflowTestModel for workflow functionality"""
    register_model_for_workflow(
        WorkflowTestModel, auto_start=True, status_field="status"
    )


def create_test_users():
    """Create standard test users for workflow testing"""
    return {
        "requester": UserFactory(username="requester"),
        "finance_reviewer": UserFactory(username="finance_reviewer"),
        "budget_manager": UserFactory(username="budget_manager"),
        "cfo": UserFactory(username="cfo"),
        "executive": UserFactory(username="executive"),
    }


def create_purchase_request_workflow():
    """Create a complete purchase request workflow for testing"""
    workflow = CompleteWorkflowFactory(
        name_en="Purchase Request Approval", name_ar="موافقة طلب الشراء"
    )
    return workflow


def create_test_purchase_request(created_by=None):
    """Create a test purchase request object"""
    if created_by is None:
        created_by = UserFactory()

    return WorkflowTestModelFactory(
        name="Purchase Request: Office Equipment - $15000",
        description="High-priority purchase request for office equipment",
        amount=15000.00,
        priority="high",
        created_by=created_by,
    )
