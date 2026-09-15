"""Grafische Benutzeroberfläche der Bänkliliste-Buchhaltung."""

import os
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, QSettings, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qfieldcloud_sdk.sdk import FileTransferType

from .export import export_csv
from .qfieldcloud import create_client, load_token, load_username


PROJECT_ID = "aca32c7b-d721-4088-b43d-6802994a0f95"
REMOTE_GPKG = Path("Baenkli-Standorte.gpkg")
LOCAL_GPKG = Path("data/Baenkli-Standorte.gpkg")

ORGANIZATION_NAME = "Mumprecht Software"
APPLICATION_NAME = "Baenkliliste-Buchhaltung"


class ExportWorker(QObject):
    """Führt QFieldCloud-Download und CSV-Export im Hintergrund aus."""

    status_changed = Signal(str)
    finished = Signal(int, str)
    failed = Signal(str)

    def __init__(self, output_csv: Path) -> None:
        super().__init__()
        self.output_csv = output_csv

    def run(self) -> None:
        """Startet Download und Export."""
        try:
            username = load_username()

            if not username:
                raise RuntimeError(
                    "QFieldCloud ist auf diesem Computer noch nicht eingerichtet."
                )

            token = load_token(username)

            if not token:
                raise RuntimeError(
                    "Für den gespeicherten QFieldCloud-Benutzer wurde "
                    "kein Token gefunden."
                )

            client = create_client(token)

            LOCAL_GPKG.parent.mkdir(parents=True, exist_ok=True)

            self.status_changed.emit(
                "Aktuelle Daten werden aus QFieldCloud geladen ..."
            )

            client.download_file(
                PROJECT_ID,
                FileTransferType.PROJECT,
                LOCAL_GPKG,
                REMOTE_GPKG,
                False,
            )

            self.status_changed.emit("CSV-Datei wird erstellt ...")

            anzahl = export_csv(
                LOCAL_GPKG,
                self.output_csv,
            )

            self.finished.emit(anzahl, str(self.output_csv.resolve()))

        except PermissionError:
            self.failed.emit(
                "Die CSV-Datei kann nicht geschrieben werden.\n\n"
                "Bitte prüfen, ob die Datei in Excel oder einem anderen "
                "Programm geöffnet ist."
            )

        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    """Hauptfenster der Anwendung."""

    def __init__(self) -> None:
        super().__init__()

        self.thread = None
        self.worker = None

        self.settings = QSettings(
            ORGANIZATION_NAME,
            APPLICATION_NAME,
        )

        self.output_dir = self.load_output_dir()

        self.setWindowTitle("Bänkliliste-Buchhaltung")

        icon_path = (
            Path(__file__).resolve().parents[2]
            / "resources"
            / "Baenkliliste-Buchhaltung.png"
        )
        self.setWindowIcon(QIcon(str(icon_path)))

        self.resize(600, 390)

        title = QLabel("Bänkliliste-Buchhaltung")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        description = QLabel(
            "Aktuelle Bänklidaten aus QFieldCloud laden\n"
            "und für die Buchhaltung als CSV-Datei exportieren."
        )
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.output_label = QLabel()
        self.output_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.output_label.setWordWrap(True)
        self.update_output_label()

        self.select_folder_button = QPushButton(
            "Ausgabeordner auswählen ..."
        )
        self.select_folder_button.clicked.connect(
            self.select_output_folder
        )

        self.export_button = QPushButton(
            "Daten aus QFieldCloud laden und CSV erstellen"
        )
        self.export_button.clicked.connect(self.start_export)

        self.folder_button = QPushButton("CSV-Ordner öffnen")
        self.folder_button.clicked.connect(self.open_output_folder)

        self.status_label = QLabel("Bereit")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout()
        layout.setContentsMargins(40, 35, 40, 35)
        layout.setSpacing(16)

        layout.addWidget(title)
        layout.addWidget(description)
        layout.addStretch()

        layout.addWidget(self.output_label)
        layout.addWidget(self.select_folder_button)

        layout.addSpacing(8)

        layout.addWidget(self.export_button)
        layout.addWidget(self.folder_button)

        layout.addStretch()
        layout.addWidget(self.status_label)

        container = QWidget()
        container.setLayout(layout)

        self.setCentralWidget(container)

    def load_output_dir(self) -> Path:
        """Lädt den zuletzt gewählten Ausgabeordner."""
        saved_dir = self.settings.value("output_dir", "")

        if saved_dir:
            path = Path(str(saved_dir))

            if path.is_dir():
                return path

        downloads = Path.home() / "Downloads"

        if downloads.is_dir():
            return downloads

        return Path.home()

    def save_output_dir(self) -> None:
        """Speichert den gewählten Ausgabeordner."""
        self.settings.setValue(
            "output_dir",
            str(self.output_dir),
        )

    def update_output_label(self) -> None:
        """Aktualisiert die Anzeige des Ausgabeordners."""
        self.output_label.setText(
            f"Ausgabeordner:\n{self.output_dir}"
        )

    def select_output_folder(self) -> None:
        """Lässt den Benutzer den Ausgabeordner auswählen."""
        selected = QFileDialog.getExistingDirectory(
            self,
            "Ausgabeordner auswählen",
            str(self.output_dir),
        )

        if not selected:
            return

        self.output_dir = Path(selected)
        self.save_output_dir()
        self.update_output_label()

    def create_output_filename(self) -> Path:
        """Erzeugt den Dateinamen mit aktuellem Datum und Uhrzeit."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

        return (
            self.output_dir
            / f"{timestamp}_Baenkliliste-Buchhaltung.csv"
        )

    def start_export(self) -> None:
        """Startet Download und Export in einem Hintergrundthread."""
        output_csv = self.create_output_filename()

        self.export_button.setEnabled(False)
        self.select_folder_button.setEnabled(False)
        self.folder_button.setEnabled(False)

        self.status_label.setText("Export wird vorbereitet ...")

        self.thread = QThread()
        self.worker = ExportWorker(output_csv)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)

        self.worker.status_changed.connect(self.status_label.setText)
        self.worker.finished.connect(self.export_finished)
        self.worker.failed.connect(self.export_failed)

        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)

        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.thread_finished)

        self.thread.start()

    def export_finished(self, anzahl: int, filename: str) -> None:
        """Verarbeitet einen erfolgreichen Export."""
        self.status_label.setText(
            f"{anzahl} Datensätze erfolgreich exportiert."
        )

        QMessageBox.information(
            self,
            "Export abgeschlossen",
            "Die CSV-Datei wurde erfolgreich erstellt.\n\n"
            f"Exportierte Datensätze: {anzahl}\n\n"
            f"Datei:\n{filename}",
        )

    def export_failed(self, message: str) -> None:
        """Zeigt einen Fehler beim Export an."""
        self.status_label.setText("Export fehlgeschlagen.")

        QMessageBox.critical(
            self,
            "Fehler beim Export",
            message,
        )

    def thread_finished(self) -> None:
        """Räumt den abgeschlossenen Hintergrundthread auf."""
        self.export_button.setEnabled(True)
        self.select_folder_button.setEnabled(True)
        self.folder_button.setEnabled(True)

        self.worker = None
        self.thread = None

    def open_output_folder(self) -> None:
        """Öffnet den aktuell gewählten Ausgabeordner."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(self.output_dir)


def run_gui() -> None:
    """Startet die grafische Benutzeroberfläche."""
    app = QApplication(sys.argv)

    app.setOrganizationName(ORGANIZATION_NAME)
    app.setApplicationName(APPLICATION_NAME)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    run_gui()
