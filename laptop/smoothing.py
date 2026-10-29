"""Smoothing sekunder di laptop (FR-04, TC-05): moving average atas lux HP."""

from collections import deque


class LuxSmoother:
    """Moving average dengan jendela tetap; None dilewati agar gap data tidak menggeser angka."""

    def __init__(self, window: int = 3):
        self.window = window
        self._values: deque[float] = deque(maxlen=window)

    def add(self, lux: float | None) -> float | None:
        if isinstance(lux, bool):
            return self.current()
        if lux is None:
            return self.current()
        if not isinstance(lux, (int, float)):
            return self.current()
        self._values.append(float(lux))
        return self.current()

    def current(self) -> float | None:
        if not self._values:
            return None
        return sum(self._values) / len(self._values)

    def reset(self) -> None:
        self._values.clear()
