#!/usr/bin/env python3
"""
Build script for django-workflow-engine PyPI release.

This script prepares the package for PyPI upload by:
1. Cleaning previous builds
2. Running tests to ensure quality
3. Building the package
4. Running basic package checks

Usage:
    python build_release.py [--test-pypi]
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


def run_command(cmd, description=""):
    """Run a command and handle errors."""
    print(f"🔄 {description}")
    print(f"Running: {cmd}")

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode == 0:
        print(f"✅ {description} - Success")
        if result.stdout:
            print(result.stdout)
    else:
        print(f"❌ {description} - Failed")
        print(f"Error: {result.stderr}")
        sys.exit(1)

    return result


def clean_build():
    """Clean previous build artifacts."""
    print("🧹 Cleaning build artifacts...")

    directories_to_clean = [
        'build',
        'dist',
        'django_workflow_engine.egg-info',
        '*.egg-info',
    ]

    for directory in directories_to_clean:
        if os.path.exists(directory):
            if os.path.isdir(directory):
                shutil.rmtree(directory)
                print(f"   Removed directory: {directory}")
            else:
                os.remove(directory)
                print(f"   Removed file: {directory}")

    # Clean __pycache__ directories
    for root, dirs, files in os.walk('.'):
        if '__pycache__' in dirs:
            pycache_path = os.path.join(root, '__pycache__')
            shutil.rmtree(pycache_path)
            print(f"   Removed __pycache__: {pycache_path}")


def run_tests():
    """Run the test suite to ensure quality."""
    print("🧪 Running test suite...")
    run_command("python -m pytest tests/ --tb=short -q", "Running tests")


def compile_translations():
    """Compile translation files."""
    print("🌍 Compiling translations...")

    # Check if we have translation files
    locale_path = Path("django_workflow_engine/locale")
    if locale_path.exists():
        for lang_dir in locale_path.iterdir():
            if lang_dir.is_dir():
                po_file = lang_dir / "LC_MESSAGES" / "django.po"
                if po_file.exists():
                    print(f"   Compiling {lang_dir.name} translations...")
                    run_command(
                        f"python -c \"import django; django.setup(); "
                        f"from django.core.management import call_command; "
                        f"call_command('compilemessages', locale=['{lang_dir.name}'])\"",
                        f"Compiling {lang_dir.name}"
                    )


def build_package():
    """Build the package for distribution."""
    print("📦 Building package...")

    # Install build dependencies
    run_command("pip install --upgrade build twine", "Installing build tools")

    # Build the package
    run_command("python -m build", "Building wheel and source distribution")


def check_package():
    """Run package checks."""
    print("✅ Checking package...")

    # Check the built package
    run_command("twine check dist/*", "Checking package with twine")

    # List the built files
    print("\n📁 Built files:")
    if os.path.exists("dist"):
        for file in os.listdir("dist"):
            file_path = os.path.join("dist", file)
            size = os.path.getsize(file_path)
            print(f"   {file} ({size:,} bytes)")


def main():
    """Main build process."""
    print("🚀 Django Workflow Engine - PyPI Release Builder")
    print("=" * 50)

    # Ensure we're in the right directory
    if not os.path.exists("pyproject.toml"):
        print("❌ Error: pyproject.toml not found. Run this script from the project root.")
        sys.exit(1)

    try:
        # Step 1: Clean previous builds
        clean_build()

        # Step 2: Run tests
        run_tests()

        # Step 3: Compile translations
        compile_translations()

        # Step 4: Build package
        build_package()

        # Step 5: Check package
        check_package()

        print("\n🎉 Package build completed successfully!")
        print("\n📋 Next steps:")
        print("   1. Review the built files in the 'dist' directory")
        print("   2. Test upload to Test PyPI: twine upload --repository testpypi dist/*")
        print("   3. Upload to PyPI: twine upload dist/*")
        print("\n💡 Note: Make sure you have configured your PyPI credentials with 'twine configure'")

    except KeyboardInterrupt:
        print("\n❌ Build interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Build failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()