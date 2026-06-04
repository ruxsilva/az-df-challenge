"""HTTP starter, the one implemented trigger. Validates the body, starts the
pipeline orchestration, and returns the status URLs. POST /api/pipeline/start
with {"payload": {...}, "branches": [{...}]} (branches optional)."""

from __future__ import annotations

import json
import logging

import azure.durable_functions as df
import azure.functions as func

from ..errors import InvalidRequestError
from ..models import PipelineRequest
from ..orchestrators.pipeline import ORCHESTRATOR_NAME

bp = df.Blueprint()
log = logging.getLogger(__name__)


@bp.route(route="pipeline/start", methods=["POST"])
@bp.durable_client_input(client_name="client")
async def start_pipeline(
    req: func.HttpRequest, client: df.DurableOrchestrationClient
) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return _bad_request("request body must be valid JSON")

    try:
        request = PipelineRequest.from_dict(body)
    except InvalidRequestError as exc:
        return _bad_request(str(exc))

    instance_id = await client.start_new(ORCHESTRATOR_NAME, client_input=request.to_dict())
    log.info("started pipeline orchestration %s", instance_id)

    return client.create_check_status_response(req, instance_id)


def _bad_request(message: str) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({"error": message}),
        status_code=400,
        mimetype="application/json",
    )
