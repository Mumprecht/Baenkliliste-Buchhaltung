"""Anmeldung an QFieldCloud."""

from getpass import getpass

from .qfieldcloud import login, save_token, save_username


def setup_login() -> str:
    """Meldet den Benutzer an und speichert die Anmeldedaten sicher.

    Returns:
        Der erfolgreich angemeldete QFieldCloud-Benutzername.
    """
    username = input("QFieldCloud-Benutzername: ").strip()

    if not username:
        raise ValueError("Es wurde kein Benutzername eingegeben.")

    password = getpass("QFieldCloud-Passwort: ")

    client = login(username, password)

    if not client.token:
        raise RuntimeError("QFieldCloud hat keinen Token zurückgegeben.")

    save_token(username, client.token)
    save_username(username)

    print()
    print("QFieldCloud-Anmeldung erfolgreich.")
    print("Benutzername wurde lokal gespeichert.")
    print("Token wurde im Windows Credential Manager gespeichert.")

    return username
