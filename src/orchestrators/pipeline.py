"""Top-level pipeline: stage 1 single container, stage 2 fan-out to N containers
in parallel (task_all), stage 3 single container after the fan-in. Each stage is
a container_lifecycle sub-orchestration. Fan-out width comes from the request,
not from inspecting any container's output."""

from __future__ import annotations

from typing import Any

import azure.durable_functions as df

from ..config import activity_retry_options, get_images
from ..models import PipelineRequest, spec_dict

bp = df.Blueprint()

ORCHESTRATOR_NAME = "pipeline_orchestrator"
LIFECYCLE = "container_lifecycle"


def _default_branches() -> list[dict[str, Any]]:
    return [{"shard": i} for i in range(3)]


def _workflow(context: df.DurableOrchestrationContext):
    request = PipelineRequest.from_dict(context.get_input())
    images = get_images()
    retry = activity_retry_options()

    ingest = yield context.call_sub_orchestrator_with_retry(
        LIFECYCLE, retry, spec_dict(images.ingest, request.payload, name="ingest")
    )

    branches = request.branches or _default_branches()
    fan_out = []
    for i, branch in enumerate(branches):
        worker_payload = {"ingest": ingest["output"], "branch": branch}
        fan_out.append(
            context.call_sub_orchestrator(
                LIFECYCLE,
                spec_dict(images.worker, worker_payload, name=f"worker-{i}"),
                f"{context.instance_id}::worker-{i}",
            )
        )

    branch_results = yield context.task_all(fan_out)

    aggregate_payload = {"branches": [r["output"] for r in branch_results]}
    aggregate = yield context.call_sub_orchestrator_with_retry(
        LIFECYCLE, retry, spec_dict(images.aggregate, aggregate_payload, name="aggregate")
    )

    return {
        "status": "completed",
        "ingest_container": ingest["container_id"],
        "branch_count": len(branch_results),
        "result": aggregate["output"],
    }


@bp.orchestration_trigger(context_name="context")
def pipeline_orchestrator(context: df.DurableOrchestrationContext):
    result = yield from _workflow(context)
    return result
