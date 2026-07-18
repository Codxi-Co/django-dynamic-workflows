# Developer Guide

This guide is the backend integration contract for `django-dynamic-workflows`.
It covers installation, workflow strategies, assignee resolution, service APIs,
extension points, and production checks. For HTTP payloads and UI behavior, see
[Frontend Integration](FRONTEND_INTEGRATION.md).

## Install and configure

```bash
pip install django-dynamic-workflows
```

```python
# settings.py
INSTALLED_APPS = [
    # ...
    "rest_framework",              # required only when using the packaged API
    "approval_workflow",
    "django_workflow_engine",
]

DJANGO_WORKFLOW_ENGINE = {
    "ENABLED_MODELS": ["purchases.PurchaseRequest"],
    "MODEL_WORKFLOW_MAPPINGS": {
        "purchases.PurchaseRequest": ["purchase-approval"],
    },
}
```

```python
# urls.py
path("api/workflow/", include("django_workflow_engine.urls")),
```

```bash
python manage.py migrate
python manage.py setup_workflows
```

## Choose a workflow strategy

| Strategy | Configuration location | Runtime position |
| --- | --- | --- |
| `WORKFLOW_PIPELINE_STAGE` (`1`) | `Stage.stage_info.approvals` | pipeline + stage |
| `WORKFLOW_PIPELINE` (`2`) | `Pipeline.pipeline_info.approvals` | pipeline |
| `WORKFLOW_ONLY` (`3`) | `WorkFlow.workflow_info.approvals` | workflow |
| `STATUS_GRAPH` (`4`) | status nodes and transitions | business status |

The first three strategies create sequential approval steps. `STATUS_GRAPH`
models state transitions and may attach approval steps to individual edges.

## Configure an approval step

`approval_type` answers **who receives the step**. `step_approval_type` answers
**what the recipient must do**. Do not use one as a substitute for the other.

```python
{
    "approvals": [
        {
            "approval_type": "assigned",
            "step_approval_type": "approve",
            "required_form": 12,
        }
    ]
}
```

### Approval types

| `approval_type` | Resolution |
| --- | --- |
| `self-approved` | user who starts/creates the workflow item |
| `user` | user ID in `approval_user` |
| `role` | `user_role` plus an optional role selection strategy |
| `assigned` | target object's configured assignee |
| `team_head` | existing team-head approval behavior |
| `department_head` | existing department-head approval behavior |

`assigned` is the only new approval type. It has no user ID in the workflow
definition: the engine resolves the user from the workflow target when it
creates the approval step.

### Step behavior types

| `step_approval_type` | Behavior |
| --- | --- |
| `approve` | normal approval; form is optional |
| `submit` | submission step; `required_form` is mandatory |
| `check_in_verify` | check-in and verification behavior from `approval_workflow` |
| `move` | routing/move step; a form is not allowed |

### Resolve from a target field

Every workflow-enabled model can have its own mapping. Configuration is merged
from `default` and the exact, case-insensitive model label.

```python
DJANGO_WORKFLOW_ENGINE = {
    "ASSIGNMENT_RESOLVERS": {
        "default": {"field": "assigned_to"},
        "purchases.PurchaseRequest": {
            "field": "assignee",
        },
    },
}
```

Dotted paths are supported. A related manager or queryset resolves to its first
row. Without explicit configuration, the engine checks `assigned_to`,
`assignee`, and `assigned_user` on the target object.

### Resolve through a separate assignment model

Use this when assignment history lives outside the workflow target.

```python
DJANGO_WORKFLOW_ENGINE = {
    "ASSIGNMENT_RESOLVERS": {
        "support.Ticket": {
            "model": "support.TicketAssignment",
            "query": {
                "ticket": "$object",
                "is_active": True,
            },
            "order_by": "-created_at",
            "user_field": "user",
        },
    },
}
```

Query values may be constants, `$object`, `$object.<dotted_path>`, or
`$approval.<key>`. The resolver filters the model, applies `order_by`, takes the
first row, then follows `user_field`.

### Resolve with a function

Configure a reusable function for a model:

```python
"support.Ticket": {"function": "support.workflow.resolve_assigned_user"}
```

Or configure a function on one approval:

```python
{
    "approval_type": "assigned",
    "assign_function": "support.workflow.resolve_escalation_owner",
}
```

```python
def resolve_escalation_owner(obj, approval):
    # Return an AUTH_USER_MODEL instance. Returning None stops flow creation.
    return obj.team.escalation_owner
```

The engine supplies `obj` and `approval` when the function declares them.
Dynamic assignment fails explicitly if no user is found; it does
not silently send sensitive approvals to the workflow creator.

## Start and inspect workflows

```python
from django_workflow_engine.services import (
    attach_workflow_to_object,
    get_available_transitions,
    get_workflow_attachment,
    perform_transition,
    start_workflow,
)

attachment = attach_workflow_to_object(
    purchase_request,
    workflow,
    user=request.user,
    auto_start=False,
)
start_workflow(purchase_request, request.user)

attachment = get_workflow_attachment(purchase_request)
transitions = get_available_transitions(purchase_request, user=request.user)
perform_transition(
    purchase_request,
    "submit",
    user=request.user,
    reason="Ready for review",
    metadata={"source": "api"},
)
```

Workflow attachment is a `GenericForeignKey`; the target model does not require
a foreign key to the engine. Keep the target object available when building
steps because the `assigned` approval type is resolved at runtime.

## Actions and events

Actions may be attached to a stage, pipeline, workflow, transition, or status
node. Database actions override settings actions. Typical events include
`after_approve`, `after_reject`, `after_delegate`, `after_move_stage`,
`before_transition`, `after_transition`, and `on_status_enter`.

See [Custom Actions](CUSTOM_ACTIONS.md) for callable signatures, failure policy,
email behavior, ordering, and inheritance.

## Validation and operational checks

- Call `full_clean()` or use the serializers when writing configuration in code.
- Do not configure both a role and concrete user for the same step.
- A `submit` step needs `required_form`; a `move` step rejects it.
- Assignment resolver functions must be deterministic and return one active user.
- Assignment-model queries should be indexed and should select a single active row.
- Run `python manage.py cleanup_workflows --dry-run` before enabling cleanup jobs.
- Keep custom action paths and assignment function paths covered by tests.

```bash
pytest -q
python manage.py check
```

## More backend references

- [Business Status Workflows](STATUS_WORKFLOWS.md)
- [Status Workflow API](STATUS_WORKFLOW_API.md)
- [Role Strategies](ROLE_STRATEGIES.md)
- [Custom Actions](CUSTOM_ACTIONS.md)
- [Migration Guide](MIGRATION_GUIDE.md)
- [Email Testing](TESTING_EMAILS.md)
- [Changelog](CHANGELOG.md)
