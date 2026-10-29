import secrets
import string
from typing import Optional
from cryptography.fernet import Fernet
import base64

class SecurityUtils:
    """أدوات الأمان المساعدة"""
    
    @staticmethod
    def generate_api_key(length: int = 32) -> str:
        """إنشاء مفتاح API عشوائي"""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    @staticmethod
    def generate_secure_password(length: int = 16) -> str:
        """إنشاء كلمة مرور آمنة"""
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    @staticmethod
    def encrypt_api_secret(secret: str, encryption_key: str) -> str:
        """تشفير سر API"""
        if not encryption_key:
            raise ValueError("Encryption key is required")
        
        # تحويل المفتاح إلى صيغة Fernet
        key = base64.urlsafe_b64encode(encryption_key.encode().ljust(32)[:32])
        cipher = Fernet(key)
        encrypted = cipher.encrypt(secret.encode())
        return encrypted.decode()
    
    @staticmethod
    def decrypt_api_secret(encrypted_secret: str, encryption_key: str) -> str:
        """فك تشفير سر API"""
        if not encryption_key:
            raise ValueError("Encryption key is required")
        
        key = base64.urlsafe_b64encode(encryption_key.encode().ljust(32)[:32])
        cipher = Fernet(key)
        decrypted = cipher.decrypt(encrypted_secret.encode())
        return decrypted.decode()
    
    @staticmethod
    def validate_api_key_format(api_key: str) -> bool:
        """التحقق من تنسيق مفتاح API"""
        # يمكن إضافة تحقق أكثر تعقيداً حسب المنصة
        return len(api_key) >= 20
    
    @staticmethod
    def mask_sensitive_data(data: str, visible_chars: int = 4) -> str:
        """إخفاء البيانات الحساسة"""
        if len(data) <= visible_chars * 2:
            return "***"
        
        start = data[:visible_chars]
        end = data[-visible_chars:]
        masked = "*" * (len(data) - visible_chars * 2)
        return f"{start}{masked}{end}"