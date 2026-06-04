"""In-memory backend (default). Status is derived from elapsed time, so the
pipeline runs with no Azure resources. Knobs travel in the payload under
"_sim", e.g. {"_sim": {"duration_seconds": 3, "fail": false}}."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

from ..models import ContainerHandle, ContainerSpec
from .base import ContainerClient, ContainerState, ContainerStatus


def _sim_opts(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("_sim", {}) if isinstance(payload, dict) else {}


class FakeContainerClient(ContainerClient):
    def start(self, spec: ContainerSpec) -> ContainerHandle:
        opts = _sim_opts(spec.payload)
        now = time.time()
        duration = float(opts.get("duration_seconds", 2.0))
        return ContainerHandle(
            id=f"fake-{uuid.uuid4().hex[:12]}",
            image=spec.image,
            backend={
                "started_at": now,
                "finish_at": now + duration,
                "fail": bool(opts.get("fail", False)),
                "payload": spec.payload,
            },
        )

    def get_state(self, handle: ContainerHandle) -> ContainerState:
        now = time.time()
        b = handle.backend
        if now < b["finish_at"]:
            return ContainerState(ContainerStatus.RUNNING)
        if b.get("fail"):
            return ContainerState(ContainerStatus.FAILED, error="simulated container failure")
        return ContainerState(ContainerStatus.SUCCEEDED)

    def get_output(self, handle: ContainerHandle) -> dict[str, Any]:
        payload = handle.backend.get("payload", {})
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        return {
            "container_id": handle.id,
            "image": handle.image,
            "digest": digest,
            "echo": payload,
        }

    def delete(self, handle: ContainerHandle) -> None:
        return None
