"""Shared constants and types used by both sync and async clients."""

import enum

DEFAULT_BASE_URL = "https://api.vainu.io/api"
JWT_REFRESH_ENDPOINT_PATH = "/token_authentication/refresh/"


class AsyncJobState(enum.StrEnum):
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    FAILURE = "failure"
    PARTIAL_FAILURE_COMPLETE = "partial_failure_complete"
    PARTIAL_FAILURE_INCOMPLETE = "partial_failure_incomplete"
    PROCESS = "process"
    STOPPED = "stopped"
