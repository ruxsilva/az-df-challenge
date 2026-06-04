"""Unit tests. Orchestrators are generators, so we drive them by hand with a mock
context, feeding the values activities and timers would return and asserting on
the operations they yield. The fake backend is tested directly."""

from __future__ import annotations

from datetime import datetime

import pytest

from src.clients.fake import FakeContainerClient
from src.errors import ContainerExecutionError, InvalidRequestError
from src.models import ContainerSpec, PipelineRequest
from src.orchestrators import container_lifecycle, pipeline


class MockContext:
    def __init__(self, input_value):
        self._input = input_value
        self.instance_id = "test-instance"
        self.current_utc_datetime = datetime(2024, 1, 1, 0, 0, 0)

    def get_input(self):
        return self._input

    def call_activity_with_retry(self, name, retry, input_=None):
        return ("activity", name, input_)

    def call_sub_orchestrator_with_retry(self, name, retry, input_=None, instance_id=None):
        return ("suborch", name, input_)

    def call_sub_orchestrator(self, name, input_=None, instance_id=None):
        return ("suborch", name, input_)

    def create_timer(self, deadline):
        return ("timer", deadline)

    def task_all(self, tasks):
        return ("task_all", tasks)


def drive(gen, responses):
    yielded = []
    sent = iter(responses)
    try:
        op = next(gen)
        while True:
            yielded.append(op)
            op = gen.send(next(sent))
    except StopIteration as stop:
        return yielded, stop.value


def test_lifecycle_happy_path_polls_then_collects_and_deletes():
    ctx = MockContext({"image": "img", "payload": {}})
    gen = container_lifecycle._workflow(ctx)

    handle = {"id": "c1", "image": "img", "backend": {}}
    yielded, result = drive(
        gen,
        responses=[
            handle,
            {"status": "running"},
            None,
            {"status": "succeeded"},
            {"result": 42},
            True,
        ],
    )

    ops = [(y[0], y[1]) if y[0] != "timer" else ("timer",) for y in yielded]
    assert ("activity", "start_container") in ops
    assert ("timer",) in ops
    assert ops[-1] == ("activity", "delete_container")
    assert result["output"] == {"result": 42}
    assert result["container_id"] == "c1"


def test_lifecycle_failed_container_still_deletes_then_raises():
    ctx = MockContext({"image": "img", "payload": {}})
    gen = container_lifecycle._workflow(ctx)

    handle = {"id": "c1", "image": "img", "backend": {}}
    seen = []
    with pytest.raises(ContainerExecutionError):
        op = next(gen)
        responses = iter(
            [
                handle,
                {"status": "failed", "error": "boom"},
                True,
            ]
        )
        while True:
            seen.append(op)
            op = gen.send(next(responses))

    assert ("activity", "delete_container") in [(y[0], y[1]) for y in seen]


def test_pipeline_runs_three_stages_with_fan_out():
    request = {"payload": {"x": 1}, "branches": [{"s": 0}, {"s": 1}]}
    ctx = MockContext(request)
    gen = pipeline._workflow(ctx)

    ingest_result = {"container_id": "ingest-1", "output": {"ok": True}}
    branch_results = [{"output": {"b": 0}}, {"output": {"b": 1}}]
    aggregate_result = {"container_id": "agg-1", "output": {"final": True}}

    yielded, result = drive(
        gen,
        responses=[ingest_result, branch_results, aggregate_result],
    )

    kinds = [y[0] for y in yielded]
    assert kinds == ["suborch", "task_all", "suborch"]
    assert len(yielded[1][1]) == 2
    assert result["status"] == "completed"
    assert result["branch_count"] == 2
    assert result["result"] == {"final": True}


def test_pipeline_defaults_to_three_branches_when_none_given():
    ctx = MockContext({"payload": {}})
    gen = pipeline._workflow(ctx)

    yielded, _ = drive(
        gen,
        responses=[
            {"container_id": "i", "output": {}},
            [{"output": {}}, {"output": {}}, {"output": {}}],
            {"container_id": "a", "output": {}},
        ],
    )
    assert len(yielded[1][1]) == 3


def test_pipeline_request_rejects_bad_input():
    with pytest.raises(InvalidRequestError):
        PipelineRequest.from_dict({"payload": "not-an-object"})
    with pytest.raises(InvalidRequestError):
        PipelineRequest.from_dict({"branches": "not-a-list"})


def test_fake_client_succeeds_immediately_with_zero_duration():
    client = FakeContainerClient()
    handle = client.start(ContainerSpec(image="img", payload={"_sim": {"duration_seconds": 0}}))
    state = client.get_state(handle)
    assert state.status.value == "succeeded"

    output = client.get_output(handle)
    assert output["image"] == "img"
    assert "digest" in output
    client.delete(handle)


def test_fake_client_reports_failure_when_requested():
    client = FakeContainerClient()
    handle = client.start(
        ContainerSpec(image="img", payload={"_sim": {"duration_seconds": 0, "fail": True}})
    )
    state = client.get_state(handle)
    assert state.status.value == "failed"
    assert state.error
