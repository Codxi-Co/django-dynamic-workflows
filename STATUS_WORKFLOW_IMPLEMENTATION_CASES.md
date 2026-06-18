# Status Workflow Implementation Cases

This guide shows how to implement the three ticket workflows using status graphs
and developer-owned custom actions.

The workflow package is responsible for:

- statuses and allowed transitions
- transition actor permissions
- approval requirements
- required transition input
- action ordering and lifecycle events
- status history and direct-change protection

The consuming project remains responsible for:

- notifications and email delivery
- SLA storage and calculations
- task and visit models
- background scheduling and retries
- escalation and assignment history
- project-specific form and location validation

## 1. Project Setup

Add the package applications and URLs:

```python
# settings.py
INSTALLED_APPS = [
    # ...
    "approval_workflow",
    "django_workflow_engine",
]
```

```python
# urls.py
from django.urls import include, path

urlpatterns = [
    path("workflow/", include("django_workflow_engine.urls")),
]
```

Apply migrations:

```bash
python manage.py migrate
```

## 2. Default Workflow Per Company

Register a default status workflow definition for every model in settings:

```python
# settings.py
DJANGO_WORKFLOW_ENGINE = {
    "DEFAULT_STATUS_WORKFLOWS": {
        "support.Ticket": {
            "status_field": "status",
            "allow_direct_change": False,
            "default_status": "new",
            "terminal_statuses": ["closed"],
            "workflow": {
                "name_en": "Standard Support Workflow",
                "name_ar": "سير عمل الدعم القياسي",
            },
            "statuses": [
                {
                    "code": "new",
                    "name_en": "New",
                    "name_ar": "جديد",
                    "category": "open",
                },
                {
                    "code": "in_progress",
                    "name_en": "In Progress",
                    "name_ar": "قيد التنفيذ",
                    "category": "active",
                },
                {
                    "code": "closed",
                    "name_en": "Closed",
                    "name_ar": "مغلق",
                    "category": "done",
                    "is_terminal": True,
                },
            ],
            "transitions": [
                {
                    "code": "start_progress",
                    "name_en": "Start Progress",
                    "from": "new",
                    "to": "in_progress",
                },
                {
                    "code": "close",
                    "name_en": "Close",
                    "from": "in_progress",
                    "to": "closed",
                },
            ],
            "company_field": "company",
            "auto_start": True,
        },
        "tasks.Task": {
            "status_field": "status",
            "default_status": "to_do",
            "statuses": [
                {"code": "to_do", "name_en": "To Do", "name_ar": "للعمل"},
                {
                    "code": "in_progress",
                    "name_en": "In Progress",
                    "name_ar": "قيد التنفيذ",
                },
            ],
            "transitions": [
                {
                    "code": "start",
                    "name_en": "Start",
                    "from": "to_do",
                    "to": "in_progress",
                }
            ],
            "company_field": "company",
            "auto_start": True,
        },
    }
}
```

The dictionary is the same design accepted by `create_status_flow_design()`.
Do not include `model` or `company`; the package adds them for the company being
provisioned. A factory is still supported for dynamically generated designs:

```python
"support.Ticket": {
    "factory": "support.workflow_defaults.ticket_status_flow",
    "company_field": "company",
}
```

### When Defaults Should Be Created

The recommended trigger is company provisioning, immediately after the company
transaction succeeds:

```python
from django_workflow_engine.status_services import auto_generate_default_flow


def provision_company(company, user):
    # Create departments, roles, and other company defaults first.
    auto_generate_default_flow(company.id, user=user)
```

The function is idempotent. Calling it repeatedly returns the existing
company/model workflows rather than creating duplicates.

Pass a model label to provision only that configured flow:

```python
auto_generate_default_flow(
    company.id,
    flow="support.Ticket",
    user=user,
)
```

An explicit design can also be supplied instead of reading settings:

```python
auto_generate_default_flow(
    company.id,
    flow={
        "model": "support.Ticket",
        "status_field": "status",
        "default_status": "new",
        "workflow": {
            "name_en": "Special Support Workflow",
            "name_ar": "سير عمل دعم خاص",
        },
        "statuses": [
            {"code": "new", "name_en": "New", "name_ar": "جديد"},
            {"code": "closed", "name_en": "Closed", "name_ar": "مغلق"},
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
    user=user,
)
```

For existing companies, call the same function from a data migration or
management command:

```python
for company in Company.objects.iterator():
    auto_generate_default_flow(company.id, user=system_user)
```

Do not provision tenant data from `AppConfig.ready()`. It runs during management
commands and may run in every web or worker process.

Lazy provisioning is also available when the first object needs a workflow:

```python
from django_workflow_engine.status_services import (
    attach_default_status_workflow,
)


ticket = serializer.save()
attachment = attach_default_status_workflow(
    ticket,
    user=request.user,
)
```

This resolves the company using `company_field`, creates the default workflow if
it does not exist, and attaches a cloned workflow to the object. The setting's
`auto_start` value controls whether the attachment starts immediately.

To provision without attaching:

```python
from django_workflow_engine.status_services import (
    get_or_create_default_status_workflow_for_object,
)

workflow = get_or_create_default_status_workflow_for_object(
    ticket,
    user=request.user,
)
```

For a single-tenant application or an already-provisioned company workflow, model
registration can store a direct default:

```python
from django_workflow_engine.services import register_model_for_statuses

register_model_for_statuses(
    Ticket,
    statuses=ticket_statuses,
    default_status=new_status,
    default_workflow=ticket_workflow,
    auto_start_workflow=True,
    status_field="status",
    allow_direct_change=False,
)
```

For multi-company projects, prefer `DEFAULT_STATUS_WORKFLOWS`; one global
`WorkflowConfiguration.default_workflow` cannot represent a different workflow
for every company.

Your model may keep its existing status field. The package synchronizes that
field when `status_field` is configured:

```python
class Ticket(models.Model):
    status = models.CharField(max_length=100, default="new")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
```

## 3. Custom Action Contract

### Model-Specific Transition Actors

Ticket, Task, and Opportunity models may use different ownership and assignment
fields. Configure actor discovery per model:

```python
DJANGO_WORKFLOW_ENGINE = {
    "TRANSITION_ACTORS": {
        "default": {
            "OWNER_FIELD": "created_by",
            "MANAGER_FIELD": "manager",
        },
        "support.Ticket": {
            "ASSIGNED_USER_FUNCTION": "support.workflow_actors.get_assigned_user",
            "TEAM_USERS_FUNCTION": "support.workflow_actors.get_team_users",
        },
        "tasks.Task": {
            "OWNER_FIELD": "requested_by",
            "ASSIGNED_USER_FIELD": "assignee",
        },
        "crm.Opportunity": {
            "ASSIGNED_USER_FIELD": "sales_owner",
        },
    }
}
```

Resolver functions always receive the object whose transition is being checked:

```python
def get_assigned_user(obj, actor_type=None):
    # For support.Ticket, obj is the Ticket instance.
    return obj.assigned_to
```

Rule-level `field` or `function` values still override the model settings for
one specific transition.

Actions can be registered by name or referenced by a dotted Python path.
Registration is recommended:

```python
# support/workflow_actions.py
from django_workflow_engine.action_registry import registry


@registry.register(name="notify_assigned_user", category="notification")
def notify_assigned_user(
    workflow_attachment,
    action_parameters,
    obj=None,
    user=None,
    metadata=None,
    **context,
):
    assigned_user = obj.assigned_to
    notification_service.send(
        recipient=assigned_user,
        template=action_parameters["template"],
        context={"ticket": obj, "actor": user},
    )
    return True
```

Common action context includes:

- `workflow_attachment`
- `obj`
- `workflow`
- `transition`
- `from_status` and `to_status`
- `status` and `status_node` for status-entry actions
- `previous_status`
- `user`
- `metadata`
- `action_parameters` for registered actions

Import the module when the application starts so registrations execute:

```python
# support/apps.py
from django.apps import AppConfig


class SupportConfig(AppConfig):
    name = "support"

    def ready(self):
        from . import workflow_actions  # noqa: F401
```

### Action Conditions

Conditions remain project functions:

```python
# support/workflow_conditions.py
def is_high_priority(**context):
    return context["obj"].priority == "high"
```

```json
{
  "function_path": "notify_team_leader",
  "condition_function": "support.workflow_conditions.is_high_priority",
  "failure_policy": "continue"
}
```

Failure policies are:

- `continue`: log the failure and execute the next action
- `stop`: stop the remaining actions for that event
- `raise`: raise the error and roll back the transition

Use `raise` only when the transition must not complete unless the action
succeeds. External side effects cannot be rolled back by the database, so use an
outbox or idempotent project service for critical integrations.

## 4. Standard Support Workflow

Business flow:

```text
New -> Assigned -> In Progress -> Pending Customer -> In Progress
                                             |
In Progress -> Resolved -> Closed             |
```

### Project Actions

```python
# support/workflow_actions.py
from django_workflow_engine.action_registry import registry
from django_workflow_engine.services import get_current_status, perform_transition


@registry.register(name="start_ticket_sla", category="sla")
def start_ticket_sla(workflow_attachment, action_parameters, obj=None, **context):
    sla_service.start(ticket=obj, policy=action_parameters["policy"])
    return True


@registry.register(name="pause_ticket_sla", category="sla")
def pause_ticket_sla(workflow_attachment, action_parameters, obj=None, **context):
    sla_service.pause(ticket=obj, reason="pending_customer")
    return True


@registry.register(name="resume_ticket_sla", category="sla")
def resume_ticket_sla(workflow_attachment, action_parameters, obj=None, **context):
    sla_service.resume(ticket=obj)
    return True


@registry.register(name="stop_ticket_sla", category="sla")
def stop_ticket_sla(workflow_attachment, action_parameters, obj=None, **context):
    sla_service.stop(ticket=obj)
    return True


@registry.register(name="schedule_ticket_auto_close", category="scheduler")
def schedule_ticket_auto_close(
    workflow_attachment,
    action_parameters,
    obj=None,
    **context,
):
    # Celery is an example. Use the scheduler selected by your project.
    auto_close_ticket.apply_async(
        kwargs={"ticket_id": obj.pk},
        countdown=action_parameters["delay_seconds"],
    )
    return True


def auto_close_ticket(ticket_id):
    ticket = Ticket.objects.get(pk=ticket_id)

    # The scheduled job must be idempotent and verify current state.
    if get_current_status(ticket).key != "resolved":
        return

    perform_transition(
        ticket,
        "close",
        user=get_system_workflow_user(),
        metadata={"survey_submitted": True, "source": "scheduled_auto_close"},
    )
```

### Survey Validator

```python
# support/workflow_validators.py
def validate_survey_submission(
    obj,
    transition,
    metadata,
    user,
    attachment,
):
    return bool(metadata.get("survey_submitted"))
```

### Full Flow Payload

Send this payload to `POST /workflow/status/flow/` or pass it to
`create_status_flow_design(payload, user=request.user)`:

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
    {"code": "new", "name_en": "New", "name_ar": "جديد", "category": "open"},
    {"code": "assigned", "name_en": "Assigned", "name_ar": "مسند", "category": "active"},
    {"code": "in_progress", "name_en": "In Progress", "name_ar": "قيد التنفيذ", "category": "active"},
    {"code": "pending_customer", "name_en": "Pending Customer", "name_ar": "بانتظار العميل", "category": "paused"},
    {
      "code": "resolved",
      "name_en": "Resolved",
      "name_ar": "تم الحل",
      "category": "done",
      "actions": [
        {
          "function_path": "schedule_ticket_auto_close",
          "parameters": {"delay_seconds": 172800},
          "failure_policy": "continue"
        }
      ]
    },
    {"code": "closed", "name_en": "Closed", "name_ar": "مغلق", "category": "done", "is_terminal": true}
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
        {
          "function_path": "notify_assigned_user",
          "parameters": {"template": "ticket_assigned"},
          "order": 1
        },
        {
          "function_path": "start_ticket_sla",
          "parameters": {"policy": "standard_support"},
          "order": 2
        }
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
        {
          "function_path": "send_customer_information_request",
          "parameters": {"template": "customer_information_required"},
          "order": 1
        },
        {
          "function_path": "pause_ticket_sla",
          "order": 2
        }
      ]
    },
    {
      "code": "resume_after_customer_response",
      "name_en": "Resume After Customer Response",
      "from": "pending_customer",
      "to": "in_progress",
      "metadata": {"required_metadata_keys": ["customer_response"]},
      "actions": [
        {
          "function_path": "notify_assigned_user",
          "parameters": {"template": "customer_responded"},
          "order": 1
        },
        {
          "function_path": "resume_ticket_sla",
          "order": 2
        }
      ]
    },
    {
      "code": "resolve",
      "name_en": "Resolve",
      "from": "in_progress",
      "to": "resolved",
      "metadata": {
        "required_metadata_keys": ["resolution"],
        "allowed_actors": ["assigned_user"]
      },
      "actions": [
        {
          "function_path": "send_customer_survey",
          "parameters": {"survey": "ticket_satisfaction"},
          "order": 1
        },
        {
          "function_path": "stop_ticket_sla",
          "order": 2
        }
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

If the survey must be an approval form, configure `approvals` with
`step_approval_type: "submit"` and `required_form`. If it is a project-owned
form, submit its result in transition metadata and validate it using
`validation_function`.

## 5. L1, L2, and L3 Escalation Workflow

Business flow:

```text
New -> Level 1 Support -> Level 2 Support -> Level 3 Support -> Resolved -> Closed
```

The transition controls whether escalation is allowed. Project actions perform
team reassignment, notification, escalation logging, and SLA calculation.

### Escalation Validator

```python
# support/workflow_validators.py
def validate_escalation_level(
    obj,
    transition,
    metadata,
    user,
    attachment,
):
    requested_level = int(metadata["escalation_level"])
    return requested_level in {2, 3}
```

### Escalation Actions

```python
# support/workflow_actions.py
@registry.register(name="reassign_support_team", category="assignment")
def reassign_support_team(
    workflow_attachment,
    action_parameters,
    obj=None,
    metadata=None,
    **context,
):
    target_level = action_parameters.get("fixed_level")
    if target_level is None:
        target_level = int(metadata["escalation_level"])
    team = support_team_service.get_team(level=target_level, company=obj.company)
    assignment_service.assign(ticket=obj, team=team)
    return True


@registry.register(name="record_escalation", category="escalation")
def record_escalation(
    workflow_attachment,
    action_parameters,
    obj=None,
    user=None,
    metadata=None,
    **context,
):
    TicketEscalation.objects.create(
        ticket=obj,
        level=metadata["escalation_level"],
        reason=metadata["escalation_reason"],
        escalated_by=user,
    )
    return True
```

### Flow Payload

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
    {"code": "new", "name_en": "New", "name_ar": "جديد", "category": "open"},
    {"code": "level_1", "name_en": "Level 1 Support", "name_ar": "دعم المستوى الأول", "category": "active"},
    {"code": "level_2", "name_en": "Level 2 Support", "name_ar": "دعم المستوى الثاني", "category": "active"},
    {"code": "level_3", "name_en": "Level 3 Support", "name_ar": "دعم المستوى الثالث", "category": "active"},
    {"code": "resolved", "name_en": "Resolved", "name_ar": "تم الحل", "category": "done"},
    {"code": "closed", "name_en": "Closed", "name_ar": "مغلق", "category": "done", "is_terminal": true}
  ],
  "transitions": [
    {
      "code": "assign_level_1",
      "name_en": "Assign Level 1",
      "from": "new",
      "to": "level_1",
      "actions": [
        {
          "function_path": "reassign_support_team",
          "parameters": {"fixed_level": 1},
          "order": 1
        }
      ]
    },
    {
      "code": "escalate_level_2",
      "name_en": "Escalate to Level 2",
      "from": "level_1",
      "to": "level_2",
      "metadata": {
        "required_metadata_keys": ["escalation_level", "escalation_reason"],
        "validation_function": "support.workflow_validators.validate_escalation_level",
        "allowed_actors": [
          "assigned_user",
          {"type": "assigned_user_manager", "manager_levels": [1]}
        ]
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
      "name_en": "Escalate to Level 3",
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
    {
      "code": "resolve",
      "name_en": "Resolve",
      "from": "level_3",
      "to": "resolved",
      "metadata": {"required_metadata_keys": ["resolution"]}
    },
    {
      "code": "close",
      "name_en": "Close",
      "from": "resolved",
      "to": "closed"
    }
  ]
}
```

To support automatic escalation, attach a status-entry action to `level_1` or
`level_2` that schedules a project task. When the task executes, it must verify
the ticket is still in that level and call `perform_transition()` using the
normal escalation transition.

## 6. Ticket With Site Visit

Business flow:

```text
New -> Assigned -> Site Visit Scheduled -> On Site -> Pending Parts
                                  ^             |              |
                                  |             +-> Resolved   |
                                  +-----------------------------+
```

### Location Validator

```python
# field_service/workflow_validators.py
def validate_check_in(obj, transition, metadata, user, attachment):
    latitude = metadata.get("latitude")
    longitude = metadata.get("longitude")
    return latitude is not None and longitude is not None
```

### Visit Actions

```python
# field_service/workflow_actions.py
@registry.register(name="create_visit_task", category="task")
def create_visit_task(
    workflow_attachment,
    action_parameters,
    obj=None,
    metadata=None,
    **context,
):
    VisitTask.objects.create(
        ticket=obj,
        assigned_to_id=metadata["engineer_id"],
        scheduled_at=metadata["scheduled_at"],
    )
    return True


@registry.register(name="record_check_in", category="visit")
def record_check_in(
    workflow_attachment,
    action_parameters,
    obj=None,
    user=None,
    metadata=None,
    **context,
):
    VisitCheckIn.objects.create(
        ticket=obj,
        engineer=user,
        latitude=metadata["latitude"],
        longitude=metadata["longitude"],
    )
    return True
```

### Flow Payload

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
    {"code": "new", "name_en": "New", "name_ar": "جديد", "category": "open"},
    {"code": "assigned", "name_en": "Assigned", "name_ar": "مسند", "category": "active"},
    {
      "code": "site_visit_scheduled",
      "name_en": "Site Visit Scheduled",
      "name_ar": "تمت جدولة الزيارة",
      "category": "active",
      "actions": [
        {
          "function_path": "send_appointment_notification",
          "parameters": {"template": "site_visit_scheduled"}
        }
      ]
    },
    {"code": "on_site", "name_en": "On Site", "name_ar": "في الموقع", "category": "active"},
    {"code": "pending_parts", "name_en": "Pending Parts", "name_ar": "بانتظار القطع", "category": "paused"},
    {"code": "resolved", "name_en": "Resolved", "name_ar": "تم الحل", "category": "done", "is_terminal": true}
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
      "metadata": {
        "required_metadata_keys": ["engineer_id", "scheduled_at"],
        "allowed_actors": ["assigned_user", {"type": "team_lead"}]
      },
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

## 7. Creating and Attaching a Flow

Create a flow from project code:

```python
from django_workflow_engine.status_services import create_status_flow_design

design = create_status_flow_design(payload, user=request.user)
workflow_id = design["workflow"]["id"]
```

Attach the template workflow to a ticket:

```python
from django_workflow_engine.models import WorkFlow
from django_workflow_engine.services import attach_workflow_to_object

workflow = WorkFlow.objects.get(pk=workflow_id)
attachment = attach_workflow_to_object(
    ticket,
    workflow,
    user=request.user,
    auto_start=True,
)
```

The default attachment behavior clones the workflow so later template changes do
not change an active ticket.

## 8. Performing Transitions

From project code:

```python
from django_workflow_engine.services import perform_transition

perform_transition(
    ticket,
    "request_customer_information",
    user=request.user,
    metadata={"customer_request": "Please attach the server logs"},
)
```

Using the package API:

```http
POST /workflow/attachments/{attachment_id}/transition/
Content-Type: application/json
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

Retrieve transitions available to the current user:

```http
GET /workflow/attachments/{attachment_id}/transitions/
```

Retrieve the complete frontend diagram:

```http
GET /workflow/status/flow/support.ticket/
GET /workflow/status/transitions/support.ticket/
```

The diagram response includes node and transition actions.

## 9. Approvals

Add approvals directly to a transition:

```json
{
  "code": "resolve",
  "name_en": "Resolve",
  "from": "in_progress",
  "to": "resolved",
  "approvals": [
    {
      "approval_type": "role",
      "user_role": 7,
      "role_selection_strategy": "anyone"
    }
  ]
}
```

The object remains in its current status until approval completes. Actions can
run at:

- `on_transition_approval_requested`
- `on_transition_approved`
- `on_transition_rejected`
- `after_transition`

Approval rejection should include a reason or evidence. Configure
`reject_behavior` and `reject_to` when rejection should move the ticket.

Submit approval actions through:

```http
POST /workflow/attachments/{attachment_id}/approve_transition/
POST /workflow/attachments/{attachment_id}/reject_transition/
```

These endpoints use the existing approval workflow and do not bypass assigned
approvers, role rules, forms, or multi-step sequencing.

## 10. Testing Project Integrations

Test the package boundary without calling external infrastructure:

```python
from unittest.mock import patch

from django.test import TestCase

from django_workflow_engine.services import perform_transition


class TicketWorkflowTest(TestCase):
    @patch("support.workflow_actions.notification_service")
    @patch("support.workflow_actions.sla_service")
    def test_assignment_notifies_user_and_starts_sla(
        self,
        sla_service,
        notification_service,
    ):
        perform_transition(
            self.ticket,
            "assign",
            user=self.manager,
            metadata={"assignee_id": self.engineer.id},
        )

        notification_service.send.assert_called_once()
        sla_service.start.assert_called_once_with(
            ticket=self.ticket,
            policy="standard_support",
        )
```

At minimum, test:

- every transition from the correct source status
- transition rejection from an incorrect source status
- every configured actor permission
- required metadata and custom validators
- approval request, acceptance, and rejection
- custom action order and conditions
- each failure policy
- scheduled job idempotency
- direct status mutation protection
- workflow clone behavior

The package repository includes executable examples in
`tests/test_status_action_orchestration.py`.
