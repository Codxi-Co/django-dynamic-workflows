"""
Translation utilities for django_workflow_engine.

This module provides helpers for logging messages in multiple languages (English/Arabic)
and managing translations throughout the workflow engine.
"""

import logging
from typing import Any, Dict, Optional

from django.utils import translation
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


# ============ Translation Constants ============

# Supported languages
SUPPORTED_LANGUAGES = ["en", "ar"]

# Language names
LANGUAGE_NAMES = {
    "en": _("English"),
    "ar": _("Arabic"),
}

# Default language
DEFAULT_LANGUAGE = "en"


# ============ Bilingual Logging ============


class BilingualLogger:
    """
    Logger that automatically logs in both English and Arabic.

    This ensures important messages are understandable regardless of
    the user's language preference.
    """

    def __init__(self, logger_name: str, always_bilingual: bool = False):
        """
        Initialize bilingual logger.

        Args:
            logger_name: Name of the logger to use
            always_bilingual: If True, always log in both languages.
                             If False, logs based on user language.
        """
        self.logger = logging.getLogger(logger_name)
        self.always_bilingual = always_bilingual

    def _get_log_message(
        self,
        message_en: str,
        message_ar: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> tuple:
        """
        Get log messages in both languages.

        Args:
            message_en: English message
            message_ar: Arabic message (optional, auto-translated if not provided)
            context: Context variables for message formatting

        Returns:
            Tuple of (message_en, message_ar)
        """
        # Format messages with context
        if context:
            try:
                message_en = message_en.format(**context)
                if message_ar:
                    message_ar = message_ar.format(**context)
            except (KeyError, ValueError) as e:
                logger.warning(f"Error formatting log message: {e}")

        # If no Arabic message provided, try to translate
        if not message_ar:
            with translation.override("ar"):
                # Try to get Arabic translation
                # Note: This only works if translation is available in .po files
                message_ar = str(_(message_en))

        return message_en, message_ar

    def info(
        self,
        message_en: str,
        message_ar: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        user_language: Optional[str] = None,
        **kwargs,
    ):
        """
        Log info level message.

        Args:
            message_en: English message
            message_ar: Arabic message (optional)
            context: Context variables for message formatting
            user_language: User's preferred language code
            **kwargs: Additional arguments for logger
        """
        msg_en, msg_ar = self._get_log_message(message_en, message_ar, context)

        if self.always_bilingual or not user_language:
            # Log both languages
            self.logger.info(f"[EN] {msg_en} | [AR] {msg_ar}", **kwargs)
        elif user_language == "ar":
            self.logger.info(f"[AR] {msg_ar}", **kwargs)
        else:
            self.logger.info(f"[EN] {msg_en}", **kwargs)

    def warning(
        self,
        message_en: str,
        message_ar: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        user_language: Optional[str] = None,
        **kwargs,
    ):
        """Log warning level message."""
        msg_en, msg_ar = self._get_log_message(message_en, message_ar, context)

        if self.always_bilingual or not user_language:
            self.logger.warning(f"[EN] {msg_en} | [AR] {msg_ar}", **kwargs)
        elif user_language == "ar":
            self.logger.warning(f"[AR] {msg_ar}", **kwargs)
        else:
            self.logger.warning(f"[EN] {msg_en}", **kwargs)

    def error(
        self,
        message_en: str,
        message_ar: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        user_language: Optional[str] = None,
        **kwargs,
    ):
        """Log error level message."""
        msg_en, msg_ar = self._get_log_message(message_en, message_ar, context)

        if self.always_bilingual or not user_language:
            self.logger.error(f"[EN] {msg_en} | [AR] {msg_ar}", **kwargs)
        elif user_language == "ar":
            self.logger.error(f"[AR] {msg_ar}", **kwargs)
        else:
            self.logger.error(f"[EN] {msg_en}", **kwargs)

    def debug(
        self,
        message_en: str,
        message_ar: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        user_language: Optional[str] = None,
        **kwargs,
    ):
        """Log debug level message."""
        msg_en, msg_ar = self._get_log_message(message_en, message_ar, context)

        if self.always_bilingual or not user_language:
            self.logger.debug(f"[EN] {msg_en} | [AR] {msg_ar}", **kwargs)
        elif user_language == "ar":
            self.logger.debug(f"[AR] {msg_ar}", **kwargs)
        else:
            self.logger.debug(f"[EN] {msg_en}", **kwargs)


# ============ Helper Functions ============


def get_user_language(user) -> str:
    """
    Get user's preferred language.

    Args:
        user: User object

    Returns:
        Language code (e.g., 'en', 'ar')
    """
    if not user:
        return DEFAULT_LANGUAGE

    # Check for language attribute
    if hasattr(user, "language"):
        lang = user.language
        if lang in SUPPORTED_LANGUAGES:
            return lang

    # Check for language preference
    if hasattr(user, "language_preference"):
        lang = user.language_preference
        if lang in SUPPORTED_LANGUAGES:
            return lang

    return DEFAULT_LANGUAGE


def get_bilingual_logger(
    module_name: str, always_bilingual: bool = False
) -> BilingualLogger:
    """
    Get a bilingual logger for a module.

    Args:
        module_name: Name of the module (usually __name__)
        always_bilingual: If True, always log in both languages

    Returns:
        BilingualLogger instance

    Example:
        >>> from django_workflow_engine.translation_utils import get_bilingual_logger
        >>> logger = get_bilingual_logger(__name__)
        >>> logger.info(
        ...     "Workflow started",
        ...     "بدأ سير العمل",
        ...     context={"workflow_id": 123}
        ... )
    """
    return BilingualLogger(module_name, always_bilingual)


# ============ Common Message Templates ============

# Workflow messages
WORKFLOW_MESSAGES = {
    "created": {
        "en": "Workflow created - ID: {workflow_id}, Name: {name}",
        "ar": "تم إنشاء سير العمل - المعرف: {workflow_id}، الاسم: {name}",
    },
    "started": {
        "en": "Workflow started for {obj_label}({obj_pk})",
        "ar": "تم بدء سير العمل لـ {obj_label}({obj_pk})",
    },
    "completed": {
        "en": "Workflow completed for {obj_label}({obj_pk})",
        "ar": "تم إكمال سير العمل لـ {obj_label}({obj_pk})",
    },
    "approved": {
        "en": "Workflow approved for {obj_label}({obj_pk}) by {user}",
        "ar": "تمت الموافقة على سير العمل لـ {obj_label}({obj_pk}) بواسطة {user}",
    },
    "rejected": {
        "en": "Workflow rejected for {obj_label}({obj_pk}) by {user}. Reason: {reason}",
        "ar": "تم رفض سير العمل لـ {obj_label}({obj_pk}) بواسطة {user}. السبب: {reason}",
    },
    "delegated": {
        "en": "Workflow delegated from {from_user} to {to_user} for {obj_label}({obj_pk})",
        "ar": "تم تفويض سير العمل من {from_user} إلى {to_user} لـ {obj_label}({obj_pk})",
    },
    "resubmitted": {
        "en": "Workflow resubmitted for {obj_label}({obj_pk}) to stage {stage}",
        "ar": "تمت إعادة تقديم سير العمل لـ {obj_label}({obj_pk}) إلى المرحلة {stage}",
    },
}

# Error messages
ERROR_MESSAGES_BILINGUAL = {
    "no_workflow": {
        "en": "No workflow attached to {obj_label}({obj_pk})",
        "ar": "لا يوجد سير عمل مرفق بـ {obj_label}({obj_pk})",
    },
    "workflow_not_active": {
        "en": "Workflow is not active (status: {status})",
        "ar": "سير العمل غير نشط (الحالة: {status})",
    },
    "no_permission": {
        "en": "User {user} does not have permission to perform this action",
        "ar": "المستخدم {user} ليس لديه إذن لتنفيذ هذا الإجراء",
    },
    "invalid_status": {
        "en": "Invalid status transition from {from_status} to {to_status}",
        "ar": "انتقال حالة غير صالح من {from_status} إلى {to_status}",
    },
    "action_not_registered": {
        "en": "Action '{action}' is not registered in the secure action registry",
        "ar": "الإجراء '{action}' غير مسجل في سجل الإجراءات الآمن",
    },
    "validation_failed": {
        "en": "Validation failed: {error}",
        "ar": "فشل التحقق من الصحة: {error}",
    },
}

# Stage messages
STAGE_MESSAGES = {
    "entered": {
        "en": "Entered stage '{stage}' for {obj_label}({obj_pk})",
        "ar": "تم الدخول إلى المرحلة '{stage}' لـ {obj_label}({obj_pk})",
    },
    "exited": {
        "en": "Exited stage '{stage}' for {obj_label}({obj_pk})",
        "ar": "تم الخروج من المرحلة '{stage}' لـ {obj_label}({obj_pk})",
    },
    "approved": {
        "en": "Stage '{stage}' approved for {obj_label}({obj_pk}) by {user}",
        "ar": "تمت الموافقة على المرحلة '{stage}' لـ {obj_label}({obj_pk}) بواسطة {user}",
    },
}


def get_message(
    message_key: str, context: Dict[str, Any], message_set: Dict = WORKFLOW_MESSAGES
) -> Dict[str, str]:
    """
    Get bilingual message from template.

    Args:
        message_key: Key for the message template
        context: Variables to format into the message
        message_set: Dictionary containing message templates

    Returns:
        Dictionary with 'en' and 'ar' keys

    Example:
        >>> msg = get_message("created", {"workflow_id": 1, "name": "Test"})
        >>> print(msg['en'])  # Workflow created - ID: 1, Name: Test
        >>> print(msg['ar'])  # تم إنشاء سير العمل - المعرف: 1، الاسم: Test
    """
    template = message_set.get(message_key, {})

    return {
        "en": template.get("en", "").format(**context) if "en" in template else "",
        "ar": template.get("ar", "").format(**context) if "ar" in template else "",
    }


def log_workflow_event(
    event_key: str,
    context: Dict[str, Any],
    user=None,
    level: str = "info",
    logger_instance: Optional[logging.Logger] = None,
):
    """
    Log a workflow event in both languages.

    Args:
        event_key: Key for the event message
        context: Variables for the message
        user: User object (for language detection)
        level: Log level (info, warning, error)
        logger_instance: Custom logger instance

    Example:
        >>> log_workflow_event(
        ...     "created",
        ...     {"workflow_id": 1, "name": "Test"},
        ...     user=request.user
        ... )
    """
    if logger_instance is None:
        logger_instance = logger

    messages = get_message(event_key, context, WORKFLOW_MESSAGES)

    user_lang = get_user_language(user) if user else None

    log_func = getattr(logger_instance, level.lower(), logger_instance.info)

    if user_lang == "ar":
        log_func(f"[AR] {messages['ar']}")
    else:
        log_func(f"[EN] {messages['en']}")

    # Always log both languages for important events
    if level in ["error", "warning"]:
        log_func(f"[BILINGUAL] EN: {messages['en']} | AR: {messages['ar']}")
