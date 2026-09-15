"""Moderne grafische Benutzeroberfläche der Bänkliste-Buchhaltung."""

import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QThread, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from qfieldcloud_sdk import sdk
from qfieldcloud_sdk.sdk import FileTransferType

from .export import export_csv
from .qfieldcloud import (
    QFIELDCLOUD_URL,
    create_client,
    load_token,
    load_username,
    save_token,
    save_username,
)


PROJECT_ID = "aca32c7b-d721-4088-b43d-6802994a0f95"
REMOTE_GPKG = Path("Baenkli-Standorte.gpkg")
LOCAL_GPKG = Path("data/Baenkli-Standorte.gpkg")

ORGANIZATION_NAME = "Mumprecht Software"
APPLICATION_NAME = "Baenkliliste-Buchhaltung"


class LoginDialog(QDialog):
    """Dialog für die QFieldCloud-Anmeldung."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setWindowTitle("QFieldCloud-Anmeldung")
        self.setModal(True)
        self.setMinimumWidth(450)

        info = QLabel(
            "Melden Sie sich mit Ihrem persönlichen "
            "QFieldCloud-Konto an."
        )
        info.setWordWrap(True)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText(
            "Benutzername oder E-Mail-Adresse"
        )

        saved_username = load_username()

        if saved_username:
            self.username_edit.setText(saved_username)

        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Passwort")
        self.password_edit.setEchoMode(
            QLineEdit.EchoMode.Password
        )

        form = QFormLayout()
        form.setSpacing(12)
        form.addRow("Benutzername:", self.username_edit)
        form.addRow("Passwort:", self.password_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )

        buttons.button(
            QDialogButtonBox.StandardButton.Ok
        ).setText("Anmelden")

        buttons.button(
            QDialogButtonBox.StandardButton.Cancel
        ).setText("Abbrechen")

        buttons.accepted.connect(self.validate_input)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.setContentsMargins(28, 25, 28, 25)
        layout.setSpacing(18)

        layout.addWidget(info)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self.setLayout(layout)

        if saved_username:
            self.password_edit.setFocus()
        else:
            self.username_edit.setFocus()

    def validate_input(self) -> None:
        """Prüft die Eingaben."""
        if not self.username():
            QMessageBox.warning(
                self,
                "QFieldCloud-Anmeldung",
                "Bitte einen Benutzernamen eingeben.",
            )
            self.username_edit.setFocus()
            return

        if not self.password():
            QMessageBox.warning(
                self,
                "QFieldCloud-Anmeldung",
                "Bitte das Passwort eingeben.",
            )
            self.password_edit.setFocus()
            return

        self.accept()

    def username(self) -> str:
        return self.username_edit.text().strip()

    def password(self) -> str:
        return self.password_edit.text()


class ExportWorker(QObject):
    """Führt Download, Prüfung und CSV-Export im Hintergrund aus."""

    status_changed = Signal(str)
    step_changed = Signal(int, str)
    finished = Signal(int, str)
    failed = Signal(str)

    def __init__(
        self,
        token: str,
        output_csv: Path,
    ) -> None:
        super().__init__()
        self.token = token
        self.output_csv = output_csv

    def validate_data(self) -> tuple[int, list[str]]:
        """Prüft die heruntergeladenen Bänklidaten."""
        if not LOCAL_GPKG.is_file():
            raise RuntimeError(
                "Das heruntergeladene GeoPackage wurde nicht gefunden."
            )

        con = sqlite3.connect(
            f"file:{LOCAL_GPKG.as_posix()}?mode=ro",
            uri=True,
        )

        try:
            rows = con.execute(
                '''
                SELECT
                    fid,
                    Banknummer,
                    Ort,
                    Vermietung,
                    Mietende
                FROM "Baenkli-Standorte"
                ORDER BY fid
                '''
            ).fetchall()
        finally:
            con.close()

        errors: list[str] = []

        if not rows:
            errors.append(
                "Das GeoPackage enthält keine Datensätze."
            )
            return 0, errors

        erlaubte_vermietungen = {
            "Firma",
            "Privat",
            "VVH",
            "Verein",
            "nicht vermietet",
        }

        for fid, banknummer, ort, vermietung, mietende in rows:
            if banknummer is None:
                errors.append(
                    f"Datensatz {fid}: Banknummer fehlt."
                )

            if vermietung not in erlaubte_vermietungen:
                errors.append(
                    f"Datensatz {fid}: unbekannte Vermietungsart "
                    f"'{vermietung}'."
                )

            if mietende:
                try:
                    datetime.strptime(
                        str(mietende),
                        "%Y-%m-%d",
                    )
                except ValueError:
                    errors.append(
                        f"Datensatz {fid}: ungültiges Mietende "
                        f"'{mietende}'."
                    )

        return len(rows), errors

    def run(self) -> None:
        """Führt den vollständigen Export aus."""
        try:
            client = create_client(self.token)

            LOCAL_GPKG.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            self.output_csv.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            self.step_changed.emit(
                1,
                "Daten werden aus QFieldCloud geladen",
            )

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

            self.step_changed.emit(
                2,
                "Daten werden geprüft",
            )

            self.status_changed.emit(
                "Daten werden geprüft ..."
            )

            anzahl, errors = self.validate_data()

            if errors:
                details = "\n".join(
                    f"• {error}"
                    for error in errors[:20]
                )

                if len(errors) > 20:
                    details += (
                        f"\n• ... und "
                        f"{len(errors) - 20} weitere Fehler."
                    )

                raise RuntimeError(
                    "Die Datenprüfung wurde nicht bestanden.\n\n"
                    f"{details}"
                )

            self.step_changed.emit(
                3,
                f"{anzahl} Datensätze geprüft",
            )

            self.status_changed.emit(
                "CSV-Datei wird erstellt ..."
            )

            anzahl = export_csv(
                LOCAL_GPKG,
                self.output_csv,
            )

            self.step_changed.emit(
                4,
                "CSV-Datei erfolgreich erstellt",
            )

            self.finished.emit(
                anzahl,
                str(self.output_csv.resolve()),
            )

        except PermissionError:
            self.failed.emit(
                "Die CSV-Datei konnte nicht geschrieben werden.\n\n"
                "Bitte prüfen Sie, ob die Datei in Excel oder "
                "einem anderen Programm geöffnet ist."
            )

        except Exception as exc:
            self.failed.emit(str(exc))


class StatusRow(QFrame):
    """Eine Statuszeile."""

    def __init__(self, text: str) -> None:
        super().__init__()

        self.icon_label = QLabel("○")
        self.icon_label.setObjectName("statusIcon")
        self.icon_label.setFixedWidth(20)

        self.text_label = QLabel(text)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(8)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)
        layout.addStretch()

        self.setLayout(layout)

    def set_pending(self) -> None:
        self.icon_label.setText("○")

    def set_active(self) -> None:
        self.icon_label.setText("●")

    def set_done(self) -> None:
        self.icon_label.setText("✓")

    def set_error(self) -> None:
        self.icon_label.setText("!")


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

        self.setWindowTitle(
            "Bänkliste-Buchhaltung"
        )

        icon_path = (
            Path(__file__).resolve().parents[2]
            / "resources"
            / "Baenkliliste-Buchhaltung.png"
        )

        self.setWindowIcon(
            QIcon(str(icon_path))
        )

        self.setMinimumSize(680, 800)
        self.resize(720, 860)

        self.build_ui()
        self.apply_style()
        self.update_user_display()
        self.update_output_display()
        self.update_preview_filename()
        self.load_last_export()

    def build_ui(self) -> None:
        """Erzeugt die Oberfläche."""
        central = QWidget()

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(
            30,
            25,
            30,
            25,
        )
        main_layout.setSpacing(14)

        # Kopf
        header = QFrame()
        header.setObjectName("headerCard")
        header.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(
            20,
            16,
            20,
            16,
        )

        icon_path = (
            Path(__file__).resolve().parents[2]
            / "resources"
            / "Baenkliliste-Buchhaltung.png"
        )

        header_icon = QLabel()
        header_icon.setPixmap(
            QIcon(str(icon_path)).pixmap(54, 54)
        )
        header_icon.setFixedSize(54, 54)

        title_layout = QVBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)

        title = QLabel(
            "Bänkliste-Buchhaltung"
        )
        title.setObjectName("title")

        subtitle = QLabel(
            "QFieldCloud → Buchhaltung"
        )
        subtitle.setObjectName("subtitle")

        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)

        header_layout.addWidget(header_icon)
        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        header.setLayout(header_layout)

        main_layout.addWidget(header)

        # QFieldCloud
        cloud_card = self.create_card(118)

        cloud_layout = QVBoxLayout()
        cloud_layout.setContentsMargins(
            20,
            16,
            20,
            16,
        )
        cloud_layout.setSpacing(8)

        cloud_title = QLabel("QFIELDCLOUD")
        cloud_title.setObjectName("sectionTitle")

        self.user_label = QLabel()
        self.user_label.setObjectName("infoValue")

        self.login_button = QPushButton(
            "Anmeldung ändern ..."
        )
        self.login_button.setObjectName(
            "secondaryButton"
        )
        self.login_button.setFixedHeight(34)
        self.login_button.clicked.connect(
            self.change_login
        )

        cloud_layout.addWidget(cloud_title)
        cloud_layout.addWidget(self.user_label)
        cloud_layout.addWidget(self.login_button)

        cloud_card.setLayout(cloud_layout)
        main_layout.addWidget(cloud_card)

        # Export
        export_card = self.create_card(245)

        export_layout = QVBoxLayout()
        export_layout.setContentsMargins(
            20,
            16,
            20,
            16,
        )
        export_layout.setSpacing(7)

        export_title = QLabel("DATENEXPORT")
        export_title.setObjectName("sectionTitle")

        self.record_label = QLabel(
            "Datensätze: noch nicht ermittelt"
        )
        self.record_label.setObjectName("infoValue")

        output_caption = QLabel("Ausgabeordner")
        output_caption.setObjectName("fieldCaption")

        self.output_label = QLabel()
        self.output_label.setObjectName("pathLabel")
        self.output_label.setWordWrap(True)
        self.output_label.setMinimumHeight(34)

        self.select_folder_button = QPushButton(
            "Ausgabeordner auswählen ..."
        )
        self.select_folder_button.setObjectName(
            "secondaryButton"
        )
        self.select_folder_button.setFixedHeight(32)
        self.select_folder_button.clicked.connect(
            self.select_output_folder
        )

        file_caption = QLabel("Datei")
        file_caption.setObjectName("fieldCaption")

        self.filename_label = QLabel()
        self.filename_label.setObjectName("pathLabel")
        self.filename_label.setWordWrap(True)
        self.filename_label.setMinimumHeight(34)

        export_layout.addWidget(export_title)
        export_layout.addWidget(self.record_label)
        export_layout.addSpacing(2)
        export_layout.addWidget(output_caption)
        export_layout.addWidget(self.output_label)
        export_layout.addWidget(
            self.select_folder_button
        )
        export_layout.addSpacing(2)
        export_layout.addWidget(file_caption)
        export_layout.addWidget(
            self.filename_label
        )

        export_card.setLayout(export_layout)
        main_layout.addWidget(export_card)

        # Hauptbutton
        self.export_button = QPushButton(
            "Daten aktualisieren und exportieren"
        )
        self.export_button.setObjectName(
            "primaryButton"
        )
        self.export_button.setFixedHeight(50)
        self.export_button.clicked.connect(
            self.start_export
        )

        main_layout.addWidget(
            self.export_button
        )

        # Status
        progress_card = self.create_card(155)

        progress_layout = QVBoxLayout()
        progress_layout.setContentsMargins(
            20,
            14,
            20,
            14,
        )
        progress_layout.setSpacing(3)

        progress_title = QLabel("STATUS")
        progress_title.setObjectName("sectionTitle")

        self.status_download = StatusRow(
            "Daten aus QFieldCloud laden"
        )

        self.status_validate = StatusRow(
            "Daten prüfen"
        )

        self.status_export = StatusRow(
            "CSV-Datei erstellen"
        )

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 4)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(7)

        self.status_label = QLabel("Bereit")
        self.status_label.setObjectName(
            "statusText"
        )

        progress_layout.addWidget(progress_title)
        progress_layout.addWidget(
            self.status_download
        )
        progress_layout.addWidget(
            self.status_validate
        )
        progress_layout.addWidget(
            self.status_export
        )
        progress_layout.addSpacing(4)
        progress_layout.addWidget(
            self.progress_bar
        )
        progress_layout.addWidget(
            self.status_label
        )

        progress_card.setLayout(progress_layout)
        main_layout.addWidget(progress_card)

        # Letzter Export
        last_card = self.create_card(135)

        last_layout = QVBoxLayout()
        last_layout.setContentsMargins(
            20,
            14,
            20,
            14,
        )
        last_layout.setSpacing(5)

        last_title = QLabel("LETZTER EXPORT")
        last_title.setObjectName("sectionTitle")

        self.last_export_label = QLabel(
            "Noch kein Export durchgeführt."
        )
        self.last_export_label.setObjectName(
            "lastExport"
        )
        self.last_export_label.setWordWrap(True)

        self.folder_button = QPushButton(
            "CSV-Ordner öffnen"
        )
        self.folder_button.setObjectName(
            "secondaryButton"
        )
        self.folder_button.setFixedHeight(32)
        self.folder_button.clicked.connect(
            self.open_output_folder
        )

        last_layout.addWidget(last_title)
        last_layout.addWidget(
            self.last_export_label
        )
        last_layout.addWidget(
            self.folder_button
        )

        last_card.setLayout(last_layout)
        main_layout.addWidget(last_card)

        main_layout.addStretch(1)

        central.setLayout(main_layout)
        self.setCentralWidget(central)

    def create_card(self, minimum_height: int) -> QFrame:
        """Erzeugt eine Card mit fester Mindesthöhe."""
        card = QFrame()
        card.setObjectName("card")
        card.setMinimumHeight(minimum_height)
        card.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        return card

    def apply_style(self) -> None:
        """Setzt das Erscheinungsbild."""
        self.setStyleSheet(
            """
            QMainWindow {
                background: #f5f6f8;
            }

            QWidget {
                font-family: "Segoe UI";
                font-size: 10pt;
                color: #25282d;
            }

            #headerCard {
                background: white;
                border: 1px solid #e0e3e7;
                border-radius: 12px;
            }

            #title {
                font-size: 20pt;
                font-weight: 600;
            }

            #subtitle {
                color: #68717c;
                font-size: 10pt;
            }

            #card {
                background: white;
                border: 1px solid #e0e3e7;
                border-radius: 12px;
            }

            #sectionTitle {
                color: #626b75;
                font-size: 9pt;
                font-weight: 700;
                letter-spacing: 1px;
            }

            #infoValue {
                font-size: 10.5pt;
                font-weight: 500;
            }

            #fieldCaption {
                color: #747d87;
                font-size: 9pt;
                font-weight: 600;
            }

            #pathLabel {
                background: #f7f8fa;
                border: 1px solid #e4e7eb;
                border-radius: 6px;
                padding: 6px 8px;
                color: #3f4750;
            }

            #primaryButton {
                background: #2f6fed;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 11pt;
                font-weight: 600;
            }

            #primaryButton:hover {
                background: #245dcc;
            }

            #primaryButton:pressed {
                background: #1e50b5;
            }

            #primaryButton:disabled {
                background: #aeb9ca;
            }

            #secondaryButton {
                background: #f1f3f5;
                color: #30363d;
                border: 1px solid #d8dde3;
                border-radius: 7px;
                padding: 5px 12px;
            }

            #secondaryButton:hover {
                background: #e8ebef;
            }

            #secondaryButton:disabled {
                color: #9aa1a9;
                background: #f5f6f7;
            }

            #statusIcon {
                font-size: 11pt;
                font-weight: 700;
            }

            #statusText {
                color: #59636e;
                padding-top: 2px;
            }

            #lastExport {
                color: #4e5761;
            }

            QProgressBar {
                background: #e8ebef;
                border: none;
                border-radius: 3px;
            }

            QProgressBar::chunk {
                background: #2f6fed;
                border-radius: 3px;
            }

            QDialog {
                background: #f5f6f8;
            }

            QLineEdit {
                background: white;
                border: 1px solid #ccd2d9;
                border-radius: 6px;
                padding: 7px;
            }

            QLineEdit:focus {
                border: 1px solid #2f6fed;
            }

            QDialogButtonBox QPushButton {
                min-width: 90px;
                padding: 7px 14px;
                border-radius: 6px;
            }
            """
        )

    def load_output_dir(self) -> Path:
        """Lädt den zuletzt gewählten Ausgabeordner."""
        saved_dir = self.settings.value(
            "output_dir",
            "",
        )

        if saved_dir:
            path = Path(str(saved_dir))

            if path.is_dir():
                return path

        downloads = Path.home() / "Downloads"

        if downloads.is_dir():
            return downloads

        return Path.home()

    def save_output_dir(self) -> None:
        self.settings.setValue(
            "output_dir",
            str(self.output_dir),
        )

    def update_user_display(self) -> None:
        """Aktualisiert die QFieldCloud-Anzeige."""
        username = load_username()

        if username and load_token(username):
            self.user_label.setText(
                f"●  {username}"
            )
        else:
            self.user_label.setText(
                "○  Nicht angemeldet"
            )

    def update_output_display(self) -> None:
        self.output_label.setText(
            str(self.output_dir)
        )

    def update_preview_filename(self) -> None:
        timestamp = datetime.now().strftime(
            "%Y-%m-%d_%H%M%S"
        )

        self.filename_label.setText(
            f"{timestamp}_Baenkliste-Buchhaltung.csv"
        )

    def select_output_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Ausgabeordner auswählen",
            str(self.output_dir),
        )

        if not selected:
            return

        self.output_dir = Path(selected)
        self.save_output_dir()
        self.update_output_display()

    def create_output_filename(self) -> Path:
        timestamp = datetime.now().strftime(
            "%Y-%m-%d_%H%M%S"
        )

        return (
            self.output_dir
            / f"{timestamp}_Baenkliste-Buchhaltung.csv"
        )

    def reset_status(self) -> None:
        self.status_download.set_pending()
        self.status_validate.set_pending()
        self.status_export.set_pending()

        self.progress_bar.setValue(0)
        self.status_label.setText(
            "Export wird vorbereitet ..."
        )

    def update_step(
        self,
        step: int,
        text: str,
    ) -> None:
        rows = [
            self.status_download,
            self.status_validate,
            self.status_export,
        ]

        for index, row in enumerate(rows, start=1):
            if index < step:
                row.set_done()
            elif index == step:
                row.set_active()
            else:
                row.set_pending()

        self.progress_bar.setValue(step)
        self.status_label.setText(text)

    def change_login(self) -> None:
        dialog = LoginDialog(self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        username = dialog.username()
        password = dialog.password()

        QApplication.setOverrideCursor(
            Qt.CursorShape.WaitCursor
        )

        try:
            client = sdk.Client(
                url=QFIELDCLOUD_URL,
                verify_ssl=True,
            )

            client.login(
                username,
                password,
            )

            if not client.token:
                raise RuntimeError(
                    "QFieldCloud hat keinen Token zurückgegeben."
                )

            save_token(
                username,
                client.token,
            )

            save_username(username)

        except Exception as exc:
            QMessageBox.critical(
                self,
                "QFieldCloud-Anmeldung fehlgeschlagen",
                "Die Anmeldung bei QFieldCloud ist "
                "fehlgeschlagen.\n\n"
                f"{exc}",
            )
            return

        finally:
            QApplication.restoreOverrideCursor()

        self.update_user_display()

        QMessageBox.information(
            self,
            "QFieldCloud-Anmeldung",
            "Die Anmeldung war erfolgreich.\n\n"
            f"Benutzer: {username}",
        )

    def start_export(self) -> None:
        username = load_username()

        if not username or not load_token(username):
            self.change_login()

            username = load_username()

            if not username:
                return

        token = load_token(username)

        if not token:
            QMessageBox.critical(
                self,
                "QFieldCloud-Anmeldung",
                "Es konnte kein QFieldCloud-Token gefunden werden.",
            )
            return

        output_csv = self.create_output_filename()

        self.reset_status()

        self.export_button.setEnabled(False)
        self.select_folder_button.setEnabled(False)
        self.folder_button.setEnabled(False)
        self.login_button.setEnabled(False)

        self.thread = QThread()

        self.worker = ExportWorker(
            token,
            output_csv,
        )

        self.worker.moveToThread(
            self.thread
        )

        self.thread.started.connect(
            self.worker.run
        )

        self.worker.status_changed.connect(
            self.status_label.setText
        )

        self.worker.step_changed.connect(
            self.update_step
        )

        self.worker.finished.connect(
            self.export_finished
        )

        self.worker.failed.connect(
            self.export_failed
        )

        self.worker.finished.connect(
            self.thread.quit
        )

        self.worker.failed.connect(
            self.thread.quit
        )

        self.thread.finished.connect(
            self.worker.deleteLater
        )

        self.thread.finished.connect(
            self.thread.deleteLater
        )

        self.thread.finished.connect(
            self.thread_finished
        )

        self.thread.start()

    def export_finished(
        self,
        anzahl: int,
        filename: str,
    ) -> None:
        self.status_download.set_done()
        self.status_validate.set_done()
        self.status_export.set_done()

        self.progress_bar.setValue(4)

        self.record_label.setText(
            f"Datensätze: {anzahl}"
        )

        self.status_label.setText(
            "Export erfolgreich abgeschlossen."
        )

        export_time = datetime.now().strftime(
            "%d.%m.%Y %H:%M:%S"
        )

        self.last_export_label.setText(
            f"{export_time}  ·  {anzahl} Datensätze\n"
            f"{Path(filename).name}"
        )

        self.settings.setValue(
            "last_export_date",
            export_time,
        )

        self.settings.setValue(
            "last_export_count",
            anzahl,
        )

        self.settings.setValue(
            "last_export_file",
            filename,
        )

        QMessageBox.information(
            self,
            "Export abgeschlossen",
            "Die CSV-Datei wurde erfolgreich erstellt.\n\n"
            f"Datensätze: {anzahl}\n\n"
            f"Datei:\n{filename}",
        )

    def export_failed(
        self,
        message: str,
    ) -> None:
        self.status_label.setText(
            "Der Export konnte nicht abgeschlossen werden."
        )

        QMessageBox.critical(
            self,
            "Export fehlgeschlagen",
            message,
        )

    def load_last_export(self) -> None:
        date = self.settings.value(
            "last_export_date",
            "",
        )

        count = self.settings.value(
            "last_export_count",
            "",
        )

        filename = self.settings.value(
            "last_export_file",
            "",
        )

        if not date or not filename:
            return

        self.last_export_label.setText(
            f"{date}  ·  {count} Datensätze\n"
            f"{Path(str(filename)).name}"
        )

    def thread_finished(self) -> None:
        self.export_button.setEnabled(True)
        self.select_folder_button.setEnabled(True)
        self.folder_button.setEnabled(True)
        self.login_button.setEnabled(True)

        self.worker = None
        self.thread = None

        self.update_output_display()
        self.update_preview_filename()

    def open_output_folder(self) -> None:
        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        os.startfile(
            self.output_dir
        )


def run_gui() -> None:
    """Startet die grafische Benutzeroberfläche."""
    app = QApplication(sys.argv)

    app.setOrganizationName(
        ORGANIZATION_NAME
    )

    app.setApplicationName(
        APPLICATION_NAME
    )

    window = MainWindow()
    window.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":
    run_gui()
