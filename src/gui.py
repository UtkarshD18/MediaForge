import os
import subprocess
import sys
import time
import json
from pathlib import Path
from typing import Callable, Optional, Any

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.ipc import IpcClient
from src.logger import get_logger


class IpcQueryThread(QThread):
    """
    Background worker thread that communicates with the daemon over UDS.
    Prevents UI stuttering or freezes.
    """
    response_received = Signal(dict)

    def __init__(self, client: IpcClient, command: dict) -> None:
        super().__init__()
        self.client = client
        self.command = command

    def run(self) -> None:
        try:
            resp = self.client.send_command(self.command)
            self.response_received.emit(resp)
        except Exception as e:
            self.response_received.emit({"success": False, "error": str(e)})

class ResourceMonitorThread(QThread):
    """
    Background thread querying CPU delta and NVIDIA GPU utilization levels.
    """
    stats_updated = Signal(float, float)  # CPU%, GPU%

    def __init__(self) -> None:
        super().__init__()
        self._running = True
        self.active_polling = True
        self._last_cpu_stats = self._read_cpu_ticks()

    def stop(self) -> None:
        self._running = False

    def _read_cpu_ticks(self) -> list[int] | None:
        try:
            with open("/proc/stat", "r") as f:
                for line in f:
                    if line.startswith("cpu "):
                        return [int(x) for x in line.split()[1:5]]
        except Exception:
            pass
        return None

    def run(self) -> None:
        while self._running:
            if not self.active_polling:
                time.sleep(1.0)
                continue

            cpu_val = 0.0
            gpu_val = 0.0
            
            # 1. Calculate CPU
            new_cpu = self._read_cpu_ticks()
            if new_cpu and self._last_cpu_stats:
                deltas = [n - o for n, o in zip(new_cpu, self._last_cpu_stats)]
                total_delta = sum(deltas)
                if total_delta > 0:
                    # Idle tick is index 3
                    idle_delta = deltas[3]
                    cpu_val = max(0.0, 100.0 * (total_delta - idle_delta) / total_delta)
                self._last_cpu_stats = new_cpu

            # 2. Calculate GPU via nvidia-smi
            try:
                out = subprocess.run(
                    ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                    capture_output=True,
                    text=True,
                    timeout=1.0
                )
                if out.returncode == 0:
                    gpu_val = float(out.stdout.strip())
            except Exception:
                gpu_val = 0.0
                
            self.stats_updated.emit(cpu_val, gpu_val)
            time.sleep(5.0)

class MediaForgeWindow(QMainWindow):
    """
    Main PySide6 dashboard window modeled in breeze-dark aesthetics.
    """
    def __init__(self, socket_path: Path, project_root: Path) -> None:
        super().__init__()
        self.socket_path = Path(socket_path).resolve()
        self.project_root = Path(project_root).resolve()
        self.client = IpcClient(self.socket_path)
        self.logger = get_logger()
        
        self.setWindowTitle("MediaForge Ingestion Engine")
        self.resize(800, 600)
        
        self.setup_stylesheet()
        self.setup_ui()
        self.setup_system_tray()
        
        # Start loops
        self.telemetry_timer = QTimer(self)
        self.telemetry_timer.timeout.connect(self.poll_daemon_status)
        self.telemetry_timer.start(1000)
        
        # Load local config for features check
        from src.config import ConfigManager
        try:
            self.gui_config = ConfigManager(self.project_root).config
        except Exception:
            self.gui_config = None

        self.resource_monitor = ResourceMonitorThread()
        self.resource_monitor.stats_updated.connect(self.update_resource_widgets)
        
        gpu_monitor_enabled = True
        if self.gui_config and not self.gui_config.features.get("gpu_monitor", True):
            gpu_monitor_enabled = False
            self.cpu_lbl.setText("CPU: Disabled")
            self.gpu_lbl.setText("GPU: Disabled")

        if gpu_monitor_enabled:
            self.resource_monitor.start()

        self.poll_daemon_status()

    def setup_stylesheet(self) -> None:
        """
        Premium HSL-tailored dark stylesheet matching KDE Breeze-dark.
        """
        self.setStyleSheet("""
            QMainWindow {
                background-color: #232629;
                color: #fcfcfc;
            }
            QWidget {
                color: #fcfcfc;
                font-family: 'Inter', 'Roboto', 'Outfit', sans-serif;
                font-size: 13px;
            }
            QTabWidget::pane {
                border: 1px solid #31363b;
                background-color: #2a2e32;
                border-radius: 6px;
            }
            QTabBar::tab {
                background-color: #232629;
                border: 1px solid #31363b;
                border-bottom-color: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 8px 16px;
                margin-right: 2px;
                color: #a1a9b1;
            }
            QTabBar::tab:selected, QTabBar::tab:hover {
                background-color: #2a2e32;
                color: #fcfcfc;
                border-bottom: 2px solid #3daee9;
            }
            QFrame#card {
                background-color: #31363b;
                border: 1px solid #3f444a;
                border-radius: 8px;
            }
            QLabel#header_title {
                font-size: 20px;
                font-weight: bold;
                color: #3daee9;
            }
            QPushButton {
                background-color: #31363b;
                border: 1px solid #4d545c;
                border-radius: 4px;
                padding: 6px 14px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #3daee9;
                border: 1px solid #3daee9;
                color: #232629;
                font-weight: bold;
            }
            QPushButton:pressed {
                background-color: #1d99f3;
            }
            QPushButton#danger_btn {
                border: 1px solid #c0392b;
            }
            QPushButton#danger_btn:hover {
                background-color: #e74c3c;
                border: 1px solid #e74c3c;
                color: #fcfcfc;
            }
            QLineEdit, QComboBox {
                background-color: #232629;
                border: 1px solid #4d545c;
                border-radius: 4px;
                padding: 5px;
                color: #fcfcfc;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #3daee9;
            }
            QProgressBar {
                background-color: #232629;
                border: 1px solid #31363b;
                border-radius: 6px;
                text-align: center;
                color: #fcfcfc;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #2ecc71;
                border-radius: 5px;
            }
            QTableWidget {
                background-color: #232629;
                border: 1px solid #31363b;
                gridline-color: #31363b;
                border-radius: 4px;
            }
            QHeaderView::section {
                background-color: #2a2e32;
                border: 1px solid #31363b;
                padding: 5px;
                color: #a1a9b1;
                font-weight: bold;
            }
            QScrollBar:vertical {
                background-color: #232629;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background-color: #4d545c;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #3daee9;
            }
        """)

    def setup_ui(self) -> None:
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # 1. Header (Title, Daemon Status, GPU/CPU displays)
        header_layout = QHBoxLayout()
        
        title_label = QLabel("MediaForge", self)
        title_label.setObjectName("header_title")
        header_layout.addWidget(title_label)
        
        # Status indicator
        status_card = QFrame(self)
        status_card.setObjectName("card")
        status_card_layout = QHBoxLayout(status_card)
        status_card_layout.setContentsMargins(8, 4, 8, 4)
        
        self.status_dot = QLabel("●", self)
        self.status_dot.setStyleSheet("color: #e74c3c; font-size: 16px;")  # Default Red (Offline)
        status_card_layout.addWidget(self.status_dot)
        
        self.status_text = QLabel("Daemon Offline", self)
        self.status_text.setStyleSheet("font-weight: bold; color: #a1a9b1;")
        status_card_layout.addWidget(self.status_text)
        header_layout.addWidget(status_card)
        
        header_layout.addStretch()
        
        # CPU/GPU utilization widgets
        res_card = QFrame(self)
        res_card.setObjectName("card")
        res_layout = QHBoxLayout(res_card)
        res_layout.setContentsMargins(10, 5, 10, 5)
        
        self.cpu_lbl = QLabel("CPU: 0%", self)
        self.cpu_lbl.setStyleSheet("color: #3daee9; font-weight: bold;")
        res_layout.addWidget(self.cpu_lbl)
        
        divider = QLabel("|", self)
        divider.setStyleSheet("color: #4d545c;")
        res_layout.addWidget(divider)
        
        self.gpu_lbl = QLabel("GPU: 0%", self)
        self.gpu_lbl.setStyleSheet("color: #2ecc71; font-weight: bold;")
        res_layout.addWidget(self.gpu_lbl)
        header_layout.addWidget(res_card)
        
        main_layout.addLayout(header_layout)
        main_layout.addSpacing(10)

        # 2. Main Tab View
        self.tabs = QTabWidget(self)
        
        self.setup_dashboard_tab()
        self.setup_history_tab()
        self.setup_settings_tab()
        
        main_layout.addWidget(self.tabs)

    def setup_dashboard_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Active Job Group
        active_card = QFrame(tab)
        active_card.setObjectName("card")
        active_layout = QVBoxLayout(active_card)
        active_layout.setContentsMargins(15, 15, 15, 15)
        
        active_header = QHBoxLayout()
        active_header.addWidget(QLabel("<b>Active Conversion Task</b>", tab))
        active_header.addStretch()
        
        # Daemon Control Actions
        self.pause_btn = QPushButton("Pause Ingestion", tab)
        self.pause_btn.clicked.connect(self.on_pause_clicked)
        active_header.addWidget(self.pause_btn)
        
        self.cancel_btn = QPushButton("Cancel Job", tab)
        self.cancel_btn.setObjectName("danger_btn")
        self.cancel_btn.clicked.connect(self.on_cancel_clicked)
        active_header.addWidget(self.cancel_btn)
        active_layout.addLayout(active_header)
        
        self.active_file_label = QLabel("Idle - Drag media files into the watched directory to begin.", tab)
        self.active_file_label.setWordWrap(True)
        active_layout.addWidget(self.active_file_label)
        
        self.progress_bar = QProgressBar(tab)
        self.progress_bar.setValue(0)
        active_layout.addWidget(self.progress_bar)
        
        self.active_meta_label = QLabel("", tab)
        self.active_meta_label.setStyleSheet("color: #a1a9b1; font-size: 11px;")
        active_layout.addWidget(self.active_meta_label)
        
        layout.addWidget(active_card)
        layout.addSpacing(10)
        
        # Queue list header
        queue_header = QHBoxLayout()
        queue_header.addWidget(QLabel("<b>Ingestion Processing Queue</b>", tab))
        queue_header.addStretch()
        layout.addLayout(queue_header)
        
        # Queue Table
        self.queue_table = QTableWidget(0, 3, tab)
        self.queue_table.setHorizontalHeaderLabels(["Filename", "Profile", "Status"])
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.verticalHeader().setVisible(False)
        layout.addWidget(self.queue_table)
        
        self.tabs.addTab(tab, "Dashboard")

    def setup_history_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Telemetry Stats Card
        stats_layout = QHBoxLayout()
        
        stats_titles = ["Files Converted", "Total Ingested", "Total Time Saved", "Average Speed"]
        self.stats_labels = []
        for title in stats_titles:
            card = QFrame(tab)
            card.setObjectName("card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 10, 10, 10)
            
            lbl_title = QLabel(title, tab)
            lbl_title.setStyleSheet("color: #a1a9b1; font-size: 11px;")
            lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(lbl_title)
            
            lbl_val = QLabel("0", tab)
            lbl_val.setStyleSheet("font-size: 18px; font-weight: bold; color: #3daee9;")
            lbl_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(lbl_val)
            self.stats_labels.append(lbl_val)
            stats_layout.addWidget(card)
            
        layout.addLayout(stats_layout)
        layout.addSpacing(10)
        
        layout.addWidget(QLabel("<b>Ingestion History</b>", tab))
        
        # History Table
        self.history_table = QTableWidget(0, 5, tab)
        self.history_table.setHorizontalHeaderLabels(["Original File", "Status", "Size Saved", "Speed", "Ingested At"])
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.verticalHeader().setVisible(False)
        layout.addWidget(self.history_table)
        
        self.tabs.addTab(tab, "History")

    def setup_settings_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Configuration Fields
        form_layout = QVBoxLayout()
        
        # Incoming Directory
        form_layout.addWidget(QLabel("Incoming Video Directory (Watched):", tab))
        incoming_row = QHBoxLayout()
        self.incoming_edit = QLineEdit(tab)
        incoming_row.addWidget(self.incoming_edit)
        incoming_browse = QPushButton("Browse", tab)
        incoming_browse.clicked.connect(lambda: self.browse_directory(self.incoming_edit))
        incoming_row.addWidget(incoming_browse)
        form_layout.addLayout(incoming_row)
        
        # Clips Directory
        form_layout.addWidget(QLabel("Target Clips Directory (Resolve Ingest):", tab))
        clips_row = QHBoxLayout()
        self.clips_edit = QLineEdit(tab)
        clips_row.addWidget(self.clips_edit)
        clips_browse = QPushButton("Browse", tab)
        clips_browse.clicked.connect(lambda: self.browse_directory(self.clips_edit))
        clips_row.addWidget(clips_browse)
        form_layout.addLayout(clips_row)
        
        # Active Profile Selector
        form_layout.addWidget(QLabel("Active Conversion Target Profile:", tab))
        self.profile_combo = QComboBox(tab)
        form_layout.addWidget(self.profile_combo)
        
        # Notification Toggle
        self.notify_check = QCheckBox("Enable Desktop Notifications (KDE Alert)", tab)
        form_layout.addWidget(self.notify_check)
        
        # Overwrite Toggle
        self.overwrite_check = QCheckBox("Overwrite Destination Files", tab)
        form_layout.addWidget(self.overwrite_check)
        
        layout.addLayout(form_layout)
        layout.addSpacing(10)
        
        # Save Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save Settings", tab)
        save_btn.clicked.connect(self.save_settings)
        btn_layout.addWidget(save_btn)
        
        # Quick access folder triggers
        open_in_btn = QPushButton("Open Incoming Folder", tab)
        open_in_btn.clicked.connect(lambda: self.open_folder(self.incoming_edit.text()))
        btn_layout.addWidget(open_in_btn)
        
        open_out_btn = QPushButton("Open Clips Folder", tab)
        open_out_btn.clicked.connect(lambda: self.open_folder(self.clips_edit.text()))
        btn_layout.addWidget(open_out_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        layout.addSpacing(15)
        
        # Live log reader console
        layout.addWidget(QLabel("<b>Engine Live Logs</b>", tab))
        self.logs_txt = QTextEdit(tab)
        self.logs_txt.setReadOnly(True)
        self.logs_txt.setStyleSheet("background-color: #1e1e24; color: #a1a9b1; font-family: monospace; font-size: 11px;")
        layout.addWidget(self.logs_txt)
        
        # Start reading logs
        self.logs_timer = QTimer(self)
        self.logs_timer.timeout.connect(self.tail_logs)
        self.logs_timer.start(2000)
        self.log_file_pointer = 0
        
        self.tabs.addTab(tab, "Settings")

    def setup_system_tray(self) -> None:
        """
        Register a system tray widget providing background controls.
        """
        self.tray_icon = QSystemTrayIcon(self)
        # Fallback to standard Qt theme icon if custom png asset is not packaged yet
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip("MediaForge Ingestion Engine")
        
        # Context Menu
        menu = QMenu(self)
        
        show_action = QAction("Open Dashboard", self)
        show_action.triggered.connect(self.showNormal)
        menu.addAction(show_action)
        
        self.tray_pause_action = QAction("Pause Queue", self)
        self.tray_pause_action.triggered.connect(self.toggle_queue_pause)
        menu.addAction(self.tray_pause_action)
        
        menu.addSeparator()
        
        open_in = QAction("Open Incoming Folder", self)
        open_in.triggered.connect(lambda: self.open_folder(self.incoming_edit.text()))
        menu.addAction(open_in)
        
        open_clips = QAction("Open Clips Folder", self)
        open_clips.triggered.connect(lambda: self.open_folder(self.clips_edit.text()))
        menu.addAction(open_clips)
        
        menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(QApplication.quit)
        menu.addAction(exit_action)
        
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()

    def on_tray_icon_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.showNormal()
                self.activateWindow()

    # --- UI Event Responders ---

    def browse_directory(self, target_edit: QLineEdit) -> None:
        curr = target_edit.text()
        default = os.path.expanduser(curr) if curr else os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(self, "Select Folder", default)
        if path:
            target_edit.setText(path)

    def open_folder(self, folder_path_str: str) -> None:
        path = Path(folder_path_str).expanduser()
        if path.exists():
            subprocess.run(["xdg-open", str(path)])
        else:
            QMessageBox.warning(self, "Invalid Directory", f"The directory does not exist: {path}")

    def on_pause_clicked(self) -> None:
        cmd = "resume" if self.pause_btn.text().startswith("Resume") else "pause"
        self.run_uds_command({"command": cmd}, self.on_pause_response)

    def toggle_queue_pause(self) -> None:
        # Tray toggle
        cmd = "resume" if self.tray_pause_action.text().startswith("Resume") else "pause"
        self.run_uds_command({"command": cmd}, self.on_pause_response)

    def on_pause_response(self, resp: dict) -> None:
        if resp.get("success"):
            self.poll_daemon_status()

    def on_cancel_clicked(self) -> None:
        reply = QMessageBox.question(
            self, "Cancel Ingestion",
            "Are you sure you want to stop and delete the current conversion?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.run_uds_command({"command": "cancel"})

    def save_settings(self) -> None:
        """
        Compile field configurations and push a settings save to the daemon.
        """
        updates = {
            "incoming_folder": self.incoming_edit.text(),
            "resolve_clips_folder": self.clips_edit.text(),
            "active_profile": self.profile_combo.currentText(),
            "notification_toggle": self.notify_check.isChecked(),
            "overwrite_existing": self.overwrite_check.isChecked()
        }
        
        # Save locally in files if daemon is offline, or request daemon update
        if self.status_text.text() == "Daemon Offline":
            # Direct save using config module
            try:
                from src.config import ConfigManager
                cm = ConfigManager(self.project_root)
                cm.save_settings(updates)
                QMessageBox.information(self, "Saved", "Settings saved locally. Daemon is offline.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save locally: {e}")
        else:
            # Save via UDS
            self.run_uds_command({
                "command": "reload_config"  # Reload triggers save updates
            }, lambda r: self.save_settings_via_uds(updates))

    def save_settings_via_uds(self, updates: dict) -> None:
        # We need an internal save script call, or since config reload parses yaml,
        # we write the YAML file first and then tell the daemon to reload.
        try:
            from src.config import ConfigManager
            cm = ConfigManager(self.project_root)
            cm.save_settings(updates)
            
            # Send reload to daemon
            self.run_uds_command({"command": "reload_config"}, self.on_settings_reloaded)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to serialize settings: {e}")

    def on_settings_reloaded(self, resp: dict) -> None:
        if resp.get("success"):
            QMessageBox.information(self, "Settings Saved", "Settings synchronized to daemon.")
            self.poll_daemon_status()
        else:
            QMessageBox.critical(self, "Sync Error", f"Daemon failed to reload: {resp.get('error')}")

    # --- Telemetry & IPC polling ---

    def run_uds_command(self, cmd: dict, callback: Callable[[dict], None] | None = None) -> None:
        worker = IpcQueryThread(self.client, cmd)
        if callback:
            worker.response_received.connect(callback)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def poll_daemon_status(self) -> None:
        self.run_uds_command({"command": "status"}, self.update_telemetry_ui)

    def update_telemetry_ui(self, resp: dict) -> None:
        if not resp.get("success"):
            # Set Offline
            self.status_dot.setStyleSheet("color: #e74c3c; font-size: 16px;")
            self.status_text.setText("Daemon Offline")
            self.status_text.setStyleSheet("font-weight: bold; color: #a1a9b1;")
            self.active_file_label.setText("Idle - Daemon is currently offline. Start the service with 'mediaforge watch'.")
            self.progress_bar.setValue(0)
            self.pause_btn.setEnabled(False)
            self.cancel_btn.setEnabled(False)
            self.tray_pause_action.setEnabled(False)
            return

        # Status active
        daemon_status = resp.get("status", "watching")
        if daemon_status == "watching":
            self.status_dot.setStyleSheet("color: #2ecc71; font-size: 16px;")  # Green
            self.status_text.setText("Watching")
            self.status_text.setStyleSheet("font-weight: bold; color: #2ecc71;")
            self.pause_btn.setText("Pause Ingestion")
            self.tray_pause_action.setText("Pause Queue")
        else:
            self.status_dot.setStyleSheet("color: #f39c12; font-size: 16px;")  # Orange
            self.status_text.setText("Queue Paused")
            self.status_text.setStyleSheet("font-weight: bold; color: #f39c12;")
            self.pause_btn.setText("Resume Ingestion")
            self.tray_pause_action.setText("Resume Queue")

        self.pause_btn.setEnabled(True)
        self.tray_pause_action.setEnabled(True)

        # 1. Update Active Job Widget
        active = resp.get("active_job")
        if active:
            filename = Path(active["filepath"]).name
            status = active["status"].replace("_", " ").title()
            progress = active.get("progress", 0.0)
            eta = active.get("eta_seconds", 0.0)
            
            self.active_file_label.setText(f"<b>Ingesting:</b> {filename} ({status})")
            self.progress_bar.setValue(int(progress))
            
            eta_str = f"{int(eta // 60):02d}:{int(eta % 60):02d} remaining" if eta > 0 else "estimating..."
            self.active_meta_label.setText(f"Progress: {progress:.1f}% | {eta_str}")
            self.cancel_btn.setEnabled(True)
        else:
            self.active_file_label.setText("Idle - Waiting for incoming files...")
            self.progress_bar.setValue(0)
            self.active_meta_label.setText("")
            self.cancel_btn.setEnabled(False)

        # 2. Update Queue list
        jobs_list = resp.get("jobs_list", [])
        queued_jobs = [j for j in jobs_list if j["status"] == "queued"]
        
        self.queue_table.setRowCount(len(queued_jobs))
        for row, job in enumerate(queued_jobs):
            name = Path(job["filepath"]).name
            self.queue_table.setItem(row, 0, QTableWidgetItem(name))
            self.queue_table.setItem(row, 1, QTableWidgetItem(job["profile_name"].upper()))
            self.queue_table.setItem(row, 2, QTableWidgetItem(job["status"].upper()))

        # 3. Update Settings configurations if text is empty (initial load)
        config = resp.get("config", {})
        if self.incoming_edit.text() == "":
            self.incoming_edit.setText(config.get("incoming_folder", ""))
            self.clips_edit.setText(config.get("resolve_clips_folder", ""))
            
            # Fetch profiles dynamically from the project dir
            self.profile_combo.clear()
            profiles_dir = self.project_root / "config" / "profiles"
            if profiles_dir.exists():
                for pf in profiles_dir.glob("*.yaml"):
                    self.profile_combo.addItem(pf.stem)
            
            self.profile_combo.setCurrentText(config.get("active_profile", "youtube"))

        # 4. Update Analytics Stats labels
        analytics = resp.get("analytics", {})
        self.stats_labels[0].setText(str(analytics.get("total_count", 0)))
        
        # Bytes conversion
        bytes_val = analytics.get("total_size_bytes", 0)
        size_str = "0 MB"
        if bytes_val > 1024**3:
            size_str = f"{bytes_val / 1024**3:.2f} GB"
        elif bytes_val > 1024**2:
            size_str = f"{bytes_val / 1024**2:.1f} MB"
        self.stats_labels[1].setText(size_str)
        
        # Time Saved
        time_sec = analytics.get("time_saved_seconds", 0.0)
        saved_str = "0s"
        if time_sec > 3600:
            saved_str = f"{time_sec / 3600:.1f} hrs"
        elif time_sec > 60:
            saved_str = f"{time_sec / 60:.1f} mins"
        else:
            saved_str = f"{int(time_sec)}s"
        self.stats_labels[2].setText(saved_str)
        
        # Average Speed
        self.stats_labels[3].setText(f"{analytics.get('avg_speed', 1.0):.2f}x")

        # 5. Populate History Table
        self.run_uds_command({"command": "history", "limit": 20}, self.populate_history_widget)

    def populate_history_widget(self, resp: dict) -> None:
        if not resp.get("success"):
            return
        history = resp.get("history", [])
        self.history_table.setRowCount(len(history))
        for row, hist in enumerate(history):
            self.history_table.setItem(row, 0, QTableWidgetItem(hist["original_name"]))
            
            # Colored Status
            status_item = QTableWidgetItem(hist["status"].upper())
            if hist["status"] == "completed":
                status_item.setForeground(QColor("#2ecc71"))
            else:
                status_item.setForeground(QColor("#e74c3c"))
            self.history_table.setItem(row, 1, status_item)
            
            # File size saved representation
            bytes_val = hist["original_size"]
            size_str = f"{bytes_val / 1024**2:.1f} MB" if bytes_val < 1024**3 else f"{bytes_val / 1024**3:.2f} GB"
            self.history_table.setItem(row, 2, QTableWidgetItem(size_str))
            
            self.history_table.setItem(row, 3, QTableWidgetItem(f"{hist['avg_speed']:.2f}x"))
            
            # Timestamp (iso format extraction)
            ts = hist["timestamp"].split(".")[0] if "." in hist["timestamp"] else hist["timestamp"]
            self.history_table.setItem(row, 4, QTableWidgetItem(ts))

    def update_resource_widgets(self, cpu: float, gpu: float) -> None:
        self.cpu_lbl.setText(f"CPU: {int(cpu)}%")
        self.gpu_lbl.setText(f"GPU: {int(gpu)}%")

    # --- Log File Tailing ---

    def tail_logs(self) -> None:
        """
        Periodically parses today's JSON log file and renders it in settings view log panel.
        """
        today = time.strftime("%Y-%m-%d")
        log_path = self.project_root / "logs" / f"{today}.log"
        if not log_path.exists():
            self.logs_txt.setPlainText("Log file empty. Awaiting ingestion actions.")
            return

        try:
            stat = log_path.stat()
            size = stat.st_size
            if size < self.log_file_pointer:
                # Reset if file rotated or truncated
                self.log_file_pointer = 0

            if size == self.log_file_pointer:
                return

            with open(log_path, "r", encoding="utf-8") as f:
                f.seek(self.log_file_pointer)
                new_data = f.read()
                self.log_file_pointer = f.tell()

            # Format raw JSON strings for nice output console presentation
            formatted = []
            for line in new_data.splitlines():
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    time_str = obj.get("time", "").split("T")[-1][:8]
                    lvl = obj.get("level", "INFO")
                    msg = obj.get("message", "")
                    mod = obj.get("module", "")
                    formatted.append(f"[{time_str}] {lvl:<6} {mod} - {msg}")
                except Exception:
                    formatted.append(line)

            if formatted:
                self.logs_txt.append("\n".join(formatted))
                # Auto scroll to bottom
                self.logs_txt.verticalScrollBar().setValue(self.logs_txt.verticalScrollBar().maximum())
        except Exception as e:
            self.logs_txt.append(f"Error reading logs: {e}")

    def closeEvent(self, event) -> None:
        """
        Override close behavior to hide the window to system tray instead of exiting.
        """
        if self.tray_icon.isVisible():
            self.hide()
            self.tray_icon.showMessage(
                "MediaForge",
                "Application is still running in the system tray.",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
            event.ignore()
        else:
            self.resource_monitor.stop()
            self.resource_monitor.wait()
            event.accept()

    def hideEvent(self, event) -> None:
        """
        Suspend resource monitoring thread on window hide.
        """
        if hasattr(self, "resource_monitor"):
            self.resource_monitor.active_polling = False
        super().hideEvent(event)

    def showEvent(self, event) -> None:
        """
        Resume resource monitoring thread on window restore.
        """
        if hasattr(self, "resource_monitor"):
            self.resource_monitor.active_polling = True
        super().showEvent(event)

def start_gui(socket_path: Path, project_root: Path) -> None:
    app = QApplication(sys.argv)
    
    # Enable system tray fallback integration
    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("System tray is not available on this desktop environment. Running standard window mode.")
        
    window = MediaForgeWindow(socket_path, project_root)
    window.show()
    sys.exit(app.exec())
