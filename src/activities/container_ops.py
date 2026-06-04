"""Activity functions: thin wrappers over the ContainerClient and the only place
side effects are allowed. Map onto the lifecycle: start, status, output, delete."""

from __future__ import annotations

import logging
from typing import Any

import azure.durable_functions as df

from ..config import get_container_client
from ..models import ContainerHandle, ContainerSpec

bp = df.Blueprint()
log = logging.getLogger(__name__)


@bp.activity_trigger(input_name="spec")
def start_container(spec: dict[str, Any]) -> dict[str, Any]:
    client = get_container_client()
    handle = client.start(ContainerSpec(**spec))
    log.info("started container %s (image=%s)", handle.id, handle.image)
    return handle.to_dict()


@bp.activity_trigger(input_name="handle")
def get_container_status(handle: dict[str, Any]) -> dict[str, Any]:
    client = get_container_client()
    state = client.get_state(ContainerHandle(**handle))
    return {"status": state.status.value, "error": state.error}


@bp.activity_trigger(input_name="handle")
def get_container_output(handle: dict[str, Any]) -> dict[str, Any]:
    client = get_container_client()
    return client.get_output(ContainerHandle(**handle))


@bp.activity_trigger(input_name="handle")
def delete_container(handle: dict[str, Any]) -> bool:
    client = get_container_client()
    client.delete(ContainerHandle(**handle))
    log.info("deleted container %s", handle.get("id"))
    return True
