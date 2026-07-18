"""
Setup Sandbox venv — สร้าง virtual environment สำหรับ sandbox พร้อม library จำเป็น
รันครั้งเดียว: python setup_sandbox_venv.py
"""

import os
import subprocess
import sys
from pathlib import Path

# รายการ library ตายตัว (ห้ามแก้โดยไม่ได้ตกลงกับทีม)
SANDBOX_PACKAGES = [
    "pygame",
    "numpy",
    "requests",
    "pandas",
    "flask",
    "pillow>=10.0.0",
]

# Path ของ venv
BASE_DIR = Path(__file__).parent
VENV_DIR = BASE_DIR / "sandbox_venv"


def create_venv():
    """สร้าง virtual environment"""
    if VENV_DIR.exists():
        print(f"⚠️ venv มีอยู่แล้วที่: {VENV_DIR}")
        print("ลบเก่าแล้วสร้างใหม่? (y/N): ", end="")
        response = input().strip().lower()
        if response != 'y':
            print("ยกเลิก")
            return False
        print("กำลังลบ venv เก่า...")
        import shutil
        shutil.rmtree(VENV_DIR)
    
    print(f"กำลังสร้าง venv ที่: {VENV_DIR}")
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    print("✅ สร้าง venv สำเร็จ")
    return True


def install_packages():
    """ติดตั้ง packages ใน venv"""
    # Path ของ pip ใน venv
    if os.name == 'nt':  # Windows
        pip_path = VENV_DIR / "Scripts" / "pip.exe"
        python_path = VENV_DIR / "Scripts" / "python.exe"
    else:  # Unix
        pip_path = VENV_DIR / "bin" / "pip"
        python_path = VENV_DIR / "bin" / "python"
    
    if not pip_path.exists():
        print(f"❌ pip ไม่พบที่: {pip_path}")
        return False
    
    print("กำลังอัปเกรด pip...")
    subprocess.run([str(pip_path), "install", "--upgrade", "pip"], check=True, capture_output=False)

    print(f"กำลังติดตั้ง packages: {', '.join(SANDBOX_PACKAGES)}")
    cmd = [str(pip_path), "install", "--only-binary=:all:"] + SANDBOX_PACKAGES
    result = subprocess.run(cmd, check=True, capture_output=False)
    print("✅ ติดตั้ง packages สำเร็จ")
    
    # ทดสอบ import pygame
    print("กำลังทดสอบ import pygame...")
    test_cmd = [str(python_path), "-c", "import pygame; print('pygame version:', pygame.version.ver)"]
    test_result = subprocess.run(test_cmd, capture_output=True, text=True)
    if test_result.returncode == 0:
        print(f"✅ {test_result.stdout.strip()}")
    else:
        print(f"⚠️ import pygame ล้มเหลว: {test_result.stderr}")
    
    return True


def main():
    print("=" * 60)
    print("Setup Sandbox venv สำหรับ Council Lab")
    print("=" * 60)
    
    if not create_venv():
        return
    
    if not install_packages():
        return
    
    print("\n" + "=" * 60)
    print("✅ Setup เสร็จสมบูรณ์")
    print(f"venv path: {VENV_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
