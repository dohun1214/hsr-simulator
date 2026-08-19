"""pytest 최소 대체 구현 (의존성 없는 환경 전용).

정식 개발 환경에서는 진짜 pytest 를 쓴다 (`pip install -e .[dev]`).
이 파일은 네트워크가 없어 pytest 를 설치할 수 없는 환경에서도
`python run_tests.py` 로 테스트를 돌릴 수 있게 하기 위한 **폴백**이다.

지원 범위: approx / fixture / raises / mark(no-op).
그 외 pytest 기능을 쓰기 시작하면 이 파일을 늘리지 말고 진짜 pytest 를 쓸 것.
"""

from __future__ import annotations

import math
from contextlib import contextmanager


class approx:  # noqa: N801 - pytest API 이름을 그대로 흉내낸다
    def __init__(self, expected, rel=1e-6, abs=1e-12):
        self.expected = expected
        self.rel = rel
        self.abs = abs

    def _close(self, a, b):
        return math.isclose(a, b, rel_tol=self.rel, abs_tol=self.abs)

    def __eq__(self, actual):
        expected = self.expected
        if isinstance(expected, (list, tuple)):
            if not isinstance(actual, (list, tuple)) or len(actual) != len(expected):
                return False
            return all(self._close(a, b) for a, b in zip(actual, expected))
        if isinstance(expected, dict):
            if not isinstance(actual, dict) or actual.keys() != expected.keys():
                return False
            return all(self._close(actual[k], expected[k]) for k in expected)
        return self._close(actual, expected)

    def __repr__(self):
        return f"approx({self.expected!r})"


def fixture(func=None, **_kwargs):
    def wrap(fn):
        fn.__minipytest_fixture__ = True
        return fn

    return wrap(func) if func is not None else wrap


@contextmanager
def raises(exc_type):
    try:
        yield
    except exc_type:
        return
    raise AssertionError(f"{exc_type.__name__} 이 발생하지 않았습니다")


class _MarkStub:
    def __getattr__(self, _name):
        def decorator(func=None, **_kwargs):
            return func if func is not None else (lambda f: f)

        return decorator


mark = _MarkStub()
