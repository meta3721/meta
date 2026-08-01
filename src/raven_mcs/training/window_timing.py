"""Window timing invariants for E0.5 / G2 (paper F2.1, F6.8)."""

from __future__ import annotations

from dataclasses import dataclass, field


class WindowTimingError(RuntimeError):
    pass


@dataclass
class WindowClock:
    """
    Enforce: θ frozen inside a window; exactly one server update when closing.

    This is the timing skeleton used by WindowRunner later.
    """

    num_windows: int
    current_window: int = 0
    model_version: int = 0
    updates_in_window: int = 0
    closed_windows: list[int] = field(default_factory=list)

    def assert_model_frozen(self, downloaded_version: int) -> None:
        if downloaded_version > self.model_version:
            raise WindowTimingError(
                f"Client downloaded version {downloaded_version} but "
                f"server model_version is {self.model_version}; future downloads are invalid"
            )

    def register_local_work(self, downloaded_version: int) -> None:
        if self.current_window >= self.num_windows:
            raise WindowTimingError("No active window remains")
        self.assert_model_frozen(downloaded_version)

    def apply_server_update(self) -> int:
        """Apply the single end-of-window global update and advance."""
        if self.current_window >= self.num_windows:
            raise WindowTimingError("Cannot update after final window")
        if self.updates_in_window != 0:
            raise WindowTimingError(
                "Window already updated; only one global update per window is allowed"
            )
        self.updates_in_window = 1
        self.model_version += 1
        self.closed_windows.append(self.current_window)
        self.current_window += 1
        self.updates_in_window = 0
        return self.model_version

    def skip_empty_window(self) -> None:
        """Close an empty window with an unchanged, newly versioned snapshot."""
        if self.current_window >= self.num_windows:
            raise WindowTimingError("Cannot skip after final window")
        if self.updates_in_window != 0:
            raise WindowTimingError("Window already updated")
        self.closed_windows.append(self.current_window)
        self.current_window += 1
        self.model_version += 1
