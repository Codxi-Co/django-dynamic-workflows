# Django Dynamic Workflows

A powerful, configurable Django package for implementing dynamic multi-step workflow processes with database-stored actions and approval flows.

## Features

- **Generic Workflow Attachment**: Attach workflows to any Django model without hardcoded relationships
- **Database-Stored Actions**: Configure actions dynamically in the database with inheritance system
- **Action Inheritance**: Stage → Pipeline → Workflow → Default action hierarchy
- **Approval Flow Integration**: Built on top of django-approval-workflow package
- **Complete Approval Actions**: Full support for approve, reject, delegate, and resubmission workflows
- **Resubmission & Delegation Logic**: Proper stage transitions and user assignments with workflow event triggers
- **Configurable Triggers**: Actions triggered on workflow events (approve, reject, delegate, etc.)
- **Default Email Actions**: Smart email notifications to creators and approvers
- **Dynamic Function Execution**: Execute Python functions by database-stored paths
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

### Department Model Configuration

The `DEPARTMENT_MODEL` setting allows you to map the department field in workflows to any model in your project:

```python
# Map to your custom Department model
'DEPARTMENT_MODEL': 'myapp.Department'

# Map to Django's built-in Group model
'DEPARTMENT_MODEL': 'auth.Group'

# Map to any other model with a name field
'DEPARTMENT_MODEL': 'companies.Division'
```

This provides maximum flexibility for organizing workflows by departments, divisions, teams, or any organizational structure.

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

### 📚 Comprehensive Guide

For complete documentation including advanced examples, conflict resolution, and best practices, see: **[CUSTOM_ACTIONS_README.md](CUSTOM_ACTIONS_README.md)**

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

# Get the auto-created stages
finance_pipeline = purchase_workflow.pipelines.get(name_en='Finance Review')
executive_pipeline = purchase_workflow.pipelines.get(name_en='Executive Approval')

# Configure Finance Stage 1: Initial Review
initial_review = finance_pipeline.stages.get(order=1)
stage_config = {
    'stage_info': {
        'color': '#3498db',
        'approvals': [
            {
                'approval_type': 'role',  # Role-based approval (lowercase)
                'user_role': 1,  # Finance Reviewer Role ID
                'role_selection_strategy': 'random',  # Lowercase (also supports 'anyone', 'consensus', 'round_robin', 'supervisor')
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
    'stage_info': {
        'color': '#f39c12',
        'approvals': [
            {
                'approval_type': 'role',  # Lowercase
                'user_role': 2,  # Budget Manager Role ID
                'role_selection_strategy': 'anyone',
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
    'stage_info': {
        'color': '#27ae60',
        'approvals': [
            {
                'approval_type': 'user',  # Specific user approval (lowercase)
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
    'stage_info': {
        'color': '#8e44ad',
        'approvals': [
            {
                'approval_type': 'role',  # Lowercase
                'user_role': 3,  # Executive Role ID
                'role_selection_strategy': 'supervisor'  # Lowercase
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

## Dependencies

- Django >= 4.0
- django-approval-workflow >= 0.8.0

## License

MIT License

## Contributing

Please read our contributing guidelines and submit pull requests to our GitHub repository.

## Support

For questions and support, please open an issue on our GitHub repository.