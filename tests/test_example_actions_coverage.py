"""Coverage for bundled example workflow actions."""

import importlib
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from django_workflow_engine.action_registry import registry
from sandbox.testapp.models import WorkflowTestModel

User = get_user_model()


class ExampleActionsCoverageTest(TestCase):
    example_action_names = [
        "send_approval_email",
        "send_rejection_email",
        "send_notification",
        "update_object_status",
        "mark_object_approved",
        "log_workflow_event",
        "update_inventory",
    ]

    def setUp(self):
        self.actions = importlib.import_module("django_workflow_engine.example_actions")
        self.creator = User.objects.create_user(
            username="example-creator",
            email="creator@example.com",
            password="pass",
        )
        self.other = User.objects.create_user(
            username="example-other",
            email="other@example.com",
            password="pass",
        )
        self.obj = WorkflowTestModel.objects.create(
            name="Example Object", created_by=self.creator
        )
        self.workflow = SimpleNamespace(id=77, name_en="Example Flow")
        self.stage = SimpleNamespace(name_en="Review")
        self.attachment = SimpleNamespace(
            workflow=self.workflow,
            target=self.obj,
            status="in_progress",
            current_stage=self.stage,
        )

    def tearDown(self):
        for action_name in self.example_action_names:
            if registry.is_registered(action_name):
                registry.unregister(action_name)

    @override_settings(
        DEFAULT_FROM_EMAIL="workflow@example.com",
        WORKFLOW_MANAGER_EMAIL="manager@example.com",
        ADMINS=[("Admin", "admin@example.com")],
    )
    def test_email_actions_success_and_validation_paths(self):
        self.assertFalse(self.actions.send_approval_email(self.attachment, {}))

        with patch(
            "django_workflow_engine.example_actions.send_mail", return_value=1
        ) as send_mail:
            result = self.actions.send_approval_email(
                self.attachment,
                {
                    "recipients": [
                        "creator",
                        "manager",
                        "admin",
                        "direct@example.com",
                    ],
                    "subject": "Approved",
                },
                user=self.creator,
            )

        self.assertTrue(result)
        self.assertEqual(send_mail.call_args.kwargs["subject"], "Approved")
        self.assertEqual(
            set(send_mail.call_args.kwargs["recipient_list"]),
            {
                "creator@example.com",
                "manager@example.com",
                "admin@example.com",
                "direct@example.com",
            },
        )

        with patch(
            "django_workflow_engine.example_actions._resolve_recipients",
            return_value=[],
        ):
            self.assertFalse(
                self.actions.send_approval_email(
                    self.attachment, {"recipients": ["creator"]}
                )
            )

        with patch(
            "django_workflow_engine.example_actions.send_mail",
            side_effect=RuntimeError("mail down"),
        ):
            self.assertFalse(
                self.actions.send_approval_email(
                    self.attachment, {"recipients": ["direct@example.com"]}
                )
            )

        self.assertFalse(self.actions.send_rejection_email(self.attachment, {}))
        with (
            patch(
                "django_workflow_engine.example_actions.render_to_string",
                return_value="Rejected body",
            ) as render,
            patch(
                "django_workflow_engine.example_actions.send_mail", return_value=1
            ) as send_mail,
        ):
            result = self.actions.send_rejection_email(
                self.attachment,
                {"recipients": ["creator"], "subject": "Rejected"},
                user=self.other,
                reason="Needs work",
            )

        self.assertTrue(result)
        render.assert_called_once()
        self.assertEqual(send_mail.call_args.kwargs["message"], "Rejected body")

        with patch(
            "django_workflow_engine.example_actions.render_to_string",
            side_effect=RuntimeError("template missing"),
        ):
            self.assertFalse(
                self.actions.send_rejection_email(
                    self.attachment, {"recipients": ["direct@example.com"]}
                )
            )

    def test_notification_action_and_user_resolution(self):
        approval = SimpleNamespace(assigned_to=self.other)
        with patch(
            "approval_workflow.services.get_current_approval_for_object",
            return_value=[approval],
        ):
            users = self.actions._resolve_user_recipients(
                ["creator", "approvers", self.other.id, "bad", None],
                self.attachment,
            )

        self.assertEqual(set(users), {self.creator, self.other})

        with patch(
            "django_workflow_engine.example_actions._resolve_user_recipients",
            return_value=[self.creator, self.other],
        ):
            self.assertTrue(
                self.actions.send_notification(
                    self.attachment,
                    {
                        "recipients": ["creator"],
                        "message": "Hello",
                        "notification_type": "warning",
                    },
                )
            )

        with patch(
            "django_workflow_engine.example_actions._resolve_user_recipients",
            side_effect=RuntimeError("resolver failed"),
        ):
            self.assertFalse(self.actions.send_notification(self.attachment, {}))

    def test_status_and_approval_update_actions(self):
        self.assertFalse(
            self.actions.update_object_status(SimpleNamespace(target=None), {})
        )
        self.assertFalse(self.actions.update_object_status(self.attachment, {}))
        self.assertFalse(
            self.actions.update_object_status(
                self.attachment,
                {"status": "done", "status_field": "missing_field"},
            )
        )

        self.assertTrue(
            self.actions.update_object_status(
                self.attachment,
                {"status": "done", "status_field": "status", "save": False},
            )
        )
        self.obj.refresh_from_db()
        self.assertNotEqual(self.obj.status, "done")

        self.assertTrue(
            self.actions.update_object_status(
                self.attachment,
                {"status": "done", "status_field": "status", "save": True},
            )
        )
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.status, "done")

        with patch.object(self.obj, "save", side_effect=RuntimeError("save failed")):
            self.assertFalse(
                self.actions.update_object_status(self.attachment, {"status": "failed"})
            )

        self.assertFalse(
            self.actions.mark_object_approved(SimpleNamespace(target=None), {})
        )

        approvable = SimpleNamespace(
            _meta=SimpleNamespace(label="tests.Approvable"),
            pk=1,
            approved_by=None,
            approved_at=None,
            save=Mock(),
        )
        self.assertTrue(
            self.actions.mark_object_approved(
                SimpleNamespace(target=approvable),
                {},
                user=self.other,
            )
        )
        self.assertEqual(approvable.approved_by, self.other)
        self.assertIsNotNone(approvable.approved_at)
        approvable.save.assert_called_once()

        no_fields = SimpleNamespace(
            _meta=SimpleNamespace(label="tests.NoFields"),
            pk=2,
            save=Mock(),
        )
        self.assertTrue(
            self.actions.mark_object_approved(SimpleNamespace(target=no_fields), {})
        )
        no_fields.save.assert_not_called()

        with patch.object(approvable, "save", side_effect=RuntimeError("save failed")):
            self.assertFalse(
                self.actions.mark_object_approved(
                    SimpleNamespace(target=approvable), {}
                )
            )

    def test_logging_and_inventory_actions(self):
        self.assertTrue(
            self.actions.log_workflow_event(
                self.attachment,
                {"event_type": "approved", "log_level": "warning"},
                user=self.other,
            )
        )
        self.assertTrue(self.actions.log_workflow_event(self.attachment, {}))
        self.assertFalse(
            self.actions.log_workflow_event(SimpleNamespace(workflow=None), {})
        )

        self.assertFalse(
            self.actions.update_inventory(SimpleNamespace(target=None), {})
        )
        self.assertFalse(self.actions.update_inventory(self.attachment, {}))

        inventory_obj = SimpleNamespace(
            _meta=SimpleNamespace(label="tests.Inventory"),
            pk=5,
            items=[1, 2, 3],
        )
        self.assertTrue(
            self.actions.update_inventory(SimpleNamespace(target=inventory_obj), {})
        )

        class BrokenInventory:
            _meta = SimpleNamespace(label="tests.Broken")
            pk = 6

            @property
            def items(self):
                raise RuntimeError("bad items")

        broken = BrokenInventory()
        self.assertFalse(
            self.actions.update_inventory(SimpleNamespace(target=broken), {})
        )

    @override_settings(
        WORKFLOW_MANAGER_EMAIL="manager@example.com",
        ADMINS=[("Admin", "admin@example.com")],
    )
    def test_helper_functions_cover_subjects_and_message_templates(self):
        recipients = self.actions._resolve_recipients(
            ["creator", "manager", "admin", "direct@example.com", "not-email"],
            self.attachment,
        )
        self.assertEqual(
            set(recipients),
            {
                "creator@example.com",
                "manager@example.com",
                "admin@example.com",
                "direct@example.com",
            },
        )

        self.creator.language = "ar"
        self.assertIn(
            "Approved", self.actions._get_default_subject("approval", self.attachment)
        )
        self.assertIn(
            "Rejected", self.actions._get_default_subject("rejection", self.attachment)
        )
        self.assertIn(
            "Update", self.actions._get_default_subject("other", self.attachment)
        )

        default_message = self.actions._prepare_email_message(
            self.attachment, {"include_details": True}, {"user": self.other}
        )
        self.assertIn("Current Stage: Review", default_message)
        self.assertIn("Action by:", default_message)

        compact_message = self.actions._prepare_email_message(
            self.attachment, {"include_details": False}, {}
        )
        self.assertNotIn("Current Stage", compact_message)

        with patch(
            "django_workflow_engine.example_actions.render_to_string",
            return_value="Template body",
        ) as render:
            self.assertEqual(
                self.actions._prepare_email_message(
                    self.attachment,
                    {"template": "emails/custom.txt"},
                    {"user": self.creator},
                ),
                "Template body",
            )
        render.assert_called_once()
