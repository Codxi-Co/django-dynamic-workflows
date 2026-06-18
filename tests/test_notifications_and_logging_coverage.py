"""Coverage for notification and logging helper modules."""

from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings

from django_workflow_engine.choices import WorkflowAttachmentStatus, WorkflowStatus
from django_workflow_engine.logging_utils import (
    WorkflowLogger,
    log_api_request,
    log_model_operation,
    log_serializer_validation,
)
from django_workflow_engine.models import Pipeline, Stage, WorkFlow, WorkflowAttachment
from django_workflow_engine.notifications import (
    get_custom_send_email_function,
    get_workflow_email_context,
    send_bulk_workflow_emails,
    send_workflow_email,
)
from sandbox.testapp.models import WorkflowTestModel

User = get_user_model()


def custom_test_email_sender(**kwargs):
    custom_test_email_sender.calls.append(kwargs)


custom_test_email_sender.calls = []


def failing_custom_test_email_sender(**kwargs):
    raise RuntimeError("custom failed")


class NotificationCoverageTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="notify-user",
            first_name="Notify",
            last_name="User",
            email="notify@example.com",
            password="pass",
        )
        self.other = User.objects.create_user(
            username="other-notify",
            email="other@example.com",
            password="pass",
        )

    @override_settings(
        WORKFLOW_SEND_EMAIL_FUNCTION=(
            "tests.test_notifications_and_logging_coverage.custom_test_email_sender"
        )
    )
    def test_custom_send_email_success(self):
        custom_test_email_sender.calls = []
        self.assertEqual(get_custom_send_email_function(), custom_test_email_sender)

        result = send_workflow_email(
            name="workflow_approved",
            user=self.user,
            context={"subject": "Custom Subject", "extra": "value"},
        )

        self.assertTrue(result)
        self.assertEqual(
            custom_test_email_sender.calls[0]["email"], "notify@example.com"
        )
        self.assertEqual(custom_test_email_sender.calls[0]["subject"], "Custom Subject")
        self.assertEqual(custom_test_email_sender.calls[0]["user"], self.user)

    @override_settings(
        WORKFLOW_SEND_EMAIL_FUNCTION=(
            "tests.test_notifications_and_logging_coverage.failing_custom_test_email_sender"
        )
    )
    def test_custom_send_email_failure_and_bad_import(self):
        self.assertFalse(
            send_workflow_email(
                name="workflow_approved",
                email="person@example.com",
                context={"subject": "Subject"},
            )
        )

        with override_settings(WORKFLOW_SEND_EMAIL_FUNCTION="missing.module.func"):
            self.assertIsNone(get_custom_send_email_function())

    def test_send_workflow_email_validation_paths(self):
        self.assertFalse(send_workflow_email(name="workflow_approved"))
        self.assertFalse(send_workflow_email(name="workflow_approved", user=999999))
        self.assertFalse(
            send_workflow_email(
                name="workflow_approved",
                user=SimpleNamespace(username="no-email"),
            )
        )

    @override_settings(DEFAULT_FROM_EMAIL="default@example.com")
    def test_send_workflow_email_fallback_html_and_plain_text(self):
        message = Mock()
        with (
            patch(
                "django_workflow_engine.notifications.render_to_string",
                return_value="<b>Hello</b>",
            ) as render,
            patch(
                "django_workflow_engine.notifications.EmailMultiAlternatives",
                return_value=message,
            ) as email_cls,
        ):
            self.assertTrue(
                send_workflow_email(
                    name="workflow_approved",
                    email="person@example.com",
                    context={"subject": "HTML"},
                    bcc=["audit@example.com"],
                )
            )

        render.assert_called_once()
        email_cls.assert_called_once()
        message.attach_alternative.assert_called_once_with("<b>Hello</b>", "text/html")
        message.send.assert_called_once_with(fail_silently=False)

        message = Mock()

        def render_templates(template, context):
            if template.endswith(".txt"):
                raise RuntimeError("no text template")
            return "<p>Plain fallback</p>"

        with (
            patch(
                "django_workflow_engine.notifications.render_to_string",
                side_effect=render_templates,
            ),
            patch(
                "django_workflow_engine.notifications.EmailMultiAlternatives",
                return_value=message,
            ),
        ):
            self.assertTrue(
                send_workflow_email(
                    name="workflow_approved",
                    email="person@example.com",
                    html_only=False,
                    template_name="custom/email.html",
                )
            )
        self.assertEqual(
            message.attach_alternative.call_args.args,
            ("<p>Plain fallback</p>", "text/html"),
        )

        with patch(
            "django_workflow_engine.notifications.render_to_string",
            side_effect=RuntimeError("render failed"),
        ):
            self.assertFalse(
                send_workflow_email(
                    name="workflow_approved",
                    email="person@example.com",
                )
            )

    def test_send_bulk_workflow_emails_paths(self):
        self.assertEqual(
            send_bulk_workflow_emails("workflow_approved", []),
            {"sent": 0, "failed": 0, "skipped": 0},
        )

        with patch(
            "django_workflow_engine.notifications.send_workflow_email",
            side_effect=[True, False],
        ) as send_one:
            result = send_bulk_workflow_emails(
                "workflow_approved",
                [
                    "direct@example.com",
                    self.user,
                    self.user.id,
                    999999,
                    SimpleNamespace(email=""),
                ],
                context={"subject": "Bulk"},
                deduplicate=True,
            )

        self.assertEqual(result, {"sent": 1, "failed": 1, "skipped": 3})
        self.assertEqual(send_one.call_count, 2)

        with patch(
            "django_workflow_engine.notifications.send_workflow_email",
            return_value=True,
        ) as send_one:
            result = send_bulk_workflow_emails(
                "workflow_approved",
                ["dupe@example.com", "dupe@example.com"],
                deduplicate=False,
            )

        self.assertEqual(result, {"sent": 2, "failed": 0, "skipped": 0})
        self.assertEqual(send_one.call_count, 2)

    @override_settings(FRONTEND_URL="https://app.example.com")
    def test_get_workflow_email_context_valid_and_invalid_attachment(self):
        target = WorkflowTestModel.objects.create(
            name="Notification Target", created_by=self.user
        )
        target.company = SimpleNamespace(name="Acme", logo="logo.png")
        workflow = WorkFlow.objects.create(
            name_en="Notification Flow",
            name_ar="Notification Flow",
            status=WorkflowStatus.ACTIVE,
        )
        pipeline = Pipeline.objects.create(workflow=workflow, name_en="Pipeline")
        stage = Stage.objects.create(pipeline=pipeline, name_en="Review", order=1)
        attachment = WorkflowAttachment.objects.create(
            workflow=workflow,
            content_type=ContentType.objects.get_for_model(target),
            object_id=str(target.pk),
            status=WorkflowAttachmentStatus.IN_PROGRESS,
            started_by=self.user,
            current_pipeline=pipeline,
            current_stage=stage,
        )

        context = get_workflow_email_context(
            attachment,
            user=self.other,
            custom_value="kept",
        )

        self.assertEqual(context["workflow_name"], "Notification Flow")
        self.assertEqual(context["stage_name"], "Review")
        self.assertEqual(context["object_name"], "Notification Target")
        self.assertEqual(context["requester_email"], "notify@example.com")
        self.assertEqual(context["actor_email"], "other@example.com")
        self.assertEqual(
            context["object_link"],
            f"https://app.example.com/workflowtestmodels/{target.pk}",
        )
        self.assertEqual(context["custom_value"], "kept")

        explicit_stage = SimpleNamespace(id=8, name_en="Explicit")
        explicit_context = get_workflow_email_context(attachment, stage=explicit_stage)
        self.assertEqual(explicit_context["stage_name"], "Explicit")
        self.assertEqual(explicit_context["stage_id"], 8)

        self.assertEqual(
            get_workflow_email_context(SimpleNamespace(), fallback=True),
            {"fallback": True},
        )


class LoggingUtilsCoverageTest(TestCase):
    def test_workflow_logger_methods_and_module_helpers(self):
        workflow_logger = WorkflowLogger("tests.workflow.logger")
        workflow_logger.logger = Mock()

        workflow_logger.log_action("custom", level="debug", object_id="1")
        workflow_logger.log_workflow_created(1, 2, "Flow", "سير")
        workflow_logger.log_workflow_attached(1, "Model", "3", user_id=2)
        workflow_logger.log_workflow_started(1, "Model", "3", user_id=2)
        workflow_logger.log_stage_moved(1, "Draft", "Review", "3", user_id=2)
        workflow_logger.log_workflow_completed(1, "3", user_id=2, duration_seconds=5)
        workflow_logger.log_workflow_rejected(1, "Review", "Bad data", "3", user_id=2)
        workflow_logger.log_approval_action("approve", 1, "Review", user_id=2)
        workflow_logger.log_error("validation", "Invalid", object_id="3")
        workflow_logger.log_performance("query", 12.5, object_id="3")

        self.assertTrue(workflow_logger.logger.info.called)
        self.assertTrue(workflow_logger.logger.warning.called)
        self.assertTrue(workflow_logger.logger.error.called)
        self.assertTrue(workflow_logger.logger.debug.called)

        with patch(
            "django_workflow_engine.logging_utils.models_logger"
        ) as models_logger:
            log_model_operation("ticket", "create", object_id="1", user_id=2)
            models_logger.log_action.assert_called_once()

        with patch(
            "django_workflow_engine.logging_utils.serializers_logger"
        ) as serializers_logger:
            log_serializer_validation("TicketSerializer", True, user_id=2)
            log_serializer_validation(
                "TicketSerializer", False, errors={"name": ["required"]}, user_id=2
            )
            self.assertEqual(serializers_logger.log_action.call_count, 2)

        with patch("django_workflow_engine.logging_utils.WorkflowLogger") as logger_cls:
            api_logger = logger_cls.return_value
            log_api_request(
                endpoint="/status/",
                method="GET",
                user_id=2,
                response_status=200,
                duration_ms=10,
            )
            api_logger.log_action.assert_called_once()
