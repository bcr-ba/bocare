"""Runtime settings: values from app/config/settings.yml, overridable per machine by environment
variables or the .env file at the repository root (same name, upper case). Defaults live in the
YAML file only; this class declares names and types."""
from functools import lru_cache
from pathlib import Path
from typing import Literal, Tuple, Type

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

ROOT_DIR = Path(__file__).resolve().parents[3]  # repository root
SETTINGS_FILE = Path(__file__).resolve().parents[1] / "config" / "settings.yml"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", env_file_encoding="utf-8", extra="ignore",
                                      yaml_file=SETTINGS_FILE, yaml_file_encoding="utf-8")

    # Language model
    llm_provider: Literal["ollama", "openrouter"]
    llm_temperature: float
    llm_max_tokens: int
    ollama_url: str
    ollama_model: str
    ollama_fallback_model: str
    ollama_num_ctx: int
    ollama_timeout_seconds: float
    ollama_keep_alive: str
    ollama_warm_up_timeout_seconds: float
    ollama_health_timeout_seconds: float
    openrouter_api_key: str = ""  # secret: set it in .env, never in settings.yml
    openrouter_model: str
    openrouter_url: str
    llm_timeout_seconds: float

    # Verification
    llm_max_attempts: int
    judge_enabled: bool
    judge_min_level: int
    judge_max_tokens: int

    # Retrieval
    medlineplus_url: str
    medlineplus_database: str
    retrieval_timeout_seconds: float
    retrieval_cache_ttl_seconds: float
    retrieval_max_snippet_chars: int
    retrieval_results_per_term: int
    retrieval_max_sources: int

    # Corpus
    medlineplus_export_page: str
    corpus_raw_file: Path
    corpus_chunks_file: Path
    chunk_target_chars: int
    chunk_max_synonyms: int

    # Semantic retrieval
    retriever: Literal["dense", "medlineplus_api"]
    embedding_provider: Literal["ollama", "fastembed"]
    embedding_model: str
    embedding_query_instruction: str
    embedding_batch_size: int
    embedding_num_ctx: int
    embedding_timeout_seconds: float
    index_dir: Path
    dense_candidates: int

    # Conversation
    default_language: Literal["fr", "en"]

    # State
    state_backend: Literal["sqlite", "memory"]
    state_db_file: Path
    session_retention_days: float

    # Tracing
    tracing_exporter: Literal["none", "console", "otlp"]
    tracing_otlp_endpoint: str
    tracing_service_name: str

    # API
    rate_limit_per_minute: int
    log_level: str

    @classmethod
    def settings_customise_sources(
        cls, settings_cls: Type[BaseSettings], init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource, dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        # Highest priority first: explicit arguments, environment, .env, then settings.yml.
        return init_settings, env_settings, dotenv_settings, YamlConfigSettingsSource(settings_cls)


@lru_cache
def get_settings() -> Settings:
    return Settings()
