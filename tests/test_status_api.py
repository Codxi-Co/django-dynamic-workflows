"""API tests for status and status-transition endpoints."""

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings

from rest_framework.test import APIClient

from django_workflow_engine.choices import (
    ApprovalTypes,
    StatusCategory,
    TransitionRejectBehavior,
    WorkflowAttachmentStatus,
    WorkflowStatus,
    WorkflowStrategy,
)
from django_workflow_engine.models import (
    Status,
    StatusTransition,
    WorkFlow,
    WorkflowStatusNode,
)
from django_workflow_engine.services import (
    attach_workflow_to_object,
    register_model_for_statuses,
)
from django_workflow_engine.status_services import create_status_flow_design
from sandbox.testapp.models import WorkflowTestModel

User = get_user_model()


@override_settings(ROOT_URLCONF="django_workflow_engine.urls")
class StatusAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="api-user", email="api@example.com", password="pass"
        )
        self.client.force_authenticate(self.user)

    def test_create_status_with_company_and_translations(self):
        content_type = ContentType.objects.get_for_model(WorkflowTestModel)
        response = self.client.post(
            "/status/",
            {
                "name_en": "New",
                "name_ar": "جديد",
                "category": StatusCategory.OPEN,
                "company": self.user.id,
                "model": "testapp.workflowtestmodel",
                "color": "#2E74B5",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["key"], "new")
        self.assertEqual(response.data["name_en"], "New")
        self.assertEqual(response.data["name_ar"], "جديد")
        self.assertEqual(response.data["company"], self.user.id)
        self.assertEqual(response.data["content_type"], content_type.id)
        self.assertEqual(response.data["model_label"], "testapp.workflowtestmodel")

    def test_create_and_get_full_status_flow_design(self):
        content_type = ContentType.objects.get_for_model(WorkflowTestModel)

        response = self.client.post(
            "/status/flow/",
            {
                "model": "testapp.workflowtestmodel",
                "company": self.user.id,
                "status_field": "status",
                "default_status": "new",
                "terminal_statuses": ["won", "lost"],
                "workflow": {
                    "name_en": "Opportunity Workflow",
                    "name_ar": "سير عمل الفرص",
                },
                "statuses": [
                    {
                        "code": "new",
                        "name_en": "New Opportunity",
                        "name_ar": "فرصة جديدة",
                        "category": StatusCategory.OPEN,
                        "metadata": {"probability": 10},
                    },
                    {
                        "code": "qualified",
                        "name_en": "Qualified",
                        "name_ar": "مؤهلة",
                        "category": StatusCategory.ACTIVE,
                        "metadata": {"probability": 40},
                    },
                    {
                        "code": "won",
                        "name_en": "Won",
                        "name_ar": "رابحة",
                        "category": StatusCategory.DONE,
                    },
                    {
                        "code": "lost",
                        "name_en": "Lost",
                        "name_ar": "خاسرة",
                        "category": StatusCategory.CANCELLED,
                    },
                ],
                "transitions": [
                    {
                        "code": "qualify",
                        "name_en": "Qualify",
                        "name_ar": "تأهيل",
                        "from": "new",
                        "to": "qualified",
                    },
                    {
                        "code": "mark_won",
                        "name_en": "Mark Won",
                        "name_ar": "تحديد كرابحة",
                        "from": "qualified",
                        "to": "won",
                        "approvals": [{"approval_type": ApprovalTypes.SELF}],
                    },
                    {
                        "code": "mark_lost",
                        "name_en": "Mark Lost",
                        "name_ar": "تحديد كخاسرة",
                        "from": "qualified",
                        "to": "lost",
                        "metadata": {"required_metadata_keys": ["lost_reason"]},
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["content_type"], content_type.id)
        self.assertEqual(response.data["configuration"]["status_field"], "status")
        self.assertEqual(response.data["workflow"]["name_en"], "Opportunity Workflow")
        self.assertEqual(
            [status["label_en"] for status in response.data["statuses"]],
            ["New Opportunity", "Qualified", "Won", "Lost"],
        )
        self.assertEqual(
            {transition["code"] for transition in response.data["transitions"]},
            {"qualify", "mark_won", "mark_lost"},
        )
        self.assertEqual(len(response.data["diagram"]["nodes"]), 4)
        self.assertEqual(len(response.data["diagram"]["edges"]), 3)

        get_response = self.client.get("/status/flow/testapp.workflowtestmodel/")
        self.assertEqual(get_response.status_code, 200, get_response.data)
        self.assertEqual(
            get_response.data["workflow"]["id"], response.data["workflow"]["id"]
        )
        self.assertEqual(
            {
                transition["code"]
                for transition in get_response.data["diagram"]["edges"]
            },
            {"qualify", "mark_won", "mark_lost"},
        )

    def test_create_full_status_flow_design_helper(self):
        result = create_status_flow_design(
            {
                "model": "testapp.workflowtestmodel",
                "company": self.user.id,
                "default_status": "new",
                "statuses": [
                    {
                        "code": "new",
                        "name_en": "New",
                        "name_ar": "جديد",
                        "category": StatusCategory.OPEN,
                    },
                    {
                        "code": "closed",
                        "name_en": "Closed",
                        "name_ar": "مغلق",
                        "category": StatusCategory.DONE,
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

        self.assertEqual(result["model"], "testapp.workflowtestmodel")
        self.assertEqual(result["statuses"][0]["label_en"], "New")
        self.assertEqual(result["transitions"][0]["code"], "close")
        self.assertEqual(Status.objects.get(key="new").created_by, self.user)

    def test_trigger_status_transition_through_attachment_api(self):
        new = Status.objects.create(
            key="new", name_en="New", name_ar="جديد", category=StatusCategory.OPEN
        )
        in_progress = Status.objects.create(
            key="in_progress",
            name_en="In Progress",
            name_ar="قيد التنفيذ",
            category=StatusCategory.ACTIVE,
        )
        register_model_for_statuses(
            WorkflowTestModel,
            statuses=[new, in_progress],
            default_status=new,
            status_field="status",
        )
        workflow = WorkFlow.objects.create(
            company=self.user,
            name_en="Ticket Workflow",
            name_ar="سير عمل التذاكر",
            status=WorkflowStatus.ACTIVE,
            strategy=WorkflowStrategy.STATUS_GRAPH,
        )
        new_node = WorkflowStatusNode.objects.create(
            workflow=workflow, status=new, is_initial=True
        )
        progress_node = WorkflowStatusNode.objects.create(
            workflow=workflow, status=in_progress
        )
        StatusTransition.objects.create(
            workflow=workflow,
            key="start_progress",
            name_en="Start Progress",
            name_ar="بدء التنفيذ",
            from_status=new_node,
            to_status=progress_node,
            metadata={"required_metadata_keys": ["assignee_id"]},
        )
        workflow.update_active_status()
        ticket = WorkflowTestModel.objects.create(name="API Ticket")
        attachment = attach_workflow_to_object(
            ticket,
            workflow,
            user=self.user,
            auto_start=True,
            disable_clone=True,
        )

        response = self.client.post(
            f"/attachments/{attachment.id}/transition/",
            {
                "transition_key": "start_progress",
                "metadata": {"assignee_id": self.user.id},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        attachment.refresh_from_db()
        ticket.refresh_from_db()
        self.assertEqual(attachment.current_status, in_progress)
        self.assertEqual(ticket.status, "in_progress")

    def test_transition_approval_api_enforces_assigned_approver(self):
        new = Status.objects.create(key="new", name_en="New")
        resolved = Status.objects.create(key="resolved", name_en="Resolved")
        register_model_for_statuses(
            WorkflowTestModel,
            statuses=[new, resolved],
            default_status=new,
            status_field="status",
        )
        workflow = WorkFlow.objects.create(
            company=self.user,
            name_en="Approval Security Workflow",
            name_ar="Approval Security Workflow",
            status=WorkflowStatus.ACTIVE,
            strategy=WorkflowStrategy.STATUS_GRAPH,
        )
        new_node = WorkflowStatusNode.objects.create(
            workflow=workflow, status=new, is_initial=True
        )
        resolved_node = WorkflowStatusNode.objects.create(
            workflow=workflow, status=resolved, is_terminal=True
        )
        StatusTransition.objects.create(
            workflow=workflow,
            key="resolve",
            name_en="Resolve",
            from_status=new_node,
            to_status=resolved_node,
            requires_approval=True,
            approval_config={"approvals": [{"approval_type": ApprovalTypes.SELF}]},
        )
        workflow.update_active_status()
        ticket = WorkflowTestModel.objects.create(name="Approval Security Ticket")
        attachment = attach_workflow_to_object(
            ticket,
            workflow,
            user=self.user,
            auto_start=True,
            disable_clone=True,
        )
        transition_response = self.client.post(
            f"/attachments/{attachment.id}/transition/",
            {"transition_key": "resolve"},
            format="json",
        )
        self.assertEqual(transition_response.status_code, 200)

        unauthorized = User.objects.create_user(username="unauthorized-approver")
        self.client.force_authenticate(unauthorized)
        denied = self.client.post(
            f"/attachments/{attachment.id}/approve_transition/",
            {"reason": "Not assigned"},
            format="json",
        )
        self.assertEqual(denied.status_code, 400)
        attachment.refresh_from_db()
        self.assertEqual(attachment.current_status, new)
        self.assertIsNotNone(attachment.pending_transition)

        self.client.force_authenticate(self.user)
        approved = self.client.post(
            f"/attachments/{attachment.id}/approve_transition/",
            {"reason": "Assigned approver"},
            format="json",
        )
        self.assertEqual(approved.status_code, 200, approved.data)
        attachment.refresh_from_db()
        self.assertEqual(attachment.current_status, resolved)
        self.assertIsNone(attachment.pending_transition)

    def test_full_ticket_flow_through_status_apis(self):
        content_type = ContentType.objects.get_for_model(WorkflowTestModel)

        def create_status(name_en, name_ar, category):
            response = self.client.post(
                "/status/",
                {
                    "name_en": name_en,
                    "name_ar": name_ar,
                    "category": category,
                    "company": self.user.id,
                    "model": "testapp.workflowtestmodel",
                },
                format="json",
            )
            self.assertEqual(response.status_code, 201, response.data)
            return response.data

        statuses = {
            "pending": create_status(
                "Pending PM Review", "بانتظار مراجعة مدير المنتج", StatusCategory.OPEN
            ),
            "new": create_status("New", "جديد", StatusCategory.OPEN),
            "in_progress": create_status(
                "In Progress", "قيد التنفيذ", StatusCategory.ACTIVE
            ),
            "on_hold": create_status("On Hold", "معلق", StatusCategory.PAUSED),
            "resolved": create_status("Resolved", "تم الحل", StatusCategory.DONE),
            "closed": create_status("Closed", "مغلق", StatusCategory.DONE),
            "duplicated": create_status("Duplicated", "مكرر", StatusCategory.CANCELLED),
            "rejected": create_status("Rejected", "مرفوض", StatusCategory.CANCELLED),
        }

        config_response = self.client.post(
            "/status/model-configurations/",
            {
                "content_type": content_type.id,
                "is_enabled": True,
                "status_field": "status",
                "default_status": statuses["pending"]["id"],
                "auto_create_attachment": True,
                "allow_direct_change": True,
            },
            format="json",
        )
        self.assertEqual(config_response.status_code, 201, config_response.data)

        models_response = self.client.get("/status/models/")
        self.assertEqual(models_response.status_code, 200, models_response.data)
        self.assertEqual(
            models_response.data,
            [
                {
                    "content_type": content_type.id,
                    "model": "testapp.workflowtestmodel",
                    "app_label": "testapp",
                    "model_name": "workflowtestmodel",
                    "label": "workflow test model",
                    "configuration_id": config_response.data["id"],
                    "status_field": "status",
                    "default_status": statuses["pending"]["id"],
                    "statuses_count": 0,
                }
            ],
        )

        for index, status_data in enumerate(statuses.values()):
            response = self.client.post(
                "/status/model-statuses/",
                {
                    "configuration": config_response.data["id"],
                    "status": status_data["id"],
                    "is_initial": status_data == statuses["pending"],
                    "is_terminal": status_data
                    in [
                        statuses["closed"],
                        statuses["duplicated"],
                        statuses["rejected"],
                    ],
                    "order": index,
                    "is_active": True,
                },
                format="json",
            )
            self.assertEqual(response.status_code, 201, response.data)

        workflow = WorkFlow.objects.create(
            company=self.user,
            name_en="Ticket API Workflow",
            name_ar="سير عمل التذاكر",
            status=WorkflowStatus.ACTIVE,
            strategy=WorkflowStrategy.STATUS_GRAPH,
        )

        nodes = {}
        for index, (name, status_data) in enumerate(statuses.items()):
            response = self.client.post(
                "/status/workflow-statuses/",
                {
                    "workflow": workflow.id,
                    "status": status_data["id"],
                    "is_initial": name == "pending",
                    "is_terminal": name in ["closed", "duplicated", "rejected"],
                    "order": index,
                    "is_active": True,
                },
                format="json",
            )
            self.assertEqual(response.status_code, 201, response.data)
            nodes[name] = response.data

        def create_transition(
            key,
            name_en,
            from_node,
            to_node,
            requires_approval=False,
            reject_behavior=TransitionRejectBehavior.STAY_CURRENT,
            reject_to_status=None,
            metadata=None,
        ):
            payload = {
                "workflow": workflow.id,
                "key": key,
                "name_en": name_en,
                "name_ar": name_en,
                "from_status": nodes[from_node]["id"],
                "to_status": nodes[to_node]["id"],
                "approvals": (
                    [{"approval_type": ApprovalTypes.SELF}] if requires_approval else []
                ),
                "reject_behavior": reject_behavior,
                "reject_to_status": (
                    nodes[reject_to_status]["id"] if reject_to_status else None
                ),
                "metadata": metadata or {},
                "is_active": True,
            }
            response = self.client.post(
                "/status/transitions/",
                payload,
                format="json",
            )
            self.assertEqual(response.status_code, 201, response.data)
            return response.data

        create_transition(
            "pm_confirm_valid",
            "PM Confirm Valid",
            "pending",
            "new",
            requires_approval=True,
            reject_behavior=TransitionRejectBehavior.MOVE_TO_STATUS,
            reject_to_status="rejected",
            metadata={"allowed_reject_status_keys": ["duplicated", "rejected"]},
        )
        create_transition(
            "start_progress",
            "Start Progress",
            "new",
            "in_progress",
            metadata={"required_metadata_keys": ["assignee_id"]},
        )
        create_transition(
            "put_on_hold",
            "Put On Hold",
            "in_progress",
            "on_hold",
            requires_approval=True,
            metadata={"required_metadata_keys": ["customer_requirement"]},
        )
        create_transition(
            "resume_from_hold",
            "Resume From Hold",
            "on_hold",
            "in_progress",
            requires_approval=True,
            metadata={"required_metadata_keys": ["customer_response"]},
        )
        create_transition(
            "resolve",
            "Resolve",
            "in_progress",
            "resolved",
            requires_approval=True,
            reject_behavior=TransitionRejectBehavior.MOVE_TO_STATUS,
            reject_to_status="in_progress",
        )
        create_transition("reopen", "Reopen", "resolved", "in_progress")
        create_transition(
            "close",
            "Close",
            "resolved",
            "closed",
            requires_approval=True,
            reject_behavior=TransitionRejectBehavior.MOVE_TO_STATUS,
            reject_to_status="in_progress",
        )
        workflow.update_active_status()

        options_response = self.client.get(
            f"/status/options/testapp.workflowtestmodel/?workflow_id={workflow.id}"
        )
        self.assertEqual(options_response.status_code, 200, options_response.data)
        self.assertEqual(options_response.data["content_type"], content_type.id)
        self.assertEqual(options_response.data["workflow"]["id"], workflow.id)
        self.assertEqual(
            [status["label_en"] for status in options_response.data["statuses"]],
            [
                "Pending PM Review",
                "New",
                "In Progress",
                "On Hold",
                "Resolved",
                "Closed",
                "Duplicated",
                "Rejected",
            ],
        )
        self.assertEqual(
            [
                status["label_en"]
                for status in options_response.data["workflow_statuses"]
            ],
            [
                "Pending PM Review",
                "New",
                "In Progress",
                "On Hold",
                "Resolved",
                "Closed",
                "Duplicated",
                "Rejected",
            ],
        )

        diagram_response = self.client.get(
            f"/status/transitions/testapp.workflowtestmodel/?workflow_id={workflow.id}"
        )
        self.assertEqual(diagram_response.status_code, 200, diagram_response.data)
        self.assertEqual(diagram_response.data["content_type"], content_type.id)
        self.assertEqual(diagram_response.data["workflow"]["id"], workflow.id)
        self.assertEqual(len(diagram_response.data["nodes"]), 8)
        self.assertEqual(len(diagram_response.data["edges"]), 7)
        self.assertEqual(
            {edge["key"] for edge in diagram_response.data["diagram"]["edges"]},
            {
                "pm_confirm_valid",
                "start_progress",
                "put_on_hold",
                "resume_from_hold",
                "resolve",
                "reopen",
                "close",
            },
        )

        ticket = WorkflowTestModel.objects.create(name="Full API Ticket")
        attachment = attach_workflow_to_object(
            ticket,
            workflow,
            user=self.user,
            auto_start=True,
            disable_clone=True,
        )

        def post_transition(key, metadata=None):
            response = self.client.post(
                f"/attachments/{attachment.id}/transition/",
                {"transition_key": key, "metadata": metadata or {}},
                format="json",
            )
            self.assertEqual(response.status_code, 200, response.data)
            attachment.refresh_from_db()
            ticket.refresh_from_db()
            return response

        def approve(reason):
            response = self.client.post(
                f"/attachments/{attachment.id}/approve_transition/",
                {"reason": reason},
                format="json",
            )
            self.assertEqual(response.status_code, 200, response.data)
            attachment.refresh_from_db()
            ticket.refresh_from_db()
            return response

        post_transition("pm_confirm_valid")
        self.assertEqual(attachment.current_status_id, statuses["pending"]["id"])
        approve("PM approved valid ticket")
        self.assertEqual(attachment.current_status_id, statuses["new"]["id"])

        post_transition("start_progress", {"assignee_id": self.user.id})
        self.assertEqual(attachment.current_status_id, statuses["in_progress"]["id"])

        post_transition(
            "put_on_hold",
            {"customer_requirement": "Need logs or attachment from customer"},
        )
        self.assertEqual(attachment.current_status_id, statuses["in_progress"]["id"])
        approve("Requirement is valid")
        self.assertEqual(attachment.current_status_id, statuses["on_hold"]["id"])

        post_transition(
            "resume_from_hold",
            {"customer_response": "Customer provided requested logs"},
        )
        self.assertEqual(attachment.current_status_id, statuses["on_hold"]["id"])
        approve("Customer response accepted")
        self.assertEqual(attachment.current_status_id, statuses["in_progress"]["id"])

        post_transition("resolve")
        approve("QA approved resolution")
        self.assertEqual(attachment.current_status_id, statuses["resolved"]["id"])

        post_transition("close")
        response = self.client.post(
            f"/attachments/{attachment.id}/reject_transition/",
            {
                "reason": "Customer rejected closure",
                "evidence": "customer-email-thread",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        attachment.refresh_from_db()
        self.assertEqual(attachment.current_status_id, statuses["in_progress"]["id"])

        post_transition("resolve")
        approve("QA approved final fix")
        post_transition("close")
        approve("Customer accepted closure")

        self.assertEqual(attachment.current_status_id, statuses["closed"]["id"])
        self.assertEqual(attachment.status, WorkflowAttachmentStatus.COMPLETED)
