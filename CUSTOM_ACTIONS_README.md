# Django Workflow Engine - Custom Actions Guide

This guide explains how to create and use custom actions in the Django Workflow Engine. Actions are functions that execute automatically when specific workflow events occur.

## 📋 Table of Contents

- [Overview](#overview)
- [Action Types](#action-types)
- [Action Execution Order](#action-execution-order)
- [Creating Custom Actions](#creating-custom-actions)
- [Registering Actions](#registering-actions)
- [Action Context Data](#action-context-data)
- [Best Practices](#best-practices)
- [Examples](#examples)
- [Avoiding Conflicts](#avoiding-conflicts)

## 🔄 Overview

The Django Workflow Engine triggers actions at key workflow events. Actions can perform various tasks like sending emails, updating external systems, logging, creating records, etc.

### Action Hierarchy

Actions are resolved in this priority order:
1. **Stage-level actions** (highest priority)
2. **Pipeline-level actions**
3. **Workflow-level actions**
4. **Default actions** (lowest priority)

## 🎯 Action Types

The system supports these action types:

| Action Type | When Triggered | Description |
|-------------|----------------|-------------|
| `ON_WORKFLOW_START` | When workflow is attached and started | Initial workflow setup |
| `AFTER_APPROVE` | After final approval of a stage | When stage is fully approved |
| `AFTER_MOVE_STAGE` | After moving to next stage | When transitioning between stages |
| `AFTER_MOVE_PIPELINE` | After moving to next pipeline | When transitioning between pipelines |
| `AFTER_REJECT` | After approval rejection | When approval is rejected |
| `AFTER_RESUBMISSION` | After resubmission request | When sent back for corrections |
| `AFTER_DELEGATE` | After approval delegation | When approval is delegated |
| `ON_WORKFLOW_COMPLETE` | When workflow finishes | Final workflow completion |

## ⚡ Action Execution Order

**Critical**: Actions are executed in a specific order to prevent conflicts:

### Approval Flow Sequence
```
1. AFTER_APPROVE          ← Approval completed
2. AFTER_MOVE_PIPELINE    ← Only if moving to different pipeline
3. AFTER_MOVE_STAGE       ← Always when moving to next stage
4. Start next stage approval flow
```

### Why This Order Matters
- **AFTER_APPROVE** happens before any movement, so you can access current stage data
- **AFTER_MOVE_PIPELINE** happens before stage movement, so you can react to pipeline changes
- **AFTER_MOVE_STAGE** happens after movement, so you can access new stage data

## 🛠️ Creating Custom Actions

### 1. Create Action Function

Create a Python function that accepts `context` and optional `parameters`:

```python
# myapp/workflow_actions.py

def send_custom_email_after_approve(context, parameters=None):
    """
    Send custom email when stage is approved

    Args:
        context (dict): Action context data
        parameters (dict): Action configuration parameters

    Returns:
        Any: Action result (optional)
    """
    attachment = context['attachment']
    approval_instance = context.get('approval_instance')
    user = context.get('user')

    # Get custom parameters
    email_template = parameters.get('email_template', 'default_approval.html')
    recipients = parameters.get('recipients', [])

    # Your custom logic here
    from django.core.mail import send_mail

    subject = f"Stage '{attachment.current_stage.name_en}' Approved"
    message = f"Stage approved by {user.get_full_name()}"

    send_mail(
        subject=subject,
        message=message,
        from_email='noreply@company.com',
        recipient_list=recipients,
        fail_silently=False
    )

    return {"email_sent": True, "recipients": len(recipients)}

def update_external_system_after_move_stage(context, parameters=None):
    """
    Update external system when moving to new stage
    """
    attachment = context['attachment']
    from_stage = context.get('from_stage')
    to_stage = context.get('to_stage')

    api_url = parameters.get('api_url')
    api_key = parameters.get('api_key')

    # Update external system
    import requests

    payload = {
        'object_id': attachment.object_id,
        'workflow_id': attachment.workflow.id,
        'from_stage': from_stage.name_en if from_stage else None,
        'to_stage': to_stage.name_en,
        'timestamp': attachment.updated_at.isoformat()
    }

    response = requests.post(
        api_url,
        json=payload,
        headers={'Authorization': f'Bearer {api_key}'}
    )

    return {"status_code": response.status_code}

def assign_role_based_approval(context, parameters=None):
    """
    Assign approval to role with specific strategy
    """
    from approval_workflow.choices import RoleSelectionStrategy

    # Available role selection strategies:
    # - 'anyone': Any user with the role can approve
    # - 'consensus': All users with the role must approve
    # - 'round_robin': Rotate approval among role users

    attachment = context['attachment']
    to_stage = context.get('to_stage')

    if to_stage:
        # Example stage configuration for role-based approval
        stage_config = {
            'approvals': [{
                'approval_type': 'ROLE',
                'user_role': 2,  # Role ID
                'role_selection_strategy': RoleSelectionStrategy.ANYONE,  # or 'anyone'
                'required_form': 1
            }]
        }

        # Update stage configuration if needed
        to_stage.stage_info = stage_config
        to_stage.save()

    return {"role_assignment": "updated"}

def create_audit_log(context, parameters=None):
    """
    Create audit log entry for workflow events
    """
    attachment = context['attachment']
    action_type = context['action_type']
    user = context.get('user')

    # Create audit record
    from myapp.models import WorkflowAuditLog

    audit_log = WorkflowAuditLog.objects.create(
        object_id=attachment.object_id,
        content_type=attachment.content_type,
        workflow=attachment.workflow,
        action_type=action_type,
        stage=attachment.current_stage,
        pipeline=attachment.current_pipeline,
        user=user,
        metadata=context,
        parameters=parameters
    )

    return {"audit_id": audit_log.id}
```

### 2. Register Action in Database

```python
# In Django admin, shell, or management command

from django_workflow_engine.models import WorkflowAction
from django_workflow_engine.choices import ActionType

# Stage-level action (highest priority)
WorkflowAction.objects.create(
    stage_id=1,  # Specific stage
    action_type=ActionType.AFTER_APPROVE,
    function_path='myapp.workflow_actions.send_custom_email_after_approve',
    parameters={
        'email_template': 'approval_notification.html',
        'recipients': ['manager@company.com', 'team@company.com']
    },
    order=1,
    is_active=True
)

# Pipeline-level action
WorkflowAction.objects.create(
    pipeline_id=1,  # Specific pipeline
    action_type=ActionType.AFTER_MOVE_STAGE,
    function_path='myapp.workflow_actions.update_external_system_after_move_stage',
    parameters={
        'api_url': 'https://api.external-system.com/workflow-updates',
        'api_key': 'your-api-key'
    },
    order=1,
    is_active=True
)

# Workflow-level action (lower priority)
WorkflowAction.objects.create(
    workflow_id=1,  # Specific workflow
    action_type=ActionType.ON_WORKFLOW_START,
    function_path='myapp.workflow_actions.create_audit_log',
    parameters={
        'log_level': 'INFO'
    },
    order=1,
    is_active=True
)
```

### 3. Action Configuration via Django Admin

The WorkflowAction model is available in Django Admin:

1. Go to **Django Admin → Workflow Actions**
2. Click **Add Workflow Action**
3. Fill in:
   - **Stage/Pipeline/Workflow**: Choose level (Stage = highest priority)
   - **Action Type**: Select when to trigger
   - **Function Path**: `myapp.workflow_actions.your_function_name`
   - **Parameters**: JSON object with configuration
   - **Order**: Execution order (lower numbers first)
   - **Is Active**: Enable/disable action

## 📊 Action Context Data

Each action receives a `context` dictionary with relevant data:

### Common Context Data
```python
context = {
    'attachment': WorkflowAttachment,  # Always present
    'action_type': str,                # Always present
    'user': User,                      # User who triggered action
    'metadata': dict,                  # Workflow metadata
}
```

### Action-Specific Context Data

#### ON_WORKFLOW_START
```python
context.update({
    'initial_stage': Stage,  # First stage of workflow
})
```

#### AFTER_APPROVE
```python
context.update({
    'approval_instance': ApprovalInstance,  # The approval that completed
})
```

#### AFTER_MOVE_STAGE
```python
context.update({
    'from_stage': Stage,     # Previous stage
    'to_stage': Stage,       # New stage
})
```

#### AFTER_MOVE_PIPELINE
```python
context.update({
    'from_pipeline': Pipeline,  # Previous pipeline
    'to_pipeline': Pipeline,    # New pipeline
})
```

#### AFTER_REJECT
```python
context.update({
    'approval_instance': ApprovalInstance,  # The rejection
    'reason': str,                          # Rejection reason
    'stage': Stage,                         # Stage where rejected
})
```

#### AFTER_RESUBMISSION
```python
context.update({
    'approval_instance': ApprovalInstance,  # The resubmission request
    'target_stage': Stage,                  # Stage to return to
    'reason': str,                          # Resubmission reason
})
```

## 💡 Best Practices

### 1. Function Design
```python
def my_action(context, parameters=None):
    """
    Always include docstring explaining:
    - What the action does
    - Expected parameters
    - Return value
    """
    # Always check for required context
    if 'attachment' not in context:
        raise ValueError("Attachment required in context")

    # Provide parameter defaults
    parameters = parameters or {}

    # Handle errors gracefully
    try:
        # Your action logic
        result = do_something()
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Action failed: {e}")
        return {"success": False, "error": str(e)}
```

### 2. Error Handling
- Actions should handle errors gracefully
- Return meaningful error information
- Use logging for debugging
- Don't let action failures break workflow progression

### 3. Performance
- Keep actions fast (< 5 seconds)
- Use async tasks for heavy operations
- Cache expensive lookups
- Avoid blocking operations

### 4. Testing
```python
def test_my_custom_action():
    """Test your custom actions"""
    from myapp.workflow_actions import send_custom_email_after_approve

    context = {
        'attachment': attachment_instance,
        'user': user_instance,
        'action_type': 'after_approve'
    }

    parameters = {
        'email_template': 'test_template.html',
        'recipients': ['test@example.com']
    }

    result = send_custom_email_after_approve(context, parameters)

    assert result['email_sent'] is True
    assert result['recipients'] == 1
```

## 🚀 Examples

### Example 1: Send Slack Notification
```python
def send_slack_notification(context, parameters=None):
    """Send Slack notification on workflow events"""
    import requests

    attachment = context['attachment']
    action_type = context['action_type']
    user = context.get('user')

    webhook_url = parameters.get('webhook_url')
    channel = parameters.get('channel', '#general')

    # Build message based on action type
    if action_type == 'after_approve':
        message = f"✅ {user.get_full_name()} approved stage '{attachment.current_stage.name_en}'"
    elif action_type == 'after_move_stage':
        to_stage = context.get('to_stage')
        message = f"➡️ Workflow moved to stage '{to_stage.name_en}'"
    elif action_type == 'on_workflow_complete':
        message = f"🎉 Workflow completed for {attachment.content_type.model}"
    else:
        message = f"📋 Workflow event: {action_type}"

    payload = {
        'channel': channel,
        'text': message,
        'username': 'Workflow Bot',
        'icon_emoji': ':robot_face:'
    }

    response = requests.post(webhook_url, json=payload)
    return {"status": response.status_code}
```

### Example 2: Update Object Status
```python
def update_object_status(context, parameters=None):
    """Update object status based on workflow stage"""
    attachment = context['attachment']
    to_stage = context.get('to_stage')

    # Get status mapping from parameters
    status_mapping = parameters.get('status_mapping', {})

    if to_stage and to_stage.name_en in status_mapping:
        new_status = status_mapping[to_stage.name_en]

        # Update the object
        obj = attachment.target
        obj.status = new_status
        obj.save(update_fields=['status'])

        return {"status_updated": new_status}

    return {"status_updated": None}

# Register with parameters:
# {
#   "status_mapping": {
#     "Initial Review": "under_review",
#     "Manager Approval": "pending_approval",
#     "Final Approval": "approved"
#   }
# }
```

### Example 3: Create Task Assignment
```python
def create_task_assignment(context, parameters=None):
    """Create task assignment when stage changes"""
    attachment = context['attachment']
    to_stage = context.get('to_stage')
    user = context.get('user')

    if not to_stage:
        return {"task_created": False}

    # Get assignee from stage configuration or parameters
    assignee_mapping = parameters.get('assignee_mapping', {})
    assignee_email = assignee_mapping.get(to_stage.name_en)

    if assignee_email:
        from django.contrib.auth import get_user_model
        from myapp.models import Task

        User = get_user_model()
        try:
            assignee = User.objects.get(email=assignee_email)

            task = Task.objects.create(
                title=f"Review {attachment.content_type.model}: {attachment.object_id}",
                description=f"Please review workflow at stage '{to_stage.name_en}'",
                assignee=assignee,
                workflow_attachment=attachment,
                due_date=timezone.now() + timedelta(days=3)
            )

            return {"task_created": True, "task_id": task.id}

        except User.DoesNotExist:
            return {"task_created": False, "error": f"User {assignee_email} not found"}

    return {"task_created": False}
```

## ⚠️ Avoiding Conflicts

### Understanding Action Execution Order

The system is designed to prevent conflicts by executing actions in a specific order:

```python
# When an approval is completed:

# 1. AFTER_APPROVE actions execute
#    - Access current stage data
#    - Perform approval-specific logic
#    - Send approval notifications

# 2. Stage/Pipeline movement happens
#    - Attachment moves to next stage
#    - Pipeline may change

# 3. AFTER_MOVE_PIPELINE actions execute (if pipeline changed)
#    - Access both old and new pipeline data
#    - Perform pipeline transition logic

# 4. AFTER_MOVE_STAGE actions execute
#    - Access both old and new stage data
#    - Perform stage transition logic

# 5. Next stage approval flow starts
```

### Conflict Prevention Guidelines

#### ✅ DO
- Use **AFTER_APPROVE** for approval-specific logic (emails, logging)
- Use **AFTER_MOVE_STAGE** for stage transition logic (status updates, task creation)
- Use **AFTER_MOVE_PIPELINE** for pipeline transition logic (role changes, permissions)
- Keep actions idempotent (safe to run multiple times)
- Use unique identifiers to prevent duplicate actions

#### ❌ DON'T
- Don't modify workflow state in action functions
- Don't trigger additional workflow movements in actions
- Don't assume actions run synchronously
- Don't create circular dependencies between actions

### Example: Proper Action Separation
```python
# ✅ GOOD: Approval-specific action
def log_approval(context, parameters=None):
    """Log approval details - runs during AFTER_APPROVE"""
    approval_instance = context.get('approval_instance')
    # Log approval details while still in current stage

# ✅ GOOD: Stage transition action
def update_status_on_stage_move(context, parameters=None):
    """Update object status - runs during AFTER_MOVE_STAGE"""
    to_stage = context.get('to_stage')
    # Update status based on new stage

# ❌ BAD: Mixing concerns
def do_everything(context, parameters=None):
    """Don't mix approval and movement logic in one action"""
    # This creates confusion about when things happen
```

### Preventing Action Conflicts

The workflow engine is specifically designed to prevent conflicts through controlled execution order:

```python
# Actual execution sequence when approval completes:

def on_final_approve(self, approval_instance):
    """This is the exact sequence from WorkflowApprovalHandler"""

    # 1. AFTER_APPROVE actions execute FIRST
    trigger_workflow_event(
        attachment,
        ActionType.AFTER_APPROVE,
        approval_instance=approval_instance,
        user=user,
    )

    # 2. THEN move to next stage
    attachment = move_to_next_stage(obj)

def move_to_next_stage(obj, user=None):
    """This is the exact sequence from services.py"""

    # Update attachment to next stage
    attachment.current_stage = next_stage
    attachment.current_pipeline = next_pipeline
    attachment.save()

    # 3. AFTER_MOVE_PIPELINE actions (if pipeline changed)
    if pipeline_changed:
        trigger_workflow_event(
            attachment,
            ActionType.AFTER_MOVE_PIPELINE,
            from_pipeline=old_pipeline,
            to_pipeline=next_pipeline,
            user=user,
        )

    # 4. AFTER_MOVE_STAGE actions (always)
    trigger_workflow_event(
        attachment,
        ActionType.AFTER_MOVE_STAGE,
        from_stage=old_stage,
        to_stage=next_stage,
        user=user,
    )

    # 5. Start next stage approval flow
    start_flow(obj, next_stage_steps)
```

### Why This Prevents Conflicts

1. **AFTER_APPROVE** sees current stage data before movement
2. **AFTER_MOVE_PIPELINE** sees both old and new pipeline data
3. **AFTER_MOVE_STAGE** sees both old and new stage data
4. Each action type has distinct context and purpose

### Action Timing Guarantees

```python
# ✅ GUARANTEED: These data are available in each action type

# AFTER_APPROVE context:
{
    'attachment': attachment,           # Still pointing to current stage
    'approval_instance': instance,      # The approval that just completed
    'user': approving_user,
    # Current stage data accessible via attachment.current_stage
}

# AFTER_MOVE_PIPELINE context:
{
    'attachment': attachment,           # Now pointing to new stage/pipeline
    'from_pipeline': old_pipeline,     # Previous pipeline
    'to_pipeline': new_pipeline,       # New pipeline
    'user': user,
}

# AFTER_MOVE_STAGE context:
{
    'attachment': attachment,           # Now pointing to new stage
    'from_stage': old_stage,           # Previous stage
    'to_stage': new_stage,             # New stage
    'user': user,
}
```

### Debugging Action Flow

Enable detailed logging to debug action execution:

```python
# settings.py
LOGGING = {
    'loggers': {
        'django_workflow_engine.services': {
            'level': 'DEBUG',
            'handlers': ['console'],
        },
        'django_workflow_engine.handlers': {
            'level': 'DEBUG',
            'handlers': ['console'],
        },
    },
}
```

### Action Flow Monitoring

Create a monitoring action to track execution:

```python
def monitor_action_flow(context, parameters=None):
    """Monitor action execution order"""
    import time

    action_type = context['action_type']
    attachment = context['attachment']

    timestamp = time.time()
    stage_name = attachment.current_stage.name_en if attachment.current_stage else "None"

    # Log with precise timing
    logger.info(
        f"ACTION_FLOW: {action_type} at {timestamp} - Stage: {stage_name}"
    )

    # Store in cache for analysis
    from django.core.cache import cache
    flow_key = f"action_flow_{attachment.id}"
    flow_data = cache.get(flow_key, [])
    flow_data.append({
        'action_type': action_type,
        'timestamp': timestamp,
        'stage': stage_name,
        'pipeline': attachment.current_pipeline.name_en if attachment.current_pipeline else "None"
    })
    cache.set(flow_key, flow_data, 300)  # 5 minutes

    return {"monitored": True, "timestamp": timestamp}
```

### Action Dependencies

If actions must run in specific order, use the `order` field:

```python
# First action
WorkflowAction.objects.create(
    stage_id=1,
    action_type=ActionType.AFTER_APPROVE,
    function_path='myapp.actions.validate_data',
    order=1,  # Runs first
)

# Second action (depends on first)
WorkflowAction.objects.create(
    stage_id=1,
    action_type=ActionType.AFTER_APPROVE,
    function_path='myapp.actions.send_notification',
    order=2,  # Runs second
)
```

## 🎭 Role Selection Strategies

When configuring role-based approvals, you can specify how users within a role are selected for approval:

### Available Strategies

```python
from approval_workflow.choices import RoleSelectionStrategy

# Strategy options:
RoleSelectionStrategy.ANYONE       # 'anyone' - Any user with the role can approve
RoleSelectionStrategy.CONSENSUS    # 'consensus' - All users with the role must approve
RoleSelectionStrategy.ROUND_ROBIN  # 'round_robin' - Rotate approval among role users
```

### Usage in Stage Configuration

```python
# Stage configuration example
stage_info = {
    'approvals': [
        {
            'approval_type': 'ROLE',
            'user_role': 2,  # Manager role ID
            'role_selection_strategy': 'anyone',  # Any manager can approve
            'required_form': 1
        },
        {
            'approval_type': 'ROLE',
            'user_role': 3,  # Executive role ID
            'role_selection_strategy': 'consensus',  # ALL executives must approve
            'required_form': 2
        },
        {
            'approval_type': 'ROLE',
            'user_role': 4,  # Reviewer role ID
            'role_selection_strategy': 'round_robin',  # Rotate among reviewers
            'required_form': 3
        }
    ]
}
```

### Strategy Behavior

| Strategy | Behavior | Use Case |
|----------|----------|----------|
| `anyone` | First available user with role approves | Fast approval, flexible |
| `consensus` | ALL users with role must approve | Critical decisions, full agreement |
| `round_robin` | Distributes load among role users | Fair workload distribution |

## 🔧 Advanced Features

### Conditional Actions

```python
def conditional_action(context, parameters=None):
    """Execute action only under certain conditions"""
    attachment = context['attachment']

    # Check conditions from parameters
    conditions = parameters.get('conditions', {})

    # Example: Only run for certain object types
    if conditions.get('model_type'):
        if attachment.content_type.model != conditions['model_type']:
            return {"skipped": True, "reason": "Model type mismatch"}

    # Example: Only run for certain amounts
    if conditions.get('min_amount'):
        obj = attachment.target
        if hasattr(obj, 'amount') and obj.amount < conditions['min_amount']:
            return {"skipped": True, "reason": "Amount too low"}

    # Execute action logic
    return perform_action()
```

### Async Actions

```python
from celery import shared_task

@shared_task
def heavy_processing_task(attachment_id, parameters):
    """Heavy processing as background task"""
    attachment = WorkflowAttachment.objects.get(id=attachment_id)
    # Perform heavy processing
    return {"processed": True}

def trigger_heavy_processing(context, parameters=None):
    """Trigger async processing"""
    attachment = context['attachment']

    # Trigger background task
    task = heavy_processing_task.delay(attachment.id, parameters)

    return {"task_id": task.id, "async": True}
```

### Dynamic Parameters

```python
def dynamic_parameters_action(context, parameters=None):
    """Use dynamic parameters based on context"""
    attachment = context['attachment']

    # Get base parameters
    base_params = parameters or {}

    # Override with object-specific settings
    obj = attachment.target
    if hasattr(obj, 'workflow_settings'):
        base_params.update(obj.workflow_settings)

    # Override with user-specific settings
    user = context.get('user')
    if user and hasattr(user, 'workflow_preferences'):
        base_params.update(user.workflow_preferences)

    # Use merged parameters
    return process_with_params(base_params)
```

---

## 📚 Summary

This guide covers everything you need to create powerful custom actions for the Django Workflow Engine:

1. **Understand action types** and when they trigger
2. **Follow the execution order** to avoid conflicts
3. **Create well-structured functions** with proper error handling
4. **Register actions** at the appropriate level (stage/pipeline/workflow)
5. **Use context data** effectively for your business logic
6. **Test your actions** thoroughly
7. **Follow best practices** for maintainable code

The action system is designed to be flexible and powerful while preventing common pitfalls through its structured execution order.