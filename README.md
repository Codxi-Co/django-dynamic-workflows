# Django Dynamic Workflows

A powerful, configurable Django package for implementing dynamic multi-step workflow processes with database-stored actions and approval flows.

## Features

- **Generic Workflow Attachment**: Attach workflows to any Django model without hardcoded relationships
- **Database-Stored Actions**: Configure actions dynamically in the database with inheritance system
- **Action Inheritance**: Stage → Pipeline → Workflow → Default action hierarchy
- **Approval Flow Integration**: Built on top of django-approval-workflow package
- **Configurable Triggers**: Actions triggered on workflow events (approve, reject, delegate, etc.)
- **Default Email Actions**: Smart email notifications to creators and approvers
- **Dynamic Function Execution**: Execute Python functions by database-stored paths
- **Admin Interface**: Rich Django admin for managing workflows, stages, and actions

## Installation

```bash
pip install django-dynamic-workflows
```

## Quick Start

1. Add to INSTALLED_APPS:

```python
INSTALLED_APPS = [
    ...
    'approval_workflow',  # Required dependency
    'django_workflow_engine',
    ...
]
```

2. Run migrations:

```bash
python manage.py migrate
```

3. Register a model for workflow support:

```python
from django_workflow_engine.services import register_model_for_workflow
from myapp.models import Ticket

register_model_for_workflow(
    Ticket,
    auto_start=True,
    status_field='workflow_status',
    stage_field='current_stage'
)
```

4. Attach and start a workflow:

```python
from django_workflow_engine.services import attach_workflow_to_object

attachment = attach_workflow_to_object(
    obj=my_ticket,
    workflow=my_workflow,
    user=request.user,
    auto_start=True
)
```

## Core Concepts

### WorkFlow, Pipeline, Stage Hierarchy
- **WorkFlow**: Top-level workflow definition
- **Pipeline**: Departments or phases within a workflow
- **Stage**: Individual approval steps within a pipeline

### Configurable Actions
- Database-stored function paths executed on workflow events
- Inheritance system: Stage overrides Pipeline overrides Workflow overrides Default
- Support for parameters and custom context

### Action Types
- `AFTER_APPROVE`: After approval step completion
- `AFTER_REJECT`: After workflow rejection
- `AFTER_RESUBMISSION`: After resubmission request
- `AFTER_DELEGATE`: After delegation to another user
- `AFTER_MOVE_STAGE`: After moving between stages
- `AFTER_MOVE_PIPELINE`: After moving between pipelines
- `ON_WORKFLOW_START`: When workflow begins
- `ON_WORKFLOW_COMPLETE`: When workflow completes

## Usage Examples

See [USAGE_EXAMPLES.md](USAGE_EXAMPLES.md) for comprehensive examples including:
- Model registration and workflow attachment
- Approval actions (approve, reject, delegate, resubmission)
- Custom workflow handlers
- API integration
- Frontend integration

## Dependencies

- Django >= 4.0
- django-approval-workflow >= 0.8.0

## License

MIT License

## Contributing

Please read our contributing guidelines and submit pull requests to our GitHub repository.

## Support

For questions and support, please open an issue on our GitHub repository.