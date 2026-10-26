"""Only process settings; no implicit dotenv, storage or provider configuration."""

import os
import sys
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    environment: Literal["development", "test"] = "development"
    host: Literal["127.0.0.1"] = "127.0.0.1"
    port: int = Field(default=8000, ge=1024, le=65535)

    @classmethod
    def load(cls, environ: Mapping[str, str] | None = None) -> Settings:
        source = os.environ if environ is None else environ
        values = {key[4:].lower(): value for key, value in source.items() if key.startswith("RPB_")}
        return cls.model_validate(values)


def load_process_settings() -> Settings:
    """CLI startup reports invalid settings without exposing environment values."""
    try:
        return Settings.load()
    except ValidationError:
        print("Invalid process configuration; startup refused.", file=sys.stderr)
        raise SystemExit(2) from None
