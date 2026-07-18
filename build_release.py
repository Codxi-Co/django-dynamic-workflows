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

import importlib.util
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


def run_command(cmd, description="", env=None):
    """Run a command and handle errors."""
    print(f"🔄 {description}")
    print(f"Running: {shlex.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)

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

    for path in [Path("build"), Path("dist"), *Path(".").glob("*.egg-info")]:
        if path.is_dir():
            shutil.rmtree(path)
            print(f"   Removed directory: {path}")
        elif path.exists():
            path.unlink()
            print(f"   Removed file: {path}")

    # Clean __pycache__ directories
    for root, dirs, files in os.walk("."):
        if "__pycache__" in dirs:
            pycache_path = os.path.join(root, "__pycache__")
            shutil.rmtree(pycache_path)
            print(f"   Removed __pycache__: {pycache_path}")


def run_tests():
    """Run the complete test suite and enforce the coverage gate."""
    print("🧪 Running test suite and coverage gate...")
    run_command(
        [sys.executable, "-m", "coverage", "erase"],
        "Clearing previous coverage data",
    )
    run_command(
        [sys.executable, "-m", "coverage", "run", "-m", "pytest", "-q"],
        "Running tests with coverage",
    )
    run_command(
        [sys.executable, "-m", "coverage", "report"],
        "Enforcing 100% production coverage",
    )


def validate_release_metadata():
    """Verify version consistency and required release documentation."""
    print("🔎 Validating release metadata...")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    package_init = Path("django_workflow_engine/__init__.py").read_text(
        encoding="utf-8"
    )
    project_version = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)
    package_version = re.search(r'^__version__ = "([^"]+)"', package_init, re.MULTILINE)
    if not project_version or not package_version:
        raise RuntimeError("Could not read project/package version metadata")
    if project_version.group(1) != package_version.group(1):
        raise RuntimeError(
            "Version mismatch: pyproject.toml="
            f"{project_version.group(1)}, package={package_version.group(1)}"
        )

    version = project_version.group(1)
    required_docs = [
        Path("README.md"),
        Path("docs/CHANGELOG.md"),
        Path("docs/DEVELOPER_GUIDE.md"),
        Path("docs/FRONTEND_INTEGRATION.md"),
    ]
    missing_docs = [str(path) for path in required_docs if not path.is_file()]
    if missing_docs:
        raise RuntimeError(f"Missing required documentation: {missing_docs}")
    changelog = required_docs[1].read_text(encoding="utf-8")
    if f"## [{version}]" not in changelog:
        raise RuntimeError(f"docs/CHANGELOG.md has no release entry for {version}")
    print(f"✅ Release metadata is consistent for v{version}")


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
                    env = {**os.environ, "DJANGO_SETTINGS_MODULE": "sandbox.settings"}
                    run_command(
                        [
                            sys.executable,
                            "-m",
                            "django",
                            "compilemessages",
                            "--locale",
                            lang_dir.name,
                        ],
                        f"Compiling {lang_dir.name}",
                        env=env,
                    )


def build_package():
    """Build the package for distribution."""
    print("📦 Building package...")

    missing_tools = [
        module
        for module in ("build", "twine")
        if importlib.util.find_spec(module) is None
    ]
    if missing_tools:
        raise RuntimeError(
            "Missing release tools. Install the dev dependencies first: "
            + ", ".join(missing_tools)
        )

    # Build the package
    run_command(
        [sys.executable, "-m", "build"],
        "Building wheel and source distribution",
    )


def check_package():
    """Run package checks."""
    print("✅ Checking package...")

    # Check the built package
    distributions = sorted(str(path) for path in Path("dist").glob("*"))
    if not distributions:
        raise RuntimeError("No distribution artifacts were built")
    run_command(
        [sys.executable, "-m", "twine", "check", *distributions],
        "Checking package with twine",
    )

    # List the built files
    print("\n📁 Built files:")
    if os.path.exists("dist"):
        for file in os.listdir("dist"):
            file_path = os.path.join("dist", file)
            size = os.path.getsize(file_path)
            print(f"   {file} ({size:,} bytes)")


def main():
    """Main build process."""
    print("🚀 Django Dynamic Workflows - PyPI Release Builder")
    print("=" * 50)

    # Ensure we're in the right directory
    if not os.path.exists("pyproject.toml"):
        print(
            "❌ Error: pyproject.toml not found. Run this script from the project root."
        )
        sys.exit(1)

    try:
        # Step 1: Clean previous builds
        clean_build()

        # Step 2: Validate version and documentation metadata
        validate_release_metadata()

        # Step 3: Run tests
        run_tests()

        # Step 4: Compile translations
        compile_translations()

        # Step 5: Build package
        build_package()

        # Step 6: Check package
        check_package()

        print("\n🎉 Package build completed successfully!")
        print("\n📋 Next steps:")
        print("   1. Review the built files in the 'dist' directory")
        print(
            "   2. Test upload to Test PyPI: twine upload --repository testpypi dist/*"
        )
        print("   3. Upload to PyPI: twine upload dist/*")
        print(
            "\n💡 Note: Make sure you have configured your PyPI credentials with 'twine configure'"
        )

    except KeyboardInterrupt:
        print("\n❌ Build interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Build failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
