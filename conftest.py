"""Shared test fixtures for django workflow engine tests."""

import os
import sys

import django
from django.conf import settings

import pytest

# Add the project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


def pytest_configure():
    """Configure Django settings for pytest."""
    if not settings.configured:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sandbox.settings")
        django.setup()
