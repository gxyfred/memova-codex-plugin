from __future__ import annotations

import ctypes
import json
import platform
import shutil
import subprocess
from ctypes import wintypes
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Protocol

SERVICE_NAME = "ai.memova.codex-conversation-collector"


class CredentialStore(Protocol):
    def get(self, account: str) -> str | None: ...

    def set(self, account: str, secret: str) -> None: ...

    def delete(self, account: str) -> None: ...


@dataclass
class MemoryCredentialStore:
    values: dict[str, str] = field(default_factory=dict)

    def get(self, account: str) -> str | None:
        return self.values.get(account)

    def set(self, account: str, secret: str) -> None:
        self.values[account] = secret

    def delete(self, account: str) -> None:
        self.values.pop(account, None)


ERR_SEC_ITEM_NOT_FOUND = -25300


@lru_cache(maxsize=1)
def _macos_frameworks() -> tuple[ctypes.CDLL, ctypes.CDLL]:
    try:
        security = ctypes.CDLL(
            "/System/Library/Frameworks/Security.framework/Security"
        )
        core_foundation = ctypes.CDLL(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )
    except OSError as exc:
        raise RuntimeError(
            "macOS Security.framework is unavailable; refusing plaintext fallback."
        ) from exc

    security.SecKeychainOpen.argtypes = [
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    security.SecKeychainOpen.restype = ctypes.c_int32
    security.SecKeychainFindGenericPassword.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    security.SecKeychainFindGenericPassword.restype = ctypes.c_int32
    security.SecKeychainAddGenericPassword.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    security.SecKeychainAddGenericPassword.restype = ctypes.c_int32
    security.SecKeychainItemModifyAttributesAndData.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    security.SecKeychainItemModifyAttributesAndData.restype = ctypes.c_int32
    security.SecKeychainItemDelete.argtypes = [ctypes.c_void_p]
    security.SecKeychainItemDelete.restype = ctypes.c_int32
    security.SecKeychainItemFreeContent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    security.SecKeychainItemFreeContent.restype = ctypes.c_int32
    core_foundation.CFRelease.argtypes = [ctypes.c_void_p]
    core_foundation.CFRelease.restype = None
    return security, core_foundation


class MacOSCredentialStore:
    """Use Security.framework directly so token material never enters process argv."""

    def __init__(self, *, keychain_path: str | None = None) -> None:
        self.keychain_path = keychain_path

    def _open_keychain(self) -> tuple[ctypes.c_void_p | None, bool]:
        if self.keychain_path is None:
            return None, False
        security, _ = _macos_frameworks()
        keychain = ctypes.c_void_p()
        status = security.SecKeychainOpen(
            self.keychain_path.encode("utf-8"), ctypes.byref(keychain)
        )
        if status != 0:
            raise RuntimeError("Unable to open the configured macOS Keychain.")
        return keychain, True

    @staticmethod
    def _release(reference: ctypes.c_void_p | None) -> None:
        if reference is not None and reference.value:
            _, core_foundation = _macos_frameworks()
            core_foundation.CFRelease(reference)

    def get(self, account: str) -> str | None:
        security, _ = _macos_frameworks()
        service = SERVICE_NAME.encode("utf-8")
        encoded_account = account.encode("utf-8")
        password_length = ctypes.c_uint32()
        password_data = ctypes.c_void_p()
        item = ctypes.c_void_p()
        keychain, release_keychain = self._open_keychain()
        try:
            status = security.SecKeychainFindGenericPassword(
                keychain,
                len(service),
                service,
                len(encoded_account),
                encoded_account,
                ctypes.byref(password_length),
                ctypes.byref(password_data),
                ctypes.byref(item),
            )
            if status == ERR_SEC_ITEM_NOT_FOUND:
                return None
            if status != 0:
                raise RuntimeError(
                    "Unable to read the Collector credential from macOS Keychain."
                )
            return ctypes.string_at(password_data, password_length.value).decode("utf-8")
        finally:
            if password_data.value:
                security.SecKeychainItemFreeContent(None, password_data)
            self._release(item)
            if release_keychain:
                self._release(keychain)

    def set(self, account: str, secret: str) -> None:
        security, _ = _macos_frameworks()
        service = SERVICE_NAME.encode("utf-8")
        encoded_account = account.encode("utf-8")
        encoded_secret = secret.encode("utf-8")
        item = ctypes.c_void_p()
        keychain, release_keychain = self._open_keychain()
        try:
            status = security.SecKeychainFindGenericPassword(
                keychain,
                len(service),
                service,
                len(encoded_account),
                encoded_account,
                None,
                None,
                ctypes.byref(item),
            )
            if status == 0:
                status = security.SecKeychainItemModifyAttributesAndData(
                    item,
                    None,
                    len(encoded_secret),
                    encoded_secret,
                )
            elif status == ERR_SEC_ITEM_NOT_FOUND:
                status = security.SecKeychainAddGenericPassword(
                    keychain,
                    len(service),
                    service,
                    len(encoded_account),
                    encoded_account,
                    len(encoded_secret),
                    encoded_secret,
                    ctypes.byref(item),
                )
            if status != 0:
                raise RuntimeError(
                    "Unable to store the Collector credential in macOS Keychain."
                )
        finally:
            self._release(item)
            if release_keychain:
                self._release(keychain)

    def delete(self, account: str) -> None:
        security, _ = _macos_frameworks()
        service = SERVICE_NAME.encode("utf-8")
        encoded_account = account.encode("utf-8")
        item = ctypes.c_void_p()
        keychain, release_keychain = self._open_keychain()
        try:
            status = security.SecKeychainFindGenericPassword(
                keychain,
                len(service),
                service,
                len(encoded_account),
                encoded_account,
                None,
                None,
                ctypes.byref(item),
            )
            if status == ERR_SEC_ITEM_NOT_FOUND:
                return
            if status != 0 or security.SecKeychainItemDelete(item) != 0:
                raise RuntimeError(
                    "Unable to delete the Collector credential from macOS Keychain."
                )
        finally:
            self._release(item)
            if release_keychain:
                self._release(keychain)


class LinuxCredentialStore:
    def _require_binary(self) -> str:
        binary = shutil.which("secret-tool")
        if binary is None:
            raise RuntimeError(
                "Secret Service command `secret-tool` is unavailable; refusing plaintext fallback."
            )
        return binary

    def get(self, account: str) -> str | None:
        completed = subprocess.run(
            [self._require_binary(), "lookup", "service", SERVICE_NAME, "account", account],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return None
        value = completed.stdout.rstrip("\n")
        return value or None

    def set(self, account: str, secret: str) -> None:
        completed = subprocess.run(
            [
                self._require_binary(),
                "store",
                "--label",
                "Memova Codex Collector",
                "service",
                SERVICE_NAME,
                "account",
                account,
            ],
            input=secret,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("Unable to store the Collector credential in Secret Service.")

    def delete(self, account: str) -> None:
        completed = subprocess.run(
            [self._require_binary(), "clear", "service", SERVICE_NAME, "account", account],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode not in {0, 1}:
            raise RuntimeError("Unable to delete the Collector credential from Secret Service.")


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


class WindowsCredentialStore:
    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2
    ERROR_NOT_FOUND = 1168

    @staticmethod
    def _target(account: str) -> str:
        return f"{SERVICE_NAME}:{account}"

    def get(self, account: str) -> str | None:
        credential_pointer = ctypes.POINTER(_CREDENTIALW)()
        result = ctypes.windll.advapi32.CredReadW(
            self._target(account),
            self.CRED_TYPE_GENERIC,
            0,
            ctypes.byref(credential_pointer),
        )
        if not result:
            if ctypes.windll.kernel32.GetLastError() == self.ERROR_NOT_FOUND:
                return None
            raise RuntimeError("Unable to read the Collector credential from Credential Manager.")
        try:
            credential = credential_pointer.contents
            raw = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
            return raw.decode("utf-16-le")
        finally:
            ctypes.windll.advapi32.CredFree(credential_pointer)

    def set(self, account: str, secret: str) -> None:
        raw = secret.encode("utf-16-le")
        buffer = ctypes.create_string_buffer(raw)
        credential = _CREDENTIALW()
        credential.Type = self.CRED_TYPE_GENERIC
        credential.TargetName = self._target(account)
        credential.CredentialBlobSize = len(raw)
        credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = self.CRED_PERSIST_LOCAL_MACHINE
        credential.UserName = account
        if not ctypes.windll.advapi32.CredWriteW(ctypes.byref(credential), 0):
            raise RuntimeError("Unable to store the Collector credential in Credential Manager.")

    def delete(self, account: str) -> None:
        result = ctypes.windll.advapi32.CredDeleteW(
            self._target(account), self.CRED_TYPE_GENERIC, 0
        )
        if not result and ctypes.windll.kernel32.GetLastError() != self.ERROR_NOT_FOUND:
            raise RuntimeError("Unable to delete the Collector credential from Credential Manager.")


def system_credential_store(system: str | None = None) -> CredentialStore:
    normalized = (system or platform.system()).lower()
    if normalized == "darwin":
        return MacOSCredentialStore()
    if normalized == "windows":
        return WindowsCredentialStore()
    if normalized == "linux":
        return LinuxCredentialStore()
    raise RuntimeError(f"No supported OS credential store exists for {normalized!r}.")


def encode_secret(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def decode_secret(value: str) -> dict:
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise RuntimeError("Stored Collector credential has an invalid format.")
    return decoded
