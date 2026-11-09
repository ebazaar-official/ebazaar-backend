from fastapi import FastAPI, Request, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime
import uvicorn
import os
import shutil
import sqlite3
from passlib.context import CryptContext
from pydantic import BaseModel

from config import settings
from database import db
from models import UserRegister, UserLogin, ProductCreate
from auth import auth_handler
from razorpay_handler import razorpay_handler

app = FastAPI(title="eBazaar API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

os.makedirs("resources/images", exist_ok=True)
os.makedirs("resources/product", exist_ok=True)
app.mount("/resources", StaticFiles(directory="resources"), name="resources")

@app.on_event("startup")
async def startup_event():
    print("=" * 50)
    print("eBazaar API Starting...")
    print("=" * 50)
    
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    seller_hash = pwd_context.hash(settings.SELLER_PASSWORD)
    
    conn = db.get_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users (username, password_hash, role)
            VALUES (?, ?, 'seller')
        ''', (settings.SELLER_USERNAME, seller_hash))
        conn.commit()
        conn.close()
        print("✓ Seller ready: admin / admin123")
    
    if settings.RAZORPAY_KEY_ID:
        print("✓ Razorpay configured (Test Mode)")
    else:
        print("⚠ Razorpay NOT configured")
    
    print("✓ API Ready")
    print("=" * 50)

# ============ REQUEST MODELS ============

class CreateOrderRequest(BaseModel):
    product_id: int

class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str

class CategoryCreate(BaseModel):
    category_name: str
    category_slug: str

# ============ HELPER ============

def get_user_from_token(request: Request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    token = auth_header.split(' ')[1]
    payload = auth_handler.decode_token(token)
    if not payload:
        return None
    return payload.get("user_id")

# ============ AUTH ENDPOINTS ============

@app.post("/api/auth/register")
async def register(user: UserRegister):
    result = auth_handler.create_user(user.username, user.password)
    
    if result and "error" in result:
        return JSONResponse(status_code=400, content={"detail": result["error"]})
    
    if not result:
        return JSONResponse(status_code=500, content={"detail": "Registration failed"})
    
    access_token = auth_handler.create_access_token({
        "user_id": result["id"],
        "username": result["username"]
    })
    refresh_token = auth_handler.create_refresh_token({"user_id": result["id"]})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": result
    }

@app.post("/api/auth/login")
async def login(user: UserLogin):
    user_data = auth_handler.authenticate_user(user.username, user.password)
    
    if not user_data:
        return JSONResponse(status_code=401, content={"detail": "Invalid username or password"})
    
    access_token = auth_handler.create_access_token({
        "user_id": user_data["id"],
        "username": user_data["username"],
        "role": user_data["role"]
    })
    refresh_token = auth_handler.create_refresh_token({"user_id": user_data["id"]})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user_data
    }

@app.get("/api/auth/me")
async def get_me(request: Request):
    user_id = get_user_from_token(request)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        return JSONResponse(status_code=404, content={"detail": "User not found"})
    
    return {
        "id": user['id'],
        "username": user['username'],
        "role": user['role'],
        "created_at": user['created_at']
    }

# ============ CATEGORY ENDPOINTS ============

@app.get("/api/categories")
async def get_categories():
    conn = db.get_connection()
    if not conn:
        return JSONResponse(status_code=500, content={"detail": "Database error"})
    
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM categories ORDER BY category_id ASC')
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for c in rows:
        result.append({
            "category_id": c['category_id'],
            "category_name": c['category_name'],
            "category_slug": c['category_slug']
        })
    return result

@app.post("/api/categories/create")
async def create_category(category: CategoryCreate, request: Request):
    user_id = get_user_from_token(request)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user or user['role'] != 'seller':
        conn.close()
        return JSONResponse(status_code=403, content={"detail": "Only admins can manage categories"})
    
    name = category.category_name.strip()
    slug = category.category_slug.strip().lower()
    
    if not name or not slug:
        conn.close()
        return JSONResponse(status_code=400, content={"detail": "Name and slug required"})
    
    if not slug.replace('_', '').isalnum():
        conn.close()
        return JSONResponse(status_code=400, content={"detail": "Slug must be alphanumeric with underscores"})
    
    try:
        cursor.execute(
            'INSERT INTO categories (category_name, category_slug) VALUES (?, ?)',
            (name, slug)
        )
        conn.commit()
        cat_id = cursor.lastrowid
        conn.close()
        
        print(f"✓ Category created: {name} ({slug})")
        return {"category_id": cat_id, "message": "Category created"}
    except sqlite3.IntegrityError:
        conn.close()
        return JSONResponse(status_code=400, content={"detail": "Category already exists"})

@app.delete("/api/categories/delete/{category_id}")
async def delete_category(category_id: int, request: Request):
    user_id = get_user_from_token(request)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT role FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user or user['role'] != 'seller':
        conn.close()
        return JSONResponse(status_code=403, content={"detail": "Only admins can manage categories"})
    
    cursor.execute('SELECT * FROM categories WHERE category_id = ?', (category_id,))
    category = cursor.fetchone()
    
    if not category:
        conn.close()
        return JSONResponse(status_code=404, content={"detail": "Category not found"})
    
    slug = category['category_slug']
    
    cursor.execute('SELECT * FROM products WHERE product_type = ?', (slug,))
    products = cursor.fetchall()
    
    deleted_count = len(products)
    
    for p in products:
        if p['image_url'] and os.path.exists(p['image_url']):
            try:
                os.remove(p['image_url'])
            except: pass
        if p['product_file'] and os.path.exists(p['product_file']):
            try:
                os.remove(p['product_file'])
            except: pass
    
    cursor.execute('DELETE FROM products WHERE product_type = ?', (slug,))
    cursor.execute('DELETE FROM categories WHERE category_id = ?', (category_id,))
    
    conn.commit()
    conn.close()
    
    print(f"✓ Category deleted: {category['category_name']} (removed {deleted_count} products)")
    
    return {
        "message": "Category deleted",
        "deleted_products": deleted_count
    }

# ============ PRODUCT ENDPOINTS ============

@app.post("/api/products/create")
async def create_product(
    request: Request,
    product_name: str = Form(...),
    product_type: str = Form(...),
    description: str = Form(...),
    guidelines: str = Form(""),
    prerequisites: str = Form(""),
    price: float = Form(...),
    image: UploadFile = File(None),
    product_file: UploadFile = File(None)
):
    print(f"\n📦 Creating product: {product_name}")
    
    image_url = ""
    if image and image.filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{image.filename}"
        image_path = f"resources/images/{filename}"
        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        image_url = image_path
    
    product_file_path = ""
    file_size = 0
    if product_file and product_file.filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{product_file.filename}"
        file_path = f"resources/product/{filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(product_file.file, buffer)
        product_file_path = file_path
        file_size = os.path.getsize(file_path)
        print(f"   ✓ Product file: {file_path} ({file_size} bytes)")
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO products (product_name, product_type, description, guidelines, prerequisites, price, image_url, product_file, file_size)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (product_name, product_type, description, guidelines or "", prerequisites or "", price, image_url, product_file_path, file_size))
    
    conn.commit()
    product_id = cursor.lastrowid
    conn.close()
    
    return {"product_id": product_id, "message": "Product created successfully"}

@app.get("/api/products/count")
async def get_product_count():
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM products')
    result = cursor.fetchone()
    conn.close()
    return {"count": result['count'] if result else 0}

@app.get("/api/products")
async def get_all_products():
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products ORDER BY created_at DESC')
    products = cursor.fetchall()
    conn.close()
    
    result = []
    for p in products:
        result.append({
            "product_id": p['product_id'],
            "product_name": p['product_name'],
            "product_type": p['product_type'],
            "description": p['description'],
            "guidelines": p['guidelines'],
            "prerequisites": p['prerequisites'],
            "price": p['price'],
            "image_url": p['image_url'],
            "product_file": p['product_file'],
            "file_size": p['file_size'] if 'file_size' in p.keys() else 0,
            "created_at": p['created_at']
        })
    return result

@app.get("/api/products/{product_id}")
async def get_product(product_id: int):
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products WHERE product_id = ?', (product_id,))
    p = cursor.fetchone()
    conn.close()
    
    if not p:
        return JSONResponse(status_code=404, content={"detail": "Product not found"})
    
    return {
        "product_id": p['product_id'],
        "product_name": p['product_name'],
        "product_type": p['product_type'],
        "description": p['description'],
        "guidelines": p['guidelines'],
        "prerequisites": p['prerequisites'],
        "price": p['price'],
        "image_url": p['image_url'],
        "product_file": p['product_file'],
        "file_size": p['file_size'] if 'file_size' in p.keys() else 0,
        "created_at": p['created_at']
    }

@app.put("/api/products/update/{product_id}")
async def update_product(
    product_id: int,
    product_name: str = Form(...),
    product_type: str = Form(...),
    description: str = Form(...),
    guidelines: str = Form(""),
    prerequisites: str = Form(""),
    price: float = Form(...),
    image: UploadFile = File(None),
    product_file: UploadFile = File(None)
):
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products WHERE product_id = ?', (product_id,))
    existing = cursor.fetchone()
    
    if not existing:
        conn.close()
        return JSONResponse(status_code=404, content={"detail": "Product not found"})
    
    image_url = existing['image_url'] if existing['image_url'] else ""
    if image and image.filename:
        if existing['image_url'] and os.path.exists(existing['image_url']):
            os.remove(existing['image_url'])
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{image.filename}"
        image_path = f"resources/images/{filename}"
        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        image_url = image_path
    
    product_file_path = existing['product_file'] if existing['product_file'] else ""
    file_size = existing['file_size'] if 'file_size' in existing.keys() else 0
    if product_file and product_file.filename:
        if existing['product_file'] and os.path.exists(existing['product_file']):
            os.remove(existing['product_file'])
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{product_file.filename}"
        file_path = f"resources/product/{filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(product_file.file, buffer)
        product_file_path = file_path
        file_size = os.path.getsize(file_path)
    
    cursor.execute('''
        UPDATE products 
        SET product_name = ?, product_type = ?, description = ?, guidelines = ?, prerequisites = ?, price = ?, image_url = ?, product_file = ?, file_size = ?
        WHERE product_id = ?
    ''', (product_name, product_type, description, guidelines, prerequisites, price, image_url, product_file_path, file_size, product_id))
    
    conn.commit()
    conn.close()
    return {"message": "Product updated successfully"}

@app.delete("/api/products/delete/{product_id}")
async def delete_product(product_id: int):
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products WHERE product_id = ?', (product_id,))
    product = cursor.fetchone()
    
    if not product:
        conn.close()
        return JSONResponse(status_code=404, content={"detail": "Product not found"})
    
    if product['image_url'] and os.path.exists(product['image_url']):
        os.remove(product['image_url'])
    if product['product_file'] and os.path.exists(product['product_file']):
        os.remove(product['product_file'])
    
    cursor.execute('DELETE FROM products WHERE product_id = ?', (product_id,))
    conn.commit()
    conn.close()
    return {"message": "Product deleted successfully"}

# ============ RAZORPAY PAYMENT ============

@app.post("/api/payment/create-order")
async def create_payment_order(request: Request, order_data: CreateOrderRequest):
    user_id = get_user_from_token(request)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products WHERE product_id = ?', (order_data.product_id,))
    product = cursor.fetchone()
    
    if not product:
        conn.close()
        return JSONResponse(status_code=404, content={"detail": "Product not found"})
    
    cursor.execute('SELECT * FROM purchases WHERE user_id = ? AND product_id = ?', (user_id, order_data.product_id))
    if cursor.fetchone():
        conn.close()
        return JSONResponse(status_code=400, content={"detail": "You already own this product"})
    
    amount = product['price']
    receipt_id = f"rcpt_{user_id}_{order_data.product_id}_{int(datetime.now().timestamp())}"
    notes = {
        "user_id": str(user_id),
        "product_id": str(order_data.product_id),
        "product_name": product['product_name']
    }
    
    razorpay_order = razorpay_handler.create_order(amount, receipt_id, notes)
    
    if not razorpay_order:
        conn.close()
        return JSONResponse(status_code=500, content={"detail": "Failed to create order"})
    
    cursor.execute('''
        INSERT INTO payments (order_id, user_id, product_id, amount, status)
        VALUES (?, ?, ?, ?, 'created')
    ''', (razorpay_order['id'], user_id, order_data.product_id, amount))
    
    conn.commit()
    conn.close()
    
    return {
        "order_id": razorpay_order['id'],
        "amount": razorpay_order['amount'],
        "currency": razorpay_order['currency'],
        "key_id": settings.RAZORPAY_KEY_ID,
        "product_name": product['product_name']
    }

@app.post("/api/payment/verify")
async def verify_payment(request: Request, verify_data: VerifyPaymentRequest):
    user_id = get_user_from_token(request)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    
    is_valid = razorpay_handler.verify_payment_signature(
        verify_data.razorpay_order_id,
        verify_data.razorpay_payment_id,
        verify_data.razorpay_signature
    )
    
    if not is_valid:
        return JSONResponse(status_code=400, content={"detail": "Payment verification failed"})
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE payments 
        SET razorpay_payment_id = ?, status = 'captured', completed_at = ?
        WHERE order_id = ? AND user_id = ?
    ''', (verify_data.razorpay_payment_id, datetime.now(), verify_data.razorpay_order_id, user_id))
    
    cursor.execute('SELECT product_id, amount FROM payments WHERE order_id = ?', (verify_data.razorpay_order_id,))
    payment = cursor.fetchone()
    
    if payment:
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO purchases (user_id, product_id, payment_id, amount)
                VALUES (?, ?, ?, ?)
            ''', (user_id, payment['product_id'], verify_data.razorpay_payment_id, payment['amount']))
        except Exception as e:
            print(f"Purchase record error: {e}")
    
    cursor.execute('''
        SELECT p.product_name, p.product_file, p.file_size FROM payments py
        JOIN products p ON py.product_id = p.product_id
        WHERE py.order_id = ?
    ''', (verify_data.razorpay_order_id,))
    result = cursor.fetchone()
    conn.commit()
    conn.close()
    
    return {
        "status": "success",
        "message": "Payment received successfully",
        "payment_id": verify_data.razorpay_payment_id,
        "order_id": verify_data.razorpay_order_id,
        "product_name": result['product_name'] if result else "",
        "product_file": result['product_file'] if result else "",
        "file_size": result['file_size'] if result and 'file_size' in result.keys() else 0
    }

# ============ PURCHASES / DELIVERY ============

@app.get("/api/purchases/my-products")
async def get_my_purchases(request: Request):
    user_id = get_user_from_token(request)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.*, pu.purchased_at
        FROM purchases pu
        JOIN products p ON pu.product_id = p.product_id
        WHERE pu.user_id = ?
        ORDER BY pu.purchased_at DESC
    ''', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for p in rows:
        result.append({
            "product_id": p['product_id'],
            "product_name": p['product_name'],
            "product_type": p['product_type'],
            "description": p['description'],
            "price": p['price'],
            "image_url": p['image_url'],
            "file_size": p['file_size'] if 'file_size' in p.keys() else 0,
            "purchased_at": p['purchased_at']
        })
    return result

@app.get("/api/purchases/check/{product_id}")
async def check_purchase(product_id: int, request: Request):
    user_id = get_user_from_token(request)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM purchases WHERE user_id = ? AND product_id = ?', (user_id, product_id))
    purchase = cursor.fetchone()
    conn.close()
    
    return {"owned": purchase is not None}

@app.get("/api/purchases/download/{product_id}")
async def download_product(product_id: int, request: Request):
    user_id = get_user_from_token(request)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM purchases WHERE user_id = ? AND product_id = ?', (user_id, product_id))
    if not cursor.fetchone():
        conn.close()
        return JSONResponse(status_code=403, content={"detail": "You don't own this product"})
    
    cursor.execute('SELECT * FROM products WHERE product_id = ?', (product_id,))
    product = cursor.fetchone()
    conn.close()
    
    if not product or not product['product_file']:
        return JSONResponse(status_code=404, content={"detail": "Product file not found"})
    
    file_path = product['product_file']
    if not os.path.exists(file_path):
        return JSONResponse(status_code=404, content={"detail": "File missing on server"})
    
    original_filename = os.path.basename(file_path)
    parts = original_filename.split('_', 2)
    if len(parts) >= 3:
        original_filename = parts[2]
    
    return FileResponse(
        path=file_path,
        filename=original_filename,
        media_type='application/octet-stream'
    )

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/")
async def root():
    return {"message": "eBazaar API", "docs": "/docs"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
