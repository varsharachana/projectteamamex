from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Credit Card Expense Categorization Agent"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/credit_card_agent"
    secret_key: str = "dev-secret-key-change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 120
    frontend_origin: str = "http://localhost:8000"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
