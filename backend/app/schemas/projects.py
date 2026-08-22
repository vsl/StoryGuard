import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Language = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=16)
]


class ProjectCreate(BaseModel):
    title: Title
    description: str = ""
    language: Language = "en"


class ProjectUpdate(BaseModel):
    title: Title | None = None
    description: str | None = None
    language: Language | None = None

    @model_validator(mode="after")
    def validate_changes(self) -> "ProjectUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Project fields cannot be null")
        return self


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    language: str
    created_at: datetime
    updated_at: datetime
