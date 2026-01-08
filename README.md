# Django Dynamic Workflows

A powerful, configurable Django package for implementing dynamic multi-step workflow processes with database-stored actions and approval flows.

## Features

- **Flexible Workflow Strategies** ⭐ NEW in v1.5.0: Choose from 3 hierarchy levels (Stage/Pipeline/Workflow-only) based on complexity
- **Generic Workflow Attachment**: Attach workflows to any Django model without hardcoded relationships
- **Database-Stored Actions**: Configure actions dynamically in the database with inheritance system
- **2-Tier Action Priority System**: Database → Settings action resolution (no conflicts)
- **Settings-Based Actions**: Configure project-wide actions via `WORKFLOW_ACTIONS_CONFIG`
- **Action Inheritance**: Stage → Pipeline → Workflow action hierarchy
- **Approval Flow Integration**: Built on top of django-approval-workflow package
- **Approval Type Support**: Control approval behavior with APPROVE, SUBMIT, CHECK_IN_VERIFY, and MOVE types
- **Complete Approval Actions**: Full support for approve, reject, delegate, and resubmission workflows
- **Resubmission & Delegation Logic**: Proper stage transitions and user assignments with workflow event triggers
- **Configurable Triggers**: Actions triggered on workflow events (approve, reject, delegate, etc.)
- **Opt-in Email Actions**: Configure email notifications using database actions or settings
- **Dynamic Function Execution**: Execute Python functions by database-stored paths
- **Workflow Cleanup & Management**: Built-in cleanup utilities to manage completed workflows and reduce database size
- **Admin Interface**: Rich Django admin for managing workflows, stages, and actions

## Installation

```bash
pip install django-dynamic-workflows
```

## Configuration

The Django Workflow Engine can be configured through your Django settings:

```python
# settings.py
DJANGO_WORKFLOW_ENGINE = {
    # Department Model Mapping (NEW)
    # Map the department GenericForeignKey to any model in your project
    'DEPARTMENT_MODEL': 'myapp.Department',  # Optional: specify your department model

    # Model Configuration
    'ENABLED_MODELS': [
        'myapp.PurchaseRequest',
        'crm.Opportunity',
        'support.Ticket',
    ],

    # Default field name for workflow status
    'DEFAULT_STATUS_FIELD': 'workflow_status',

    # Workflow Mappings
    'MODEL_WORKFLOW_MAPPINGS': {
        'myapp.PurchaseRequest': ['purchase_approval', 'emergency_approval'],
        'crm.Opportunity': ['sales_process'],
    },

    # Auto-start Configuration
    'AUTO_START_WORKFLOWS': {
        'myapp.PurchaseRequest': {
            'workflow_slug': 'purchase_approval',
            'conditions': {'amount__gte': 1000}  # Only for amounts >= 1000
        }
    },

    # Permissions
    'PERMISSIONS': {
        'REQUIRE_PERMISSION_TO_START': True,
        'REQUIRE_PERMISSION_TO_APPROVE': True,
    }
}
```
### Company Model Architecture

**Important**: The `company` field in workflow models uses Django's `AUTH_USER_MODEL` (User model) for maximum flexibility:

```python
# Workflow models use User as company for multi-tenant support:
class WorkFlow(models.Model):
    company = models.ForeignKey(
        settings.AUTH_USER_MODEL,  # Uses your User model
        on_delete=models.SET_NULL,
        related_name="workflow_company"
    )
```

#### Why User Model for Company?

This design supports various multi-tenant architectures:

```python
# Single Company per User
user.username = "acme_corp"
user.email = "admin@acmecorp.com"

# Multi-tenant SaaS where users represent companies
company_user = User.objects.create(
    username="company_123",
    email="admin@company123.com"
)

# Enterprise where User has company profile
user.profile.company_name = "Enterprise Corp"
```

#### Usage Examples

```python
# Create workflows for specific companies (users)
workflow = WorkFlow.objects.create(
    company=company_user,  # User representing the company
    name_en="Company Workflow"
)

# Filter workflows by company
company_workflows = WorkFlow.objects.filter(company=company_user)

# Multi-tenant isolation
user_workflows = WorkFlow.objects.filter(company=request.user)
```

This approach provides flexibility for:
- 🏢 **Multi-tenant SaaS**: Each tenant has a user representing their company
- 🏛️ **Enterprise**: Companies can be mapped through user profiles or groups
- 🔒 **Security**: Natural permission boundaries through Django's user system
- 📊 **Scalability**: Leverage Django's user management and authentication


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

3. Register the built-in workflow handler:

```python
# settings.py
APPROVAL_HANDLERS = [
    "django_workflow_engine.handlers.WorkflowApprovalHandler",
]
```

This enables automatic workflow progression when approvals are completed.

4. Configure Approval Package Models:

Django Dynamic Workflows is built on top of the `django-approval-workflow` package. You need to configure two essential models for the approval system to work:

#### Required Settings

```python
# settings.py

# Role Model - for role-based approvals
# This model represents user roles (e.g., Manager, Director, CEO)
APPROVAL_ROLE_MODEL = 'myapp.Role'  # or 'auth.Group' to use Django's built-in Group model

# Dynamic Form Model - for approval forms (optional)
# This model represents dynamic forms that can be attached to approval steps
APPROVAL_DYNAMIC_FORM_MODEL = 'myapp.DynamicForm'  # Optional: for form-based approvals
```

#### Option 1: Use Django's Built-in Group Model (Simplest)

The easiest way is to use Django's built-in `Group` model for roles:

```python
# settings.py
APPROVAL_ROLE_MODEL = 'auth.Group'
```

Then create groups in Django admin or programmatically:

```python
from django.contrib.auth.models import Group

# Create roles as groups
finance_role = Group.objects.create(name='Finance Manager')
executive_role = Group.objects.create(name='Executive')

# Assign users to roles
user.groups.add(finance_role)
```

#### Option 2: Create a Custom Role Model

For more control, create a custom Role model:

```python
# myapp/models.py
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class Role(models.Model):
    """Custom role model for approval workflows."""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    users = models.ManyToManyField(User, related_name='approval_roles')

    class Meta:
        db_table = 'approval_roles'

    def __str__(self):
        return self.name
```

Then configure it in settings:

```python
# settings.py
APPROVAL_ROLE_MODEL = 'myapp.Role'
```

#### Option 3: Dynamic Form Model (Optional)

If you want to attach forms to approval steps, create a DynamicForm model:

```python
# myapp/models.py
class DynamicForm(models.Model):
    """Dynamic form that can be attached to approval steps."""
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    form_schema = models.JSONField()  # Store form fields as JSON

    def __str__(self):
        return self.name
```

Configure it:

```python
# settings.py
APPROVAL_DYNAMIC_FORM_MODEL = 'myapp.DynamicForm'
```

#### Complete Settings Example

```python
# settings.py
INSTALLED_APPS = [
    ...
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'approval_workflow',
    'django_workflow_engine',
    'myapp',
    ...
]

# Approval Package Configuration
APPROVAL_ROLE_MODEL = 'auth.Group'  # Using Django's built-in Group model
# APPROVAL_DYNAMIC_FORM_MODEL = 'myapp.DynamicForm'  # Optional

# Django Workflow Engine Configuration
DJANGO_WORKFLOW_ENGINE = {
    'DEPARTMENT_MODEL': 'myapp.Department',
}
```

4. Register a model for workflow support:

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

## 🔄 Workflow Cloning & Immutability

**IMPORTANT**: Django Dynamic Workflows automatically clones workflows when attaching them to objects to ensure **workflow immutability**. This prevents corruption of running workflows when the original workflow template is modified.

### How It Works

```python
# When you attach a workflow:
attachment = attach_workflow_to_object(obj=my_object, workflow=template_workflow)

# A clone is created automatically:
# - Original workflow: ID=1, name="Purchase Approval"
# - Cloned workflow: ID=2, name="Purchase Approval (Copy)", cloned_from=1

# Later modifications to the original won't affect running workflows:
template_workflow.name_en = "Updated Purchase Approval"
template_workflow.save()
# Running workflow (ID=2) remains unchanged - immutable! ✅
```

### Disable Cloning (Advanced)

If you need to use the original workflow without cloning (not recommended):

```python
attachment = attach_workflow_to_object(
    obj=my_object,
    workflow=template_workflow,
    disable_clone=True  # ⚠️ WARNING: May cause corruption
)
```

**⚠️ Warning**: Setting `disable_clone=True` may cause workflow corruption if the original workflow is modified after attachment. Only use this for special cases where you need direct workflow sharing.

### Benefits of Workflow Cloning

- ✅ **Data Integrity**: Running workflows remain stable even when templates change
- ✅ **Version Control**: Each workflow execution has its own immutable version
- ✅ **Audit Trail**: `cloned_from` field tracks the original template
- ✅ **Safe Updates**: Modify workflow templates without breaking active processes

## Core Concepts

### WorkFlow, Pipeline, Stage Hierarchy
- **WorkFlow**: Top-level workflow definition
- **Pipeline**: Departments or phases within a workflow
- **Stage**: Individual approval steps within a pipeline

## Workflow Strategy System

**New in v1.5.0**: The workflow engine now supports **3 flexible strategies** for structuring your approval workflows based on organizational complexity.

### Strategy Overview

Choose the right strategy based on your workflow complexity and organizational structure:

| Strategy | Value | Structure | Approvals Location | Use Case |
|----------|-------|-----------|-------------------|----------|
| **WORKFLOW_PIPELINE_STAGE** | 1 | Workflow → Pipeline → Stage | `stage_info` | Complex multi-department workflows with detailed stages |
| **WORKFLOW_PIPELINE** | 2 | Workflow → Pipeline | `pipeline_info` | Department-level approvals without stage granularity |
| **WORKFLOW_ONLY** | 3 | Workflow only | `workflow_info` | Simple single-step approval workflows |

### Strategy 1: WORKFLOW_PIPELINE_STAGE (Full Hierarchy)

**Best For**: Complex workflows with multiple departments and detailed approval stages

**Structure**:
```
Workflow
  ├── Pipeline 1 (Finance Department)
  │   ├── Stage 1 (Initial Review) ← Approvals here
  │   ├── Stage 2 (Budget Check) ← Approvals here
  │   └── Stage 3 (CFO Approval) ← Approvals here
  └── Pipeline 2 (Management)
      └── Stage 1 (Executive Approval) ← Approvals here
```

**Configuration Example**:
```python
from django_workflow_engine.models import WorkFlow, Pipeline, Stage
from django_workflow_engine.choices import WorkflowStrategy, ApprovalTypes
from approval_workflow.choices import RoleSelectionStrategy

# Create workflow with Strategy 1
workflow = WorkFlow.objects.create(
    name_en="Purchase Request Approval",
    strategy=WorkflowStrategy.WORKFLOW_PIPELINE_STAGE,
    company=user,
    is_active=True
)

# Create pipeline
finance_pipeline = Pipeline.objects.create(
    workflow=workflow,
    name_en="Finance Review",
    order=0
)

# Create stage with approvals in stage_info
initial_review = Stage.objects.create(
    pipeline=finance_pipeline,
    name_en="Initial Review",
    order=0,
    stage_info={
        "color": "#3498db",
        "approvals": [
            {
                "approval_type": ApprovalTypes.ROLE,
                "user_role": finance_role.id,
                "role_selection_strategy": RoleSelectionStrategy.ANYONE
            }
        ]
    }
)
```

**Use Cases**:
- Large purchase approvals with multiple review stages
- Complex HR workflows (recruitment → onboarding → training)
- Multi-department project approvals
- Detailed compliance workflows

### Strategy 2: WORKFLOW_PIPELINE (Two-Level)

**Best For**: Department-based workflows without stage-level detail

**Structure**:
```
Workflow
  ├── Pipeline 1 (HR Department) ← Approvals here
  ├── Pipeline 2 (Finance Department) ← Approvals here
  └── Pipeline 3 (Legal Department) ← Approvals here

Note: NO stages allowed in Strategy 2
```

**Configuration Example**:
```python
# Create workflow with Strategy 2
workflow = WorkFlow.objects.create(
    name_en="Employee Onboarding",
    strategy=WorkflowStrategy.WORKFLOW_PIPELINE,
    company=user,
    is_active=True
)

# Create pipeline with approvals in pipeline_info
hr_pipeline = Pipeline.objects.create(
    workflow=workflow,
    name_en="HR Processing",
    order=0,
    pipeline_info={
        "approvals": [
            {
                "approval_type": ApprovalTypes.ROLE,
                "user_role": hr_manager_role.id,
                "role_selection_strategy": RoleSelectionStrategy.ANYONE
            }
        ]
    }
)

# IMPORTANT: Do NOT create stages for Strategy 2 workflows
# Stages are not allowed and will be rejected by validation
```

**Use Cases**:
- Department-based approval workflows
- Sequential departmental reviews
- Cross-functional team approvals
- Simple multi-step processes

### Strategy 3: WORKFLOW_ONLY (Single-Level)

**Best For**: Simple, single-step approval workflows

**Structure**:
```
Workflow ← Approvals here

Note: NO pipelines or stages allowed in Strategy 3
```

**Configuration Example**:
```python
# Create workflow with Strategy 3
workflow = WorkFlow.objects.create(
    name_en="Time Off Request",
    strategy=WorkflowStrategy.WORKFLOW_ONLY,
    company=user,
    is_active=True,
    workflow_info={
        "approvals": [
            {
                "approval_type": ApprovalTypes.USER,
                "approval_user": manager.id
            }
        ]
    }
)

# IMPORTANT: Do NOT create pipelines or stages for Strategy 3 workflows
# They are not allowed and will be rejected by validation
```

**Use Cases**:
- Simple manager approval workflows
- Quick sign-off processes
- Single-step authorization
- Lightweight approval needs

### Strategy Selection Guide

**Choose Strategy 1** if you need:
- Multiple departments with detailed stages
- Complex approval chains with many steps
- Fine-grained control over each approval stage
- Different forms/requirements per stage

**Choose Strategy 2** if you need:
- Department-level approvals without stage detail
- Sequential departmental reviews
- Simpler structure than Strategy 1
- Each department approves as a unit

**Choose Strategy 3** if you need:
- Single approval step
- Minimal complexity
- Quick implementation
- One approver or approval group

### Strategy Validation

The system automatically validates structural constraints:

```python
# Strategy 1: Requires pipelines with stages
workflow = WorkFlow.objects.create(strategy=1, ...)
is_valid, msg = workflow.validate_completeness()
# Returns: False, "Strategy 1 workflow must have at least one pipeline"

# Strategy 2: Requires pipelines, NO stages allowed
workflow = WorkFlow.objects.create(strategy=2, ...)
pipeline = Pipeline.objects.create(workflow=workflow, ...)
stage = Stage.objects.create(pipeline=pipeline, ...)  # ❌ ValidationError!
# Error: "Strategy 2 (Workflow→Pipeline) cannot have stages."

# Strategy 3: NO pipelines or stages allowed
workflow = WorkFlow.objects.create(strategy=3, ...)
pipeline = Pipeline.objects.create(workflow=workflow, ...)  # ❌ ValidationError!
# Error: "Cannot create pipelines for Strategy 3 (Workflow Only) workflows."
```

### Using Serializers with Strategies

The serializers automatically validate strategy constraints:

```python
from django_workflow_engine.serializers import WorkFlowSerializer

# Strategy 1: Full hierarchy
workflow_data = {
    "name_en": "Complex Approval",
    "strategy": 1,  # WORKFLOW_PIPELINE_STAGE
    "pipelines": [
        {
            "name_en": "Finance",
            "stages": [
                {
                    "name_en": "Review",
                    "stage_info": {
                        "approvals": [{"approval_type": "role", "user_role": 1}]
                    }
                }
            ]
        }
    ]
}

# Strategy 2: Pipeline-level only
workflow_data = {
    "name_en": "Department Approval",
    "strategy": 2,  # WORKFLOW_PIPELINE
    "pipelines": [
        {
            "name_en": "HR",
            "pipeline_info": {
                "approvals": [{"approval_type": "role", "user_role": 2}]
            }
            # Note: No "stages" field - not allowed for Strategy 2
        }
    ]
}

# Strategy 3: Workflow-level only
workflow_data = {
    "name_en": "Simple Approval",
    "strategy": 3,  # WORKFLOW_ONLY
    "workflow_info": {
        "approvals": [{"approval_type": "user", "approval_user": 123}]
    }
    # Note: No "pipelines" field - not allowed for Strategy 3
}

serializer = WorkFlowSerializer(data=workflow_data)
if serializer.is_valid():
    workflow = serializer.save()
```

### Strategy Migration

If you're upgrading from a previous version, your existing workflows will continue to work. The default strategy is Strategy 1 (WORKFLOW_PIPELINE_STAGE).

To verify your workflows are using the correct strategy:

```python
from django_workflow_engine.models import WorkFlow

for workflow in WorkFlow.objects.all():
    is_valid, message = workflow.validate_completeness()
    print(f"{workflow.name_en} (Strategy {workflow.strategy}): {message}")
```

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

## Automatic Status Updates on Workflow Completion/Rejection

**New in v1.2.7**: Automatically update your model's status field when workflows complete or are rejected.

### Overview

The workflow engine can automatically update your model's status field based on workflow outcomes:
- When workflow **completes** → Update to completion status (e.g., "won", "closed", "completed")
- When workflow is **rejected** → Update to rejection status (e.g., "lost", "cancelled", "rejected")

This eliminates manual status management and ensures your models stay in sync with workflow states.

### Configuration

Configure status updates in your `WorkflowConfiguration`:

```python
from django_workflow_engine.models import WorkflowConfiguration
from django.contrib.contenttypes.models import ContentType

# Get or create configuration for your model
ct = ContentType.objects.get_for_model(YourModel)
config, created = WorkflowConfiguration.objects.get_or_create(
    content_type=ct,
    defaults={
        'status_field': 'status',  # Field name on your model
        'completion_status_value': 'completed',  # Value on workflow completion
        'rejection_status_value': 'rejected',    # Value on workflow rejection
    }
)
```

### Real-World Examples

#### Example 1: CRM Opportunity Workflow

```python
# models.py
class Opportunity(models.Model):
    name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=50, default='draft')
    # ... other fields

# Configure workflow
from django_workflow_engine.services import register_model_for_workflow

register_model_for_workflow(
    Opportunity,
    status_field='status',
    stage_field='current_stage'
)

# Set status values
ct = ContentType.objects.get_for_model(Opportunity)
config = WorkflowConfiguration.objects.get(content_type=ct)
config.completion_status_value = 'won'      # When deal closes
config.rejection_status_value = 'lost'      # When deal fails
config.save()

# Workflow behavior:
# - All stages approved → opportunity.status = 'won'
# - Any stage rejected → opportunity.status = 'lost'
```

#### Example 2: Support Ticket Workflow

```python
# models.py
class Ticket(models.Model):
    title = models.CharField(max_length=200)
    status = models.CharField(max_length=50, default='open')
    priority = models.CharField(max_length=20)
    # ... other fields

# Configure workflow
ct = ContentType.objects.get_for_model(Ticket)
config, created = WorkflowConfiguration.objects.get_or_create(
    content_type=ct,
    defaults={
        'status_field': 'status',
        'completion_status_value': 'closed',
        'rejection_status_value': 'cancelled',
    }
)

# Workflow behavior:
# - Resolution approved → ticket.status = 'closed'
# - Ticket rejected → ticket.status = 'cancelled'
```

#### Example 3: Purchase Request Workflow

```python
# models.py
class PurchaseRequest(models.Model):
    title = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=50, default='pending')
    # ... other fields

# Configure workflow
ct = ContentType.objects.get_for_model(PurchaseRequest)
config = WorkflowConfiguration.objects.get(content_type=ct)
config.status_field = 'status'
config.completion_status_value = 'approved'
config.rejection_status_value = 'denied'
config.save()

# Workflow behavior:
# - All approvals completed → purchase_request.status = 'approved'
# - Finance rejects → purchase_request.status = 'denied'
```

### How It Works

When a workflow completes or is rejected, the system:

1. **Looks up the configuration** for your model's ContentType
2. **Checks if status_field is configured** (e.g., "status")
3. **Verifies the field exists** on your model
4. **Updates the field value**:
   - On completion: Sets `completion_status_value`
   - On rejection: Sets `rejection_status_value`
5. **Saves the change** using `update_fields` for efficiency
6. **Logs the update** for audit trail

### Optional Configuration

Status updates are completely optional and backward compatible:

```python
# No status field configured → No automatic updates
config.status_field = ''  # Not configured

# Status field configured but no completion value → No update on completion
config.status_field = 'status'
config.completion_status_value = ''  # Won't update on completion
config.rejection_status_value = 'rejected'  # Will update on rejection

# Full configuration → Updates on both events
config.status_field = 'status'
config.completion_status_value = 'completed'
config.rejection_status_value = 'rejected'
```

### Logging and Audit Trail

All status updates are logged:

```python
# Info log on successful update
logger.info(
    "Updated Opportunity(123).status from 'in_progress' to 'won' on workflow completion"
)

# Warning if field doesn't exist
logger.warning(
    "Model Opportunity does not have field 'status', cannot update status on completion"
)

# Debug if not configured
logger.debug(
    "No status_field configured for Opportunity, skipping status update"
)
```

### Django Admin Configuration

You can also configure status values via Django Admin:

1. Go to **Django Admin** → **Workflow Configurations**
2. Select your model's configuration
3. Set the fields:
   - **Status field**: The field name (e.g., "status")
   - **Completion status value**: Value on workflow completion (e.g., "completed")
   - **Rejection status value**: Value on workflow rejection (e.g., "rejected")
4. Save

### Migration

After upgrading to v1.2.7, run the migration:

```bash
python manage.py migrate django_workflow_engine
```

This adds the `completion_status_value` and `rejection_status_value` fields to `WorkflowConfiguration`.

### Best Practices

1. **Use consistent status values** across your application
2. **Define status choices** in your model for validation:
   ```python
   class Opportunity(models.Model):
       STATUS_CHOICES = [
           ('draft', 'Draft'),
           ('in_progress', 'In Progress'),
           ('won', 'Won'),
           ('lost', 'Lost'),
       ]
       status = models.CharField(max_length=50, choices=STATUS_CHOICES)
   ```

3. **Log status changes** for audit purposes (handled automatically)
4. **Test your workflow** to ensure status transitions work as expected
5. **Consider using signals** if you need additional logic on status change

## Custom Actions

The Django Workflow Engine supports powerful custom actions that execute automatically at key workflow events. Actions can send emails, update external systems, create tasks, log events, and more.

### Quick Example
```python
# myapp/workflow_actions.py
def send_approval_notification(context, parameters=None):
    """Send email when stage is approved"""
    attachment = context['attachment']
    user = context.get('user')

    recipients = parameters.get('recipients', [])

    send_mail(
        subject=f"Stage '{attachment.current_stage.name_en}' Approved",
        message=f"Approved by {user.get_full_name()}",
        from_email='noreply@company.com',
        recipient_list=recipients,
    )

    return {"email_sent": True}

# Register in Django Admin or code:
from django_workflow_engine.models import WorkflowAction
from django_workflow_engine.choices import ActionType

WorkflowAction.objects.create(
    stage_id=1,  # Specific stage
    action_type=ActionType.AFTER_APPROVE,
    function_path='myapp.workflow_actions.send_approval_notification',
    parameters={'recipients': ['manager@company.com']},
    order=1,
    is_active=True
)
```

### Action Types & Timing

| Action Type | When Triggered | Use For |
|-------------|----------------|---------|
| `AFTER_APPROVE` | After stage approval | Approval notifications, logging |
| `AFTER_MOVE_STAGE` | After moving to next stage | Status updates, task creation |
| `AFTER_MOVE_PIPELINE` | After moving to next pipeline | Role changes, permissions |
| `ON_WORKFLOW_START` | When workflow starts | Initial setup, notifications |
| `ON_WORKFLOW_COMPLETE` | When workflow finishes | Final actions, cleanup |
| `AFTER_REJECT` | After rejection | Rejection handling |
| `AFTER_RESUBMISSION` | After resubmission | Resubmission handling |

### Action Execution Order (Conflict Prevention)

The system prevents conflicts by executing actions in a specific order:

```
1. AFTER_APPROVE          ← Approval completed (sees current stage)
2. AFTER_MOVE_PIPELINE    ← Pipeline transition (if needed)
3. AFTER_MOVE_STAGE       ← Stage transition (sees new stage)
4. Start next stage approval flow
```

### Available Role Selection Strategies

When configuring role-based approvals:

```python
from approval_workflow.choices import RoleSelectionStrategy

# Available strategies:
'anyone'       # Any user with the role can approve
'consensus'    # ALL users with the role must approve
'round_robin'  # Rotate approval among role users
```

### 📚 Comprehensive Guides

- **Custom Actions**: For complete documentation including advanced examples, conflict resolution, and best practices, see: **[CUSTOM_ACTIONS_README.md](CUSTOM_ACTIONS_README.md)**
- **Approval Types**: For detailed information on approval behavior types (APPROVE, SUBMIT, CHECK_IN_VERIFY, MOVE), see: **[APPROVAL_TYPE_INTEGRATION_GUIDE.md](APPROVAL_TYPE_INTEGRATION_GUIDE.md)**

## Complete Example: Purchase Request Workflow

This example demonstrates a complete workflow from A to Z with 2 pipelines and multiple stages.

### Scenario: Purchase Request Process
- **Pipeline 1 (Finance Department)**: Initial Review → Budget Approval → Final Finance Sign-off
- **Pipeline 2 (Management)**: Executive Approval

### Step 1: Setup Models

```python
# models.py
from django.db import models
from django.contrib.auth.models import User

class PurchaseRequest(models.Model):
    title = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField()
    requester = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    # Workflow fields
    workflow_status = models.CharField(max_length=50, default='pending')
    current_stage = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"Purchase Request: {self.title} - ${self.amount}"
```

### Step 2: Register Model for Workflow

```python
# apps.py or management command
from django_workflow_engine.services import register_model_for_workflow
from .models import PurchaseRequest

register_model_for_workflow(
    PurchaseRequest,
    auto_start=True,
    status_field='workflow_status'
    # Note: No stage_field needed - use get_current_stage(instance) helper instead
)
```

### Step 3: Create Workflow Structure Using Serializers

```python
# Create via API serializers (recommended) or Django Admin
from django_workflow_engine.serializers import WorkFlowSerializer, StageSerializer
from django_workflow_engine.models import WorkFlow, Pipeline, Stage
from rest_framework.request import Request

# 1. Create Workflow with Pipelines using WorkFlowSerializer
workflow_data = {
    'name_en': 'Purchase Request Approval',
    'name_ar': 'موافقة طلب الشراء',
    'company': 1,
    'is_active': True,
    'pipelines': [
        {
            'name_en': 'Finance Review',
            'name_ar': 'مراجعة مالية',
            'department_id': 1,  # Finance Department
            'order': 1,
            'number_of_stages': 3  # Will auto-create 3 stages
        },
        {
            'name_en': 'Executive Approval',
            'name_ar': 'موافقة تنفيذية',
            'department_id': 2,  # Management Department
            'order': 2,
            'number_of_stages': 1  # Will auto-create 1 stage
        }
    ]
}

# Create workflow with auto-generated stages
context = {'request': request, 'company_user': company_instance}
workflow_serializer = WorkFlowSerializer(data=workflow_data, context=context)
if workflow_serializer.is_valid():
    result = workflow_serializer.save()  # Returns workflow with pipelines and stages
    purchase_workflow = WorkFlow.objects.get(id=result['id'])

# 2. Configure Stage Approvals and Forms
# Now configure each stage with approval requirements, roles, and forms
from django_workflow_engine.serializers import StageSerializer
from django_workflow_engine.choices import ApprovalTypes
from approval_workflow.choices import RoleSelectionStrategy

# Get the auto-created stages
finance_pipeline = purchase_workflow.pipelines.get(name_en='Finance Review')
executive_pipeline = purchase_workflow.pipelines.get(name_en='Executive Approval')

# Configure Finance Stage 1: Initial Review
initial_review = finance_pipeline.stages.get(order=1)
stage_config = {
    'name_en': 'Initial Review',
    'name_ar': 'المراجعة الأولية',
    'pipeline_id': finance_pipeline.id,
    'stage_info': {
        'color': '#3498db',
        'approvals': [
            {
                'approval_type': ApprovalTypes.ROLE,
                'user_role': 1,  # Finance Reviewer Role ID
                'role_selection_strategy': RoleSelectionStrategy.ROUND_ROBIN,
                'required_form': 1  # Initial Review Form ID
            }
        ]
    }
}

stage_serializer = StageSerializer(initial_review, data=stage_config, partial=True)
if stage_serializer.is_valid():
    stage_serializer.save()

# Configure Finance Stage 2: Budget Approval
budget_approval = finance_pipeline.stages.get(order=2)
stage_config = {
    'name_en': 'Budget Approval',
    'name_ar': 'موافقة الميزانية',
    'pipeline_id': finance_pipeline.id,
    'stage_info': {
        'color': '#f39c12',
        'approvals': [
            {
                'approval_type': ApprovalTypes.ROLE,
                'user_role': 2,  # Budget Manager Role ID
                'role_selection_strategy': RoleSelectionStrategy.ANYONE,
                'required_form': 2  # Budget Approval Form ID
            }
        ]
    }
}

stage_serializer = StageSerializer(budget_approval, data=stage_config, partial=True)
if stage_serializer.is_valid():
    stage_serializer.save()

# Configure Finance Stage 3: Final Finance Sign-off
finance_signoff = finance_pipeline.stages.get(order=3)
stage_config = {
    'name_en': 'Final Finance Sign-off',
    'name_ar': 'الموافقة المالية النهائية',
    'pipeline_id': finance_pipeline.id,
    'stage_info': {
        'color': '#27ae60',
        'approvals': [
            {
                'approval_type': ApprovalTypes.USER,
                'approval_user': 123,  # CFO User ID
                'required_form': 3  # Final Approval Form ID
            }
        ]
    }
}

stage_serializer = StageSerializer(finance_signoff, data=stage_config, partial=True)
if stage_serializer.is_valid():
    stage_serializer.save()

# Configure Executive Stage: Executive Approval
executive_approval = executive_pipeline.stages.get(order=1)
stage_config = {
    'name_en': 'Executive Approval',
    'name_ar': 'موافقة تنفيذية',
    'pipeline_id': executive_pipeline.id,
    'stage_info': {
        'color': '#8e44ad',
        'approvals': [
            {
                'approval_type': ApprovalTypes.ROLE,
                'user_role': 3,  # Executive Role ID
                'role_selection_strategy': RoleSelectionStrategy.CONSENSUS
                # No required_form - executives can approve without additional forms
            }
        ]
    }
}

stage_serializer = StageSerializer(executive_approval, data=stage_config, partial=True)
if stage_serializer.is_valid():
    stage_serializer.save()
```

### Step 4: Start Workflow (A → Z Process)

```python
# views.py
from django_workflow_engine.services import attach_workflow_to_object

def create_purchase_request(request):
    # Create purchase request
    purchase_request = PurchaseRequest.objects.create(
        title=request.POST['title'],
        amount=request.POST['amount'],
        description=request.POST['description'],
        requester=request.user
    )

    # Attach and start workflow
    attachment = attach_workflow_to_object(
        obj=purchase_request,
        workflow=purchase_workflow,
        user=request.user,
        auto_start=True,
        metadata={
            'amount': float(purchase_request.amount),
            'priority': 'normal',
            'department': 'finance'
        }
    )

    # At this point:
    # - Purchase request is at "Initial Review" stage
    # - Current pipeline: Finance Review
    # - Status: "in_progress"

    return purchase_request
```

### Step 5: Progress Through Workflow

```python
# Helper function to get current stage (replaces stage_field dependency)
from django_workflow_engine.services import get_current_stage, get_workflow_attachment

def get_current_stage_info(purchase_request):
    """Get current stage information for purchase request"""
    attachment = get_workflow_attachment(purchase_request)
    if attachment:
        return {
            'current_stage': attachment.current_stage,
            'current_pipeline': attachment.current_pipeline,
            'stage_name': attachment.current_stage.name_en if attachment.current_stage else None,
            'pipeline_name': attachment.current_pipeline.name_en if attachment.current_pipeline else None
        }
    return None

# Use WorkflowApprovalSerializer (based on existing CRM implementation)
from django_workflow_engine.serializers import WorkflowApprovalSerializer

# FINANCE PIPELINE - STAGE 1: Initial Review
def approve_initial_review(request, purchase_request_id):
    purchase_request = PurchaseRequest.objects.get(id=purchase_request_id)

    # Check current stage
    stage_info = get_current_stage_info(purchase_request)
    print(f"Current stage: {stage_info['stage_name']} in {stage_info['pipeline_name']}")

    serializer = WorkflowApprovalSerializer(
        instance=purchase_request,  # Use instance, not object_instance
        data={
            'action': 'APPROVED',  # Use ApprovalStatus choices
            'form_data': {
                'reviewer_comment': 'Initial review passed - budget code verified',
                'budget_code': 'BDG-2024-001'
            }
        },
        context={'request': request}
    )

    if serializer.is_valid():
        serializer.save()
        # ✅ Automatically moves to: Finance Pipeline → Budget Approval stage

# FINANCE PIPELINE - STAGE 2: Budget Approval
def approve_budget(request, purchase_request_id):
    purchase_request = PurchaseRequest.objects.get(id=purchase_request_id)

    serializer = WorkflowApprovalSerializer(
        instance=purchase_request,
        data={
            'action': 'APPROVED',
            'form_data': {
                'budget_manager_comment': 'Budget approved - sufficient funds available',
                'allocated_budget': '50000.00'
            }
        },
        context={'request': request}
    )

    if serializer.is_valid():
        serializer.save()
        # ✅ Automatically moves to: Finance Pipeline → Final Finance Sign-off stage

# FINANCE PIPELINE - STAGE 3: Final Finance Sign-off
def final_finance_approval(request, purchase_request_id):
    purchase_request = PurchaseRequest.objects.get(id=purchase_request_id)

    serializer = WorkflowApprovalSerializer(
        instance=purchase_request,
        data={
            'action': 'APPROVED',
            'form_data': {
                'cfo_comment': 'Financially approved - ready for executive review',
                'finance_ref': 'FIN-2024-PR-001'
            }
        },
        context={'request': request}
    )

    if serializer.is_valid():
        serializer.save()
        # ✅ PIPELINE TRANSITION: Finance → Management Pipeline

# MANAGEMENT PIPELINE - STAGE 1: Executive Approval
def executive_approval(request, purchase_request_id):
    purchase_request = PurchaseRequest.objects.get(id=purchase_request_id)

    serializer = WorkflowApprovalSerializer(
        instance=purchase_request,
        data={
            'action': 'APPROVED',
            # No form_data required for executive approval (as configured)
        },
        context={'request': request}
    )

    if serializer.is_valid():
        serializer.save()
        # ✅ WORKFLOW COMPLETED!
        # Status automatically changes to: "completed"
```

### Step 6: Handle Rejections and Special Cases

```python
# Reject workflow
def reject_budget_approval(request, purchase_request_id):
    purchase_request = PurchaseRequest.objects.get(id=purchase_request_id)

    serializer = WorkflowApprovalSerializer(
        instance=purchase_request,
        data={
            'action': 'REJECTED',  # Use ApprovalStatus.REJECTED
            'reason': 'Insufficient budget allocation for this quarter'
        },
        context={'request': request}
    )

    if serializer.is_valid():
        serializer.save()
        # ❌ Workflow status becomes "rejected"

# Request resubmission to previous stage
def request_resubmission(request, purchase_request_id):
    purchase_request = PurchaseRequest.objects.get(id=purchase_request_id)

    # Get the initial review stage for resubmission
    finance_pipeline = purchase_request.workflow.pipelines.get(name_en='Finance Review')
    initial_review_stage = finance_pipeline.stages.get(order=1)

    serializer = WorkflowApprovalSerializer(
        instance=purchase_request,
        data={
            'action': 'NEEDS_RESUBMISSION',  # Use ApprovalStatus.NEEDS_RESUBMISSION
            'stage_id': initial_review_stage.id,  # Back to Initial Review
            'reason': 'Please provide additional cost breakdown details'
        },
        context={'request': request}
    )

    if serializer.is_valid():
        serializer.save()
        # ↩️ Goes back to specified stage

# Delegate to another user
def delegate_approval(request, purchase_request_id):
    purchase_request = PurchaseRequest.objects.get(id=purchase_request_id)

    serializer = WorkflowApprovalSerializer(
        instance=purchase_request,
        data={
            'action': 'DELEGATED',  # Use ApprovalStatus.DELEGATED
            'user_id': 123,  # Senior manager user ID
            'reason': 'Amount exceeds my approval limit'
        },
        context={'request': request}
    )

    if serializer.is_valid():
        serializer.save()
        # 👥 Approval responsibility transferred to user 123
```

**✨ New in v1.0.5**: Complete resubmission and delegation logic implementation with proper workflow event triggers and stage transitions.

### Step 7: Track Progress

```python
from django_workflow_engine.services import get_workflow_progress, get_workflow_attachment

def get_purchase_status(purchase_request_id):
    purchase_request = PurchaseRequest.objects.get(id=purchase_request_id)

    # Get workflow attachment and current stage info
    attachment = get_workflow_attachment(purchase_request)
    if not attachment:
        return {'error': 'No workflow attached to this purchase request'}

    # Get detailed progress using the attachment's workflow
    progress = get_workflow_progress(attachment.workflow, purchase_request)

    # Use helper function for current stage info
    stage_info = get_current_stage_info(purchase_request)

    return {
        'current_stage': stage_info['stage_name'] if stage_info else None,
        'current_pipeline': stage_info['pipeline_name'] if stage_info else None,
        'progress_percentage': progress['progress_percentage'],
        'status': progress['status'],
        'next_stage': attachment.next_stage.name_en if attachment.next_stage else 'Workflow Complete',
        'started_by': attachment.started_by.username if attachment.started_by else None,
        'started_at': attachment.started_at,
        'metadata': attachment.metadata,
        'workflow_name': attachment.workflow.name_en
    }

# Enhanced helper to check if user requires action
from approval_workflow.models import ApprovalInstance
from approval_workflow.choices import ApprovalStatus
from django.contrib.contenttypes.models import ContentType

def user_requires_action(purchase_request, user):
    """Check if user has pending approval for this purchase request"""
    content_type = ContentType.objects.get_for_model(PurchaseRequest)

    return ApprovalInstance.objects.filter(
        assigned_to=user,
        status=ApprovalStatus.CURRENT,
        flow__content_type=content_type,
        flow__object_id=str(purchase_request.id)
    ).exists()

# Example usage
def check_purchase_status_for_user(purchase_request_id, user):
    purchase_request = PurchaseRequest.objects.get(id=purchase_request_id)
    status = get_purchase_status(purchase_request_id)

    status['requires_user_action'] = user_requires_action(purchase_request, user)
    status['can_approve'] = user_requires_action(purchase_request, user)

    return status
```

### Complete Workflow Flow Summary

```
📝 Purchase Request Created
    ↓ (auto_start=True)

🏢 FINANCE PIPELINE
    ↓
📋 Stage 1: Initial Review
    ↓ (approved)
💰 Stage 2: Budget Approval
    ↓ (approved)
✅ Stage 3: Final Finance Sign-off
    ↓ (approved - PIPELINE TRANSITION)

🏢 MANAGEMENT PIPELINE
    ↓
👔 Stage 1: Executive Approval
    ↓ (approved)

🎉 WORKFLOW COMPLETED
```

### API Integration Example

```javascript
// Track workflow progress
const trackPurchaseWorkflow = async (purchaseId) => {
    const response = await fetch(`/api/purchase-requests/${purchaseId}/workflow_status/`);
    const status = await response.json();

    console.log(`Current Stage: ${status.current_stage}`);
    console.log(`Progress: ${status.progress_percentage}%`);
    console.log(`Status: ${status.status}`);
};

// Approve current stage
const approvePurchaseStage = async (purchaseId, formData) => {
    const response = await fetch(`/api/purchase-requests/${purchaseId}/workflow_action/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            action: 'approved',
            form_data: formData
        })
    });

    if (response.ok) {
        trackPurchaseWorkflow(purchaseId);
    }
};
```

This example shows the complete journey from creating a purchase request to final approval, demonstrating how the workflow engine handles multi-pipeline, multi-stage processes with proper progression control.

## Detailed Workflow Data Functions

The Django Workflow Engine provides optimized functions for retrieving comprehensive workflow information with minimal database queries.

### Core Functions

#### `get_detailed_workflow_data()`

Get complete workflow information with all nested pipelines and stages.

```python
from django_workflow_engine.services import get_detailed_workflow_data

# Get specific workflow with full details
workflow_data = get_detailed_workflow_data(workflow_id=1)

# Get all active workflows for a company
workflows_data = get_detailed_workflow_data(company_id=1)

# Get all workflows including inactive
all_workflows = get_detailed_workflow_data(include_inactive=True)
```

**Response Structure:**
```python
{
    'id': 1,
    'name_en': 'Purchase Request Workflow',
    'name_ar': 'سير عمل طلب الشراء',
    'company': 1,
    'company_name': 'Acme Corp',
    'is_active': True,
    'pipelines_count': 2,
    'total_stages_count': 4,
    'pipelines': [
        {
            'id': 1,
            'name_en': 'Finance Review',
            'stages_count': 3,
            'stages': [
                {
                    'id': 1,
                    'name_en': 'Initial Review',
                    'approvals_count': 1,
                    'has_approvals': True,
                    'approval_configuration': {
                        'approvals': [
                            {
                                'approval_type': 'ROLE',
                                'approval_type_display': 'Role-based Approval',
                                'role_selection_strategy': 'anyone',
                                'strategy_display': 'Any user with role can approve'
                            }
                        ]
                    }
                }
            ]
        }
    ],
    'workflow_summary': {
        'total_pipelines': 2,
        'total_stages': 4,
        'total_approvals': 6
    }
}
```

#### `get_workflow_pipeline_structure()`

Get simplified pipeline structure for visualization.

```python
from django_workflow_engine.services import get_workflow_pipeline_structure

structure = get_workflow_pipeline_structure(workflow_id=1)
```

#### `get_workflow_approval_summary()`

Get approval statistics and breakdown.

```python
from django_workflow_engine.services import get_workflow_approval_summary

summary = get_workflow_approval_summary(workflow_id=1)
# Returns approval counts by type, strategy, and pipeline breakdown
```

#### `get_workflow_statistics()`

Get system-wide workflow statistics.

```python
from django_workflow_engine.services import get_workflow_statistics

# All workflows
stats = get_workflow_statistics()

# Company-specific
stats = get_workflow_statistics(company_id=1)
```

### Performance Features

- **Optimized Queries**: Uses `select_related` and `prefetch_related` for minimal database hits
- **Smart Caching**: Processes related data in memory to avoid N+1 queries
- **Flexible Filtering**: Company and active status filters with efficient query building
- **Rich Metadata**: Enriched approval configurations with human-readable displays

### Usage Examples

#### Workflow Dashboard

```python
def build_workflow_dashboard(company_id=None):
    """Build comprehensive workflow dashboard data"""
    # Get all workflows with statistics
    workflows_data = get_detailed_workflow_data(
        company_id=company_id,
        include_inactive=False
    )

    return {
        'workflows': workflows_data['workflows'],
        'total_count': workflows_data['total_count'],
        'statistics': workflows_data['statistics']
    }
```

#### Workflow Analysis

```python
def analyze_workflow_complexity(workflow_id):
    """Analyze workflow complexity metrics"""
    # Get detailed data
    workflow = get_detailed_workflow_data(workflow_id=workflow_id)

    # Get approval breakdown
    approval_summary = get_workflow_approval_summary(workflow_id)

    return {
        'complexity_score': workflow['workflow_summary']['total_approvals'],
        'pipeline_count': workflow['pipelines_count'],
        'avg_approvals_per_stage': (
            approval_summary['total_approvals'] /
            workflow['total_stages_count']
        ),
        'role_based_percentage': (
            approval_summary['by_type']['ROLE'] /
            approval_summary['total_approvals'] * 100
        )
    }
```

#### Workflow Visualization Data

```python
def get_workflow_diagram_data(workflow_id):
    """Get data formatted for workflow diagrams"""
    structure = get_workflow_pipeline_structure(workflow_id)

    nodes = []
    edges = []

    for pipeline in structure['pipelines']:
        for i, stage in enumerate(pipeline['stages']):
            nodes.append({
                'id': f"stage-{stage['id']}",
                'label': stage['name_en'],
                'color': stage['color'],
                'approvals': stage['approvals_count']
            })

            # Connect to previous stage
            if i > 0:
                prev_stage = pipeline['stages'][i-1]
                edges.append({
                    'from': f"stage-{prev_stage['id']}",
                    'to': f"stage-{stage['id']}"
                })

    return {'nodes': nodes, 'edges': edges}
```

#### Performance Monitoring

```python
def monitor_workflow_performance():
    """Monitor system-wide workflow performance"""
    stats = get_workflow_statistics()
    overview = stats['overview']

    return {
        'total_workflows': overview['total_workflows'],
        'active_percentage': (
            overview['active_workflows'] /
            overview['total_workflows'] * 100
        ),
        'avg_complexity': overview['avg_stages_per_workflow'],
        'companies': len(stats['by_company']),
        'bottlenecks': [
            company for company, data in stats['by_company'].items()
            if data['approvals'] / data['stages'] > 2.0  # High approval ratio
        ]
    }
```

## Custom Actions & Email Notifications

⭐ **IMPORTANT CHANGE in v1.5.5**: This package **DOES NOT send emails**. It only provides workflow orchestration and action hooks.

### Key Principles

- **No Built-in Email Sending**: The package focuses on workflow orchestration, not email delivery
- **User-Implemented Actions**: You must implement your own action handlers in your application
- **Action Hooks Only**: The package triggers action events; you decide what happens
- **Maximum Flexibility**: Use any email service (Django mail, SendGrid, Mailgun, etc.)

### How to Implement Email Notifications

1. **Create action handlers in your app:**

```python
# myapp/workflow_actions.py
from django.core.mail import send_mail

def send_approval_email(workflow_attachment, action_parameters, **context):
    """Your custom email handler."""
    obj = workflow_attachment.target

    send_mail(
        subject='Workflow Approved',
        message=f'Your {obj} has been approved!',
        from_email='noreply@example.com',
        recipient_list=[obj.created_by.email],
    )
    return True

def send_rejection_email(workflow_attachment, action_parameters, **context):
    """Your custom rejection handler."""
    obj = workflow_attachment.target
    reason = context.get('reason', 'No reason provided')

    send_mail(
        subject='Workflow Rejected',
        message=f'Your {obj} was rejected. Reason: {reason}',
        from_email='noreply@example.com',
        recipient_list=[obj.created_by.email],
    )
    return True
```

2. **Configure actions to use YOUR handlers:**

```python
# Via WorkflowAction model
from django_workflow_engine.models import WorkflowAction
from django_workflow_engine.choices import ActionType

WorkflowAction.objects.create(
    workflow=my_workflow,
    action_type=ActionType.AFTER_APPROVE,
    function_path='myapp.workflow_actions.send_approval_email',
    is_active=True,
    order=1,
)

# Or via settings
WORKFLOW_ACTIONS_CONFIG = [
    {
        'action_type': 'after_approve',
        'function_path': 'myapp.workflow_actions.send_approval_email',
        'order': 1,
    },
    {
        'action_type': 'after_reject',
        'function_path': 'myapp.workflow_actions.send_rejection_email',
        'order': 1,
    },
]

# Settings-based actions configuration (optional)
WORKFLOW_ACTIONS_CONFIG = [
    # Notifications (Order 1 - run first)
    {
        "action_type": "after_approve",
        "function_path": "crm.notifications.send_opportunity_approved_notification",
        "order": 1,
        "parameters": {"recipients": ["creator", "next_approvers"]},
    },
    {
        "action_type": "on_workflow_start",
        "function_path": "crm.notifications.opportunity_workflow_started",
        "order": 1,
        "parameters": {"recipients": ["current_approvers"]},
    },
    # Status Updates (Order 2 - run after notifications)
    {
        "action_type": "after_approve",
        "function_path": "crm.notifications.update_opportunity_status",
        "order": 2,
        "parameters": {"status": "IN_PROGRESS"},
    },
]
```

### Action Priority System

⭐ **IMPORTANT CHANGE in v1.5.5**: Default actions are no longer automatically executed. You must explicitly configure actions using either the database or settings.

The workflow engine uses a **2-tier priority system** for action execution:

**Priority 1: Database Actions (Highest)**
- Custom actions stored in the database
- Inheritance order: Stage → Pipeline → Workflow
- If found at any level, stops and executes only these actions

**Priority 2: Settings-Based Actions (Fallback)**
- Actions configured in `WORKFLOW_ACTIONS_CONFIG` setting
- Allows project-wide action definitions
- Used if no database actions found
- If not explicitly configured, no actions will execute

**Example Flow:**
1. Check for stage-level database actions → Found? Execute and stop
2. Check for pipeline-level database actions → Found? Execute and stop
3. Check for workflow-level database actions → Found? Execute and stop
4. Check for settings-based actions (`WORKFLOW_ACTIONS_CONFIG`) → Found? Execute and stop
5. If no actions configured at any level → No action executed (logs a debug message)

**Benefits:**
- **No Surprises**: Actions only execute when explicitly configured
- **No Email Failures**: Avoid mail server errors when not configured
- **Clear Intent**: Actions reflect your explicit configuration
- **Flexibility**: Configure actions at any level (stage, pipeline, workflow, or settings)
- **Inheritance**: Stage actions override pipeline/workflow actions
- **Clear Logging**: Logs show action source (DB or settings) or absence of actions

### Available Action Types (Hooks)

The package triggers these action events that you can hook into:

| Action Type | When Triggered | Context Provided |
|-------------|----------------|------------------|
| `AFTER_APPROVE` | After approval | workflow_attachment, user, stage |
| `AFTER_REJECT` | After rejection | workflow_attachment, user, stage, reason |
| `AFTER_RESUBMISSION` | Resubmission required | workflow_attachment, user, stage, comments |
| `AFTER_DELEGATE` | Approval delegated | workflow_attachment, user, delegated_to |
| `AFTER_MOVE_STAGE` | Stage progression | workflow_attachment, from_stage, to_stage |
| `AFTER_MOVE_PIPELINE` | Pipeline progression | workflow_attachment, from_pipeline, to_pipeline |
| `ON_WORKFLOW_START` | Workflow starts | workflow_attachment, initial_stage, initial_pipeline |
| `ON_WORKFLOW_COMPLETE` | Workflow completes | workflow_attachment, user |

**Example: Implementing all action handlers**

```python
# myapp/workflow_actions.py

def handle_after_approve(workflow_attachment, action_parameters, **context):
    """Called after approval."""
    # Your logic here (email, webhook, logging, etc.)
    pass

def handle_after_reject(workflow_attachment, action_parameters, **context):
    """Called after rejection."""
    pass

def handle_after_move_stage(workflow_attachment, action_parameters, **context):
    """Called when stage changes."""
    pass

# ... implement other handlers as needed
```

### Custom Actions via API

You can define custom actions when creating workflows, pipelines, or stages using the REST API:

```python
# Create workflow with custom actions
workflow_data = {
    "name_en": "Purchase Request",
    "name_ar": "طلب شراء",
    "company": company_id,
    "status": "active",
    "actions": [
        {
            "action_type": "after_approve",
            "function_path": "myapp.actions.send_custom_approval",
            "parameters": {
                "template": "custom_approved",
                "recipients": ["creator", "manager@example.com"],
                "subject": "Custom Approval Notification"
            },
            "order": 1,
            "is_active": True
        },
        {
            "action_type": "after_reject",
            "function_path": "myapp.actions.send_custom_rejection",
            "parameters": {
                "template": "custom_rejected",
                "recipients": ["creator"],
                "cc": ["supervisor@example.com"]
            },
            "order": 1,
            "is_active": True
        }
    ],
    "pipelines": [
        {
            "name_en": "Finance Review",
            "order": 0,
            "actions": [  # Pipeline-level custom actions
                {
                    "action_type": "after_move_stage",
                    "function_path": "myapp.actions.notify_finance_team",
                    "parameters": {"team_email": "finance@example.com"},
                    "order": 1
                }
            ],
            "stages": [
                {
                    "name_en": "Budget Approval",
                    "order": 0,
                    "actions": [  # Stage-level custom actions
                        {
                            "action_type": "after_approve",
                            "function_path": "myapp.actions.update_budget_system",
                            "parameters": {"api_endpoint": "/api/budget/update"},
                            "order": 1
                        }
                    ]
                }
            ]
        }
    ]
}

# POST to /api/workflows/
serializer = WorkFlowSerializer(data=workflow_data)
if serializer.is_valid():
    workflow = serializer.save()
```

### Action Inheritance

Actions follow a hierarchical inheritance model:

1. **Stage-level actions** (highest priority): Execute if defined for the specific stage
2. **Pipeline-level actions**: Execute if no stage actions and pipeline actions exist
3. **Workflow-level actions**: Execute if no stage or pipeline actions exist
4. **Settings-based actions**: Execute if configured in `WORKFLOW_ACTIONS_CONFIG` and no database actions exist
5. **No action**: If no actions configured at any level, no action is executed

Example:
```python
# If Stage 1 has custom actions → Execute Stage 1 actions only
# If Stage 1 has NO actions but Pipeline 1 has actions → Execute Pipeline 1 actions
# If neither Stage 1 nor Pipeline 1 have actions → Execute Workflow-level actions
# If no database actions exist → Check WORKFLOW_ACTIONS_CONFIG settings
# If no actions at any level → No action executed (logs debug message)
```

### Custom Email Functions

Integrate your own email service by providing a custom email function:

```python
# myapp/utils.py
def send_email(name, email, subject, context, user=None):
    """
    Custom email function compatible with django-workflow-engine.

    Args:
        name: Email template name
        email: Recipient email address
        subject: Email subject
        context: Dict with workflow context (workflow_name, stage_name, etc.)
        user: Optional user object
    """
    # Example: SendGrid integration
    import sendgrid
    from sendgrid.helpers.mail import Mail

    sg = sendgrid.SendGridAPIClient(api_key=os.environ.get('SENDGRID_API_KEY'))

    message = Mail(
        from_email='noreply@company.com',
        to_emails=email,
        subject=subject,
        html_content=render_template(name, context)
    )

    try:
        response = sg.send(message)
        return response.status_code == 202
    except Exception as e:
        logger.error(f"SendGrid error: {e}")
        return False

# settings.py
WORKFLOW_SEND_EMAIL_FUNCTION = 'myapp.utils.send_email'
```

### Writing Custom Action Handlers

Create custom action handlers that integrate with external systems:

```python
# myapp/actions.py
def send_custom_approval(workflow_attachment, action_parameters, **context):
    """
    Custom action handler for approval notifications.

    Args:
        workflow_attachment: WorkflowAttachment instance
        action_parameters: Dict from action configuration
        **context: Additional context (user, stage, reason, etc.)

    Returns:
        bool: True if action succeeded
    """
    from django_workflow_engine.notifications import send_bulk_workflow_emails
    from django_workflow_engine.recipient_resolver import resolve_recipients

    # Get parameters
    template = action_parameters.get('template', 'default_template')
    recipient_types = action_parameters.get('recipients', ['creator'])
    subject = action_parameters.get('subject', 'Workflow Update')

    # Resolve recipients
    email_addresses = resolve_recipients(
        recipient_types=recipient_types,
        workflow_attachment=workflow_attachment,
        **context
    )

    if not email_addresses:
        return False

    # Build context
    email_context = {
        'workflow_name': workflow_attachment.workflow.name_en,
        'current_stage': workflow_attachment.current_stage.name_en if workflow_attachment.current_stage else 'N/A',
        'user': context.get('user'),
        'custom_field': action_parameters.get('custom_field'),
    }

    # Send emails
    result = send_bulk_workflow_emails(
        name=template,
        recipients=list(email_addresses),
        context=email_context,
        deduplicate=False
    )

    return result['sent'] > 0


def update_external_system(workflow_attachment, action_parameters, **context):
    """Example: Update external CRM system."""
    import requests

    api_endpoint = action_parameters.get('api_endpoint')
    api_key = action_parameters.get('api_key')

    try:
        response = requests.post(
            api_endpoint,
            json={
                'workflow_id': workflow_attachment.workflow.id,
                'status': workflow_attachment.status,
                'stage': workflow_attachment.current_stage.name_en if workflow_attachment.current_stage else None,
            },
            headers={'Authorization': f'Bearer {api_key}'}
        )
        return response.status_code == 200
    except Exception as e:
        logger.error(f"External system update failed: {e}")
        return False
```

### Recipient Types

The system supports several recipient types that are automatically resolved:

| Recipient Type | Resolves To |
|----------------|-------------|
| `"creator"` | User who created the attached object (object.created_by) |
| `"current_approver"` | Current approval step approver(s) |
| `"delegated_to"` | User to whom approval was delegated |
| `"workflow_starter"` | User who started the workflow |
| `"user@example.com"` | Direct email address |
| User object | Direct user object |
| User ID (int) | User by ID |

Example:
```python
{
    "recipients": [
        "creator",                    # Resolves to object.created_by.email
        "current_approver",           # Resolves to current approval user(s)
        "manager@company.com",        # Direct email
        "delegated_to"                # From delegation context
    ]
}
```

### Managing Actions in Django Admin

Actions can be managed through the Django admin interface:

1. Navigate to **Django Workflow Engine → Workflow Actions**
2. Create new action or edit existing
3. Select scope: Workflow, Pipeline, or Stage
4. Choose action type and set function path
5. Configure parameters as JSON
6. Set execution order and active status

### Testing Email Notifications

Use the provided test mocks to test email notifications without sending actual emails:

```python
from unittest.mock import patch
from django.test import TestCase

class WorkflowEmailTest(TestCase):
    @patch('django_workflow_engine.action_handlers.send_approval_notification')
    def test_approval_sends_email(self, mock_handler):
        # Mock the handler to return success
        mock_handler.return_value = True

        # Execute workflow approval
        serializer = WorkflowApprovalSerializer(
            instance=my_object,
            data={'action': 'approved'},
            context={'request': request}
        )
        serializer.save()

        # Verify handler was called
        self.assertTrue(mock_handler.called)
```

### Best Practices

1. **Use Action Inheritance**: Define common actions at workflow level, specific ones at stage level
2. **Enable Auto-Creation**: Let the system create default actions, override only where needed
3. **Custom Email Functions**: Use for integration with your email service provider
4. **Idempotent Handlers**: Ensure action handlers can be safely re-executed
5. **Error Handling**: Return `False` from handlers on failure for proper logging
6. **Testing**: Always test with mocked email sending to avoid actual emails during tests

## Workflow Cleanup & Database Management

As workflows complete, `WorkflowAttachment` records accumulate in your database. Use the built-in cleanup utilities to reduce database size while preserving workflow templates for reuse.

### Check What Can Be Cleaned

```bash
python manage.py cleanup_workflows --stats
```

Output:
```
=== Workflow Cleanup Statistics ===

Workflow Attachments (Instances):
  Total: 1523
  Completed: 892 (58.6%)
  Rejected: 145 (9.5%)
  In Progress: 486 (31.9%)

Completed/Rejected by Age:
  Older than 30 days: 645 (62.2%)
  Older than 90 days: 412 (39.7%)
  Older than 365 days: 89 (8.6%)

Recommendations:
  → Consider running: python manage.py cleanup_workflows --days=30
```

### Cleanup Commands

```bash
# Preview cleanup (dry run) - 30-day retention
python manage.py cleanup_workflows --days=30 --dry-run

# Actual cleanup - delete completed workflows older than 30 days
python manage.py cleanup_workflows --days=30

# Aggressive cleanup - 7-day retention
python manage.py cleanup_workflows --days=7

# Delete all completed workflows immediately
python manage.py cleanup_workflows --days=0

# Clean only rejected workflows (keep completed for audit)
python manage.py cleanup_workflows --days=30 --status rejected
```

### What Gets Cleaned Up

✅ **Deleted**:
- WorkflowAttachment records (workflow instances)
- ApprovalRequest records (approval history)
- Related workflow data

❌ **NOT Deleted**:
- Your main objects (Opportunities, Leaves, etc.)
- Workflow templates (WorkFlow, Pipeline, Stage)
- WorkflowAction configurations

### Automatic Cleanup (Optional)

**WARNING**: This deletes workflow history immediately when completed. Only enable if you don't need workflow history.

```python
# settings.py

# Auto-delete workflow attachments when they reach final status
WORKFLOW_AUTO_CLEANUP_COMPLETED = True  # Default: False
```

### Scheduled Cleanup (Recommended)

**Option 1: Cron Job**

```bash
# Edit crontab
crontab -e

# Add this line (runs daily at 2 AM, keeps 30 days of history)
0 2 * * * cd /path/to/project && python manage.py cleanup_workflows --days=30
```

**Option 2: Django Celery Beat**

```python
# celery.py or tasks.py

from celery import shared_task
from django.core.management import call_command

@shared_task
def cleanup_old_workflows():
    """Clean up workflows older than 30 days."""
    call_command('cleanup_workflows', days=30)

# In celerybeat schedule:
from celery.schedules import crontab

app.conf.beat_schedule = {
    'cleanup-old-workflows': {
        'task': 'yourapp.tasks.cleanup_old_workflows',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    },
}
```

### Programmatic Usage

```python
from django_workflow_engine.cleanup import (
    cleanup_completed_workflow_attachments,
    get_cleanup_statistics,
)

# Get statistics
stats = get_cleanup_statistics()
print(f"Completed workflows: {stats['completed_attachments']}")

# Cleanup with dry run
result = cleanup_completed_workflow_attachments(
    older_than_days=30,
    dry_run=True
)
print(f"Would delete: {result['attachments_deleted']}")

# Actual cleanup
result = cleanup_completed_workflow_attachments(older_than_days=30)
print(f"Deleted: {result['attachments_deleted']} attachments")
```

### Cleanup Best Practices

1. **Choose the Right Retention Period**:
   - 7 days: Aggressive cleanup, minimal history
   - 30 days: Recommended for most cases
   - 90 days: Keep for quarterly reports
   - 365 days: Keep for annual audits

2. **Always Test First**: Run with `--dry-run` before actual cleanup

3. **Back Up Before Large Cleanups**: Backup database before deleting thousands of records

4. **Monitor Database Size**: Check disk space savings after cleanup

## Dependencies

- Django >= 4.0
- django-approval-workflow >= 0.8.0

## License

MIT License

## Contributing

Please read our contributing guidelines and submit pull requests to our GitHub repository.

## Support

For questions and support, please open an issue on our GitHub repository.