from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    LLM_API_KEY: str
    LLM_BASE_URL: str
    LLM_MODEL: str
    LLM_MAX_COMPLETION_TOKENS: int = 4096

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{quote_plus(self.POSTGRES_USER)}"
            f":{quote_plus(self.POSTGRES_PASSWORD)}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()
