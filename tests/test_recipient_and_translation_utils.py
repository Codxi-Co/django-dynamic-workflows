"""Coverage for notification recipient and bilingual translation helpers."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from django_workflow_engine import recipient_resolver
from django_workflow_engine.recipient_resolver import (
    _resolve_current_approvers,
    _resolve_delegated_to,
    _resolve_user_id,
    _resolve_workflow_starter,
    resolve_recipients,
)
from django_workflow_engine.translation_utils import (
    ERROR_MESSAGES_BILINGUAL,
    STAGE_MESSAGES,
    BilingualLogger,
    get_bilingual_logger,
    get_message,
    get_user_language,
    log_workflow_event,
)
from sandbox.testapp.models import WorkflowTestModel

User = get_user_model()


class RecipientResolverTest(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user(
            username="creator",
            email="creator@example.com",
            password="pass",
        )
        self.starter = User.objects.create_user(
            username="starter",
            email="starter@example.com",
            password="pass",
        )
        self.direct = User.objects.create_user(
            username="direct",
            email="direct@example.com",
            password="pass",
        )
        self.obj = WorkflowTestModel.objects.create(
            name="Recipient Target", created_by=self.creator
        )
        self.attachment = SimpleNamespace(target=self.obj, started_by=self.starter)

    def test_resolve_recipients_handles_all_supported_inputs(self):
        delegated = User.objects.create_user(
            username="delegate",
            email="delegate@example.com",
            password="pass",
        )
        approval_user = User.objects.create_user(
            username="approver",
            email="approver@example.com",
            password="pass",
        )
        approval = SimpleNamespace(user=approval_user, role=None)

        with patch(
            "approval_workflow.services.get_current_approval_for_object",
            return_value=approval,
        ):
            recipients = resolve_recipients(
                [
                    "creator",
                    "current_approver",
                    "delegated_to",
                    "workflow_starter",
                    "direct@example.com",
                    self.direct,
                    self.direct.id,
                    "unknown",
                ],
                self.attachment,
                delegated_to=delegated,
            )

        self.assertEqual(
            recipients,
            {
                "creator@example.com",
                "approver@example.com",
                "delegate@example.com",
                "starter@example.com",
                "direct@example.com",
            },
        )

    def test_resolve_recipients_handles_missing_inputs(self):
        self.assertEqual(resolve_recipients(["creator"], None), set())
        self.assertEqual(
            resolve_recipients(["creator"], SimpleNamespace(target=None)), set()
        )

        no_email_user = SimpleNamespace(email="")
        recipients = resolve_recipients([no_email_user, 999999], self.attachment)
        self.assertEqual(recipients, set())

    def test_resolve_current_approvers_handles_lists_roles_and_errors(self):
        user_with_email = SimpleNamespace(email="role-user@example.com")
        role_approval = SimpleNamespace(user=None, role="manager")
        user_approval = SimpleNamespace(
            user=SimpleNamespace(email="current@example.com"), role=None
        )
        empty_user_approval = SimpleNamespace(user=SimpleNamespace(email=""), role=None)

        with (
            patch(
                "approval_workflow.services.get_current_approval_for_object",
                return_value=[user_approval, empty_user_approval, role_approval],
            ),
            patch(
                "django_workflow_engine.utils.get_users_from_role",
                return_value=[user_with_email],
            ),
        ):
            emails = _resolve_current_approvers(self.obj)

        self.assertEqual(emails, {"current@example.com", "role-user@example.com"})

        with patch(
            "approval_workflow.services.get_current_approval_for_object",
            return_value=None,
        ):
            self.assertEqual(_resolve_current_approvers(self.obj), set())

        with patch(
            "approval_workflow.services.get_current_approval_for_object",
            side_effect=RuntimeError("boom"),
        ):
            self.assertEqual(_resolve_current_approvers(self.obj), set())

        self.assertEqual(_resolve_current_approvers(None), set())

    def test_private_resolvers_cover_empty_and_id_cases(self):
        self.assertEqual(_resolve_delegated_to({}), None)
        self.assertEqual(
            _resolve_delegated_to({"delegated_to": self.direct}), "direct@example.com"
        )
        self.assertEqual(
            _resolve_delegated_to({"delegated_to": self.direct.id}),
            "direct@example.com",
        )
        self.assertEqual(_resolve_delegated_to({"delegated_to": object()}), None)

        self.assertEqual(_resolve_workflow_starter(None), None)
        self.assertEqual(
            _resolve_workflow_starter(SimpleNamespace(started_by=None)), None
        )
        self.assertEqual(
            _resolve_workflow_starter(self.attachment), "starter@example.com"
        )

        self.assertEqual(_resolve_user_id(self.direct.id), "direct@example.com")
        self.assertEqual(_resolve_user_id(999999), None)

    def test_current_approvers_import_error_path(self):
        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "approval_workflow.services":
                raise ImportError("missing")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            self.assertEqual(_resolve_current_approvers(self.obj), set())


class TranslationUtilsTest(TestCase):
    def test_get_user_language_checks_supported_attributes(self):
        self.assertEqual(get_user_language(None), "en")
        self.assertEqual(get_user_language(SimpleNamespace(language="ar")), "ar")
        self.assertEqual(get_user_language(SimpleNamespace(language="fr")), "en")
        self.assertEqual(
            get_user_language(SimpleNamespace(language_preference="ar")), "ar"
        )
        self.assertEqual(
            get_user_language(SimpleNamespace(language_preference="fr")), "en"
        )

    def test_get_message_formats_known_and_unknown_templates(self):
        self.assertEqual(
            get_message("created", {"workflow_id": 1, "name": "Demo"})["en"],
            "Workflow created - ID: 1, Name: Demo",
        )
        self.assertEqual(get_message("missing", {})["en"], "")
        self.assertIn(
            "No workflow",
            get_message(
                "no_workflow",
                {"obj_label": "app.Model", "obj_pk": 7},
                ERROR_MESSAGES_BILINGUAL,
            )["en"],
        )
        self.assertIn(
            "Entered stage",
            get_message(
                "entered",
                {"stage": "Review", "obj_label": "app.Model", "obj_pk": 7},
                STAGE_MESSAGES,
            )["en"],
        )

    def test_bilingual_logger_formats_and_routes_languages(self):
        logger = BilingualLogger("tests.translation", always_bilingual=False)
        logger.logger = Mock()

        self.assertEqual(
            logger._get_log_message(
                "Hello {name}",
                "مرحبا {name}",
                {"name": "Sara"},
            ),
            ("Hello Sara", "مرحبا Sara"),
        )
        english, arabic = logger._get_log_message("Hello {missing}", context={"x": 1})
        self.assertEqual(english, "Hello {missing}")
        self.assertTrue(arabic)

        logger.info("Info", "معلومة")
        logger.info("Info", "معلومة", user_language="ar")
        logger.info("Info", "معلومة", user_language="en")
        logger.warning("Warn", "تحذير")
        logger.warning("Warn", "تحذير", user_language="ar")
        logger.warning("Warn", "تحذير", user_language="en")
        logger.error("Error", "خطأ")
        logger.error("Error", "خطأ", user_language="ar")
        logger.error("Error", "خطأ", user_language="en")
        logger.debug("Debug", "تصحيح")
        logger.debug("Debug", "تصحيح", user_language="ar")
        logger.debug("Debug", "تصحيح", user_language="en")

        self.assertEqual(logger.logger.info.call_count, 3)
        self.assertEqual(logger.logger.warning.call_count, 3)
        self.assertEqual(logger.logger.error.call_count, 3)
        self.assertEqual(logger.logger.debug.call_count, 3)

        always = BilingualLogger("tests.translation.always", always_bilingual=True)
        always.logger = Mock()
        always.info("Info", "معلومة", user_language="ar")
        self.assertIn("[EN]", always.logger.info.call_args.args[0])

    def test_get_bilingual_logger_and_log_workflow_event(self):
        logger = get_bilingual_logger(
            "tests.translation.factory", always_bilingual=True
        )
        self.assertIsInstance(logger, BilingualLogger)
        self.assertTrue(logger.always_bilingual)

        plain_logger = Mock()
        log_workflow_event(
            "created",
            {"workflow_id": 2, "name": "Flow"},
            logger_instance=plain_logger,
        )
        plain_logger.info.assert_called_once()
        self.assertIn("[EN]", plain_logger.info.call_args.args[0])

        arabic_logger = Mock()
        log_workflow_event(
            "created",
            {"workflow_id": 3, "name": "Flow"},
            user=SimpleNamespace(language="ar"),
            logger_instance=arabic_logger,
        )
        arabic_logger.info.assert_called_once()
        self.assertIn("[AR]", arabic_logger.info.call_args.args[0])

        warning_logger = Mock()
        log_workflow_event(
            "created",
            {"workflow_id": 4, "name": "Flow"},
            level="warning",
            logger_instance=warning_logger,
        )
        self.assertEqual(warning_logger.warning.call_count, 2)

        fallback_logger = SimpleNamespace(info=Mock())
        log_workflow_event(
            "created",
            {"workflow_id": 5, "name": "Flow"},
            level="unknown",
            logger_instance=fallback_logger,
        )
        fallback_logger.info.assert_called_once()
