from datetime import datetime, timedelta
from typing import Optional
from jose import jwt, JWTError
from passlib.context import CryptContext
from config import settings
from database import db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthHandler:
    @staticmethod
    def hash_password(password: str) -> str:
        return pwd_context.hash(password)
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def create_access_token(data: dict) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire, "type": "access"})
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    
    @staticmethod
    def create_refresh_token(data: dict) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire, "type": "refresh"})
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    
    @staticmethod
    def decode_token(token: str) -> Optional[dict]:
        try:
            return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        except JWTError:
            return None
    
    @staticmethod
    def create_user(username: str, password: str) -> Optional[dict]:
        conn = db.get_connection()
        if not conn:
            return {"error": "Database connection failed"}
        
        cursor = conn.cursor()
        
        # Block reserved seller username from being registered
        if username == settings.SELLER_USERNAME:
            conn.close()
            return {"error": "This username is reserved"}
        
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            conn.close()
            return {"error": "Username already exists"}
        
        password_hash = AuthHandler.hash_password(password)
        
        cursor.execute('''
            INSERT INTO users (username, password_hash, role)
            VALUES (?, ?, 'buyer')
        ''', (username, password_hash))
        
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        
        return {
            "id": user_id,
            "username": username,
            "role": "buyer"
        }
    
    @staticmethod
    def authenticate_user(username: str, password: str) -> Optional[dict]:
        # 1. Check seller credentials from .env FIRST
        if username == settings.SELLER_USERNAME:
            if password == settings.SELLER_PASSWORD:
                return {
                    "id": 1,
                    "username": username,
                    "role": "seller"
                }
            else:
                # Seller username entered but wrong password - REJECT immediately
                # Do NOT fall back to database check
                return None
        
        # 2. Buyer check from database (only for non-seller usernames)
        conn = db.get_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()
            conn.close()
            
            if user and AuthHandler.verify_password(password, user['password_hash']):
                return {
                    "id": user['id'],
                    "username": user['username'],
                    "role": user['role']
                }
        
        return None

auth_handler = AuthHandler()
