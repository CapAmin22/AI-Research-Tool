import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_title: str = "Agent Reach Vercel API"
    app_version: str = "1.0.0"
    
    # Keys injected by Vercel
    groq_api_key: str | None = None
    vm_host: str = "http://130.210.24.167:8000"
    vm_api_key: str = "change-me-to-a-random-string"

def get_settings() -> Settings:
    return Settings()
