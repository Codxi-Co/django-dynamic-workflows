"""Test configuration and fixtures for speeding up tests."""

import uuid
from unittest.mock import Mock, patch

from django.conf import settings

import pytest


# Optimize Django settings for tests
def pytest_configure(config):
    """Configure Django settings for optimal test performance."""
    settings.DEBUG = False
    settings.TEMPLATE_DEBUG = False

    # Disable migrations for faster test database creation
    settings.MIGRATION_MODULES = {
        "django_workflow_engine": None,
        "approval_workflow": None,
        "auth": None,
        "contenttypes": None,
        "sessions": None,
    }

    # Disable workflow emails by default in tests
    settings.WORKFLOW_DISABLE_EMAILS = True

    # Configure approval handlers for workflow progression
    settings.APPROVAL_HANDLERS = [
        "django_workflow_engine.handlers.WorkflowApprovalHandler",
    ]

    # Monkey-patch approval_workflow to use our generic handler resolution
    import approval_workflow.handlers

    from django_workflow_engine.handlers import (
        get_handler_for_instance as get_workflow_handler,
    )

    # Store original function
    _original_get_handler = approval_workflow.handlers.get_handler_for_instance

    def patched_get_handler_for_instance(instance):
        """Try workflow engine handler first, then fallback to original."""
        # Try our generic workflow handler
        workflow_handler = get_workflow_handler(instance)
        if workflow_handler:
            return workflow_handler
        # Fallback to original approval_workflow logic
        return _original_get_handler(instance)

    # Replace the function
    approval_workflow.handlers.get_handler_for_instance = (
        patched_get_handler_for_instance
    )
    import approval_workflow.services

    approval_workflow.services.get_handler_for_instance = (
        patched_get_handler_for_instance
    )


@pytest.fixture(autouse=True)
def mock_email_backend():
    """Mock email backend to speed up tests."""
    with patch("django.core.mail.send_mail") as mock_send:
        mock_send.return_value = True  # Simulate successful email sending
        yield mock_send


@pytest.fixture(autouse=True)
def mock_async_email_backend():
    """Deprecated: No longer needed as package doesn't send emails."""
    # Package no longer sends emails, so no need to mock
    yield None


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
            stage_info={
                "approvals": [{"approval_type": "user", "approval_user": user.id}]
            },
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
