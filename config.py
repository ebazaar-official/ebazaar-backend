import os
import secrets
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Security: no predictable fallback. If missing, generate random (forces re-login on restart)
    SECRET_KEY = os.getenv("SECRET_KEY", "").strip() or secrets.token_urlsafe(48)
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    
    # Seller credentials - NO defaults, must come from .env
    SELLER_USERNAME = os.getenv("SELLER_USERNAME", "").strip()
    SELLER_PASSWORD = os.getenv("SELLER_PASSWORD", "").strip()
    
    # Razorpay
    RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "").strip()
    RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "").strip()

    def validate(self):
        """Fail-fast validation. Server refuses to start if required values are missing."""
        errors = []

        # SECRET_KEY must be present (auto-generated if missing, but warn if too weak)
        if not self.SECRET_KEY:
            errors.append("SECRET_KEY must be set in .env")

        # Seller username required
        if not self.SELLER_USERNAME:
            errors.append("SELLER_USERNAME must be set in .env")

        # Seller password required
        if not self.SELLER_PASSWORD:
            errors.append("SELLER_PASSWORD must be set in .env")

        if errors:
            print("=" * 62)
            print("❌ CRITICAL CONFIGURATION ERROR — SERVER WILL NOT START")
            print("=" * 62)
            for err in errors:
                print(f"   • {err}")
            print("=" * 62)
            print("Fix your backend/.env file and restart the server.")
            print("=" * 62)
            raise SystemExit(1)

settings = Settings()
settings.validate()

