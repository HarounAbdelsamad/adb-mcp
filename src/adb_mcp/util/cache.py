from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from PIL import Image


@dataclass
class Snapshot:
    snapshot_id: str
    nodes: list  # list[UiNode] — typed loosely to avoid circular imports
    xml: str
    screenshot: Image.Image | None
    captured_at: float = field(default_factory=time.monotonic)

    def age_ms(self) -> float:
        return (time.monotonic() - self.captured_at) * 1000


class SnapshotCache:
    """Stores the last accessibility snapshot per device serial."""

    def __init__(self) -> None:
        self._store: dict[str, Snapshot] = {}

    def put(
        self,
        serial: str,
        nodes: list,
        xml: str,
        screenshot: Image.Image | None = None,
    ) -> Snapshot:
        snap = Snapshot(
            snapshot_id=str(uuid.uuid4()),
            nodes=nodes,
            xml=xml,
            screenshot=screenshot,
        )
        self._store[serial] = snap
        return snap

    def get(self, serial: str) -> Snapshot | None:
        return self._store.get(serial)

    def get_fresh(self, serial: str, max_age_ms: float) -> Snapshot | None:
        snap = self._store.get(serial)
        if snap and snap.age_ms() <= max_age_ms:
            return snap
        return None

    def invalidate(self, serial: str) -> None:
        self._store.pop(serial, None)


snapshot_cache = SnapshotCache()
