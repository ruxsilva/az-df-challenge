"""ContainerClient interface that keeps the orchestrator backend-agnostic."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..models import ContainerHandle, ContainerSpec


class ContainerStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in (ContainerStatus.SUCCEEDED, ContainerStatus.FAILED)


@dataclass
class ContainerState:
    status: ContainerStatus
    error: str | None = None


class ContainerClient(ABC):
    @abstractmethod
    def start(self, spec: ContainerSpec) -> ContainerHandle:
        ...

    @abstractmethod
    def get_state(self, handle: ContainerHandle) -> ContainerState:
        ...

    @abstractmethod
    def get_output(self, handle: ContainerHandle) -> dict[str, Any]:
        ...

    @abstractmethod
    def delete(self, handle: ContainerHandle) -> None:
        ...
