# Migration Guide: Upgrading to Secure Action Registry

This guide helps you migrate existing Django Dynamic Workflows projects to use the new secure action registry system.

## Table of Contents

1. [Overview](#overview)
2. [Benefits of Migration](#benefits-of-migration)
3. [Migration Strategies](#migration-strategies)
4. [Step-by-Step Migration](#step-by-step-migration)
5. [Common Examples](#common-examples)
6. [Troubleshooting](#troubleshooting)
7. [Best Practices](#best-practices)

---

## Overview

The new secure action registry replaces unsafe dynamic function imports with a whitelist-based system. This guide shows you how to migrate your existing workflow actions to the new system.

**Key Points:**
- ✅ **100% Backward Compatible** - Existing code continues to work
- ✅ **Gradual Migration** - Migrate at your own pace
- ✅ **No Breaking Changes** - No immediate action required
- ⚠️ **Recommended** - Migrate for better security and performance

---

## Benefits of Migration

### Security
- **Before:** Any function path stored in database could execute
- **After:** Only pre-registered actions can execute

### Performance
- **Before:** Dynamic imports on every action execution
- **After:** Direct function lookup (faster)

### Debugging
- **Before:** Generic import errors
- **After:** Clear error messages with action names

### Validation
- **Before:** No signature validation
- **After:** Validated at registration time

---

## Migration Strategies

### Strategy 1: Gradual Migration (Recommended)

Migrate actions incrementally while keeping legacy support.

**Pros:**
- Low risk
- Can test as you go
- No downtime

**Cons:**
- Longer migration period
- Mixed approach temporarily

### Strategy 2: Big Bang Migration

Migrate all actions at once.

**Pros:**
- Consistent codebase
- Cleaner migration

**Cons:**
- Higher risk
- Requires testing everything upfront

### Strategy 3: New Projects Only

Use registry only for new actions, keep legacy for old ones.

**Pros:**
- Minimal changes
- Low risk

**Cons:**
- Two systems to maintain
- Inconsistent approach

---

## Step-by-Step Migration

### Step 1: Create an Actions Module

Create a dedicated module for your workflow actions.

**Directory Structure:**
```
myapp/
├── __init__.py
├── models.py
├── workflow_actions.py      # New file for actions
└── ...
```

**Basic Template:**
```python
# myapp/workflow_actions.py
"""
Workflow action handlers for myapp.

All workflow actions are registered using the secure action registry.
"""

import logging
from django_workflow_engine.action_registry import register_action

logger = logging.getLogger(__name__)


@register_action(name="send_notification", category="notification")
def send_notification(workflow_attachment, action_parameters, **context):
    """
    Send notification when workflow action occurs.

    Args:
        workflow_attachment: The WorkflowAttachment instance
        action_parameters: Dict with notification parameters
        **context: Additional context (user, stage, etc.)

    Returns:
        bool: True if successful
    """
    try:
        # Your notification logic here
        logger.info(f"Notification sent for {workflow_attachment}")
        return True
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
        return False
```

---

### Step 2: Register Existing Actions

Convert your existing action functions to registered actions.

**Before (Legacy):**
```python
# myapp/actions.py
def send_approval_email(workflow_attachment, action_parameters, **context):
    # ... logic ...
    pass
```

**After (Registered):**
```python
# myapp/workflow_actions.py
from django_workflow_engine.action_registry import register_action

@register_action(
    name="send_approval_email",
    category="email",
    description="Send approval email notification"
)
def send_approval_email(workflow_attachment, action_parameters, **context):
    # ... same logic ...
    pass
```

---

### Step 3: Update Database Entries

Update `WorkflowAction` entries to use action names instead of function paths.

**Option A: Django Shell**
```python
# Run in Django shell: python manage.py shell

from django_workflow_engine.models import WorkflowAction

# Map old paths to new action names
MIGRATION_MAP = {
    "myapp.actions.send_email": "send_approval_email",
    "myapp.actions.send_notification": "send_notification",
    "myapp.actions.update_status": "update_object_status",
}

for old_path, new_name in MIGRATION_MAP.items():
    updated = WorkflowAction.objects.filter(
        function_path=old_path
    ).update(
        function_path=new_name
    )
    print(f"Updated {updated} actions: {old_path} → {new_name}")
```

**Option B: Django Management Command**
```python
# Create: myapp/management/commands/migrate_workflow_actions.py

from django.core.management.base import BaseCommand
from django_workflow_engine.models import WorkflowAction

class Command(BaseCommand):
    help = 'Migrate workflow actions to registry'

    def handle(self, *args, **options):
        MIGRATION_MAP = {
            "myapp.actions.send_email": "send_approval_email",
            # Add your mappings here
        }

        for old_path, new_name in MIGRATION_MAP.items():
            count = WorkflowAction.objects.filter(
                function_path=old_path
            ).update(function_path=new_name)

            if count:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ Updated {count} actions: {old_path} → {new_name}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"⚠ No actions found: {old_path}")
                )
```

**Run the command:**
```bash
python manage.py migrate_workflow_actions
```

---

### Step 4: Ensure Actions are Registered

Make sure your actions are loaded before they're needed.

**Option A: App Registry (Recommended)**

Create an `apps.py` configuration:

```python
# myapp/apps.py
from django.apps import AppConfig

class MyAppConfig(AppConfig):
    name = 'myapp'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        # Import workflow actions to register them
        import myapp.workflow_actions
```

Update `myapp/__init__.py`:
```python
# myapp/__init__.py
default_app_config = 'myapp.apps.MyAppConfig'
```

**Option B: Import in Settings**

```python
# settings.py

# Import workflow actions to register them
INSTALLED_APPS = [
    # ... your apps ...
    'myapp',
    # Import actions after apps are loaded
]

# Import workflow actions at startup
try:
    import myapp.workflow_actions
except ImportError:
    pass  # Actions module may not exist yet
```

---

### Step 5: Test Migrated Actions

Verify your actions work correctly.

```python
# In Django shell
from django_workflow_engine.action_registry import registry

# Check registration
print("Registered actions:")
for category, actions in registry.list_actions_by_category().items():
    print(f"  {category}: {', '.join(actions)}")

# Test execution
from django_workflow_engine.models import WorkflowAttachment

attachment = WorkflowAttachment.objects.first()
if attachment:
    # Test your action
    result = registry.execute_action(
        action_name="send_approval_email",
        workflow_attachment=attachment,
        user=None
    )
    print(f"Action result: {result}")
```

---

### Step 6: Monitor Logs

Watch for warnings about legacy imports:

```bash
# In development
tail -f logs/django.log | grep "legacy import"

# Or with Django debug toolbar
# Check logs for:
# "Action 'xyz' not in secure registry. Using legacy dynamic import"
```

---

## Common Examples

### Example 1: Email Actions

**Before:**
```python
# Database: function_path = "myapp.actions.send_approval_email"

# myapp/actions.py
def send_approval_email(workflow_attachment, action_parameters, **context):
    recipients = action_parameters.get('recipients', [])
    # ... send email logic ...
    return True
```

**After:**
```python
# Database: function_path = "send_approval_email"

# myapp/workflow_actions.py
@register_action(name="send_approval_email", category="email")
def send_approval_email(workflow_attachment, action_parameters, **context):
    recipients = action_parameters.get('recipients', [])
    # ... same send email logic ...
    return True
```

---

### Example 2: Notification Actions

**Before:**
```python
# Database: function_path = "myapp.workflow.notify_department"

# myapp/workflow.py
def notify_department(workflow_attachment, action_parameters, **context):
    department = action_parameters.get('department')
    # ... notification logic ...
    return True
```

**After:**
```python
# Database: function_path = "notify_department"

# myapp/workflow_actions.py
@register_action(name="notify_department", category="notification")
def notify_department(workflow_attachment, action_parameters, **context):
    department = action_parameters.get('department')
    # ... same notification logic ...
    return True
```

---

### Example 3: Status Update Actions

**Before:**
```python
# Database: function_path = "myapp.handlers.update_purchase_order_status"

# myapp/handlers.py
def update_purchase_order_status(workflow_attachment, action_parameters, **context):
    obj = workflow_attachment.target
    status = action_parameters.get('status')
    obj.status = status
    obj.save()
    return True
```

**After:**
```python
# Database: function_path = "update_po_status"

# myapp/workflow_actions.py
@register_action(name="update_po_status", category="status_update")
def update_purchase_order_status(workflow_attachment, action_parameters, **context):
    obj = workflow_attachment.target
    status = action_parameters.get('status')
    obj.status = status
    obj.save()
    return True
```

---

### Example 4: Complex Actions with Validation

```python
# myapp/workflow_actions.py
from django.core.exceptions import ValidationError
from django_workflow_engine.action_registry import register_action

@register_action(
    name="approve_purchase_order",
    category="approval",
    description="Approve purchase order and update inventory"
)
def approve_purchase_order(workflow_attachment, action_parameters, **context):
    """
    Approve purchase order and update inventory.

    Action Parameters:
        - update_inventory (bool): Whether to update inventory
        - notify_vendor (bool): Whether to notify vendor
    """
    from myapp.models import PurchaseOrder

    obj = workflow_attachment.target

    # Validate object type
    if not isinstance(obj, PurchaseOrder):
        logger.error(f"Expected PurchaseOrder, got {type(obj)}")
        return False

    # Validate status
    if obj.status != 'pending_approval':
        logger.warning(f"Purchase order {obj.id} is not pending approval")
        return False

    try:
        # Update status
        obj.status = 'approved'
        obj.approved_by = context.get('user')
        obj.approved_at = timezone.now()
        obj.save()

        # Update inventory if requested
        if action_parameters.get('update_inventory'):
            update_inventory_for_order(obj)

        # Notify vendor if requested
        if action_parameters.get('notify_vendor'):
            send_vendor_notification(obj)

        logger.info(f"Purchase order {obj.id} approved successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to approve purchase order {obj.id}: {e}")
        return False
```

---

## Troubleshooting

### Issue 1: "Action not registered" Error

**Symptom:**
```
ActionNotRegisteredError: Action 'send_email' is not registered
```

**Solution:**
1. Verify the action is registered:
```python
from django_workflow_engine.action_registry import registry
print(registry.is_registered("send_email"))  # Should be True
```

2. Check your apps.py imports the actions module
3. Restart your Django server

---

### Issue 2: Legacy Import Warnings

**Symptom:**
```
WARNING: Action 'myapp.actions.send_email' not in secure registry.
Using legacy dynamic import (not recommended)
```

**Solution:**
1. Register the action (see Step 2)
2. Update database entries (see Step 3)
3. Or, suppress warnings (not recommended):
```python
# settings.py
WORKFLOW_LOG_LEGACY_WARNINGS = False
```

---

### Issue 3: Actions Not Loading

**Symptom:**
```python
registry.list_actions()  # Returns empty list
```

**Solution:**
1. Check apps.py configuration:
```python
# myapp/apps.py
def ready(self):
    import myapp.workflow_actions  # Make sure this runs
```

2. Verify no import errors:
```python
python -c "import myapp.workflow_actions"
```

3. Check Django logs for import errors

---

### Issue 4: Database Update Failed

**Symptom:**
```python
WorkflowAction.objects.filter(function_path=old_path).update(function_path=new_path)
# Returns 0 (no rows updated)
```

**Solution:**
1. Check if path exists:
```python
WorkflowAction.objects.filter(function_path=old_path).count()
```

2. List all current paths:
```python
WorkflowAction.objects.values_list('function_path', flat=True).distinct()
```

3. Verify exact path matches (including app name)

---

## Best Practices

### 1. Use Descriptive Action Names

❌ **Bad:**
```python
@register_action(name="action1")
def send_email(...):
    pass
```

✅ **Good:**
```python
@register_action(name="send_approval_email_notification")
def send_approval_email_notification(...):
    pass
```

### 2. Group Actions by Category

```python
@register_action(name="send_email", category="email")
def send_email(...): pass

@register_action(name="send_sms", category="sms")
def send_sms(...): pass

@register_action(name="update_status", category="status_update")
def update_status(...): pass
```

### 3. Add Clear Descriptions

```python
@register_action(
    name="approve_purchase_order",
    category="approval",
    description="Approve PO and update inventory (PO must be in pending status)"
)
def approve_purchase_order(...):
    pass
```

### 4. Validate Inputs

```python
@register_action(name="update_status")
def update_status(workflow_attachment, action_parameters, **context):
    # Validate required parameters
    status = action_parameters.get('status')
    if not status:
        logger.error("Status parameter required")
        return False

    # Validate object type
    if not hasattr(workflow_attachment.target, 'status'):
        logger.error("Target object does not have status field")
        return False

    # ... rest of logic
```

### 5. Use Proper Error Handling

```python
@register_action(name="complex_action")
def complex_action(workflow_attachment, action_parameters, **context):
    try:
        # Your logic here
        return True
    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        return False
    except Exception as e:
        logger.exception(f"Unexpected error in complex_action: {e}")
        return False
```

### 6. Log Key Events

```python
import logging

logger = logging.getLogger(__name__)

@register_action(name="important_action")
def important_action(workflow_attachment, action_parameters, **context):
    logger.info(
        f"Executing important_action for {workflow_attachment.target} "
        f"by user {context.get('user')}"
    )

    try:
        # ... logic ...
        logger.info(f"Successfully completed important_action")
        return True
    except Exception as e:
        logger.error(f"Failed to execute important_action: {e}")
        return False
```

### 7. Document Parameters

```python
@register_action(name="send_notification")
def send_notification(workflow_attachment, action_parameters, **context):
    """
    Send notification to recipients.

    Args:
        workflow_attachment: The WorkflowAttachment instance
        action_parameters: Dict containing:
            - recipients (list): List of email addresses
            - subject (str): Email subject
            - template (str): Email template name
            - context (dict): Template context variables
        **context: Additional context:
            - user: User who triggered the action

    Returns:
        bool: True if notification sent successfully
    """
    # ... implementation
```

---

## Checklist

Use this checklist to track your migration progress:

- [ ] Create workflow_actions.py module
- [ ] Register at least one action
- [ ] Test action registration
- [ ] Update database entries (function paths)
- [ ] Configure apps.py to load actions
- [ ] Test migrated actions in development
- [ ] Monitor logs for legacy warnings
- [ ] Update documentation
- [ ] Train team on new pattern
- [ ] Deploy to staging
- [ ] Test in staging
- [ ] Deploy to production
- [ ] Monitor production logs

---

## Next Steps

After completing the migration:

1. **Remove Legacy Imports** (Optional)
   ```python
   # settings.py
   WORKFLOW_DISABLE_LEGACY_IMPORT = True
   ```

2. **Add Tests**
   ```python
   # tests/test_workflow_actions.py
   from django_workflow_engine.action_registry import registry

   def test_action_registered():
       assert registry.is_registered("send_approval_email")
   ```

3. **Document Custom Actions**
   - Create internal documentation
   - Add examples for your team
   - Document action parameters

---

## Support

For issues or questions:
1. Check the main documentation: `README.md`
2. Review the current behavior in [Developer Guide](DEVELOPER_GUIDE.md)
3. Open an issue on GitHub
4. Check existing actions in your codebase for examples

---

## Summary

✅ **Migration is safe and gradual**
✅ **No breaking changes**
✅ **Backward compatible**
✅ **Recommended for security**

**Estimated Time:** 2-4 hours for a typical project

**Risk Level:** Low (legacy fallback ensures continued operation)
