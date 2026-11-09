from pydantic import BaseModel, validator
from typing import Optional
from datetime import datetime
import re

class UserRegister(BaseModel):
    username: str
    password: str
    
    @validator('username')
    def validate_username(cls, v):
        if not re.match(r'^[a-zA-Z0-9_]{3,20}$', v):
            raise ValueError('Username must be 3-20 characters, alphanumeric or underscore only')
        return v.lower()
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError('Password must be at least 6 characters')
        if not re.search(r'[a-zA-Z]', v):
            raise ValueError('Password must contain letters')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain numbers')
        return v

class UserLogin(BaseModel):
    username: str
    password: str
    
    @validator('username')
    def validate_username(cls, v):
        return v.lower()

class ProductCreate(BaseModel):
    product_name: str
    product_type: str
    description: str
    guidelines: Optional[str] = ""
    prerequisites: Optional[str] = ""
    price: float
    image_url: Optional[str] = ""
    product_file: Optional[str] = ""
    
    @validator('product_name')
    def validate_product_name(cls, v):
        if len(v) < 3:
            raise ValueError('Product name must be at least 3 characters')
        return v
    
    @validator('price')
    def validate_price(cls, v):
        if v <= 0:
            raise ValueError('Price must be greater than 0')
        return v
