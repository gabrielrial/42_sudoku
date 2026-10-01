from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-z0-9_-]+$")
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def lowercase_username(cls, value: Any) -> Any:
        return value.lower() if isinstance(value, str) else value


class UserResponse(BaseModel):
    id: int
    username: str
    # email: str

    model_config = ConfigDict(from_attributes=True)


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
