"""결정론적 난수.

요구사항:

- 동일한 상태 + 동일한 행동 -> 항상 동일한 결과
- BattleState 를 복제하면 난수 스트림 위치도 함께 복제되어야 한다
  (그래야 미래 상태 탐색 결과가 재현 가능하다)

따라서 전역 `random` 모듈을 절대 쓰지 않고, 난수 상태를 BattleState 안에 값으로 들고 다닌다.
알고리즘은 splitmix64 (구현이 짧고, 플랫폼/파이썬 버전에 무관하게 동일한 수열).
"""

from __future__ import annotations

from dataclasses import dataclass

_MASK64 = (1 << 64) - 1
_GOLDEN = 0x9E3779B97F4A7C15


def _splitmix64(x: int) -> int:
    x = (x + _GOLDEN) & _MASK64
    z = x
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK64
    return z ^ (z >> 31)


@dataclass
class RngState:
    """전투 상태에 저장되는 난수 상태."""

    seed: int = 0
    counter: int = 0

    def clone(self) -> "RngState":
        return RngState(self.seed, self.counter)

    def next_u64(self) -> int:
        self.counter += 1
        return _splitmix64((self.seed + self.counter * _GOLDEN) & _MASK64)

    def random(self) -> float:
        """[0.0, 1.0) 균등 분포."""
        return (self.next_u64() >> 11) / float(1 << 53)

    def randrange(self, n: int) -> int:
        """0 이상 n 미만의 정수. n <= 0 이면 0."""
        if n <= 0:
            return 0
        return self.next_u64() % n

    def choice(self, seq):
        return seq[self.randrange(len(seq))]
