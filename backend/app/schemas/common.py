from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """api.md 统一响应结构"""
    code: int = 0
    data: T | None = None
    message: str = "ok"


class PaginatedResponse(BaseModel, Generic[T]):
    total: int
    page: int
    page_size: int
    items: list[T]


def ok(data: T) -> ApiResponse[T]:
    return ApiResponse(code=0, data=data, message="ok")


def err(code: int, message: str) -> ApiResponse[None]:
    return ApiResponse(code=code, data=None, message=message)
