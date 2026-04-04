from pydantic import BaseModel, Field

class ResearchRunRequest(BaseModel):
    query: str = Field(min_length=1)
    selected_dataset_path: str | None = None
