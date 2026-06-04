"""Environment-driven settings and the ContainerClient factory. Reading these
from orchestrator code is safe because env vars are constant across replays."""

from __future__ import annotations

import os
from dataclasses import dataclass

import azure.durable_functions as df

from .clients.base import ContainerClient


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Images:
    ingest: str
    worker: str
    aggregate: str


def get_images() -> Images:
    return Images(
        ingest=_env("INGEST_IMAGE", "myacr.azurecr.io/ingest:latest"),
        worker=_env("WORKER_IMAGE", "myacr.azurecr.io/worker:latest"),
        aggregate=_env("AGGREGATE_IMAGE", "myacr.azurecr.io/aggregate:latest"),
    )


@dataclass(frozen=True)
class PollSettings:
    initial_seconds: int
    max_seconds: int
    max_attempts: int


def get_poll_settings() -> PollSettings:
    return PollSettings(
        initial_seconds=int(_env("POLL_INITIAL_SECONDS", "5")),
        max_seconds=int(_env("POLL_MAX_SECONDS", "60")),
        max_attempts=int(_env("POLL_MAX_ATTEMPTS", "720")),
    )


def activity_retry_options() -> df.RetryOptions:
    opts = df.RetryOptions(
        first_retry_interval_in_milliseconds=2000,
        max_number_of_attempts=4,
    )
    opts.backoff_coefficient = 2.0
    opts.max_retry_interval_in_milliseconds = 30000
    return opts


def get_container_client() -> ContainerClient:
    backend = _env("CONTAINER_BACKEND", "fake").lower()
    if backend == "fake":
        from .clients.fake import FakeContainerClient

        return FakeContainerClient()
    if backend == "aci":
        from .clients.aci import AciContainerClient

        return AciContainerClient()
    raise ValueError(f"unknown CONTAINER_BACKEND: {backend!r}")
