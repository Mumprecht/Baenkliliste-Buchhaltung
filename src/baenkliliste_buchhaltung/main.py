"""Hauptprogramm der Bänkliliste-Buchhaltung."""

from pathlib import Path

from qfieldcloud_sdk.sdk import FileTransferType

from .auth import setup_login
from .export import export_csv
from .qfieldcloud import create_client, load_token, load_username


PROJECT_ID = "aca32c7b-d721-4088-b43d-6802994a0f95"
REMOTE_GPKG = Path("Baenkli-Standorte.gpkg")

LOCAL_GPKG = Path("data/Baenkli-Standorte.gpkg")
OUTPUT_CSV = Path("output/Baenkliliste-Buchhaltung.csv")


def get_authenticated_client():
    """Erstellt einen angemeldeten QFieldCloud-Client."""
    username = load_username()

    if username:
        token = load_token(username)

        if token:
            return username, create_client(token)

        print(
            "Für den gespeicherten QFieldCloud-Benutzer wurde "
            "kein Token gefunden."
        )
    else:
        print("QFieldCloud ist auf diesem Computer noch nicht eingerichtet.")

    print()
    print("QFieldCloud-Anmeldung wird gestartet.")
    print()

    username = setup_login()
    token = load_token(username)

    if not token:
        raise RuntimeError(
            "Der QFieldCloud-Token konnte nach der Anmeldung "
            "nicht geladen werden."
        )

    return username, create_client(token)


def main() -> None:
    """Lädt die aktuellen Bänklidaten und erzeugt die Buchhaltungs-CSV."""
    print("Bänkliliste-Buchhaltung")
    print("======================")
    print()

    username, client = get_authenticated_client()

    LOCAL_GPKG.parent.mkdir(parents=True, exist_ok=True)

    print()
    print(f"QFieldCloud-Benutzer: {username}")
    print("QFieldCloud: Baenkli-Standorte.gpkg wird heruntergeladen ...")

    client.download_file(
        PROJECT_ID,
        FileTransferType.PROJECT,
        LOCAL_GPKG,
        REMOTE_GPKG,
        True,
    )

    print()
    print("CSV wird erzeugt ...")

    anzahl = export_csv(
        LOCAL_GPKG,
        OUTPUT_CSV,
    )

    print()
    print(f"Fertig: {anzahl} Datensätze exportiert.")
    print(f"CSV-Datei: {OUTPUT_CSV.resolve()}")


if __name__ == "__main__":
    main()
