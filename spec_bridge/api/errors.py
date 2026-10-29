"""Refusals in the API contract: every HTTPException reply is {"detail": "<reason>"}.

A route lists the codes it refuses with, so the contract (web/openapi.json) and the UI's
generated types name them. A 422 can also be FastAPI's own reply to a malformed request,
whose detail is a list, so a route that refuses with 422 documents both forms.
"""

from typing import Any

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    detail: str


class InvalidRequest(BaseModel):
    """FastAPI's reply to a request that does not match the route's parameters or body."""

    detail: list[dict[str, Any]]


UPLOAD = {400: "the file is empty", 413: "the file is over the upload limit"}


def refusals(reasons: dict[int, str]) -> dict[int | str, dict[str, Any]]:
    """FastAPI `responses=` for the given codes and their descriptions."""
    return {
        code: {
            "model": ErrorDetail | InvalidRequest if code == 422 else ErrorDetail,
            "description": reason,
        }
        for code, reason in reasons.items()
    }
