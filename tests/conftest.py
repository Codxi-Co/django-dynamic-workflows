"""Test configuration and fixtures for speeding up tests."""

import uuid
from unittest.mock import Mock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_email_backend():
    """Mock email backend to speed up tests."""
    with patch("django.core.mail.send_mail") as mock_send:
        mock_send.return_value = True  # Simulate successful email sending
        yield mock_send


# Remove auto-mocking that breaks tests - use selective mocking instead


@pytest.fixture
def fast_user_factory():
    """Factory for creating users without slow operations."""
    from django.contrib.auth import get_user_model

    User = get_user_model()

    def create_user(username="testuser", email="test@example.com", **kwargs):
        return User.objects.create_user(
            username=username, email=email, password="testpass123", **kwargs
        )

    return create_user


@pytest.fixture
def fast_workflow_factory():
    """Factory for creating workflows with minimal setup."""
    from django_workflow_engine.choices import WorkflowStatus
    from django_workflow_engine.models import Pipeline, Stage, WorkFlow
    from sandbox.testapp.models import Company, Department

    def create_workflow(user, name="Test Workflow"):
        from django.contrib.auth import get_user_model

        User = get_user_model()

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
            name_en=name,
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
        )

        workflow.update_active_status()

        return {
            "workflow": workflow,
            "pipeline": pipeline,
            "stage": stage,
            "company": company,
            "company_user": company_user,
            "department": department,
        }

    return create_workflow
