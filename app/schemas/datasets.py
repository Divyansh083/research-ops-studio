from pydantic import BaseModel, Field

class DatasetGenerateRequest(BaseModel):
    request: str = Field(min_length=1)
    selected_dataset_path: str | None = None

class DatasetUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=1, max_length=15000000)  # Approx 10MB after base64 overhead
