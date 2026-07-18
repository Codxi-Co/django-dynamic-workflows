# Business Status Workflows

This guide explains the business-status system: reusable statuses, model-specific status catalogs, status graph workflows, transition approvals, helper services, and REST APIs.

Use this system when the business state of an object matters as much as the approval workflow itself. Examples:

- Tickets: New -> In Progress -> On Hold -> Resolved -> Closed
- Opportunities: New -> Qualified -> Proposal -> Negotiation -> Won/Lost
- Tasks: To Do -> In Progress -> Review -> Done

The status system can be used with or without workflow transitions.

## Concepts

### Status

`Status` is a reusable business state. It has:

- `name_en`, `name_ar`
- `category`: `open`, `active`, `paused`, `done`, `cancelled`, `other`
- `content_type`: optional model scope, such as `crm.opportunity`
- `company`
- `metadata`: JSON for future UI/business flags
- audit fields: `created_by`, `created_at`, `modified_by`, `modified_at`

The API does not require clients to send a machine key. `key` is generated from `name_en`.

### Model Status Configuration

`ModelStatusConfiguration` defines which statuses a Django model can use.

Example: Tickets and Opportunities can both have a status named `Closed`, but each model has its own catalog and ordering.

### Status Graph Workflow

Status graph workflows use `WorkflowStrategy.STATUS_GRAPH`.

Instead of Pipeline/Stage movement, the workflow is a graph:

```text
New -> In Progress -> Resolved -> Closed
                 |
                 v
              On Hold -> In Progress
```

Each workflow status is a `WorkflowStatusNode`. Movement is controlled by `StatusTransition`.

### Transition

A transition is one named movement from one status node to one target status node.

Do not model one transition with many possible targets. Use multiple outgoing transitions from the same status:

```json
[
  { "code": "mark_won", "from": "qualified", "to": "won" },
  { "code": "mark_lost", "from": "qualified", "to": "lost" },
  { "code": "put_on_hold", "from": "qualified", "to": "on_hold" }
]
```

This keeps each action deterministic and easy to authorize, audit, and render.

## Approval Rules

Transition approval is driven by `approvals`.

No approval required:

```json
{
  "code": "start_progress",
  "from": "new",
  "to": "in_progress",
  "approvals": []
}
```

Approval required:

```json
{
  "code": "mark_won",
  "from": "qualified",
  "to": "won",
  "approvals": [
    {
      "approval_type": "role",
      "user_role": 5,
      "role_selection_strategy": "anyone"
    }
  ]
}
```

`requires_approval` is inferred internally:

- missing `approvals`, `null`, or `[]` means no approval
- non-empty `approvals` means approval required

The old `approval_config` and `requires_approval` keys are accepted as write-only compatibility inputs on low-level transition APIs, but new clients should use `approvals`.

## Form-Based Approval

Status transition approvals use the same approval values as the existing approval workflow system.

Example: the approver must submit a form before the status can move:

```json
{
  "code": "put_on_hold",
  "name_en": "Put On Hold",
  "from": "in_progress",
  "to": "on_hold",
  "approvals": [
    {
      "approval_type": "role",
      "user_role": 7,
      "role_selection_strategy": "anyone",
      "step_approval_type": "submit",
      "required_form": 12
    }
  ],
  "metadata": {
    "required_metadata_keys": ["customer_requirement"]
  }
}
```

Supported approval fields include:

- `approval_type`: `self-approved`, `user`, `role`
- `approval_user`: user id for user-based approvals
- `user_role`: role id for role-based approvals
- `role_selection_strategy`: `anyone`, `consensus`, `round_robin`, plus enhanced strategies where configured
- `step_approval_type`: `approve`, `submit`, `check_in_verify`, `move`
- `required_form`: dynamic form id

When a transition with approvals is triggered, the engine creates or extends the existing `ApprovalFlow` and creates `ApprovalInstance` rows. The transition data is stored in `ApprovalInstance.extra_fields`:

- `workflow_id`
- `status_transition_id`
- `status_transition_key`
- `from_status_id`
- `to_status_id`

The existing status transition remains pending until it is approved or rejected.

## Rejection Behavior

Every transition can define what happens when its approval is rejected.

Stay in the current status:

```json
{
  "code": "close",
  "from": "resolved",
  "to": "closed",
  "approvals": [{ "approval_type": "self-approved" }],
  "reject_behavior": "stay_current_status"
}
```

Move to a specific status:

```json
{
  "code": "close",
  "from": "resolved",
  "to": "closed",
  "approvals": [{ "approval_type": "self-approved" }],
  "reject_behavior": "move_to_specific_status",
  "reject_to": "in_progress"
}
```

Rejection requires a reason or evidence.

## Transition Actions

Status transitions can trigger custom actions using the same action system as the rest of the workflow engine.

Useful action types:

- `BEFORE_TRANSITION`
- `AFTER_TRANSITION`
- `ON_TRANSITION_APPROVAL_REQUESTED`
- `ON_TRANSITION_APPROVED`
- `ON_TRANSITION_REJECTED`

Example:

```python
from django_workflow_engine.choices import ActionType
from django_workflow_engine.models import WorkflowAction

WorkflowAction.objects.create(
    transition=close_transition,
    action_type=ActionType.AFTER_TRANSITION,
    function_path="support.workflow_actions.notify_ticket_closed",
    parameters={"template": "ticket_closed"},
    order=1,
    is_active=True,
)
```

The full-design API accepts the same actions inline. If `action_type` is omitted
for a transition action, it defaults to `after_transition`:

```json
{
  "code": "assign",
  "name_en": "Assign",
  "from": "new",
  "to": "assigned",
  "actions": [
    {
      "function_path": "support.workflow_actions.notify_assigned_user",
      "parameters": {"template": "ticket_assigned"},
      "order": 1
    },
    {
      "action_type": "after_transition",
      "function_path": "support.workflow_actions.start_sla",
      "parameters": {"policy": "standard_support"},
      "order": 2
    }
  ]
}
```

`GET /status/flow/<model>/` and `GET /status/transitions/<model>/` return the
configured actions under each node and transition so diagram clients can display
the complete behavior.

### Conditions and Failure Policies

Conditions remain developer-owned functions. The package evaluates the function
before invoking the action:

```json
{
  "function_path": "support.workflow_actions.notify_priority_team",
  "condition_function": "support.workflow_conditions.is_high_priority",
  "failure_policy": "continue"
}
```

The condition receives the workflow action context plus `action_parameters`.
It must return a truthy value to run the action.

Supported failure policies:

- `continue`: log the exception and execute the next action
- `stop`: log the exception and stop the remaining actions for that event
- `raise`: raise the exception and roll back the atomic transition

Scheduling, retries, notification delivery, SLA records, task models, and
escalation persistence belong to the consuming project. A custom action can call
Celery, Django-Q, an API, or any project service without the package selecting
that infrastructure.

## Transition Actor Rules

Approvals answer "who must approve this movement?". Actor rules answer "who is allowed to trigger this movement?".

If a transition has no actor rules, any authenticated caller that satisfies the optional `permission_codename` can trigger it. To restrict who can move an object, put `allowed_actors` in the transition metadata:

```json
{
  "code": "start_progress",
  "from": "to_do",
  "to": "in_progress",
  "metadata": {
    "allowed_actors": [
      "creator",
      "assigned_user",
      { "type": "assigned_user_manager", "manager_levels": [2] },
      { "type": "specific_role", "role": 5, "role_selection_strategy": "anyone" }
    ]
  }
}
```

Supported actor types:

- `creator` / `owner`
- `assigned_user`
- `team_member`
- `team_lead`
- `department_member`
- `specific_role`
- `specific_user`
- `assignment_history_user`
- `creator_manager` / `owner_manager`
- `assigned_user_manager`
- `custom_function`

Project-specific object relationships are configured per model through
`DJANGO_WORKFLOW_ENGINE["TRANSITION_ACTORS"]`. A `default` section is merged
with the exact model section:

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
            "TEAM_LEAD_FUNCTION": "support.workflow_actors.get_team_lead",
            "DEPARTMENT_USERS_FUNCTION": "support.workflow_actors.get_department_users",
            "ASSIGNMENT_HISTORY_USERS_FUNCTION": "support.workflow_actors.get_assignment_history_users",
        },
        "tasks.Task": {
            "OWNER_FIELD": "requested_by",
            "ASSIGNED_USER_FIELD": "assignee",
            "TEAM_USERS_FIELD": "project.members",
            "TEAM_LEAD_FIELD": "project.lead",
        },
        "crm.Opportunity": {
            "OWNER_FIELD": "created_by",
            "ASSIGNED_USER_FIELD": "sales_owner",
            "DEPARTMENT_FIELD": "sales_department",
        },
    }
}
```

Every configured resolver receives the main business object as `obj`. When a
Ticket transition is evaluated, `obj` is the Ticket instance:

```python
# support/workflow_actors.py
def get_assigned_user(obj, actor_type=None):
    # obj is the Ticket currently being moved.
    return obj.assigned_to


def get_team_users(obj, actor_type=None):
    return obj.support_team.users.all()
```

Resolvers may accept only `obj` for compatibility. They may also accept
`actor_type`, which identifies the rule being resolved, such as
`assigned_user`, `team_member`, or `team_lead`.

The old flat `TRANSITION_ACTORS` dictionary remains supported and applies to all
models, but per-model configuration is recommended when models use different
fields.

Manager rules can target direct or higher-level managers:

```json
{ "type": "assigned_user_manager", "manager_levels": [1, 2] }
```

If a custom function is used, it may return a boolean or an iterable/queryset of allowed users:

```json
{
  "type": "custom_function",
  "function": "myapp.workflow_actors.can_move_from_review"
}
```

## Status Enter Actions

Status nodes can also have actions that run after the object enters that status. Use this for status-local behavior such as SLA timers, delayed reminders, queue notifications, or escalation setup.

Example: when a task enters `In Review`, create an SLA reminder that will notify QA if the item stays there too long:

```python
from django_workflow_engine.choices import ActionType
from django_workflow_engine.models import WorkflowAction

WorkflowAction.objects.create(
    status_node=in_review_node,
    action_type=ActionType.ON_STATUS_ENTER,
    function_path="support.workflow_actions.schedule_review_sla_reminder",
    parameters={
        "sla_minutes": 120,
        "notify_user": "qa.lead@example.com",
    },
    order=1,
    is_active=True,
)
```

The action handler receives the same execution style as other workflow actions. Legacy function paths receive keyword arguments:

```python
def schedule_review_sla_reminder(
    attachment,
    obj,
    workflow,
    status_node,
    status,
    transition,
    previous_status,
    user,
    sla_minutes,
    notify_user,
    **kwargs,
):
    # Schedule a job, create an SLA row, or call your notification service.
    return True
```

The full status-flow helper can create status actions inline. `action_type` defaults to `on_status_enter` for status actions:

```json
{
  "code": "in_review",
  "name_en": "In Review",
  "category": "active",
  "actions": [
    {
      "function_path": "support.workflow_actions.schedule_review_sla_reminder",
      "parameters": {
        "sla_minutes": 120,
        "notify_user": "qa.lead@example.com"
      }
    }
  ]
}
```

## Full Design Helper

You do not have to use the packaged APIs. You can create a full status workflow from your own code:

For company-specific default workflow provisioning, settings factories, lazy
attachment, and recommended company-creation trigger points, see
See the provisioning examples in the **[Status Workflow API guide](STATUS_WORKFLOW_API.md)**.

```python
from django_workflow_engine.status_services import create_status_flow_design

result = create_status_flow_design(
    {
        "model": "crm.opportunity",
        "company": request.user.company_id,
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
                "category": "open",
                "metadata": {"probability": 10, "show_in_pipeline": True},
            },
            {
                "code": "qualified",
                "name_en": "Qualified",
                "name_ar": "مؤهلة",
                "category": "active",
                "metadata": {"probability": 40, "show_in_pipeline": True},
            },
            {
                "code": "won",
                "name_en": "Won",
                "name_ar": "رابحة",
                "category": "done",
                "is_terminal": True,
            },
            {
                "code": "lost",
                "name_en": "Lost",
                "name_ar": "خاسرة",
                "category": "cancelled",
                "is_terminal": True,
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
                "approvals": [
                    {
                        "approval_type": "role",
                        "user_role": 5,
                        "role_selection_strategy": "anyone",
                    }
                ],
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
    user=request.user,
)
```

The helper creates:

- `Status`
- `ModelStatusConfiguration`
- `ModelStatus`
- `WorkFlow` with `WorkflowStrategy.STATUS_GRAPH`
- `WorkflowConfiguration`
- `WorkflowStatusNode`
- `StatusTransition`

It also sets audit fields where available.

## Read Full Design Helper

Use this to render a frontend editor, diagram, or dropdowns without using the REST API:

```python
from django_workflow_engine.status_services import get_status_flow_design

flow = get_status_flow_design("crm.opportunity")
```

The response contains:

```json
{
  "model": "crm.opportunity",
  "content_type": 22,
  "configuration": {},
  "workflow": {},
  "statuses": [],
  "nodes": [],
  "transitions": [],
  "diagram": {
    "nodes": [],
    "edges": []
  }
}
```

## Other Helper Functions

Create a single status for a model:

```python
from django_workflow_engine.status_services import create_status_for_model

status = create_status_for_model(
    model="support.ticket",
    name_en="In Progress",
    name_ar="قيد التنفيذ",
    category="active",
    company=request.user.company,
    user=request.user,
    metadata={"sla_paused": False},
)
```

Resolve a model label to `ContentType`:

```python
from django_workflow_engine.status_services import resolve_status_content_type

content_type = resolve_status_content_type("support.ticket")
```

## REST API

### Single Status CRUD

Canonical endpoint:

```http
POST /status/
GET /status/
GET /status/<id>/
PATCH /status/<id>/
DELETE /status/<id>/
```

Create status using model label:

```json
POST /status/
{
  "company": 1,
  "model": "support.ticket",
  "name_en": "In Progress",
  "name_ar": "قيد التنفيذ",
  "category": "active",
  "metadata": {
    "sla_paused": false
  }
}
```

### Full Flow CRUD

Create a complete flow:

```http
POST /status/flow/
```

Read a complete flow:

```http
GET /status/flow/support.ticket/
GET /status/flow/support.ticket/?workflow_id=123
```

### Frontend Dropdowns

Return model statuses and workflow statuses:

```http
GET /status/options/support.ticket/
GET /status/options/support.ticket/?workflow_id=123
```

### Diagram Data

Return frontend-ready nodes and edges:

```http
GET /status/transitions/support.ticket/
GET /status/transitions/support.ticket/?workflow_id=123
```

### Enabled Models

Return models that have status configuration enabled:

```http
GET /status/models/
```

### Low-Level Endpoints

These are useful for admin builders or advanced editors:

```http
GET/POST /status/model-configurations/
GET/POST /status/model-statuses/
GET/POST /status/workflow-statuses/
GET/POST /status/transitions/
GET/POST /status/attachments/
GET      /status/history/
```

## Runtime API

Attach a status-graph workflow to an object:

```python
from django_workflow_engine.services import attach_workflow_to_object

attachment = attach_workflow_to_object(
    ticket,
    workflow,
    user=request.user,
    auto_start=True,
)
```

Perform a transition:

```python
from django_workflow_engine.services import perform_transition

perform_transition(
    ticket,
    "start_progress",
    user=request.user,
    metadata={"assignee_id": request.user.id},
)
```

Transitions with `approvals` must be processed through the approval workflow.
The compatibility aliases below use the same approval serializer and therefore
enforce assigned approvers, roles, forms, and approval ordering:

```http
POST /attachments/{attachment_id}/approve_transition/
Content-Type: application/json

{"reason": "Approved by support lead", "form_data": {}}
```

```http
POST /attachments/{attachment_id}/reject_transition/
Content-Type: application/json

{
  "reason": "Customer rejected the resolution",
  "evidence": "customer-email-thread"
}
```

The generic `POST /attachments/{attachment_id}/approve/` endpoint is also
supported. Final approval and rejection callbacks complete or route the pending
status transition automatically.

## API Customization

Projects often have their own base viewsets and serializers. You can plug them into the status APIs:

```python
DJANGO_WORKFLOW_ENGINE = {
    "STATUS_API_VIEWSET_MIXINS": [
        "my_project.api.mixins.GenericCompanyViewSetMixin",
    ],
    "STATUS_BASE_SERIALIZER": "my_project.api.serializers.BaseSerializer",
    "STATUS_NAMED_SERIALIZER": "my_project.api.serializers.SharedNamedWithTimeStampedSerializer",
}
```

Use this when your project handles:

- company scoping differently
- request user assignment differently
- shared serializer fields
- common validation rules
- common response formatting

The packaged status viewsets still provide default audit handling:

- `created_by` is set on create when available
- `modified_by` is set on create/update when available

## Design Recommendations

1. Use `Status` for business state, not approval state.
2. Use one transition per action and one target per transition.
3. Use multiple outgoing transitions when a status has multiple possible directions.
4. Use `metadata.required_metadata_keys` for business input requirements such as `assignee_id`, `customer_requirement`, or `lost_reason`.
   For advanced validation, add `metadata.validation_function`; the developer
   function receives `obj`, `transition`, `metadata`, `user`, and `attachment`.
5. Use `approvals` for approval requirements. Do not send `requires_approval`.
6. Use `reject_behavior` and `reject_to` for approval rejection routing.
7. Keep terminal statuses explicit with `is_terminal` or `terminal_statuses`.
8. Prefer helper services from custom APIs so your project owns authentication/company behavior while the package owns workflow creation correctness.

## Ticket Example

```json
{
  "model": "support.ticket",
  "company": 1,
  "status_field": "status",
  "default_status": "pending_pm_review",
  "terminal_statuses": ["closed", "duplicated", "rejected"],
  "workflow": {
    "name_en": "Ticket Workflow",
    "name_ar": "سير عمل التذاكر"
  },
  "statuses": [
    {"code": "pending_pm_review", "name_en": "Pending PM Review", "name_ar": "بانتظار مراجعة مدير المنتج", "category": "open"},
    {"code": "new", "name_en": "New", "name_ar": "جديد", "category": "open"},
    {"code": "in_progress", "name_en": "In Progress", "name_ar": "قيد التنفيذ", "category": "active"},
    {"code": "on_hold", "name_en": "On Hold", "name_ar": "معلق", "category": "paused"},
    {"code": "resolved", "name_en": "Resolved", "name_ar": "تم الحل", "category": "done"},
    {"code": "closed", "name_en": "Closed", "name_ar": "مغلق", "category": "done", "is_terminal": true},
    {"code": "duplicated", "name_en": "Duplicated", "name_ar": "مكرر", "category": "cancelled", "is_terminal": true},
    {"code": "rejected", "name_en": "Rejected", "name_ar": "مرفوض", "category": "cancelled", "is_terminal": true}
  ],
  "transitions": [
    {
      "code": "pm_confirm_valid",
      "name_en": "PM Confirm Valid",
      "from": "pending_pm_review",
      "to": "new",
      "approvals": [{"approval_type": "role", "user_role": 5, "role_selection_strategy": "anyone"}],
      "reject_behavior": "move_to_specific_status",
      "reject_to": "rejected",
      "metadata": {"allowed_reject_status_keys": ["duplicated", "rejected"]}
    },
    {
      "code": "start_progress",
      "name_en": "Start Progress",
      "from": "new",
      "to": "in_progress",
      "metadata": {"required_metadata_keys": ["assignee_id"]}
    },
    {
      "code": "put_on_hold",
      "name_en": "Put On Hold",
      "from": "in_progress",
      "to": "on_hold",
      "approvals": [{"approval_type": "role", "user_role": 6, "role_selection_strategy": "anyone"}],
      "metadata": {"required_metadata_keys": ["customer_requirement"]}
    },
    {
      "code": "resume_from_hold",
      "name_en": "Resume From Hold",
      "from": "on_hold",
      "to": "in_progress",
      "approvals": [{"approval_type": "role", "user_role": 6, "role_selection_strategy": "anyone"}],
      "metadata": {"required_metadata_keys": ["customer_response"]}
    },
    {
      "code": "resolve",
      "name_en": "Resolve",
      "from": "in_progress",
      "to": "resolved",
      "approvals": [{"approval_type": "role", "user_role": 7, "role_selection_strategy": "anyone"}],
      "reject_behavior": "move_to_specific_status",
      "reject_to": "in_progress"
    },
    {
      "code": "reopen",
      "name_en": "Reopen",
      "from": "resolved",
      "to": "in_progress"
    },
    {
      "code": "close",
      "name_en": "Close",
      "from": "resolved",
      "to": "closed",
      "approvals": [{"approval_type": "role", "user_role": 8, "role_selection_strategy": "anyone"}],
      "reject_behavior": "move_to_specific_status",
      "reject_to": "in_progress"
    }
  ]
}
```
