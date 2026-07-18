# Status Workflow API Guide

This guide defines and operates the three ticket workflow cases using REST APIs.
It assumes the package URLs are mounted under `/workflow/`:

```python
path("workflow/", include("django_workflow_engine.urls"))
```

Authentication, company scoping, and permission classes should be supplied by
the consuming project through the package API customization settings.

## 1. Core Endpoints

| Operation | Endpoint |
|---|---|
| Create complete flow | `POST /workflow/status/flow/` |
| Read complete model flow | `GET /workflow/status/flow/<app_label.model>/` |
| Read diagram | `GET /workflow/status/transitions/<app_label.model>/` |
| List model status options | `GET /workflow/status/options/<app_label.model>/` |
| Manage node/transition actions | `/workflow/status/actions/` |
| List current status attachments | `GET /workflow/status/attachments/` |
| Read status history | `GET /workflow/status/history/` |
| Attach through project ViewSet | `POST /api/tickets/<id>/attach_workflow/` |
| Available transitions | `GET /workflow/attachments/<id>/transitions/` |
| Perform transition | `POST /workflow/attachments/<id>/transition/` |
| Approve pending transition | `POST /workflow/attachments/<id>/approve_transition/` |
| Reject pending transition | `POST /workflow/attachments/<id>/reject_transition/` |

## 2. Expose Ticket Attachment APIs

Use `WorkflowMixin` on the project ViewSet:

```python
from rest_framework.viewsets import ModelViewSet

from django_workflow_engine.views import WorkflowMixin


class TicketViewSet(WorkflowMixin, ModelViewSet):
    queryset = Ticket.objects.all()
    serializer_class = TicketSerializer
```

Attach the workflow returned by the flow-creation API:

```http
POST /api/tickets/410/attach_workflow/
Content-Type: application/json
Authorization: Bearer <token>
```

```json
{
  "workflow_id": 25,
  "auto_start": true,
  "metadata": {
    "source": "ticket_api"
  }
}
```

The response includes the workflow attachment ID used by runtime endpoints.

## 3. Standard Support Workflow API

Create the full flow:

```http
POST /workflow/status/flow/
Content-Type: application/json
Authorization: Bearer <token>
```

```json
{
  "model": "support.ticket",
  "company": 1,
  "status_field": "status",
  "allow_direct_change": false,
  "default_status": "new",
  "terminal_statuses": ["closed"],
  "workflow": {
    "name_en": "Standard Support Workflow",
    "name_ar": "سير عمل الدعم القياسي"
  },
  "statuses": [
    {"code": "new", "key": "new", "name_en": "New", "name_ar": "جديد", "category": "open"},
    {"code": "assigned", "key": "assigned", "name_en": "Assigned", "name_ar": "مسند", "category": "active"},
    {"code": "in_progress", "key": "in_progress", "name_en": "In Progress", "name_ar": "قيد التنفيذ", "category": "active"},
    {"code": "pending_customer", "key": "pending_customer", "name_en": "Pending Customer", "name_ar": "بانتظار العميل", "category": "paused"},
    {
      "code": "resolved",
      "key": "resolved",
      "name_en": "Resolved",
      "name_ar": "تم الحل",
      "category": "done",
      "actions": [
        {
          "function_path": "schedule_ticket_auto_close",
          "parameters": {"delay_seconds": 172800}
        }
      ]
    },
    {"code": "closed", "key": "closed", "name_en": "Closed", "name_ar": "مغلق", "category": "done", "is_terminal": true}
  ],
  "transitions": [
    {
      "code": "assign",
      "name_en": "Assign",
      "from": "new",
      "to": "assigned",
      "metadata": {
        "required_metadata_keys": ["assignee_id"],
        "allowed_actors": ["creator", {"type": "team_lead"}]
      },
      "actions": [
        {"function_path": "notify_assigned_user", "parameters": {"template": "ticket_assigned"}, "order": 1},
        {"function_path": "start_ticket_sla", "parameters": {"policy": "standard_support"}, "order": 2}
      ]
    },
    {
      "code": "start_progress",
      "name_en": "Start Progress",
      "from": "assigned",
      "to": "in_progress",
      "metadata": {"allowed_actors": ["assigned_user"]}
    },
    {
      "code": "request_customer_information",
      "name_en": "Request Customer Information",
      "from": "in_progress",
      "to": "pending_customer",
      "metadata": {
        "required_metadata_keys": ["customer_request"],
        "allowed_actors": ["assigned_user"]
      },
      "actions": [
        {"function_path": "send_customer_information_request", "order": 1},
        {"function_path": "pause_ticket_sla", "order": 2}
      ]
    },
    {
      "code": "resume_after_customer_response",
      "name_en": "Resume After Customer Response",
      "from": "pending_customer",
      "to": "in_progress",
      "metadata": {"required_metadata_keys": ["customer_response"]},
      "actions": [
        {"function_path": "notify_assigned_user", "parameters": {"template": "customer_responded"}, "order": 1},
        {"function_path": "resume_ticket_sla", "order": 2}
      ]
    },
    {
      "code": "resolve",
      "name_en": "Resolve",
      "from": "in_progress",
      "to": "resolved",
      "metadata": {"required_metadata_keys": ["resolution"]},
      "actions": [
        {"function_path": "send_customer_survey", "order": 1},
        {"function_path": "stop_ticket_sla", "order": 2}
      ]
    },
    {
      "code": "close",
      "name_en": "Close",
      "from": "resolved",
      "to": "closed",
      "metadata": {
        "required_metadata_keys": ["survey_submitted"],
        "validation_function": "support.workflow_validators.validate_survey_submission"
      }
    }
  ]
}
```

Operate the flow:

```http
POST /workflow/attachments/90/transition/

{"transition_key": "assign", "metadata": {"assignee_id": 44}}
```

```http
POST /workflow/attachments/90/transition/

{"transition_key": "request_customer_information", "metadata": {"customer_request": "Attach server logs"}}
```

```http
POST /workflow/attachments/90/transition/

{"transition_key": "resume_after_customer_response", "metadata": {"customer_response": "Logs attached"}}
```

## 4. L1, L2, and L3 Escalation API

Create the flow using `POST /workflow/status/flow/`:

```json
{
  "model": "support.ticket",
  "company": 1,
  "status_field": "status",
  "allow_direct_change": false,
  "default_status": "new",
  "terminal_statuses": ["closed"],
  "workflow": {
    "name_en": "Tiered Support Workflow",
    "name_ar": "سير عمل مستويات الدعم"
  },
  "statuses": [
    {"code": "new", "key": "new", "name_en": "New", "name_ar": "جديد"},
    {"code": "level_1", "key": "level_1", "name_en": "Level 1 Support", "name_ar": "دعم المستوى الأول"},
    {"code": "level_2", "key": "level_2", "name_en": "Level 2 Support", "name_ar": "دعم المستوى الثاني"},
    {"code": "level_3", "key": "level_3", "name_en": "Level 3 Support", "name_ar": "دعم المستوى الثالث"},
    {"code": "resolved", "key": "resolved", "name_en": "Resolved", "name_ar": "تم الحل"},
    {"code": "closed", "key": "closed", "name_en": "Closed", "name_ar": "مغلق", "is_terminal": true}
  ],
  "transitions": [
    {
      "code": "assign_level_1",
      "name_en": "Assign Level 1",
      "from": "new",
      "to": "level_1",
      "actions": [
        {"function_path": "reassign_support_team", "parameters": {"fixed_level": 1}, "failure_policy": "raise"}
      ]
    },
    {
      "code": "escalate_level_2",
      "name_en": "Escalate Level 2",
      "from": "level_1",
      "to": "level_2",
      "metadata": {
        "required_metadata_keys": ["escalation_level", "escalation_reason"],
        "validation_function": "support.workflow_validators.validate_escalation_level",
        "allowed_actors": ["assigned_user", {"type": "assigned_user_manager", "manager_levels": [1]}]
      },
      "actions": [
        {"function_path": "reassign_support_team", "order": 1, "failure_policy": "raise"},
        {"function_path": "notify_team_leader", "order": 2},
        {"function_path": "record_escalation", "order": 3},
        {"function_path": "calculate_team_sla", "order": 4}
      ]
    },
    {
      "code": "escalate_level_3",
      "name_en": "Escalate Level 3",
      "from": "level_2",
      "to": "level_3",
      "metadata": {
        "required_metadata_keys": ["escalation_level", "escalation_reason"],
        "validation_function": "support.workflow_validators.validate_escalation_level"
      },
      "actions": [
        {"function_path": "reassign_support_team", "order": 1, "failure_policy": "raise"},
        {"function_path": "notify_team_leader", "order": 2},
        {"function_path": "record_escalation", "order": 3},
        {"function_path": "calculate_team_sla", "order": 4}
      ]
    },
    {"code": "resolve", "name_en": "Resolve", "from": "level_3", "to": "resolved"},
    {"code": "close", "name_en": "Close", "from": "resolved", "to": "closed"}
  ]
}
```

Escalate:

```http
POST /workflow/attachments/91/transition/
```

```json
{
  "transition_key": "escalate_level_2",
  "reason": "Requires database specialist",
  "metadata": {
    "escalation_level": 2,
    "escalation_reason": "Requires database specialist"
  }
}
```

The package validates the transition and calls project actions. The project
stores assignment, escalation history, and SLA calculations.

## 5. Site Visit Ticket API

Create the flow using `POST /workflow/status/flow/`:

```json
{
  "model": "support.ticket",
  "company": 1,
  "status_field": "status",
  "allow_direct_change": false,
  "default_status": "new",
  "terminal_statuses": ["resolved"],
  "workflow": {
    "name_en": "Site Visit Ticket Workflow",
    "name_ar": "سير عمل تذاكر الزيارة الميدانية"
  },
  "statuses": [
    {"code": "new", "key": "new", "name_en": "New", "name_ar": "جديد"},
    {"code": "assigned", "key": "assigned", "name_en": "Assigned", "name_ar": "مسند"},
    {
      "code": "site_visit_scheduled",
      "key": "site_visit_scheduled",
      "name_en": "Site Visit Scheduled",
      "name_ar": "تمت جدولة الزيارة",
      "actions": [
        {"function_path": "send_appointment_notification"}
      ]
    },
    {"code": "on_site", "key": "on_site", "name_en": "On Site", "name_ar": "في الموقع"},
    {"code": "pending_parts", "key": "pending_parts", "name_en": "Pending Parts", "name_ar": "بانتظار القطع"},
    {"code": "resolved", "key": "resolved", "name_en": "Resolved", "name_ar": "تم الحل", "is_terminal": true}
  ],
  "transitions": [
    {
      "code": "assign",
      "name_en": "Assign",
      "from": "new",
      "to": "assigned",
      "metadata": {"required_metadata_keys": ["engineer_id"]}
    },
    {
      "code": "schedule_visit",
      "name_en": "Schedule Site Visit",
      "from": "assigned",
      "to": "site_visit_scheduled",
      "metadata": {"required_metadata_keys": ["engineer_id", "scheduled_at"]},
      "actions": [
        {"function_path": "notify_assigned_user", "order": 1},
        {"function_path": "create_visit_task", "order": 2, "failure_policy": "raise"}
      ]
    },
    {
      "code": "check_in",
      "name_en": "Check In",
      "from": "site_visit_scheduled",
      "to": "on_site",
      "metadata": {
        "required_metadata_keys": ["latitude", "longitude"],
        "validation_function": "field_service.workflow_validators.validate_check_in",
        "allowed_actors": ["assigned_user"]
      },
      "actions": [
        {"function_path": "record_check_in", "failure_policy": "raise"}
      ]
    },
    {
      "code": "request_parts",
      "name_en": "Request Parts",
      "from": "on_site",
      "to": "pending_parts",
      "metadata": {"required_metadata_keys": ["parts"]},
      "actions": [
        {"function_path": "create_parts_request", "failure_policy": "raise"}
      ]
    },
    {
      "code": "parts_received",
      "name_en": "Parts Received",
      "from": "pending_parts",
      "to": "on_site",
      "metadata": {"required_metadata_keys": ["parts_receipt_id"]}
    },
    {
      "code": "resolve",
      "name_en": "Resolve",
      "from": "on_site",
      "to": "resolved",
      "metadata": {"required_metadata_keys": ["resolution"]}
    }
  ]
}
```

Check in:

```http
POST /workflow/attachments/92/transition/
```

```json
{
  "transition_key": "check_in",
  "metadata": {
    "latitude": 24.7136,
    "longitude": 46.6753
  }
}
```

Request parts:

```json
{
  "transition_key": "request_parts",
  "metadata": {
    "parts": [
      {"sku": "PART-100", "quantity": 2}
    ]
  }
}
```

## 6. Approval APIs

If a transition contains `approvals`, performing it creates approval instances
and leaves the object in its current status.

Approve using the assigned approval user:

```http
POST /workflow/attachments/90/approve_transition/
```

```json
{
  "reason": "Resolution approved",
  "form_data": {
    "verification_notes": "Tested successfully"
  }
}
```

Reject:

```http
POST /workflow/attachments/90/reject_transition/
```

```json
{
  "reason": "Issue still occurs",
  "evidence": "customer-email-551",
  "reject_to_status_id": 18
}
```

These endpoints use the existing approval workflow. They enforce assigned users,
role strategies, forms, and multi-step ordering.

## 7. Add or Update Actions Separately

Create a transition action after the workflow is designed:

```http
POST /workflow/status/actions/
```

```json
{
  "transition": 65,
  "action_type": "after_transition",
  "function_path": "support.workflow_actions.notify_team_leader",
  "condition_function": "support.workflow_conditions.is_high_priority",
  "failure_policy": "continue",
  "parameters": {"template": "high_priority_escalation"},
  "order": 2,
  "is_active": true
}
```

Create a status-entry action:

```json
{
  "status_node": 31,
  "action_type": "on_status_enter",
  "function_path": "support.workflow_actions.schedule_sla_check",
  "parameters": {"delay_minutes": 120},
  "order": 1,
  "is_active": true
}
```

## 8. Company Default Provisioning API

Company provisioning is project-owned because company models and authorization
differ. Expose a small project endpoint around the package helper:

```python
from rest_framework.response import Response
from rest_framework.views import APIView

from django_workflow_engine.status_services import auto_generate_default_flow


class ProvisionCompanyStatusWorkflowsView(APIView):
    def post(self, request, company_id):
        workflows = auto_generate_default_flow(
            company_id,
            flow=request.data.get("flow"),
            user=request.user,
        )
        return Response(
            {
                model: {
                    "workflow_id": workflow.id,
                    "name_en": workflow.name_en,
                }
                for model, workflow in workflows.items()
            }
        )
```

```http
POST /api/companies/12/provision-status-workflows/
```

Omit `flow` to create every model configured in
`DEFAULT_STATUS_WORKFLOWS`. Send a model label to provision one configured
model, or send a full design dictionary containing `model`.

Provisioning is idempotent. Repeating the request returns existing defaults for
that company and model.

## 9. Read APIs for Frontend

Get the complete graph:

```http
GET /workflow/status/flow/support.ticket/?workflow_id=25
```

Get diagram nodes and edges:

```http
GET /workflow/status/transitions/support.ticket/?workflow_id=25
```

Get transitions available to the authenticated user:

```http
GET /workflow/attachments/90/transitions/
```

Get status history:

```http
GET /workflow/status/history/?content_type=support.ticket&object_id=410
```

Projects should apply company filtering through their configured API mixins.
