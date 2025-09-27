"""Companies app configuration."""

from django.apps import AppConfig


class CompaniesConfig(AppConfig):
    """Companies app configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "tests.companies"
    label = "companies"
