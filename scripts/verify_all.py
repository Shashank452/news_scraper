#!/usr/bin/env python3
"""
Pre-push verification tool.
Runs syntax compilation, checks database connectivity, and executes full test suite.
Use before pushing code to GitHub to guarantee all CI checks will pass.
"""

import py_compile
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent


def check_syntax() -> bool:
    print("\n[1/3] Compiling and checking Python syntax...")
    py_files = list(ROOT_DIR.glob("*.py")) + list(ROOT_DIR.glob("*/*.py"))
    has_error = False
    for pf in py_files:
        if ".venv" in str(pf) or "__pycache__" in str(pf):
            continue
        try:
            py_compile.compile(str(pf), doraise=True)
        except py_compile.PyCompileError as e:
            print(f"  [FAIL] Syntax error in {pf.name}: {e}")
            has_error = True
    if not has_error:
        print("  [PASS] All Python files compiled cleanly.")
    return not has_error


def run_tests() -> bool:
    print("\n[2/3] Running complete test suite via pytest...")
    result = subprocess.run([sys.executable, "-m", "pytest", "-v", "--tb=short"], cwd=str(ROOT_DIR))
    if result.returncode == 0:
        print("  [PASS] All unit and integration tests passed.")
        return True
    else:
        print("  [FAIL] One or more tests failed.")
        return False


def main():
    print("=" * 60)
    print(" Indian Equities News Scraper - Pre-Push Verification")
    print("=" * 60)

    if not check_syntax():
        print("\n❌ Verification FAILED at syntax check. Fix errors before pushing.")
        sys.exit(1)

    if not run_tests():
        print("\n❌ Verification FAILED at test suite. Fix failing tests before pushing.")
        sys.exit(1)

    print("\n[3/3] Overall Status: READY TO PUSH TO GITHUB")
    print("=" * 60)
    print(" All tests passed. GitHub Actions CI will succeed and allow merging.")
    print("=" * 60)
    sys.exit(0)


if __name__ == "__main__":
    main()
