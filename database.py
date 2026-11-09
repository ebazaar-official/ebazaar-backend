import os
import sqlite3
from sqlite3 import Error
from datetime import datetime

class Database:
    def __init__(self, db_file=None):
        self.db_file = db_file or os.getenv("DATABASE_PATH" , "digitalstore.db")
        self.init_database()
    
    def get_connection(self):
        try:
            conn = sqlite3.connect(self.db_file)
            conn.row_factory = sqlite3.Row
            return conn
        except Error as e:
            print(f"Database connection error: {e}")
            return None
    
    def init_database(self):
        conn = self.get_connection()
        if conn:
            cursor = conn.cursor()
            
            # USERS TABLE
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'buyer',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            
            # PRODUCTS TABLE
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS products (
                    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_name TEXT NOT NULL,
                    product_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    guidelines TEXT,
                    prerequisites TEXT,
                    price REAL NOT NULL,
                    image_url TEXT,
                    product_file TEXT,
                    file_size INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # CATEGORIES TABLE (NEW)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS categories (
                    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category_name TEXT UNIQUE NOT NULL,
                    category_slug TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # ORDERS TABLE
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    buyer_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # PAYMENTS TABLE
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT UNIQUE NOT NULL,
                    razorpay_payment_id TEXT UNIQUE,
                    user_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT DEFAULT 'INR',
                    status TEXT DEFAULT 'created',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
            ''')
            
            # PURCHASES TABLE
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS purchases (
                    purchase_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    payment_id TEXT,
                    amount REAL NOT NULL,
                    purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, product_id)
                )
            ''')
            
            # Migration: add file_size if missing
            cursor.execute("PRAGMA table_info(products)")
            columns = [col['name'] for col in cursor.fetchall()]
            if 'file_size' not in columns:
                print("⚠ Adding missing 'file_size' column to products table...")
                cursor.execute('ALTER TABLE products ADD COLUMN file_size INTEGER DEFAULT 0')
            
            # Seed default categories if empty
            cursor.execute('SELECT COUNT(*) as cnt FROM categories')
            count = cursor.fetchone()['cnt']
            
            if count == 0:
                print("✓ Seeding default categories...")
                default_categories = [
                    ('Browser Extension', 'extension'),
                    ('eBooks', 'ebooks'),
                    ('Templates', 'templates'),
                    ('AI Agents', 'ai_agents'),
                    ('Audio Books', 'audiobooks'),
                    ('Other', 'other')
                ]
                for name, slug in default_categories:
                    cursor.execute(
                        'INSERT INTO categories (category_name, category_slug) VALUES (?, ?)',
                        (name, slug)
                    )
            
            conn.commit()
            conn.close()
            print("✓ Database initialized (with categories)")

db = Database()
