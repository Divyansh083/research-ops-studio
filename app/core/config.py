from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Groq
    groq_api_key: str = ""
    llm_model: str = "llama-3.3-70b-versatile"
    llm_temperature: float = 0.0
    llm_timeout: int = 120

    # Local embeddings
    embedding_model: str = "BAAI/bge-base-en-v1.5"

    # CORS
    cors_allowed_origins: str = (
        "http://localhost:3000,"
        "http://127.0.0.1:3000,"
        "http://localhost:3001,"
        "http://127.0.0.1:3001"
    )

    # ChromaDB
    chroma_persist_dir: str = "./chroma_db"
    chroma_collection: str = "research_docs"

    # Agent limits
    max_search_results: int = 5
    max_rag_results: int = 5

    # Code sandbox
    code_sandbox_dir: str = "./.code_sandbox"
    code_sandbox_timeout: int = 120
    code_sandbox_python: str = ""

    # Sandbox security
    code_sandbox_policy: str = "standard"
    code_sandbox_max_memory_mb: int = 512
    code_sandbox_max_output_bytes: int = 1_048_576
    code_sandbox_max_files: int = 20
    code_sandbox_allow_network: bool = False
    code_sandbox_audit_log: bool = True

    # Local datasets
    dataset_root_dir: str = "./data"
    dataset_upload_dir: str = "./data/uploads"

    # LangSmith (optional)
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "multi-agent-research-assistant"


settings = Settings()
