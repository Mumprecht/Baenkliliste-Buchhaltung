"""Aufbereitung und CSV-Export der Bänklidaten für die Buchhaltung."""

import csv
import sqlite3
from datetime import date
from pathlib import Path


CSV_FIELDS = [
    "Nr.",
    "Objekt",
    "Standort",
    "Objektart",
    "Sponsor",
    "Sponsorart",
    "Ort",
    "Laufzeit",
    "Bezahlt bis",
    "Status",
]


def laufzeit(vermietung: str | None) -> str:
    """Ermittelt die Laufzeit anhand der Vermietungsart."""
    if vermietung is None:
        return ""

    wert = vermietung.strip()

    if wert == "nicht vermietet":
        return ""

    if wert == "Firma":
        return "5 Jahre"

    return "10 Jahre"


def status(mietende: str | None, heute: date | None = None) -> str:
    """Ermittelt den Buchhaltungsstatus anhand des Mietendes."""
    if not mietende:
        return "Nicht vergeben"

    if heute is None:
        heute = date.today()

    ende = date.fromisoformat(mietende)

    if heute > ende:
        return "Abgelaufen"

    if ende.year == heute.year and ende.month == 12 and ende.day == 31:
        return "Läuft bald ab"

    return "Aktiv"


def format_datum(datum: str | None) -> str:
    """Formatiert ein ISO-Datum als TT.MM.JJJJ."""
    if not datum:
        return ""

    wert = date.fromisoformat(datum)
    return wert.strftime("%d.%m.%Y")


def export_csv(
    quelle: Path,
    ziel: Path,
    heute: date | None = None,
) -> int:
    """Erzeugt die CSV-Datei für die Bänkliverwaltung/Buchhaltung.

    Returns:
        Anzahl exportierter Datensätze.
    """
    quelle = Path(quelle)
    ziel = Path(ziel)

    if heute is None:
        heute = date.today()

    if not quelle.is_file():
        raise FileNotFoundError(f"GeoPackage nicht gefunden: {quelle}")

    ziel.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(
        f"file:{quelle.resolve().as_posix()}?mode=ro",
        uri=True,
    )
    con.row_factory = sqlite3.Row

    try:
        rows = con.execute(
            '''
            SELECT
                Banknummer,
                Ort,
                Sponsor,
                Vermietung,
                Wohnort,
                Mietende
            FROM "Baenkli-Standorte"
            ORDER BY Banknummer
            '''
        ).fetchall()

        with ziel.open("w", encoding="utf-8-sig", newline="") as csvfile:
            writer = csv.DictWriter(
                csvfile,
                fieldnames=CSV_FIELDS,
                delimiter=";",
            )

            writer.writeheader()

            for row in rows:
                writer.writerow(
                    {
                        "Nr.": row["Banknummer"],
                        "Objekt": f"Ruhebänkli Nr. {row['Banknummer']}",
                        "Standort": row["Ort"] or "",
                        "Objektart": "Bank",
                        "Sponsor": row["Sponsor"] or "",
                        "Sponsorart": row["Vermietung"] or "",
                        "Ort": row["Wohnort"] or "",
                        "Laufzeit": laufzeit(row["Vermietung"]),
                        "Bezahlt bis": format_datum(row["Mietende"]),
                        "Status": status(row["Mietende"], heute),
                    }
                )

        return len(rows)

    finally:
        con.close()
