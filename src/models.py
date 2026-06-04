"""Dataclasses passed between functions, all JSON-serialisable."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .errors import InvalidRequestError


@dataclass
class ContainerSpec:
    image: str
    payload: dict[str, Any] = field(default_factory=dict)
    name: str | None = None
    env: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ContainerHandle:
    id: str
    image: str
    backend: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PipelineRequest:
    payload: dict[str, Any] = field(default_factory=dict)
    branches: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "PipelineRequest":
        raw = raw or {}
        if not isinstance(raw, dict):
            raise InvalidRequestError("request body must be a JSON object")
        payload = raw.get("payload") or {}
        branches = raw.get("branches") or []
        if not isinstance(payload, dict):
            raise InvalidRequestError("'payload' must be a JSON object")
        if not isinstance(branches, list):
            raise InvalidRequestError("'branches' must be a JSON array")
        return cls(payload=payload, branches=branches)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def spec_dict(image: str, payload: dict[str, Any], name: str | None = None) -> dict[str, Any]:
    return ContainerSpec(image=image, payload=payload, name=name).to_dict()
