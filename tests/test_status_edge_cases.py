"""Edge-case coverage for reusable statuses and status graph workflows."""

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase

from rest_framework import serializers

from django_workflow_engine.choices import (
    ApprovalTypes,
    StatusCategory,
    TransitionRejectBehavior,
    WorkflowAttachmentStatus,
    WorkflowStatus,
    WorkflowStrategy,
)
from django_workflow_engine.models import (
    ModelStatus,
    ModelStatusConfiguration,
    Status,
    StatusHistory,
    StatusTransition,
    WorkFlow,
    WorkflowStatusNode,
)
from django_workflow_engine.serializers import (
    StatusSerializer,
    StatusTransitionSerializer,
)
from django_workflow_engine.services import (
    attach_workflow_to_object,
    get_current_status,
    get_workflow_attachment,
    perform_transition,
    register_model_for_statuses,
    reject_pending_transition,
)
from django_workflow_engine.status_services import (
    create_status_flow_design,
    create_status_for_model,
    get_status_flow_design,
    resolve_status_content_type,
    status_option,
)
from sandbox.testapp.models import WorkflowTestModel

User = get_user_model()


class StatusServiceEdgeCaseTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="status-edge-user", email="edge@example.com", password="pass"
        )
        self.content_type = ContentType.objects.get_for_model(WorkflowTestModel)

    def test_resolve_status_content_type_rejects_bad_labels(self):
        for label in [None, "", "missingdot", "bad.model"]:
            with self.subTest(label=label):
                with self.assertRaisesMessage(ValueError, "Invalid model"):
                    resolve_status_content_type(label)

    def test_create_status_for_model_and_empty_flow_design(self):
        status = create_status_for_model(
            model="testapp.workflowtestmodel",
            name_en="Waiting",
            name_ar="انتظار",
            category=StatusCategory.PAUSED,
            company=self.user,
            user=self.user,
        )

        self.assertEqual(status.content_type, self.content_type)
        self.assertEqual(status.company, self.user)
        self.assertEqual(status.created_by, self.user)
        self.assertEqual(status.key, "waiting")

        design = get_status_flow_design("testapp.workflowtestmodel")
        self.assertEqual(design["configuration"], None)
        self.assertEqual(design["workflow"], None)
        self.assertEqual(design["statuses"], [])
        self.assertEqual(design["diagram"], {"nodes": [], "edges": []})

    def test_status_option_defaults_without_model_status(self):
        status = Status.objects.create(
            key="draft",
            name_en="Draft",
            name_ar="مسودة",
            category=StatusCategory.OPEN,
            metadata={"flag": True},
        )

        option = status_option(status)

        self.assertEqual(option["key"], "draft")
        self.assertEqual(option["label_ar"], "مسودة")
        self.assertEqual(option["metadata"], {"flag": True})
        self.assertFalse(option["is_initial"])
        self.assertFalse(option["is_terminal"])
        self.assertEqual(option["order"], 0)

    def test_status_slug_generation_fallback_and_duplicate_suffix(self):
        first = Status.objects.create(name_en="!!!")
        second = Status.objects.create(name_en="!!!")

        self.assertEqual(first.key, "status")
        self.assertEqual(second.key, "status_2")
        self.assertEqual(str(first), "!!!")

    def test_create_status_flow_design_validation_errors(self):
        base_payload = {"model": "testapp.workflowtestmodel"}
        invalid_payloads = [
            ({**base_payload, "statuses": []}, "statuses is required"),
            (
                {
                    **base_payload,
                    "statuses": [{"name_en": "New"}],
                },
                "statuses[0].code is required",
            ),
            (
                {
                    **base_payload,
                    "default_status": "missing",
                    "statuses": [{"code": "new", "name_en": "New"}],
                },
                "default_status does not match any status code",
            ),
            (
                {
                    **base_payload,
                    "statuses": [{"code": "new", "name_en": "New"}],
                    "transitions": [{"from": "new", "to": "new"}],
                },
                "transitions[0].code is required",
            ),
            (
                {
                    **base_payload,
                    "statuses": [{"code": "new", "name_en": "New"}],
                    "transitions": [{"code": "stay", "from": "new", "to": "new"}],
                },
                "transitions[0].name_en is required",
            ),
            (
                {
                    **base_payload,
                    "statuses": [{"code": "new", "name_en": "New"}],
                    "transitions": [
                        {
                            "code": "bad",
                            "name_en": "Bad",
                            "from": "new",
                            "to": "missing",
                        }
                    ],
                },
                "transitions[0] references unknown status code",
            ),
        ]

        for payload, message in invalid_payloads:
            with self.subTest(message=message):
                with self.assertRaisesMessage(ValueError, message):
                    create_status_flow_design(payload, user=self.user)

    def test_create_status_flow_design_accepts_legacy_approval_config(self):
        result = create_status_flow_design(
            {
                "model": "testapp.workflowtestmodel",
                "default_status": "open",
                "terminal_statuses": ["done"],
                "statuses": [
                    {"code": "open", "name_en": "Open", "node_metadata": {"x": 1}},
                    {"code": "done", "name_en": "Done"},
                ],
                "transitions": [
                    {
                        "key": "finish",
                        "label": "Finish",
                        "from": "open",
                        "to": "done",
                        "approval_config": {
                            "approvals": [{"approval_type": ApprovalTypes.SELF}]
                        },
                        "reject_to": "open",
                    }
                ],
            },
            user=self.user,
        )

        self.assertEqual(result["nodes"][0]["metadata"], {"x": 1})
        self.assertTrue(result["nodes"][1]["is_terminal"])
        self.assertEqual(
            result["transitions"][0]["approvals"],
            [{"approval_type": ApprovalTypes.SELF}],
        )
        self.assertEqual(result["transitions"][0]["reject_to"], "open")


class StatusModelAndSerializerEdgeCaseTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="serializer-edge-user",
            email="serializer-edge@example.com",
            password="pass",
        )
        self.content_type = ContentType.objects.get_for_model(WorkflowTestModel)
        self.open_status = Status.objects.create(
            key="open", name_en="Open", content_type=self.content_type
        )
        self.done_status = Status.objects.create(
            key="done", name_en="Done", content_type=self.content_type
        )
        self.config = ModelStatusConfiguration.objects.create(
            content_type=self.content_type,
            default_status=self.open_status,
        )
        self.model_status = ModelStatus.objects.create(
            configuration=self.config,
            status=self.open_status,
            is_initial=True,
        )
        self.workflow = WorkFlow.objects.create(
            company=self.user,
            name_en="Serializer Flow",
            status=WorkflowStatus.ACTIVE,
            strategy=WorkflowStrategy.STATUS_GRAPH,
        )
        self.open_node = WorkflowStatusNode.objects.create(
            workflow=self.workflow, status=self.open_status, is_initial=True
        )
        self.done_node = WorkflowStatusNode.objects.create(
            workflow=self.workflow, status=self.done_status, is_terminal=True
        )

    def test_model_string_helpers(self):
        transition = StatusTransition.objects.create(
            workflow=self.workflow,
            key="close",
            name_en="Close",
            from_status=self.open_node,
            to_status=self.done_node,
        )

        self.assertIn("testapp.workflowtestmodel", str(self.config))
        self.assertIn("Status config", str(self.config))
        self.assertIn("Open", str(self.model_status))
        self.assertEqual(str(self.open_node), "Serializer Flow: Open")
        self.assertEqual(str(transition), "Close: Open -> Done")

    def test_status_transition_clean_validates_node_workflow_and_reject_target(self):
        other_workflow = WorkFlow.objects.create(
            company=self.user,
            name_en="Other Flow",
            status=WorkflowStatus.ACTIVE,
            strategy=WorkflowStrategy.STATUS_GRAPH,
        )
        other_node = WorkflowStatusNode.objects.create(
            workflow=other_workflow, status=self.done_status
        )

        with self.assertRaisesMessage(ValidationError, "from_status must belong"):
            StatusTransition(
                workflow=self.workflow,
                key="bad_from",
                name_en="Bad From",
                from_status=other_node,
                to_status=self.done_node,
            ).clean()

        with self.assertRaisesMessage(ValidationError, "to_status must belong"):
            StatusTransition(
                workflow=self.workflow,
                key="bad_to",
                name_en="Bad To",
                from_status=self.open_node,
                to_status=other_node,
            ).clean()

        with self.assertRaisesMessage(ValidationError, "reject_to_status must belong"):
            StatusTransition(
                workflow=self.workflow,
                key="bad_reject",
                name_en="Bad Reject",
                from_status=self.open_node,
                to_status=self.done_node,
                reject_to_status=other_node,
            ).clean()

        with self.assertRaisesMessage(ValidationError, "reject_to_status is required"):
            StatusTransition(
                workflow=self.workflow,
                key="missing_reject",
                name_en="Missing Reject",
                from_status=self.open_node,
                to_status=self.done_node,
                reject_behavior=TransitionRejectBehavior.MOVE_TO_STATUS,
            ).clean()

    def test_status_serializer_model_validation_paths(self):
        user_content_type = ContentType.objects.get_for_model(User)
        serializer = StatusSerializer(
            data={
                "name_en": "Invalid",
                "model": "bad-model",
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("model", serializer.errors)

        serializer = StatusSerializer(
            data={
                "name_en": "Conflict",
                "content_type": self.content_type.id,
                "model": f"{user_content_type.app_label}.{user_content_type.model}",
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("different models", str(serializer.errors["model"][0]))

        serializer = StatusSerializer(
            data={"name_en": "Global", "category": StatusCategory.OTHER}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        status = serializer.save()
        self.assertEqual(StatusSerializer(status).data["model_label"], None)

    def test_status_transition_serializer_approval_compatibility(self):
        serializer = StatusTransitionSerializer(
            data={
                "workflow": self.workflow.id,
                "key": "approve_close",
                "name_en": "Approve Close",
                "from_status": self.open_node.id,
                "to_status": self.done_node.id,
                "approvals": [{"approval_type": ApprovalTypes.SELF}],
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        transition = serializer.save()
        self.assertTrue(transition.requires_approval)
        self.assertEqual(
            StatusTransitionSerializer(transition).data["approvals"],
            [{"approval_type": ApprovalTypes.SELF}],
        )

        update_serializer = StatusTransitionSerializer(
            transition,
            data={"name_en": "Approve Close Renamed"},
            partial=True,
        )
        self.assertTrue(update_serializer.is_valid(), update_serializer.errors)
        updated = update_serializer.save()
        self.assertTrue(updated.requires_approval)
        self.assertEqual(
            updated.approval_config,
            {"approvals": [{"approval_type": ApprovalTypes.SELF}]},
        )

        invalid = StatusTransitionSerializer(
            data={
                "workflow": self.workflow.id,
                "key": "invalid_approval",
                "name_en": "Invalid Approval",
                "from_status": self.open_node.id,
                "to_status": self.done_node.id,
                "approvals": "not-a-list",
            }
        )
        self.assertFalse(invalid.is_valid())
        self.assertIn("approvals", invalid.errors)


class StatusTransitionRejectionEdgeCaseTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="reject-edge-user",
            email="reject-edge@example.com",
            password="pass",
        )
        self.open_status = Status.objects.create(
            key="open", name_en="Open", category=StatusCategory.OPEN
        )
        self.review_status = Status.objects.create(
            key="review", name_en="Review", category=StatusCategory.ACTIVE
        )
        self.rejected_status = Status.objects.create(
            key="rejected", name_en="Rejected", category=StatusCategory.CANCELLED
        )
        self.cancelled_status = Status.objects.create(
            key="cancelled", name_en="Cancelled", category=StatusCategory.CANCELLED
        )
        self.external_status = Status.objects.create(
            key="external", name_en="External", category=StatusCategory.CANCELLED
        )
        register_model_for_statuses(
            WorkflowTestModel,
            statuses=[
                self.open_status,
                self.review_status,
                self.rejected_status,
                self.cancelled_status,
            ],
            default_status=self.open_status,
            status_field="status",
        )
        self.workflow = WorkFlow.objects.create(
            company=self.user,
            name_en="Reject Flow",
            status=WorkflowStatus.ACTIVE,
            strategy=WorkflowStrategy.STATUS_GRAPH,
        )
        self.open_node = WorkflowStatusNode.objects.create(
            workflow=self.workflow, status=self.open_status, is_initial=True
        )
        self.review_node = WorkflowStatusNode.objects.create(
            workflow=self.workflow, status=self.review_status
        )
        self.rejected_node = WorkflowStatusNode.objects.create(
            workflow=self.workflow, status=self.rejected_status, is_terminal=True
        )
        self.cancelled_node = WorkflowStatusNode.objects.create(
            workflow=self.workflow, status=self.cancelled_status, is_terminal=True
        )
        self.start_transition = StatusTransition.objects.create(
            workflow=self.workflow,
            key="start",
            name_en="Start",
            from_status=self.open_node,
            to_status=self.review_node,
        )
        self.workflow.update_active_status()

    def _ticket_with_pending_transition(self, transition):
        ticket = WorkflowTestModel.objects.create(name=f"Ticket {transition.key}")
        attach_workflow_to_object(
            ticket,
            self.workflow,
            user=self.user,
            auto_start=True,
            disable_clone=True,
        )
        perform_transition(ticket, "start", user=self.user)
        transition.from_status = self.review_node
        transition.save(update_fields=["from_status"])
        perform_transition(ticket, transition.key, user=self.user)
        return ticket

    def _approval_transition(self, **kwargs):
        defaults = {
            "workflow": self.workflow,
            "from_status": self.review_node,
            "to_status": self.cancelled_node,
            "requires_approval": True,
            "approval_config": {"approvals": [{"approval_type": ApprovalTypes.SELF}]},
        }
        defaults.update(kwargs)
        return StatusTransition.objects.create(**defaults)

    def test_reject_move_to_status_requires_target_when_no_default(self):
        transition = self._approval_transition(
            key="reject_without_target",
            name_en="Reject Without Target",
            reject_behavior=TransitionRejectBehavior.STAY_CURRENT,
        )
        ticket = self._ticket_with_pending_transition(transition)
        transition.reject_behavior = TransitionRejectBehavior.MOVE_TO_STATUS
        transition.save(update_fields=["reject_behavior"])

        with self.assertRaisesMessage(ValueError, "no target status"):
            reject_pending_transition(ticket, user=self.user, reason="No target")

    def test_reject_move_to_status_validates_allowed_keys_and_workflow_membership(self):
        transition = self._approval_transition(
            key="reject_to_allowed",
            name_en="Reject To Allowed",
            reject_behavior=TransitionRejectBehavior.MOVE_TO_STATUS,
            reject_to_status=self.rejected_node,
            metadata={"allowed_reject_status_keys": ["rejected", "external"]},
        )
        ticket = self._ticket_with_pending_transition(transition)

        transition.metadata = {"allowed_reject_status_keys": ["rejected"]}
        transition.save(update_fields=["metadata"])
        with self.assertRaisesMessage(ValueError, "not an allowed rejection target"):
            reject_pending_transition(
                ticket,
                user=self.user,
                reason="Wrong target",
                reject_to_status=self.cancelled_status,
            )

        transition.metadata = {"allowed_reject_status_keys": ["rejected", "external"]}
        transition.save(update_fields=["metadata"])
        with self.assertRaisesMessage(ValueError, "not part of workflow"):
            reject_pending_transition(
                ticket,
                user=self.user,
                reason="External target",
                reject_to_status=self.external_status,
            )

        reject_pending_transition(
            ticket,
            user=self.user,
            reason="Valid target",
            reject_to_status=self.rejected_status,
        )
        self.assertEqual(get_current_status(ticket), self.rejected_status)

    def test_reject_can_cancel_workflow_and_records_history(self):
        transition = self._approval_transition(
            key="cancel_on_reject",
            name_en="Cancel On Reject",
            reject_behavior=TransitionRejectBehavior.CANCEL_WORKFLOW,
        )
        ticket = self._ticket_with_pending_transition(transition)

        result = reject_pending_transition(
            ticket,
            user=self.user,
            metadata={"evidence": "customer asked to cancel"},
        )
        attachment = get_workflow_attachment(ticket)

        self.assertIsNotNone(result)
        self.assertEqual(attachment.status, WorkflowAttachmentStatus.CANCELLED)
        self.assertIsNotNone(attachment.completed_at)
        self.assertEqual(attachment.pending_transition, None)
        self.assertTrue(
            StatusHistory.objects.filter(
                transition=transition,
                metadata__reject_behavior=TransitionRejectBehavior.CANCEL_WORKFLOW,
            ).exists()
        )

    def test_reject_without_move_records_history_and_keeps_current_status(self):
        transition = self._approval_transition(
            key="request_changes",
            name_en="Request Changes",
            reject_behavior=TransitionRejectBehavior.REQUEST_CHANGES,
        )
        ticket = self._ticket_with_pending_transition(transition)

        reject_pending_transition(ticket, user=self.user, reason="Fix the evidence")
        attachment = get_workflow_attachment(ticket)

        self.assertEqual(attachment.current_status, self.review_status)
        self.assertEqual(attachment.pending_transition, None)
        self.assertTrue(
            StatusHistory.objects.filter(
                transition=transition,
                metadata__reject_behavior=TransitionRejectBehavior.REQUEST_CHANGES,
            ).exists()
        )

    def test_perform_transition_rejects_wrong_workflow_type_and_pending_transition(
        self,
    ):
        ticket = WorkflowTestModel.objects.create(name="Wrong strategy")
        attach_workflow_to_object(
            ticket,
            self.workflow,
            user=self.user,
            auto_start=True,
            disable_clone=True,
        )
        self.workflow.strategy = WorkflowStrategy.WORKFLOW_ONLY
        self.workflow.save(update_fields=["strategy"])

        with self.assertRaisesMessage(ValueError, "not a status graph workflow"):
            perform_transition(ticket, "start", user=self.user)

        self.workflow.strategy = WorkflowStrategy.STATUS_GRAPH
        self.workflow.save(update_fields=["strategy"])
        pending_transition = self._approval_transition(
            key="pending_guard",
            name_en="Pending Guard",
            reject_behavior=TransitionRejectBehavior.STAY_CURRENT,
        )
        pending_ticket = self._ticket_with_pending_transition(pending_transition)

        with self.assertRaisesMessage(ValueError, "already pending approval"):
            perform_transition(pending_ticket, "start", user=self.user)
