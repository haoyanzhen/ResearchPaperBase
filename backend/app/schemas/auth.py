from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str

    @field_validator("username")
    @classmethod
    def username_length(cls, v: str) -> str:
        if not 2 <= len(v) <= 50:
            raise ValueError("用户名长度须在 2-50 字符之间")
        return v

    @field_validator("password")
    @classmethod
    def password_length(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("密码至少 6 位")
        return v


class RegisterResponse(BaseModel):
    user_id: str
    username: str
    email: str
    created_at: datetime


class LoginRequest(BaseModel):
    credential: str   # 用户名或邮箱
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int   # 秒
    user: "UserInfo"


class UserInfo(BaseModel):
    user_id: str
    username: str
    email: str
    is_admin: bool = False


class MeResponse(BaseModel):
    user_id: str
    username: str
    email: str
    is_admin: bool
    is_active: bool
    created_at: datetime


class UpdateMeRequest(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
    password: str | None = None
