# create methods to encrypt and decrypt any string using reversible encryption

from cryptography.fernet import Fernet
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import os

# Generate a key using PBKDF2
def _get_key():
    # Get salt and password from environment variables
    salt = os.getenv('ENCRYPTION_SALT', 'qualium_salt').encode()
    password = os.getenv('ENCRYPTION_PASSWORD', 'qualium_password').encode()
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password))
    return key

def encrypt_string(string):
    """
    Encrypt a string using Fernet symmetric encryption.
    
    Args:
        string (str): The string to encrypt
        
    Returns:
        str: The encrypted string in base64 format
    """
    if string is None:
        return None
    if not isinstance(string, str):
        raise TypeError("Input must be a string")
        
    f = Fernet(_get_key())
    encrypted_data = f.encrypt(string.encode())
    return encrypted_data.decode()

def decrypt_string(encrypted_string):
    """
    Decrypt a string that was encrypted using encrypt_string.
    
    Args:
        encrypted_string (str): The encrypted string in base64 format
        
    Returns:
        str: The decrypted string
    """
    if encrypted_string is None:
        return None
    if not isinstance(encrypted_string, str):
        raise TypeError("Input must be a string")
        
    f = Fernet(_get_key())
    decrypted_data = f.decrypt(encrypted_string.encode())
    return decrypted_data.decode()