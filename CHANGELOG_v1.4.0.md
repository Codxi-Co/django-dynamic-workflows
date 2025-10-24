# Changelog v1.4.0 - Email Notifications & Custom Actions System

**Release Date:** October 24, 2024

## 🎉 Major Features

### Email Notification System
- **Automatic Default Actions**: Workflows automatically get email notification actions for all events (approve, reject, delegate, resubmit, stage move)
- **Custom Actions via API**: Define custom actions when creating workflows, pipelines, or stages through REST API
- **Action Inheritance**: Hierarchical action system (Stage → Pipeline → Workflow → Default)
- **Custom Email Integration**: Support for custom email services (SendGrid, Mailgun, AWS SES, etc.)
- **Smart Recipient Resolution**: Automatic resolution of recipient types (creator, current_approver, delegated_to, workflow_starter)
- **Email Deduplication**: Prevents duplicate emails to the same recipient
- **Bulk Email Sending**: Efficient batch processing for multiple recipients

## 📦 New Components

### Core Modules (6 new files)
- `action_executor.py` - Execute workflow actions based on events
- `action_handlers.py` - Default email notification handlers for all action types
- `action_management.py` - Utilities for creating, cloning, and managing actions
- `notifications.py` - Email sending service with context building and deduplication
- `recipient_resolver.py` - Resolve recipient types to actual email addresses
- `WorkflowActionInputSerializer` - Structured serializer for Swagger/OpenAPI documentation

### Email Templates (6 new templates)
- `base.html` - Base template for all workflow emails
- `workflow_approved.html` - Approval notification template
- `workflow_rejected.html` - Rejection notification template
- `workflow_action_required.html` - Stage progression notification template
- `workflow_delegated.html` - Delegation notification template
- `workflow_resubmission_required.html` - Resubmission notification template

## 🔧 API Changes

### Serializer Enhancements
- **WorkFlowSerializer**: Added optional `actions` field for custom action definitions
- **PipelineSerializer**: Added optional `actions` field for pipeline-level custom actions
- **StageSerializer**: Added optional `actions` field for stage-level custom actions

### API Request Example
```python
{
    "name_en": "Purchase Request",
    "status": "active",
    "actions": [
        {
            "action_type": "after_approve",
            "function_path": "myapp.actions.send_custom_email",
            "parameters": {
                "template": "custom_approved",
                "recipients": ["creator", "manager@example.com"]
            },
            "order": 1,
            "is_active": true
        }
    ]
}
```

### Swagger/OpenAPI Documentation
- Full schema definition for action input structure
- Clear field descriptions and examples
- Choice fields with available action types

## ⚙️ Configuration Settings

### New Settings
```python
# Enable/disable automatic default action creation (default: True)
WORKFLOW_AUTO_CREATE_ACTIONS = True

# Globally disable email sending (default: False)
WORKFLOW_DISABLE_EMAILS = False

# Custom email function path (optional)
WORKFLOW_SEND_EMAIL_FUNCTION = 'myapp.utils.send_email'
```

## 🎨 Admin Interface Improvements

### Performance Optimization
- Removed workflow-related filters from admin interfaces for better performance with large datasets
- Reduced database queries when browsing admin lists

### WorkflowAction Admin
- Enhanced scope display (Workflow / Pipeline / Stage)
- Improved queryset optimization with `select_related`
- Clear field groupings and descriptions

## 📝 Default Actions

When `WORKFLOW_AUTO_CREATE_ACTIONS=True`, the following actions are automatically created:

| Action Type | Trigger | Recipients | Purpose |
|-------------|---------|------------|---------|
| AFTER_APPROVE | After stage approval | Creator | Notify creator of approval |
| AFTER_REJECT | After rejection | Creator | Notify creator of rejection |
| AFTER_RESUBMISSION | Resubmission required | Creator, Current Approver | Notify about required changes |
| AFTER_DELEGATE | Approval delegated | Delegated User, Creator | Notify about delegation |
| AFTER_MOVE_STAGE | Stage progression | Creator | Notify about progress |

## 🧪 Testing

### New Test Suite
- **21 email notification tests** covering:
  - Default action creation
  - Custom action creation via serializers
  - Action inheritance at all levels
  - Action cloning with workflows
  - Email execution with mocks
  - Custom email function integration
  - Recipient resolution
  - Email deduplication

### Test Coverage
- **307 total tests** (all passing)
- Comprehensive mocking for email testing
- Integration tests with complete workflow flows

## 📚 Documentation

### README Enhancements
- New comprehensive section: "Email Notifications & Custom Actions"
- Configuration examples and best practices
- Custom email function integration examples (SendGrid, Mailgun)
- Writing custom action handlers guide
- Recipient type documentation
- Testing examples with mocks

### Code Examples
- Complete workflow with custom actions
- Custom email service integration
- Action handler implementation
- External system integration examples

## 🔄 Action Inheritance System

Actions follow a clear hierarchy:

1. **Stage-level** (highest priority) - Execute if defined for specific stage
2. **Pipeline-level** - Execute if no stage actions exist
3. **Workflow-level** - Execute if no stage or pipeline actions exist
4. **Default actions** - Auto-created if no custom actions at any level

## 🎯 Recipient Types

Supported recipient resolution:

| Type | Resolves To |
|------|-------------|
| `"creator"` | `object.created_by.email` |
| `"current_approver"` | Current approval step approver(s) |
| `"delegated_to"` | User receiving delegation |
| `"workflow_starter"` | User who started workflow |
| `"email@example.com"` | Direct email address |
| User object | User's email |
| User ID | User lookup by ID |

## 🔌 Custom Email Function Interface

```python
def send_email(name, email, subject, context, user=None):
    """
    Args:
        name: Email template name
        email: Recipient email
        subject: Email subject
        context: Workflow context dict
        user: Optional user object
    Returns:
        bool: Success status
    """
```

## ⚡ Performance

- Email deduplication prevents redundant sends
- Bulk email processing for efficiency
- Optimized admin queries with select_related
- Smart caching of recipient resolution

## 🛠️ Migration Notes

### For Existing Users
1. **No action required** - All changes are backwards compatible
2. **Optional**: Set `WORKFLOW_AUTO_CREATE_ACTIONS=False` to disable auto-creation
3. **Optional**: Configure custom email function via `WORKFLOW_SEND_EMAIL_FUNCTION`
4. **Automatic**: Existing workflows work without modification

### For New Users
1. Email notifications work out-of-the-box with default actions
2. Customize via API when creating workflows
3. Override at any level (workflow/pipeline/stage)

## 🐛 Bug Fixes

None - this is a feature release

## 📊 Statistics

- **Files Added**: 12 (6 modules, 6 templates)
- **Lines Added**: 3,798
- **Tests Added**: 22
- **Test Success Rate**: 100% (307/307)

## 🔜 What's Next

Future enhancements may include:
- SMS notifications
- Webhook actions
- Slack/Teams integration
- Schedule-based actions
- Conditional action execution

## 🙏 Acknowledgments

Special thanks to all contributors and users providing feedback!

---

**Full Changelog**: https://github.com/Codxi-Co/django-dynamic-workflows/compare/v1.3.1...v1.4.0
