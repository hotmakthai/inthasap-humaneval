import os
import sqlite3
import json
import ast

SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-prod")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")

def get_user(user_id):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    # [แก้บั๊ก 1] เปลี่ยนเป็น parameterized query ป้องกัน SQL Injection
    query = "SELECT * FROM users WHERE id = ?"
    cursor.execute(query, (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result

def load_data(data):
    # [แก้บั๊ก 4] เพิ่ม try-except จัดการ JSONDecodeError
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return None

def eval_expression(expr):
    # [แก้บั๊ก 5] ตรวจสอบชนิดข้อมูลที่คืนกลับมาว่าเป็นชนิดที่ปลอดภัย
    # ป้องกัน eval()/exec() โดยใช้ ast.literal_eval() เท่านั้น
    if not isinstance(expr, str):
        raise TypeError("Expression must be a string")
    # ห้ามใช้ eval() หรือ exec() โดยเด็ดขาด
    result = ast.literal_eval(expr)
    if isinstance(result, (int, float, str, bool, list, dict, tuple, type(None))):
        return result
    raise ValueError("Unsafe expression result type")

def calculate_total(items):
    total = 0
    # [แก้บั๊ก 6] เปลี่ยนเป็น loop แบบ Pythonic
    for item in items:
        total = total + item
    return total

def find_max(numbers):
    # [แก้บั๊ก 3] จัดการกรณี list ว่าง
    if not numbers:
        return None
    max_val = numbers[0]
    for n in numbers:
        if n > max_val:
            max_val = n
    return max_val

def process_file(filename):
    # [แก้บั๊ก 2] ใช้ os.path.basename() ป้องกัน Path Traversal
    safe_filename = os.path.basename(filename)
    # ตรวจสอบว่า safe_filename ไม่เป็น path ที่อันตราย
    if not safe_filename or safe_filename.startswith('.'):
        raise ValueError("Invalid filename")
    path = "uploads/" + safe_filename
    with open(path, "r") as f:
        return f.read()

class UserStore:
    def __init__(self):
        self.users = []
    
    def add(self, name, age):
        self.users.append({"name": name, "age": age})
    
    def find(self, name):
        for u in self.users:
            if u["name"] == name:
                return u
        return None
