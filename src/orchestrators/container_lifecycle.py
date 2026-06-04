"""Sub-orchestrator owning one container's lifecycle: start, poll until done,
collect output, delete. The orchestrator drives the wait with create_timer so an
activity never blocks for hours, and cleanup always runs. The generator lives in
_workflow so it can be unit tested with a mock context."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import azure.durable_functions as df

from ..config import activity_retry_options, get_poll_settings
from ..errors import ContainerExecutionError

bp = df.Blueprint()

ORCHESTRATOR_NAME = "container_lifecycle"


def _workflow(context: df.DurableOrchestrationContext):
    spec: dict[str, Any] = context.get_input()
    retry = activity_retry_options()
    poll = get_poll_settings()

    handle = yield context.call_activity_with_retry("start_container", retry, spec)

    output: dict[str, Any] | None = None
    error: str | None = None
    attempts = 0
    backoff = poll.initial_seconds

    try:
        while True:
            state = yield context.call_activity_with_retry(
                "get_container_status", retry, handle
            )
            status = state["status"]

            if status == "succeeded":
                output = yield context.call_activity_with_retry(
                    "get_container_output", retry, handle
                )
                break
            if status == "failed":
                error = state.get("error") or "container reported failure"
                break

            attempts += 1
            if attempts >= poll.max_attempts:
                error = f"timed out waiting for container after {attempts} probes"
                break

            deadline = context.current_utc_datetime + timedelta(seconds=backoff)
            yield context.create_timer(deadline)
            backoff = min(backoff * 2, poll.max_seconds)
    except Exception as exc:
        error = f"unexpected orchestration error: {exc}"

    try:
        yield context.call_activity_with_retry("delete_container", retry, handle)
    except Exception:
        pass

    if error is not None:
        raise ContainerExecutionError(error)

    return {
        "container_id": handle["id"],
        "image": handle["image"],
        "output": output,
    }


@bp.orchestration_trigger(context_name="context")
def container_lifecycle(context: df.DurableOrchestrationContext):
    result = yield from _workflow(context)
    return result
