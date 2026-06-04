"""Azure Container Instances backend, a sketch showing where the real SDK calls
go. Selected by CONTAINER_BACKEND=aci. Needs azure-identity and
azure-mgmt-containerinstance (kept out of requirements.txt to stay runnable
offline). Auth uses DefaultAzureCredential."""

from __future__ import annotations

import os
from typing import Any

from ..models import ContainerHandle, ContainerSpec
from .base import ContainerClient, ContainerState, ContainerStatus

_STATE_MAP = {
    "Pending": ContainerStatus.PENDING,
    "Running": ContainerStatus.RUNNING,
    "Succeeded": ContainerStatus.SUCCEEDED,
    "Failed": ContainerStatus.FAILED,
    "Terminated": ContainerStatus.SUCCEEDED,
}


class AciContainerClient(ContainerClient):
    def __init__(self) -> None:
        self.subscription_id = os.environ["AZURE_SUBSCRIPTION_ID"]
        self.resource_group = os.environ["ACI_RESOURCE_GROUP"]
        self.region = os.environ.get("ACI_REGION", "westeurope")
        self.registry = os.environ["ACR_LOGIN_SERVER"]

    def _client(self):
        from azure.identity import DefaultAzureCredential
        from azure.mgmt.containerinstance import ContainerInstanceManagementClient

        return ContainerInstanceManagementClient(
            credential=DefaultAzureCredential(),
            subscription_id=self.subscription_id,
        )

    def start(self, spec: ContainerSpec) -> ContainerHandle:
        from azure.mgmt.containerinstance.models import (
            Container,
            ContainerGroup,
            EnvironmentVariable,
            ImageRegistryCredential,
            OperatingSystemTypes,
            ResourceRequests,
            ResourceRequirements,
        )

        group_name = spec.name or f"job-{os.urandom(6).hex()}"
        env = [EnvironmentVariable(name=k, value=v) for k, v in spec.env.items()]
        env.append(EnvironmentVariable(name="INPUT_PAYLOAD", value=_json(spec.payload)))

        container = Container(
            name="work",
            image=spec.image,
            resources=ResourceRequirements(
                requests=ResourceRequests(cpu=1.0, memory_in_gb=1.5)
            ),
            environment_variables=env,
        )
        group = ContainerGroup(
            location=self.region,
            os_type=OperatingSystemTypes.linux,
            restart_policy="Never",
            containers=[container],
            image_registry_credentials=[
                ImageRegistryCredential(
                    server=self.registry,
                    username=os.environ.get("ACR_USERNAME", ""),
                    password=os.environ.get("ACR_PASSWORD", ""),
                )
            ],
        )

        self._client().container_groups.begin_create_or_update(
            self.resource_group, group_name, group
        )
        return ContainerHandle(
            id=group_name, image=spec.image, backend={"group_name": group_name}
        )

    def get_state(self, handle: ContainerHandle) -> ContainerState:
        group = self._client().container_groups.get(
            self.resource_group, handle.backend["group_name"]
        )
        instance_view = getattr(group, "instance_view", None)
        raw_state = (
            instance_view.state if instance_view and instance_view.state else "Pending"
        )
        status = _STATE_MAP.get(raw_state, ContainerStatus.RUNNING)

        if status is ContainerStatus.SUCCEEDED and group.containers:
            cur = group.containers[0].instance_view
            code = cur.current_state.exit_code if cur and cur.current_state else 0
            if code not in (0, None):
                return ContainerState(
                    ContainerStatus.FAILED, error=f"container exited with code {code}"
                )
        return ContainerState(status)

    def get_output(self, handle: ContainerHandle) -> dict[str, Any]:
        logs = self._client().containers.list_logs(
            self.resource_group, handle.backend["group_name"], "work"
        )
        return {"container_id": handle.id, "logs": logs.content}

    def delete(self, handle: ContainerHandle) -> None:
        try:
            self._client().container_groups.begin_delete(
                self.resource_group, handle.backend["group_name"]
            )
        except Exception:
            pass


def _json(value: Any) -> str:
    import json

    return json.dumps(value, default=str)
