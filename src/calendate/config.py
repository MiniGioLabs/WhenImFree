"""Configuration."""

from __future__ import annotations
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Core
    SECRET_KEY: str = "replace-me"
    BASE_URL: str = "http://localhost:8000"
    HTTPS_ONLY: bool = False
    DATABASE_PATH: str = ""
    TEMPLATES_DIR: str = ""
    STATIC_DIR: str = ""

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""

    # PostHog
    POSTHOG_API_KEY: str = ""
    POSTHOG_HOST: str = "https://us.posthog.com"

    # Google Maps
    GOOGLE_MAPS_API_KEY: str = ""

    # S3
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_BUCKET: str = ""
    AWS_REGION: str = "us-east-1"

    @property
    def twilio_configured(self) -> bool:
        return bool(self.TWILIO_ACCOUNT_SID and self.TWILIO_AUTH_TOKEN)

    @property
    def posthog_configured(self) -> bool:
        return bool(self.POSTHOG_API_KEY)

    @property
    def s3_configured(self) -> bool:
        return bool(self.AWS_ACCESS_KEY_ID and self.AWS_S3_BUCKET)

    @property
    def stripe_configured(self) -> bool:
        return bool(self.STRIPE_SECRET_KEY)

    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()
