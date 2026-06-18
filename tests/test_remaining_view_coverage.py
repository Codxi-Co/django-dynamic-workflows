"""Direct branch coverage for REST views and workflow mixin actions."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, force_authenticate

from django_workflow_engine.models import (
    Status,
    StatusAttachment,
    WorkFlow,
    WorkflowAction,
    WorkflowAttachment,
)
from django_workflow_engine.status_services import create_status_flow_design
from django_workflow_engine.views import (
    ExampleTicketViewSet,
    StatusActionViewSet,
    StatusAttachmentViewSet,
    StatusAuditViewSetMixin,
    StatusEnabledModelsView,
    StatusFlowDesignView,
    StatusHistoryViewSet,
    StatusModelOptionsView,
    StatusTransitionDiagramView,
    StatusViewSet,
    WorkflowAttachmentViewSet,
    WorkflowMixin,
    _content_type_from_model_string,
    _status_full_flow_response,
)
from sandbox.testapp.models import WorkflowTestModel

User = get_user_model()


class RemainingViewCoverageTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username="view-coverage")
        self.content_type = ContentType.objects.get_for_model(WorkflowTestModel)
        result = create_status_flow_design(
            {
                "model": "testapp.WorkflowTestModel",
                "company": self.user.pk,
                "status_field": "status",
                "default_status": "new",
                "terminal_statuses": ["closed"],
                "workflow": {
                    "name_en": "View Flow",
                    "name_ar": "View Flow",
                },
                "statuses": [
                    {
                        "code": "new",
                        "name_en": "New",
                        "name_ar": "New",
                    },
                    {
                        "code": "closed",
                        "name_en": "Closed",
                        "name_ar": "Closed",
                        "is_terminal": True,
                    },
                ],
                "transitions": [
                    {
                        "code": "close",
                        "name_en": "Close",
                        "from": "new",
                        "to": "closed",
                    }
                ],
            },
            user=self.user,
        )
        self.workflow = WorkFlow.objects.get(pk=result["workflow"]["id"])

    def request(self, method="get", path="/", data=None):
        raw = getattr(self.factory, method)(path, data=data or {}, format="json")
        force_authenticate(raw, user=self.user)
        return Request(raw, parsers=[JSONParser()])

    def test_audit_mixin_and_content_type_resolution(self):
        serializer = MagicMock()
        serializer.Meta.model = SimpleNamespace(created_by=True, modified_by=True)
        view = StatusAuditViewSetMixin()
        view.request = SimpleNamespace(user=self.user)
        view.perform_create(serializer)
        serializer.save.assert_called_with(
            created_by=self.user,
            modified_by=self.user,
        )
        view.perform_update(serializer)
        serializer.save.assert_called_with(modified_by=self.user)

        self.assertIsNone(_content_type_from_model_string("invalid"))
        self.assertIsNone(_content_type_from_model_string("missing.Model"))

    def test_status_read_views_cover_invalid_empty_and_full_designs(self):
        invalid = StatusModelOptionsView().get(self.request(), "invalid")
        self.assertEqual(invalid.status_code, 404)

        options = StatusModelOptionsView().get(
            self.request(path=f"/?workflow_id={self.workflow.pk}"),
            "testapp.WorkflowTestModel",
        )
        self.assertEqual(options.status_code, 200)
        self.assertEqual(len(options.data["workflow_statuses"]), 2)

        extra = Status.objects.create(
            company=self.user,
            content_type=self.content_type,
            name_en="Extra",
            name_ar="Extra",
        )
        default_options = StatusModelOptionsView().get(
            self.request(path=f"/?company_id={self.user.pk}"),
            "testapp.WorkflowTestModel",
        )
        self.assertIn(
            extra.pk, {item["id"] for item in default_options.data["statuses"]}
        )

        invalid_diagram = StatusTransitionDiagramView().get(
            self.request(),
            "invalid",
        )
        self.assertEqual(invalid_diagram.status_code, 404)

        with patch(
            "django_workflow_engine.views.WorkflowConfiguration.objects.filter"
        ) as configurations:
            configurations.return_value.first.return_value = None
            empty = StatusTransitionDiagramView().get(
                self.request(),
                "testapp.WorkflowTestModel",
            )
        self.assertEqual(empty.data["nodes"], [])

        diagram = StatusTransitionDiagramView().get(
            self.request(path=f"/?workflow_id={self.workflow.pk}"),
            "testapp.WorkflowTestModel",
        )
        self.assertEqual(len(diagram.data["edges"]), 1)

        payload = _status_full_flow_response(
            self.content_type,
        )
        self.assertEqual(len(payload["nodes"]), 2)
        self.assertEqual(len(payload["transitions"]), 1)

    def test_flow_design_and_enabled_model_views(self):
        invalid_workflow = StatusFlowDesignView().get(
            self.request(path="/?workflow_id=999999"),
            "testapp.WorkflowTestModel",
        )
        self.assertEqual(invalid_workflow.status_code, 404)

        invalid_model = StatusFlowDesignView().get(self.request(), "invalid")
        self.assertEqual(invalid_model.status_code, 404)

        valid = StatusFlowDesignView().get(
            self.request(path=f"/?workflow_id={self.workflow.pk}"),
            "testapp.WorkflowTestModel",
        )
        self.assertEqual(valid.status_code, 200)

        invalid_post = StatusFlowDesignView().post(self.request(method="post", data={}))
        self.assertEqual(invalid_post.status_code, 400)

        enabled = StatusEnabledModelsView().get(self.request())
        self.assertTrue(enabled.data)

    def test_queryset_filter_branches(self):
        attachment_view = WorkflowAttachmentViewSet()
        attachment_view.request = self.request(
            path=(
                "/?content_type=testapp.workflowtestmodel"
                "&status=in_progress&workflow_id=1"
            )
        )
        self.assertIsNotNone(attachment_view.get_queryset())
        attachment_view.request = self.request(path="/?content_type=invalid")
        self.assertIsNotNone(attachment_view.get_queryset())

        status_view = StatusViewSet()
        status_view.request = self.request(
            path=(
                f"/?company_id={self.user.pk}&model=testapp.WorkflowTestModel"
                f"&content_type={self.content_type.pk}&is_active=true"
            )
        )
        self.assertIsNotNone(status_view.get_queryset())
        status_view.request = self.request(
            path="/?content_type=testapp.WorkflowTestModel"
        )
        self.assertIsNotNone(status_view.get_queryset())

        action_view = StatusActionViewSet()
        action_view.request = self.request(
            path="/?status_node=1&transition=1&workflow=1&action_type=after_transition"
        )
        self.assertIsNotNone(action_view.get_queryset())

        status_attachment_view = StatusAttachmentViewSet()
        status_attachment_view.request = self.request(
            path="/?content_type=testapp.workflowtestmodel"
        )
        self.assertIsNotNone(status_attachment_view.get_queryset())
        status_attachment_view.request = self.request(path="/?content_type=invalid")
        self.assertIsNotNone(status_attachment_view.get_queryset())

        history = StatusHistoryViewSet()
        history.request = self.request(
            path=(
                "/?model=testapp.WorkflowTestModel&object_id=1"
                "&workflow=1&transition=1&company_id=1"
            )
        )
        self.assertIsNotNone(history.get_queryset())

    def test_attachment_viewset_actions_cover_errors_and_success(self):
        view = WorkflowAttachmentViewSet()
        view.request = self.request(method="post", data={})
        missing = SimpleNamespace(target=None)
        view.get_object = lambda: missing
        self.assertEqual(view.approve(view.request).status_code, 404)
        self.assertEqual(view.transitions(self.request()).status_code, 404)
        self.assertEqual(view.transition(view.request).status_code, 404)
        self.assertEqual(view.approve_transition(view.request).status_code, 404)
        self.assertEqual(view.reject_transition(view.request).status_code, 404)

        started = SimpleNamespace(status="in_progress", target=object())
        view.get_object = lambda: started
        self.assertEqual(view.start(view.request).status_code, 400)

        target = WorkflowTestModel.objects.create(
            name="View target",
            created_by=self.user,
        )
        attachment = MagicMock(
            target=target,
            object_id=str(target.pk),
            status="not_started",
            current_stage=None,
            metadata={},
        )
        view.get_object = lambda: attachment

        with patch(
            "django_workflow_engine.views.start_workflow_for_object",
            return_value=SimpleNamespace(status="in_progress", current_stage=None),
        ):
            self.assertEqual(view.start(view.request).status_code, 200)
        with patch(
            "django_workflow_engine.views.start_workflow_for_object",
            side_effect=RuntimeError("start failed"),
        ):
            self.assertEqual(view.start(view.request).status_code, 400)

        with patch(
            "django_workflow_engine.views.get_available_transitions",
            return_value=[],
        ):
            self.assertEqual(view.transitions(self.request()).status_code, 200)
        attachment.get_progress_info.return_value = {"progress": 50}
        self.assertEqual(view.progress(self.request()).data["progress"], 50)

        view.request = self.request(
            method="post",
            data={"transition_key": "close"},
        )
        with patch(
            "django_workflow_engine.views.perform_transition",
            side_effect=RuntimeError("transition failed"),
        ):
            self.assertEqual(view.transition(view.request).status_code, 400)

        serializer = MagicMock()
        serializer.is_valid.return_value = True
        serializer.validated_data = {"action": "approved"}
        serializer.save.return_value = {}
        view.request = self.request(method="post", data={"action": "approved"})
        with patch(
            "django_workflow_engine.views.WorkflowApprovalSerializer",
            return_value=serializer,
        ):
            self.assertEqual(view.approve(view.request).status_code, 200)
        serializer.save.side_effect = RuntimeError("approval failed")
        with patch(
            "django_workflow_engine.views.WorkflowApprovalSerializer",
            return_value=serializer,
        ):
            self.assertEqual(view.approve(view.request).status_code, 400)
        serializer.is_valid.return_value = False
        serializer.errors = {"action": ["invalid"]}
        with patch(
            "django_workflow_engine.views.WorkflowApprovalSerializer",
            return_value=serializer,
        ):
            self.assertEqual(view.approve(view.request).status_code, 400)

        request = self.request(
            method="post",
            data={"reason": "reason", "reject_to_status_id": 999999},
        )
        self.assertEqual(view.reject_transition(request).status_code, 400)

        request = self.request(method="post", data={"reason": "reason"})
        approval = MagicMock()
        approval.is_valid.return_value = True
        approval.save.side_effect = RuntimeError("reject failed")
        with patch(
            "django_workflow_engine.views.WorkflowApprovalSerializer",
            return_value=approval,
        ):
            self.assertEqual(view.reject_transition(request).status_code, 400)

        attachment.target = None
        self.assertEqual(view.start(self.request(method="post")).status_code, 404)

    def test_status_attachment_set_status_paths(self):
        view = StatusAttachmentViewSet()
        missing = SimpleNamespace(target=None)
        view.get_object = lambda: missing
        request = self.request(method="post", data={"status_id": 1})
        self.assertEqual(view.set_status(request).status_code, 404)

        target = WorkflowTestModel.objects.create(
            name="Status target",
            created_by=self.user,
        )
        attachment = SimpleNamespace(target=target)
        view.get_object = lambda: attachment
        request = self.request(method="post", data={"status_id": 999999})
        self.assertEqual(view.set_status(request).status_code, 400)

        target_status = Status.objects.filter(
            content_type=self.content_type,
        ).first()
        request = self.request(
            method="post",
            data={"status_id": target_status.pk},
        )
        with patch(
            "django_workflow_engine.views.set_status",
            side_effect=RuntimeError("set failed"),
        ):
            self.assertEqual(view.set_status(request).status_code, 400)
        updated = StatusAttachment(
            content_type=self.content_type,
            object_id=str(target.pk),
            status=target_status,
        )
        with patch(
            "django_workflow_engine.views.set_status",
            return_value=updated,
        ):
            self.assertEqual(view.set_status(request).status_code, 200)

    def test_workflow_mixin_all_primary_response_paths(self):
        obj = WorkflowTestModel.objects.create(
            name="Mixin target",
            created_by=self.user,
        )

        class View(WorkflowMixin):
            def get_object(self):
                return obj

        view = View()
        request = self.request(method="post", data={})
        self.assertEqual(view.attach_workflow(request).status_code, 400)

        request = self.request(method="post", data={"workflow_id": 999999})
        self.assertEqual(view.attach_workflow(request).status_code, 404)

        request = self.request(
            method="post",
            data={"workflow_id": self.workflow.pk},
        )
        with patch(
            "django_workflow_engine.views.is_model_workflow_enabled",
            return_value=False,
        ):
            self.assertEqual(view.attach_workflow(request).status_code, 400)

        attached = SimpleNamespace(id=8, status="not_started")
        with patch(
            "django_workflow_engine.views.attach_workflow_to_object",
            return_value=attached,
        ):
            self.assertEqual(view.attach_workflow(request).status_code, 200)

        with patch(
            "django_workflow_engine.views.attach_workflow_to_object",
            side_effect=RuntimeError("attach failed"),
        ):
            self.assertEqual(view.attach_workflow(request).status_code, 400)

        with patch(
            "django_workflow_engine.views.get_workflow_attachment",
            return_value=None,
        ):
            self.assertEqual(view.workflow_status(self.request()).status_code, 404)
            self.assertEqual(view.workflow_action(request).status_code, 404)
            self.assertEqual(view.start_workflow(request).status_code, 404)

        attachment = MagicMock(status="in_progress")
        with patch(
            "django_workflow_engine.views.get_workflow_attachment",
            return_value=attachment,
        ):
            self.assertEqual(view.workflow_status(self.request()).status_code, 200)
            self.assertEqual(view.start_workflow(request).status_code, 400)

        attachment.status = "not_started"
        serializer = MagicMock()
        serializer.is_valid.return_value = True
        serializer.validated_data = {"action": "approved"}
        serializer.save.return_value = {}
        with (
            patch(
                "django_workflow_engine.views.get_workflow_attachment",
                return_value=attachment,
            ),
            patch(
                "django_workflow_engine.views.WorkflowApprovalSerializer",
                return_value=serializer,
            ),
        ):
            self.assertEqual(view.workflow_action(request).status_code, 200)
        serializer.save.side_effect = RuntimeError("action failed")
        with (
            patch(
                "django_workflow_engine.views.get_workflow_attachment",
                return_value=attachment,
            ),
            patch(
                "django_workflow_engine.views.WorkflowApprovalSerializer",
                return_value=serializer,
            ),
        ):
            self.assertEqual(view.workflow_action(request).status_code, 400)
        serializer.is_valid.return_value = False
        serializer.errors = {"action": ["invalid"]}
        with (
            patch(
                "django_workflow_engine.views.get_workflow_attachment",
                return_value=attachment,
            ),
            patch(
                "django_workflow_engine.views.WorkflowApprovalSerializer",
                return_value=serializer,
            ),
        ):
            self.assertEqual(view.workflow_action(request).status_code, 400)

        with (
            patch(
                "django_workflow_engine.views.get_workflow_attachment",
                return_value=attachment,
            ),
            patch(
                "django_workflow_engine.views.start_workflow_for_object",
                return_value=SimpleNamespace(status="in_progress", current_stage=None),
            ),
        ):
            self.assertEqual(view.start_workflow(request).status_code, 200)
        with (
            patch(
                "django_workflow_engine.views.get_workflow_attachment",
                return_value=attachment,
            ),
            patch(
                "django_workflow_engine.views.start_workflow_for_object",
                side_effect=RuntimeError("start failed"),
            ),
        ):
            self.assertEqual(view.start_workflow(request).status_code, 400)

    def test_example_viewset_queryset_and_context_helpers(self):
        view = ExampleTicketViewSet()
        with patch("rest_framework.viewsets.ModelViewSet.get_queryset") as get_queryset:
            get_queryset.return_value.prefetch_related.return_value = "queryset"
            self.assertEqual(view.get_queryset(), "queryset")
        with patch(
            "rest_framework.viewsets.ModelViewSet.get_serializer_context",
            return_value={},
        ):
            self.assertTrue(view.get_serializer_context()["include_workflow"])
