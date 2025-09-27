# Django Dynamic Workflows - Translations

This package supports both Arabic and English translations for all user-facing text.

## Supported Languages

- **English (en)**: Default language
- **Arabic (ar)**: Full translation support with RTL text handling

## Usage

### Django Settings

Add the following to your Django settings:

```python
# Internationalization
LANGUAGE_CODE = 'en'  # or 'ar' for Arabic

LANGUAGES = [
    ('en', 'English'),
    ('ar', 'العربية'),
]

USE_I18N = True
USE_L10N = True

# Add locale paths
LOCALE_PATHS = [
    os.path.join(BASE_DIR, 'locale'),
    # Include django-dynamic-workflows locale
    os.path.join(os.path.dirname(__file__), '..', 'venv', 'lib', 'python3.x', 'site-packages', 'django_workflow_engine', 'locale'),
]
```

### In Views and Templates

```python
from django.utils.translation import gettext_lazy as _

# In views
message = _("Workflow created successfully")

# In templates
{% load i18n %}
{% trans "Workflow" %}
```

### API Responses

The workflow engine automatically translates:
- Model verbose names and field labels
- Validation error messages
- API help text
- Email template subjects and content

### Switching Languages

```python
from django.utils.translation import activate

# Switch to Arabic
activate('ar')

# Switch to English
activate('en')
```

## Translation Coverage

### Models
- ✅ WorkFlow - سير العمل
- ✅ Pipeline - خط الأنابيب
- ✅ Stage - المرحلة
- ✅ WorkflowAttachment - مرفق سير العمل
- ✅ WorkflowAction - إجراء سير العمل
- ✅ WorkflowConfiguration - إعداد سير العمل

### Status Values
- ✅ Active/Inactive - نشط/غير نشط
- ✅ In Progress - قيد التنفيذ
- ✅ Completed - مكتمل
- ✅ Rejected - مرفوض
- ✅ Cancelled - ملغي

### API Messages
- ✅ Validation errors
- ✅ Help text
- ✅ Field labels
- ✅ Success/error messages

### Email Templates
- ✅ Subject lines
- ✅ Email content
- ✅ Action buttons

## Development

### Adding New Translations

1. Add new translatable strings using `_()`:
```python
from django.utils.translation import gettext_lazy as _
message = _("New message to translate")
```

2. Update translation files:
```bash
python manage.py makemessages -l ar
python manage.py makemessages -l en
```

3. Edit the `.po` files in `locale/[lang]/LC_MESSAGES/django.po`

4. Compile messages:
```bash
python manage.py compilemessages
# or use the package-specific command
python manage.py compilemessages --locale ar --locale en
```

### Translation File Structure
```
django_workflow_engine/
├── locale/
│   ├── ar/
│   │   └── LC_MESSAGES/
│   │       ├── django.po  # Arabic translations
│   │       └── django.mo  # Compiled Arabic
│   └── en/
│       └── LC_MESSAGES/
│           ├── django.po  # English translations
│           └── django.mo  # Compiled English
```

## Features

### RTL Support
When using Arabic language, the workflow engine automatically:
- Displays text in right-to-left direction
- Adjusts field ordering for Arabic context
- Formats dates and numbers appropriately

### Dynamic Language Switching
- API responses adapt to request language headers
- Admin interface switches based on user preferences
- Email notifications sent in user's preferred language

### Validation Messages
All validation errors are translated:
```python
# English
"Workflow is not in progress (current status: completed)"

# Arabic
"سير العمل ليس قيد التنفيذ (الحالة الحالية: مكتمل)"
```