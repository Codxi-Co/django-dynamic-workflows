"""Management command to compile translation messages for django-workflow-engine."""

import os

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Compile translation messages for django-workflow-engine."""

    help = "Compile translation messages for Arabic and English"

    def add_arguments(self, parser):
        parser.add_argument(
            "--locale",
            "-l",
            action="append",
            default=[],
            help="Locale(s) to process; Default is to process all. Can be used multiple times.",
        )

    def handle(self, *args, **options):
        """Handle the command execution."""
        locales = options.get("locale") or ["en", "ar"]

        # Get the package directory
        package_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

        self.stdout.write(
            self.style.SUCCESS(
                f'Compiling messages for django-workflow-engine in locales: {", ".join(locales)}'
            )
        )

        for locale in locales:
            locale_dir = os.path.join(package_dir, "locale", locale, "LC_MESSAGES")
            po_file = os.path.join(locale_dir, "django.po")
            mo_file = os.path.join(locale_dir, "django.mo")

            if os.path.exists(po_file):
                self.stdout.write(f"Compiling {locale} messages...")
                try:
                    # Use Django's compilemessages
                    call_command("compilemessages", locale=[locale], verbosity=0)

                    if os.path.exists(mo_file):
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✓ Successfully compiled {locale} messages"
                            )
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f"⚠ Warning: {mo_file} not found after compilation"
                            )
                        )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"✗ Error compiling {locale} messages: {e}")
                    )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"⚠ No translation file found for {locale}: {po_file}"
                    )
                )

        self.stdout.write(self.style.SUCCESS("✓ Translation compilation completed!"))
