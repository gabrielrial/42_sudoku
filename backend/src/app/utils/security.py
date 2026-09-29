
from pwdlib import PasswordHash

# HASH

_hasher = PasswordHash.recommended()

DUMMY_HASH = _hasher.hash("timing-equaliser")

def hash_password(password: str) -> str:
    return _hasher.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return _hasher.verify(password, password_hash)



