"""Domain errors raised across the orchestration."""


class ContainerExecutionError(Exception):
    """A container failed, or its lifecycle could not be completed."""


class InvalidRequestError(Exception):
    """The pipeline was started with a payload that cannot be processed."""
