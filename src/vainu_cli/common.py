"""Shared constants and types used by both sync and async clients."""

import enum
from typing import Literal, Protocol, TypeAlias

DEFAULT_BASE_URL = "https://api.vainu.io/api"
JWT_REFRESH_ENDPOINT_PATH = "/token_authentication/refresh/"
ResponseFormat: TypeAlias = Literal["json", "csv", "jsonl"]
DEFAULT_RESPONSE_FORMAT: ResponseFormat = "json"
RESPONSE_FORMATS: tuple[ResponseFormat, ...] = ("json", "csv", "jsonl")


class ResponseLike(Protocol):
    text: str

    def json(self) -> dict: ...


def parse_response(response: ResponseLike, format: ResponseFormat) -> dict | str:
    if format == "json":
        return response.json()
    return response.text


class AsyncJobState(enum.StrEnum):
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    FAILURE = "failure"
    PARTIAL_FAILURE_COMPLETE = "partial_failure_complete"
    PARTIAL_FAILURE_INCOMPLETE = "partial_failure_incomplete"
    PROCESS = "process"
    STOPPED = "stopped"
