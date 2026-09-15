"""Zugriff auf QFieldCloud."""

from pathlib import Path

import keyring
from qfieldcloud_sdk import sdk


QFIELDCLOUD_URL = "https://app.qfield.cloud/api/v1/"
KEYRING_SERVICE = "Baenkliliste-Buchhaltung-QFieldCloud"

CONFIG_DIR = Path.home() / ".baenkliliste-buchhaltung"
USERNAME_FILE = CONFIG_DIR / "qfieldcloud-user.txt"


def create_client(token: str = "") -> sdk.Client:
    """Erstellt einen QFieldCloud-Client."""
    return sdk.Client(
        url=QFIELDCLOUD_URL,
        token=token,
        verify_ssl=True,
    )


def login(username: str, password: str) -> sdk.Client:
    """Meldet einen Benutzer bei QFieldCloud an."""
    client = create_client()
    client.login(username, password)
    return client


def save_token(username: str, token: str) -> None:
    """Speichert den QFieldCloud-Token im Windows Credential Manager."""
    keyring.set_password(KEYRING_SERVICE, username, token)


def load_token(username: str) -> str | None:
    """Liest den QFieldCloud-Token aus dem Windows Credential Manager."""
    return keyring.get_password(KEYRING_SERVICE, username)


def delete_token(username: str) -> None:
    """Löscht den lokal gespeicherten QFieldCloud-Token."""
    try:
        keyring.delete_password(KEYRING_SERVICE, username)
    except keyring.errors.PasswordDeleteError:
        pass


def save_username(username: str) -> None:
    """Speichert den zuletzt verwendeten QFieldCloud-Benutzernamen lokal."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    USERNAME_FILE.write_text(
        username.strip(),
        encoding="utf-8",
    )


def load_username() -> str | None:
    """Liest den zuletzt verwendeten QFieldCloud-Benutzernamen."""
    if not USERNAME_FILE.is_file():
        return None

    username = USERNAME_FILE.read_text(
        encoding="utf-8",
    ).strip()

    return username or None
