import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
import bcrypt

# Set environment variable for test database to avoid messing with main db
os.environ["DATABASE_URL"] = "sqlite:///./test_chatbot.db"

from backend import database as db
from backend.main import is_strong_password, create_access_token, decode_access_token
from backend.translator import translator_engine

class TestWebRAGUpgrades(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure database is clean
        if os.path.exists("test_chatbot.db"):
            os.remove("test_chatbot.db")
        db.init_db()

    @classmethod
    def tearDownClass(cls):
        # Clean up database
        if os.path.exists("test_chatbot.db"):
            try:
                os.remove("test_chatbot.db")
            except PermissionError:
                pass

    def test_password_strength(self):
        # Weak passwords
        self.assertFalse(is_strong_password("short"))
        self.assertFalse(is_strong_password("nouppercase1!"))
        self.assertFalse(is_strong_password("NOLOWERCASE1!"))
        self.assertFalse(is_strong_password("NoNumber!"))
        self.assertFalse(is_strong_password("NoSpecialChar1"))
        # Strong password
        self.assertTrue(is_strong_password("StrongPassword123!"))

    def test_user_creation_and_lockout(self):
        email = "testuser@webrag.com"
        username = "testuser"
        pwd = "TestPassword123!"
        
        # Hash pwd
        pwd_hash = bcrypt.hashpw(pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        # Create user
        success = db.create_user(email, username, pwd_hash)
        self.assertTrue(success)
        
        # Verify user details
        user = db.get_user_by_email(email)
        self.assertIsNotNone(user)
        self.assertEqual(user["username"], username)
        self.assertEqual(user["failed_attempts"], 0)
        self.assertEqual(user["is_locked"], 0)
        
        # Failed login attempt 1
        db.increment_failed_attempts(email)
        user = db.get_user_by_email(email)
        self.assertEqual(user["failed_attempts"], 1)
        self.assertEqual(user["is_locked"], 0)
        
        # Failed login attempt 2
        db.increment_failed_attempts(email)
        user = db.get_user_by_email(email)
        self.assertEqual(user["failed_attempts"], 2)
        self.assertEqual(user["is_locked"], 0)
        
        # Failed login attempt 3 -> Lockout
        db.increment_failed_attempts(email)
        user = db.get_user_by_email(email)
        self.assertEqual(user["failed_attempts"], 3)
        self.assertEqual(user["is_locked"], 1)
        self.assertIsNotNone(user["lock_until"])
        
        # Reset failed attempts
        db.reset_failed_attempts(email)
        user = db.get_user_by_email(email)
        self.assertEqual(user["failed_attempts"], 0)
        self.assertEqual(user["is_locked"], 0)
        self.assertIsNone(user["lock_until"])

    def test_jwt_token_handling(self):
        email = "jwtuser@webrag.com"
        token = create_access_token(email, is_admin=0)
        self.assertIsNotNone(token)
        
        payload = decode_access_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["email"], email)
        self.assertEqual(payload["is_admin"], 0)

    def test_translation_engine(self):
        self.assertEqual(translator_engine.model_name, "facebook/nllb-200-distilled-600M")
        
        # Empty text
        res = translator_engine.translate("", "en", "hi")
        self.assertEqual(res, "")
        
        # Same language (doesn't load model)
        res_same = translator_engine.translate("Hello", "en", "en")
        self.assertEqual(res_same, "Hello")

if __name__ == "__main__":
    unittest.main()
