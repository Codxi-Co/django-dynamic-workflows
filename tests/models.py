"""Test models for django-workflow-engine tests."""

from django.db import models


class Company(models.Model):
    """Test company model for tests."""

    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'companies'

    def __str__(self):
        return self.name