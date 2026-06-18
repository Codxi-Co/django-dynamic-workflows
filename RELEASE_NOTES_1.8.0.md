# Release Notes - v1.8.0

**Release Date:** June 18, 2026  
**Status:** Ready for Release  
**Minimum Python:** 3.10+  
**Minimum Django:** 5.2+  
**Minimum django-approval-workflow:** 0.9.0+

---

## Business Status Workflows

v1.8.0 adds first-class business status workflows through `WorkflowStrategy.STATUS_GRAPH`.

This is designed for systems where the object's business state is central to the workflow:

- Support Tickets: New -> In Progress -> On Hold -> Resolved -> Closed
- CRM Opportunities: New -> Qualified -> Proposal -> Negotiation -> Won/Lost
- Tasks: To Do -> In Progress -> Review -> Done

The status system can be used with or without workflow transitions.

---

## What's New

### 1. Status Graph Strategy

New strategy:

```python
WorkflowStrategy.STATUS_GRAPH
```

Status graph workflows use status nodes and transitions instead of pipelines and stages.

### 2. Reusable Status Model

Statuses now support:

- Company scoping
- Optional model `ContentType` scoping
- Arabic and English names
- Business category
- UI/business metadata
- Audit fields

### 3. Model-Specific Status Catalogs

Each model can have its own configured statuses.

Examples:

- `support.Ticket`: New, In Progress, On Hold, Resolved, Closed
- `crm.Opportunity`: New, Qualified, Proposal, Won, Lost
- `tasks.Task`: To Do, In Progress, Review, Done

### 4. Full Status Flow API

Create a complete status workflow design in one API call:

```http
POST /status/flow/
```

Read a complete status workflow design for a model:

```http
GET /status/flow/<app_label.model>/
```

### 5. Frontend-Friendly APIs

```http
GET /status/models/
GET /status/options/<app_label.model>/
GET /status/transitions/<app_label.model>/
```

These endpoints support model dropdowns, status dropdowns, and diagram rendering.

### 6. Helper Services

Projects can avoid the packaged APIs and use helper services directly:

```python
from django_workflow_engine.status_services import (
    create_status_for_model,
    create_status_flow_design,
    get_status_flow_design,
    resolve_status_content_type,
)
```

### 7. Transition Approvals and Forms

Status transitions now use the same approval values as the existing approval system:

```json
{
  "code": "mark_won",
  "from": "qualified",
  "to": "won",
  "approvals": [
    {
      "approval_type": "role",
      "user_role": 5,
      "role_selection_strategy": "anyone",
      "step_approval_type": "submit",
      "required_form": 12
    }
  ]
}
```

Approval requirement is inferred:

- no `approvals`, `null`, or `[]` means no approval
- non-empty `approvals` means approval required

When a transition has approvals, the engine creates or extends the existing `ApprovalFlow` and creates `ApprovalInstance` rows. Transition metadata is stored in `ApprovalInstance.extra_fields`.

### 8. Transition Rejection Behavior

Transitions can define what happens when a pending transition approval is rejected:

- stay in current status
- move to a specific status
- request changes
- cancel workflow

Rejections require a reason or evidence.

### 9. Status API Customization

Projects can plug in their own viewset mixins and serializer bases:

```python
DJANGO_WORKFLOW_ENGINE = {
    "STATUS_API_VIEWSET_MIXINS": [
        "my_project.api.mixins.GenericCompanyViewSetMixin",
    ],
    "STATUS_BASE_SERIALIZER": "my_project.api.serializers.BaseSerializer",
    "STATUS_NAMED_SERIALIZER": "my_project.api.serializers.SharedNamedWithTimeStampedSerializer",
}
```

This is useful for projects with custom company scoping, audit handling, or shared serializer behavior.

### 10. Transition Actor Rules

Transitions can restrict who is allowed to trigger a move without requiring an approval cycle. Configure `metadata.allowed_actors` with creator/owner, assigned user, managers, team or department resolvers, specific users, specific roles, assignment history, or a project custom function.

Actor field and resolver settings can be configured per model with a `default`
fallback. Resolver functions receive the main target object as `obj`.

### 11. Status Enter Actions

Status nodes can run custom actions when an object enters that status:

```python
WorkflowAction.objects.create(
    status_node=in_review_node,
    action_type=ActionType.ON_STATUS_ENTER,
    function_path="support.workflow_actions.schedule_review_sla_reminder",
    parameters={"sla_minutes": 120, "notify_user": "qa.lead@example.com"},
)
```

This supports SLA timers, reminders, escalation setup, notifications, and other status-local behavior. Full status-flow creation can also include these actions inline under each status `actions` list.

Transition actions can also be declared inline in the full status-flow design
and are returned by flow and diagram APIs. Actions support optional developer
conditions and `continue`, `stop`, or `raise` failure policies. Advanced
transition input can be checked by a developer `validation_function`.

The package intentionally does not implement a scheduler, notification
provider, SLA store, task model, or escalation store. Custom actions integrate
with the consuming project's selected services.

Projects with multiple companies can define complete designs directly in
`DEFAULT_STATUS_WORKFLOWS` and call
`auto_generate_default_flow(company_id, flow=None)` during company provisioning.
Dynamic factories remain supported. Lazy object-level provisioning and attachment are
available through `get_or_create_default_status_workflow_for_object()` and
`attach_default_status_workflow()`.

---

## Documentation

New guide:

- `STATUS_WORKFLOWS_GUIDE.md`
- `STATUS_WORKFLOW_IMPLEMENTATION_CASES.md`
- `STATUS_WORKFLOW_API_GUIDE.md`

Updated:

- `README.md`
- `CHANGELOG.md`

---

## Migrations

Run:

```bash
python manage.py migrate django_workflow_engine
```

New migration:

- `0008_status_workflows.py`

---

## Backward Compatibility

v1.8.0 is designed to be backward compatible:

- Existing workflow strategies remain supported.
- Existing workflow APIs remain available.
- Existing pipeline/stage workflows do not need to migrate to status graphs.
- Low-level transition APIs still accept legacy `approval_config` and `requires_approval` as write-only compatibility inputs.

---

## Validation

Recommended pre-release checks:

```bash
python -m django check --settings=sandbox.settings
python -m django makemigrations django_workflow_engine --check --dry-run --settings=sandbox.settings
pytest -q
python -m build
twine check dist/*
```

---

## Files Changed

Key additions:

- `django_workflow_engine/status_services.py`
- `django_workflow_engine/status_permissions.py`
- `django_workflow_engine/status_urls.py`
- `STATUS_WORKFLOWS_GUIDE.md`
- `tests/test_status_api.py`
- `tests/test_status_actions.py`
- `tests/test_status_workflows.py`
- `tests/test_ticketing_status_graph_business_case.py`
- `tests/test_transition_actor_permissions.py`

Key updated modules:

- `django_workflow_engine/models.py`
- `django_workflow_engine/services.py`
- `django_workflow_engine/serializers.py`
- `django_workflow_engine/views.py`
- `django_workflow_engine/settings.py`
- `django_workflow_engine/choices.py`
- `django_workflow_engine/urls.py`
- `django_workflow_engine/utils.py`
- `django_workflow_engine/admin.py`

---

**Version:** 1.8.0  
**Release Date:** June 18, 2026  
**Package:** django-dynamic-workflows  
**License:** MIT
