"""Authentication module with Argon2id password hashing and JWT tokens"""
import os
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import jwt, JWTError
import psycopg2
from psycopg2.extras import RealDictCursor

SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = int(os.getenv("TOKEN_EXPIRE_HOURS", "24"))

ph = PasswordHasher(
    time_cost=2,
    memory_cost=65536,
    parallelism=1,
    hash_len=32,
    salt_len=16
)

def get_db_connection():
    """Get database connection"""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable is required")
    return psycopg2.connect(db_url, cursor_factory=RealDictCursor)

def hash_password(password: str) -> str:
    """Hash password with Argon2id"""
    return ph.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash"""
    try:
        ph.verify(password_hash, password)
        return True
    except VerifyMismatchError:
        return False

def hash_token(token: str) -> str:
    """Hash session token with SHA256 for fast lookup"""
    return hashlib.sha256(token.encode()).hexdigest()

def create_session_token() -> str:
    """Generate secure session token"""
    return secrets.token_urlsafe(32)

def create_jwt_token(user_id: str, email: str) -> str:
    """Create JWT access token"""
    expire = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": user_id,
        "email": email,
        "exp": expire,
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_jwt_token(token: str) -> Optional[dict]:
    """Verify and decode JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

def create_user(email: str, password: str) -> Optional[dict]:
    """Create new user with hashed password"""
    password_hash = hash_password(password)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("""
                    INSERT INTO users (email, password_hash)
                    VALUES (%s, %s)
                    RETURNING id, email, created_at, role
                """, (email.lower(), password_hash))
                user = cur.fetchone()
                conn.commit()
                return dict(user)
            except psycopg2.IntegrityError:
                conn.rollback()
                return None

def authenticate_user(email: str, password: str) -> Optional[dict]:
    """Authenticate user by email and password"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, email, password_hash, role, is_active
                FROM users WHERE email = %s
            """, (email.lower(),))
            user = cur.fetchone()

            if not user:
                return None
            if not user['is_active']:
                return None
            if not verify_password(password, user['password_hash']):
                return None

            # Update last login
            cur.execute("""
                UPDATE users SET last_login = NOW() WHERE id = %s
            """, (user['id'],))
            conn.commit()

            return {
                "id": str(user['id']),
                "email": user['email'],
                "role": user['role']
            }

def create_session(user_id: str, ip_address: str = None, user_agent: str = None) -> str:
    """Create session and return token"""
    token = create_session_token()
    token_hash = hash_token(token)
    expires_at = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_sessions (user_id, token_hash, expires_at, ip_address, user_agent)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, token_hash, expires_at, ip_address, user_agent))
            conn.commit()

    return token

def verify_session(token: str) -> Optional[dict]:
    """Verify session token and return user info"""
    token_hash = hash_token(token)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT s.user_id, s.expires_at, u.email, u.role
                FROM user_sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.token_hash = %s AND s.expires_at > NOW() AND u.is_active = TRUE
            """, (token_hash,))
            session = cur.fetchone()

            if not session:
                return None

            return {
                "id": str(session['user_id']),
                "email": session['email'],
                "role": session['role']
            }

def invalidate_session(token: str) -> bool:
    """Invalidate session token (logout)"""
    token_hash = hash_token(token)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM user_sessions WHERE token_hash = %s
            """, (token_hash,))
            deleted = cur.rowcount > 0
            conn.commit()
            return deleted

def cleanup_expired_sessions():
    """Remove expired sessions"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_sessions WHERE expires_at < NOW()")
            conn.commit()
