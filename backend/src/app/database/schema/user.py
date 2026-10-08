from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
