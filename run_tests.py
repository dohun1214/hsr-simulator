#!/usr/bin/env python3
"""의존성 없이 테스트를 실행하는 폴백 러너.

    python run_tests.py

pytest 가 설치되어 있으면 그대로 pytest 를 쓰는 것이 좋다 (`python -m pytest`).
이 스크립트는 pytest 를 설치할 수 없는 환경(오프라인 등)을 위한 것이다.
"""

from __future__ import annotations

import importlib.util
import inspect
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

#: HSR_FORCE_MINIPYTEST=1 로 폴백 경로를 강제로 검증할 수 있다.
_FORCE_FALLBACK = os.environ.get("HSR_FORCE_MINIPYTEST") == "1"

_HAS_REAL_PYTEST = False
if _FORCE_FALLBACK:
    sys.path.insert(0, os.path.join(ROOT, "tools", "minipytest"))
    sys.modules.pop("pytest", None)
else:
    try:  # 진짜 pytest 가 설치되어 있으면 그대로 위임한다
        import pytest  # noqa: F401

        _HAS_REAL_PYTEST = True
    except ImportError:
        sys.path.insert(0, os.path.join(ROOT, "tools", "minipytest"))


def _is_fixture(obj) -> bool:
    """minipytest 폴백과 진짜 pytest 양쪽의 fixture 를 모두 인식한다."""
    if getattr(obj, "__minipytest_fixture__", False):
        return True
    return hasattr(obj, "_pytestfixturefunction")


def _unwrap_fixture(obj):
    """진짜 pytest fixture 는 원본 함수를 감싸고 있을 수 있다."""
    return getattr(obj, "__wrapped__", obj)


def load_module(path):
    name = "t_" + os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    if _HAS_REAL_PYTEST:
        import pytest as _pytest

        return int(_pytest.main(["-q", os.path.join(ROOT, "tests")]))
    return run_fallback()


def run_fallback() -> int:
    test_dir = os.path.join(ROOT, "tests")
    files = sorted(
        os.path.join(test_dir, f)
        for f in os.listdir(test_dir)
        if f.startswith("test_") and f.endswith(".py")
    )

    passed = 0
    failures = []

    for path in files:
        module = load_module(path)
        fixtures = {
            name: obj
            for name, obj in vars(module).items()
            if callable(obj) and _is_fixture(obj)
        }
        for name in sorted(vars(module)):
            func = getattr(module, name)
            if not (name.startswith("test_") and inspect.isfunction(func)):
                continue
            try:
                kwargs = {
                    param: _unwrap_fixture(fixtures[param])()
                    for param in inspect.signature(func).parameters
                    if param in fixtures
                }
                func(**kwargs)
                passed += 1
            except Exception:  # noqa: BLE001
                failures.append((os.path.basename(path), name, traceback.format_exc()))

    for file_name, test_name, tb in failures:
        print(f"\n=== FAIL {file_name}::{test_name} ===\n{tb}")

    print(f"\n{passed} passed, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
