import bcrypt

BCRYPT_MAX_BYTES = 72


def validate_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError("Password must be at most 72 bytes")
    return password


def hash_password(password: str) -> str:
    validate_password(password)
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False
