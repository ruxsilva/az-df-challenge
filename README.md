# Container Pipeline on Azure Durable Functions

A serverless orchestration that runs pre-existing containerized workloads in a
coordinated way: one sequential stage, a parallel fan-out, then a final
sequential stage. The containers are treated as a black box (opaque input in,
opaque output out).

The purpose of this project is to demonstrate a possible solution for the
purposed challenge of an interview process.

During exploration and the implementation, official documentation
and AI was used.

## Pipeline shape

```
POST /api/pipeline/start
        |
        v
Stage 1   single container          (ingest)
        |
        v
Stage 2   N containers in parallel   (workers, via task_all)
        |
        v
Stage 3   single container           (aggregate, after all branches finish)
```

Every stage reuses the same `container_lifecycle` sub-orchestration, which runs
one container through its full lifecycle: start, poll until done, collect output,
delete.

## How long-running containers are handled

A container might run for seconds or hours. The wrong approach is to have an
activity call the container and block until it finishes, because activities are
not meant to run for hours.

So the orchestrator drives the wait instead:

1. An activity starts the container and returns straight away with a handle.
2. The orchestrator polls the status in a loop, sleeping between checks with
   `context.create_timer`. This sleep is durable and uses no compute while
   waiting, with backoff from 5s up to 60s.
3. When the container succeeds, an activity collects the output.
4. Cleanup (delete) always runs, on success and on failure.

A cap on poll attempts stops an orchestration from waiting forever.

For very long jobs an alternative is to have the container call back via a
webhook and use `wait_for_external_event` instead of polling. Polling was chosen
here because it works against any backend without changing the black-box images.

## Errors, retries, cleanup

- Transient activity faults retry with exponential backoff (`call_activity_with_retry`).
- A container that fails its work is not retried. It surfaces as a failed status
  and raises `ContainerExecutionError`.
- Bad input is rejected with a 400 before any orchestration starts.
- Delete always runs, even on failure or timeout, so containers are not leaked.
- Partial fan-out failure is fail-fast: if any branch fails, `task_all` raises and
  the pipeline fails. Whether to instead continue with the branches that succeeded
  is a business decision; it would be a small change at the fan-in point.

## Backend abstraction

The orchestrator and activities depend only on the `ContainerClient` interface
(`start`, `get_state`, `get_output`, `delete`). Which backend actually runs the
containers is a config choice (`CONTAINER_BACKEND`) and never reaches the
orchestration logic.

- `FakeContainerClient` (default): an in-memory simulation. Status is derived
  from elapsed time, so no shared state is needed and the pipeline runs anywhere.
- `AciContainerClient`: a sketch against Azure Container Instances showing where
  the real SDK calls go. ACI container groups are ephemeral, which maps cleanly
  onto start, run, delete. A Container Apps Job would self-terminate instead, so
  delete becomes a no-op. The interface hides that difference.

## Triggers

Only the HTTP starter is implemented (`http_starter.py`). It is intentionally
thin: validate input, call `client.start_new`, return the status URLs. It holds
no business logic, so adding another trigger is just another starter that calls
`start_new`. The orchestrator does not change.

Other triggers that would fit, all of which would be just another starter:

- Queue (Storage): a producer drops a request message on a queue and the starter
  picks it up. Good for decoupling and load levelling, with a built-in retry and
  poison queue for messages that keep failing.
- Service Bus: same idea but with sessions, deduplication and ordering. The
  choice when the work belongs to a real enterprise messaging system.
- Blob: fires when a file lands in a container, so the blob itself is the input
  to the pipeline.
- Event Grid: reacts to events from Azure or third parties. Usually preferred
  over the raw blob trigger for "data arrived" cases because it scales and
  delivers more reliably.
- Cron Job: runs on a CRON schedule for batch runs, for example a nightly pipeline.

## Project layout

```
home-asgn/
  function_app.py              app entry, registers the blueprints
  host.json                    durable task hub and concurrency
  local.settings.json          sample settings (CONTAINER_BACKEND=fake)
  requirements.txt
  src/
    models.py                  dataclasses passed between functions
    errors.py                  domain errors
    config.py                  settings and the ContainerClient factory
    starters/http_starter.py   the HTTP trigger
    orchestrators/
      pipeline.py              the 3-stage orchestrator
      container_lifecycle.py   one container: start, poll, collect, delete
    activities/container_ops.py  thin wrappers over the client
    clients/
      base.py                  ContainerClient interface
      fake.py                  in-memory simulation (default)
      aci.py                   Azure Container Instances sketch
  tests/test_pipeline.py       unit tests (orchestrators + fake backend)
```

## Running locally

```bash
cd home-asgn
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Durable Functions needs a storage emulator locally:
#   npm i -g azurite && azurite
func start
```

Start a pipeline:

```bash
curl -X POST http://localhost:7071/api/pipeline/start \
  -H "Content-Type: application/json" \
  -d '{"payload": {"_sim": {"duration_seconds": 3}}, "branches": [{"shard": 0}, {"shard": 1}]}'
```

The response includes a `statusQueryGetUri` to follow progress. Set
`"_sim": {"fail": true}` on a payload to exercise the failure and cleanup path.

## Tests

```bash
pip install pytest
pytest
```

The code is structured to be testable without a running host:

- Orchestrators are generators, so they are driven directly with a mock context
  (the `_workflow` function behind each one), feeding the values activities and
  timers would return and asserting on the operations they yield: start, poll,
  timer, collect, delete, and the fan-out then fan-in order.
- Input validation (`PipelineRequest`) and the `FakeContainerClient` success and
  failure paths are tested directly.
- For full end-to-end coverage the pipeline can be run against the fake backend on
  the Azurite storage emulator, with no Azure resources.
