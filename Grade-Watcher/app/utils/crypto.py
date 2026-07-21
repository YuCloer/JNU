"""AES-256-GCM 加解密，密钥由 Windows DPAPI 保护"""
import os
import json
import ctypes
import ctypes.wintypes
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.utils.config import DATA_DIR

KEY_FILE = DATA_DIR / ".master_key"


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _dpapi_encrypt(data: bytes) -> bytes:
    blob_in = _DATA_BLOB(len(data), ctypes.create_string_buffer(data, len(data)))
    blob_out = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        raise OSError("DPAPI 加密失败")
    result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return result


def _dpapi_decrypt(data: bytes) -> bytes:
    blob_in = _DATA_BLOB(len(data), ctypes.create_string_buffer(data, len(data)))
    blob_out = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        raise OSError("DPAPI 解密失败")
    result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return result


def _get_master_key() -> bytes:
    """获取 AES 主密钥：首次生成随机 256-bit key，用 DPAPI 加密后存盘"""
    DATA_DIR.mkdir(exist_ok=True)
    if KEY_FILE.exists():
        return _dpapi_decrypt(KEY_FILE.read_bytes())
    key = AESGCM.generate_key(bit_length=256)
    KEY_FILE.write_bytes(_dpapi_encrypt(key))
    return key


def encrypt_json(obj, path: Path):
    """将 JSON 对象加密写入文件"""
    DATA_DIR.mkdir(exist_ok=True)
    plaintext = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    nonce = os.urandom(12)
    aesgcm = AESGCM(_get_master_key())
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    path.write_bytes(nonce + ciphertext)


def decrypt_json(path: Path):
    """从加密文件读取 JSON 对象，文件不存在返回 None"""
    if not path.exists():
        return None
    raw = path.read_bytes()
    nonce, ciphertext = raw[:12], raw[12:]
    aesgcm = AESGCM(_get_master_key())
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return json.loads(plaintext.decode("utf-8"))
