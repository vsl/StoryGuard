import uuid
from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

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
    current_manuscript_version_id: uuid.UUID | None
    current_manuscript_version: str | None = None
    chapter_count: int | None = None
    created_at: datetime
    updated_at: datetime


class SearchMatchRead(BaseModel):
    chunk_id: str
    chapter_id: str
    chapter_ordinal: int
    scene_id: str | None
    text: str
    score: float


class ProjectSearchRead(BaseModel):
    characters: list[dict] = Field(default_factory=list)
    locations: list[dict] = Field(default_factory=list)
    events: list[dict] = Field(default_factory=list)
    manuscript_matches: list[SearchMatchRead]
