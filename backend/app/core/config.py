from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/paperpush"
    SECRET_KEY: str = "change-this-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24h

    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # Agent 层文件存储根目录（PDF / 文本文件）
    # 生产环境建议挂载持久化卷并通过 .env 覆盖
    STORAGE_DIR: str = "./storage"


settings = Settings()
