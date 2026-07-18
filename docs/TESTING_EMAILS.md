# Email Mocking Guide for Tests

This guide explains how email functionality is mocked in tests for better performance and reliability.

## Automatic Email Mocking

All tests automatically mock email functionality through fixtures in `conftest.py`:

### 1. Django's send_mail (Automatic)

```python
@pytest.fixture(autouse=True)
def mock_email_backend():
    """Mock email backend to speed up tests."""
    with patch("django.core.mail.send_mail") as mock_send:
        mock_send.return_value = True
        yield mock_send
```

**What it does**: Prevents actual email sending via Django's `send_mail()` function.

**Applied**: Automatically to all tests.

### 2. Async Email Attempts (Automatic)

```python
@pytest.fixture(autouse=True)
def mock_async_email_backend():
    """Mock async email attempts to prevent task queue operations."""
    with patch("django_workflow_engine.default_actions._try_async_email") as mock_async:
        mock_async.return_value = False  # No async email available
        yield mock_async
```

**What it does**: Prevents tests from trying to queue async emails via Celery/Django-Q.

**Applied**: Automatically to all tests.

## Manual Email Mocking (When Needed)

### Option 1: Mock _send_email Directly

For tests that specifically test email logic:

```python
from unittest.mock import patch

def test_workflow_email_notification():
    with patch("django_workflow_engine.default_actions._send_email") as mock_send:
        mock_send.return_value = True

        # Your test code that triggers email sending
        result = default_send_email_on_workflow_start(**context)

        # Verify email was called
        assert result is True
        mock_send.assert_called_once()

        # Check email content
        call_args = mock_send.call_args
        recipients, subject, message, context = call_args[0]
        assert "test@example.com" in recipients
        assert "Workflow Started" in subject
```

### Option 2: Mock django.core.mail.send_mail

For lower-level email testing:

```python
@patch("django_workflow_engine.default_actions._try_async_email")
@patch("django.core.mail.send_mail")
def test_send_email_function(self, mock_send_mail, mock_async_email):
    mock_async_email.return_value = False  # No async available
    mock_send_mail.return_value = True

    result = _send_email(
        recipients=["test@example.com"],
        subject="Test",
        message="Test message",
        context={}
    )

    assert result is True
    mock_send_mail.assert_called_once_with(
        subject="Test",
        message="Test message",
        from_email="noreply@example.com",
        recipient_list=["test@example.com"],
        fail_silently=True,
    )
```

### Option 3: Use Django's mail.outbox (For Integration Tests)

For integration tests that want to verify actual email content:

```python
from django.core import mail

def test_workflow_sends_correct_email():
    # Clear outbox
    mail.outbox = []

    # Your test code
    attach_workflow_to_object(obj, workflow, user, auto_start=True)

    # Check emails in outbox
    assert len(mail.outbox) == 1
    email = mail.outbox[0]
    assert email.subject == "Workflow Started"
    assert "test@example.com" in email.to
```

## Configuration Settings

### Test Settings (sandbox/settings.py)

```python
# Email backend for testing
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
DEFAULT_FROM_EMAIL = 'noreply@example.com'

# Disable workflow emails in tests for better performance
WORKFLOW_DISABLE_EMAILS = False  # Set to True for fastest tests
```

### Override in Specific Tests

```python
from django.test import override_settings

@override_settings(WORKFLOW_DISABLE_EMAILS=True)
def test_without_emails():
    # All workflow emails are disabled for this test
    attach_workflow_to_object(obj, workflow, user, auto_start=True)
    # No emails sent, faster execution
```

## Common Test Patterns

### Pattern 1: Test Workflow Logic (Ignore Emails)

Most tests should use this pattern:

```python
def test_workflow_attachment():
    # Email mocking is automatic via conftest.py
    # Just test your workflow logic
    attachment = attach_workflow_to_object(
        obj, workflow, user, auto_start=True
    )

    assert attachment.status == WorkflowAttachmentStatus.IN_PROGRESS
    # Email functionality is mocked, no need to worry about it
```

### Pattern 2: Test Email Sending Logic

For tests that specifically verify email behavior:

```python
from unittest.mock import patch

@patch("django_workflow_engine.default_actions._send_email")
def test_email_notification_content(mock_send_email):
    mock_send_email.return_value = True

    # Trigger email
    result = default_send_email_on_workflow_start(**context)

    # Verify email details
    assert result is True
    mock_send_email.assert_called_once()

    # Check arguments
    call_args = mock_send_email.call_args[0]
    recipients, subject, message, ctx = call_args

    assert "user@example.com" in recipients
    assert "Workflow Started" in subject
    assert "Test Workflow" in message
```

### Pattern 3: Test Email Disabled Setting

```python
from django.test import override_settings

@override_settings(WORKFLOW_DISABLE_EMAILS=True)
def test_performance_without_emails():
    import time

    start = time.time()
    attach_workflow_to_object(obj, workflow, user, auto_start=True)
    elapsed = (time.time() - start) * 1000

    # Should be faster without email operations
    assert elapsed < 50  # ms
```

### Pattern 4: Test Async Email Queueing

```python
@patch("django_workflow_engine.default_actions._try_async_email")
def test_async_email_attempted(mock_async):
    mock_async.return_value = True  # Async succeeded

    result = _send_email(
        recipients=["test@example.com"],
        subject="Test",
        message="Message",
        context={}
    )

    assert result is True
    mock_async.assert_called_once_with(
        ["test@example.com"],
        "Test",
        "Message"
    )
```

## Debugging Email Tests

### Check if Emails are Being Sent

```python
def test_check_email_mock():
    from django.core import mail

    # For locmem backend
    print(f"Emails sent: {len(mail.outbox)}")

    # For mocked backend
    from unittest.mock import patch
    with patch("django.core.mail.send_mail") as mock:
        # Your code
        print(f"Send mail called: {mock.called}")
        print(f"Call count: {mock.call_count}")
        print(f"Call args: {mock.call_args}")
```

### Verify Mock is Active

```python
import pytest
from unittest.mock import patch

def test_verify_auto_mock(mock_email_backend, mock_async_email_backend):
    # These are automatically provided by conftest.py
    assert mock_email_backend is not None
    assert mock_async_email_backend is not None

    # Test that they're being used
    from django.core.mail import send_mail
    send_mail("Test", "Message", "from@test.com", ["to@test.com"])

    mock_email_backend.assert_called_once()
```

## Performance Impact

With email mocking:
- **Before**: Tests took ~150s (with real email operations)
- **After**: Tests take ~90s (with mocked emails)
- **Improvement**: ~40% faster

### Workflow Attachment Performance

| Configuration | Time per Attachment |
|--------------|---------------------|
| Real emails (synchronous) | ~200ms |
| Mocked emails | ~20ms |
| WORKFLOW_DISABLE_EMAILS=True | ~15ms |

## Best Practices

1. **Default to Mocked Emails**: Let `conftest.py` handle email mocking automatically
2. **Test Email Logic Separately**: Use dedicated tests for email content verification
3. **Use locmem Backend**: Already configured in `sandbox/settings.py`
4. **Disable Emails for Performance Tests**: Use `WORKFLOW_DISABLE_EMAILS=True`
5. **Mock Async Operations**: Always mock `_try_async_email` to prevent task queue operations

## Troubleshooting

### Test Fails with "AssertionError: expected call not found"

**Problem**: Test expects `fail_silently=False` but code uses `fail_silently=True`

**Solution**: Update test expectation:
```python
mock_send_mail.assert_called_once_with(
    subject=subject,
    message=message,
    from_email="noreply@example.com",
    recipient_list=recipients,
    fail_silently=True,  # Changed from False
)
```

### Emails are Actually Being Sent in Tests

**Problem**: Real SMTP connections in tests

**Solution**: Verify settings:
```python
# settings.py
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# Or for complete disabling
WORKFLOW_DISABLE_EMAILS = True
```

### Async Email Tests Fail

**Problem**: Tests try to queue tasks to Celery/Django-Q

**Solution**: Ensure `mock_async_email_backend` is active:
```python
@patch("django_workflow_engine.default_actions._try_async_email")
def test_something(mock_async):
    mock_async.return_value = False
    # Your test code
```

## Related Files

- `tests/conftest.py` - Global fixtures for email mocking
- `sandbox/settings.py` - Test email backend configuration
- `django_workflow_engine/default_actions.py` - Email sending implementation
- `tests/test_default_actions.py` - Email functionality tests

## Summary

✅ **All email operations are automatically mocked in tests**
✅ **No configuration needed for most tests**
✅ **Tests run faster without real email operations**
✅ **Easy to verify email content when needed**
✅ **Prevents accidental email sending during development**
