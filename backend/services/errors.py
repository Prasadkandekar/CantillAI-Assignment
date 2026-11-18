"""Service-level errors carrying the HTTP status the API should return."""
from __future__ import annotations


class ServiceError(Exception):
    def __init__(self, status: int, detail):
        super().__init__(detail if isinstance(detail, str) else str(detail))
        self.status = status
        self.detail = detail


def bad_request(detail):
    return ServiceError(400, detail)


def not_found(detail):
    return ServiceError(404, detail)


def conflict(detail):
    return ServiceError(409, detail)


def unprocessable(detail):
    return ServiceError(422, detail)
