import json
import sqlite3
import subprocess
import sys
import os
import urllib.request
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QProcess
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QInputDialog,
    QPushButton, QSplitter, QStatusBar, QTableWidget, QTableWidgetItem, QDialog,
    QTextEdit, QVBoxLayout, QWidget, QComboBox, QProgressBar, QSpinBox, QCheckBox, QSizePolicy
)

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "aisorter.db"
CONFIG_PATH = ROOT / "config.json"
GUI_SETTINGS_PATH = ROOT / "data" / "gui_settings.json"


class ClassicTitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_window = parent
        self.drag_pos = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(22)
        self.setStyleSheet("background:#000080;color:#ffffff;font-weight:bold;")
        layout = QHBoxLayout(self); layout.setContentsMargins(3, 1, 3, 1); layout.setSpacing(2)
        label = QLabel("📁  LLM File Sorter"); label.setStyleSheet("color:#ffffff;font-weight:bold;")
        layout.addWidget(label); layout.addStretch()
        for text, slot in [("_", parent.showMinimized), ("□", parent.showMaximized), ("×", parent.close)]:
            button = QPushButton(text); button.setFixedSize(21, 19)
            button.setStyleSheet("""
                QPushButton { background: #c0c0c0; color: #000000; border: 2px solid;
                    border-color: #ffffff #404040 #404040 #ffffff; padding: 0; }
                QPushButton:pressed { border-color: #404040 #ffffff #ffffff #404040; }
            """)
            button.clicked.connect(slot); layout.addWidget(button)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.parent_window.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self.drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.parent_window.move(event.globalPosition().toPoint() - self.drag_pos)

    def mouseReleaseEvent(self, event):
        self.drag_pos = None


class SorterWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LFS - LLM File Sorter")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.resize(1024, 768)
        self.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.watch_process = None
        self.scan_process = None
        self.gui_settings = json.loads(GUI_SETTINGS_PATH.read_text(encoding="utf-8")) if GUI_SETTINGS_PATH.exists() else {}
        self.setStyleSheet("""
            QWidget { font-family: 'Tahoma'; font-size: 13px; color: #000000; }
            QMainWindow { background: #c0c0c0; }
            QFrame#card { background: #c0c0c0; border: 2px solid; border-color: #ffffff #808080 #808080 #ffffff; border-radius: 0px; }
            QPushButton { padding: 6px 12px; border: 2px solid; border-color: #ffffff #404040 #404040 #ffffff; border-radius: 0px; background: #c0c0c0; color: #000000; }
            QPushButton:pressed { border-color: #404040 #ffffff #ffffff #404040; }
            QPushButton#primary { background: #000080; color: white; border-color: #ffffff #404040 #404040 #ffffff; font-weight: bold; }
            QLineEdit { padding: 5px; border: 2px solid; border-color: #808080 #ffffff #ffffff #808080; border-radius: 0px; background: white; color: #000000; }
            QComboBox { padding: 4px; border: 2px solid; border-color: #808080 #ffffff #ffffff #808080; border-radius: 0px; background: white; color: #000000; }
            QComboBox QAbstractItemView { background: white; color: #000000; selection-background-color: #000080; selection-color: white; border: 1px solid #808080; }
            QProgressBar { min-height: 20px; border: 2px solid; border-color: #808080 #ffffff #ffffff #808080; background: #ffffff; color: #000000; text-align: center; }
            QProgressBar::chunk { background: #000080; border: 1px solid #c0c0c0; margin: 1px; }
            QTableWidget { background: white; color: #000000; border: 2px solid; border-color: #808080 #ffffff #ffffff #808080; gridline-color: #c0c0c0; selection-background-color: #000080; selection-color: white; }
            QTableWidget QTableCornerButton::section { background: #c0c0c0; border: 1px solid #808080; }
            QScrollBar:vertical, QScrollBar:horizontal { background: #ffffff; border: 1px solid #808080; }
            QScrollBar:vertical { width: 16px; }
            QScrollBar:horizontal { height: 16px; }
            QScrollBar::handle:vertical { min-height: 24px; background: #c0c0c0; border: 2px solid; border-color: #ffffff #404040 #404040 #ffffff; }
            QScrollBar::handle:horizontal { min-width: 24px; background: #c0c0c0; border: 2px solid; border-color: #ffffff #404040 #404040 #ffffff; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { background: #c0c0c0; border: 1px solid #808080; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 16px; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 16px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical, QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: #ffffff; }
            QHeaderView::section { background: #c0c0c0; color: #000000; padding: 5px; border: 1px solid #808080; font-weight: bold; }
            QTextEdit { background: white; color: #000000; border: 2px solid; border-color: #808080 #ffffff #ffffff #808080; }
            QListWidget { background: #c0c0c0; color: #000000; border: 2px solid; border-color: #808080 #ffffff #ffffff #808080; }
            QListWidget::item { padding: 8px 6px; }
            QListWidget::item:selected { background: #000080; color: white; }
            QStatusBar { background: #c0c0c0; border-top: 1px solid #808080; }
            QDialog { background: #c0c0c0; color: #000000; }
            QDialog QLabel { color: #000000; }
            QWidget#windowRoot { background: #c0c0c0; border: 2px solid; border-color: #ffffff #404040 #404040 #ffffff; }
        """)
        self.build_ui()
        QTimer.singleShot(0, self.refresh)
        QTimer.singleShot(100, self.update_services)
        self.service_timer = QTimer(self)
        self.service_timer.timeout.connect(self.update_services)
        self.service_timer.start(5000)

    def card(self, layout):
        frame = QFrame(); frame.setObjectName("card"); frame.setLayout(layout); return frame

    def build_ui(self):
        root = QWidget(); root.setObjectName("windowRoot"); outer = QVBoxLayout(root); outer.setContentsMargins(2, 2, 2, 2); outer.setSpacing(0)
        self.title_bar = ClassicTitleBar(self)
        outer.addWidget(self.title_bar)
        body = QWidget(); body_layout = QHBoxLayout(body); body_layout.setContentsMargins(12, 12, 12, 12)
        nav = QFrame(); nav.setFixedWidth(220); nav.setObjectName("card"); nav_layout = QVBoxLayout(nav)
        title = QLabel("📁  LFS"); title.setStyleSheet("font-size:18px;font-weight:bold;color:#153d70;padding:12px")
        title.setToolTip("LFS - LLM File Sorter")
        nav_layout.addWidget(title)
        self.nav = QListWidget(); self.nav.addItems(["⌂  대시보드", "▤  분류 결과 (준비중)", "⚙  설정"]); self.nav.setCurrentRow(0); self.nav.currentRowChanged.connect(self.change_page)
        nav_layout.addWidget(self.nav); nav_layout.addStretch(); body_layout.addWidget(nav)

        content = QWidget(); main = QVBoxLayout(content); main.setContentsMargins(12, 0, 0, 0)
        header = QHBoxLayout(); h = QLabel("LFS"); h.setStyleSheet("font-size:25px;font-weight:bold;color:#153d70")
        self.watch_label = QLabel("●  감시 중"); self.watch_label.setStyleSheet("color:#006000;background:#c0c0c0;border:2px solid;border-color:#808080 #ffffff #ffffff #808080;padding:4px 10px;font-weight:bold")
        header.addWidget(h); header.addWidget(self.watch_label); header.addStretch(); main.addLayout(header)

        paths = QGridLayout()
        self.path_edits = []
        defaults = [self.gui_settings.get("input_dir", str(Path.home()/"Downloads")), self.gui_settings.get("staging_dir", str(ROOT/"staging")), self.gui_settings.get("output_dir", str(ROOT/"정리된파일"))]
        for row, label, default in [(0,"감시할 다운로드 폴더",defaults[0]),(1,"임시 처리 폴더",defaults[1]),(2,"분류 저장 폴더",defaults[2])]:
            paths.addWidget(QLabel(label), row, 0); edit = QLineEdit(default); self.path_edits.append(edit); paths.addWidget(edit,row,1)
            button = QPushButton("폴더 선택"); button.clicked.connect(lambda _, e=edit: self.choose_folder(e)); paths.addWidget(button,row,2)
        services = QVBoxLayout(); self.ollama_label = QLabel(); self.tesseract_label = QLabel(); self.ollama_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter); self.tesseract_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter); services.addWidget(self.ollama_label); services.addWidget(self.tesseract_label)
        model_row = QHBoxLayout(); model_row.addWidget(QLabel("사용 모델:")); self.model_combo = QComboBox(); self.model_combo.addItem(self.config.get("ollama_model", "qwen3:4b"), self.config.get("ollama_model", "qwen3:4b")); QTimer.singleShot(150, self.load_models); self.model_combo.currentIndexChanged.connect(self.model_changed); self.model_combo.setToolTip("선택한 Ollama 모델을 분류에 사용합니다."); model_row.addWidget(self.model_combo, 1)
        services.addLayout(model_row); paths.addLayout(services,0,3,3,1)
        main.addWidget(self.card(paths))

        progress_layout = QGridLayout()
        self.progress_title = QLabel("스캔 대기 중")
        self.progress_title.setStyleSheet("font-size:18px;font-weight:bold;color:#000080")
        self.progress_current = QLabel("현재 처리 파일: -")
        self.progress_count = QLabel("처리 파일: 0 / 0")
        self.progress_bar = QProgressBar(); self.progress_bar.setFixedHeight(22); self.progress_bar.setRange(0, 100); self.progress_bar.setValue(0); self.progress_bar.setTextVisible(False)
        self.progress_elapsed = QLabel("경과 시간: -   예상 남은 시간: -")
        progress_layout.addWidget(self.progress_title, 0, 0); progress_layout.addWidget(self.progress_count, 0, 1); progress_layout.addWidget(self.progress_bar, 1, 0, 1, 2); progress_layout.addWidget(self.progress_current, 2, 0); progress_layout.addWidget(self.progress_elapsed, 2, 1)
        main.addWidget(self.card(progress_layout))

        stats = QHBoxLayout(); self.stat_labels = {}
        for key, text, color in [("CLASSIFIED","분류 완료","blue"),("REVIEW_REQUIRED","검토 필요","orange"),("CONFIRMED","승인 완료","green"),("TOTAL","전체 처리","purple")]:
            box = QVBoxLayout(); label = QLabel(text); value = QLabel("0"); value.setStyleSheet(f"font-size:24px;font-weight:bold;color:{color}"); box.addWidget(label); box.addWidget(value); self.stat_labels[key] = value
            stat_card = self.card(box); stat_card.setStyleSheet("background:#c0c0c0; border:0px;"); stats.addWidget(stat_card)
        main.addLayout(stats)

        filter_row = QHBoxLayout(); filter_row.addWidget(QLabel("표시:")); self.filter_combo = QComboBox(); self.filter_combo.addItems(["전체", "분류 완료", "검토 필요", "승인 완료"]); self.filter_combo.currentIndexChanged.connect(self.refresh); filter_row.addWidget(self.filter_combo); filter_row.addStretch(); self.delete_button = QPushButton("기록 삭제"); self.delete_button.setToolTip("원본 파일은 유지하고 선택한 분류 기록만 삭제합니다."); self.delete_button.clicked.connect(self.delete_records); filter_row.addWidget(self.delete_button); main.addLayout(filter_row)
        splitter = QSplitter(Qt.Horizontal)
        left = QWidget(); left_layout = QVBoxLayout(left); left_layout.addWidget(QLabel("파일 목록 (Ctrl/Shift로 여러 개 선택 가능)")); self.table = QTableWidget(0,6); self.table.setHorizontalHeaderLabels(["ID","파일명","AI 분류","신뢰도","상태","근거"]); self.table.setSelectionBehavior(QTableWidget.SelectRows); self.table.setSelectionMode(QTableWidget.ExtendedSelection); self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn); self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn); self.table.itemSelectionChanged.connect(self.show_selected); self.table.horizontalHeader().setStretchLastSection(False); self.table.setStyleSheet("QTableWidget { background:white; color:#000000; border:2px solid; border-color:#808080 #ffffff #ffffff #808080; gridline-color:#c0c0c0; selection-background-color:#000080; selection-color:#ffffff; } QTableWidget::item:selected { background:#000080; color:#ffffff; }"); left_layout.addWidget(self.table); splitter.addWidget(left)
        right = QWidget(); right_layout = QVBoxLayout(right); right_layout.addWidget(QLabel("선택 파일 미리보기")); self.preview = QTextEdit(); self.preview.setReadOnly(True); self.preview.setPlaceholderText("왼쪽 목록에서 파일을 선택하면 내용과 분류 근거가 표시됩니다."); right_layout.addWidget(self.preview); splitter.addWidget(right); splitter.setSizes([850,420]); main.addWidget(splitter,1)

        actions = QHBoxLayout(); self.refresh_button = QPushButton("새로고침"); self.refresh_button.setToolTip("분류 결과를 다시 읽습니다."); self.refresh_button.clicked.connect(self.refresh); self.scan_button = QPushButton("스캔 시작"); self.scan_button.setObjectName("primary"); self.scan_button.setToolTip("감시 폴더의 새 파일을 즉시 분석합니다."); self.scan_button.clicked.connect(self.scan); self.watch_button = QPushButton("감시 중지"); self.watch_button.setToolTip("다운로드 폴더 감시를 켜거나 끕니다."); self.watch_button.clicked.connect(self.toggle_watch); revise = QPushButton("분류 수정"); revise.setToolTip("선택한 파일의 카테고리를 바꿉니다."); revise.clicked.connect(self.revise); approve = QPushButton("선택 승인"); approve.setObjectName("primary"); approve.setToolTip("선택 파일을 지정 저장 폴더로 복사합니다."); approve.clicked.connect(self.approve); undo = QPushButton("되돌리기"); undo.setToolTip("마지막 승인 복사를 되돌립니다."); undo.clicked.connect(self.undo); actions.addWidget(self.scan_button); actions.addWidget(self.watch_button); actions.addStretch(); actions.addWidget(revise); actions.addWidget(approve); actions.addWidget(undo)
        filter_row.insertWidget(filter_row.count(), self.refresh_button)
        for button in (self.delete_button, self.refresh_button, self.scan_button, self.watch_button, revise, approve, undo):
            button.setStyleSheet("QPushButton { padding: 6px 12px; border: 2px solid; border-radius: 0px; border-color: #ffffff #404040 #404040 #ffffff; background: #c0c0c0; color: #000000; font-weight: normal; } QPushButton:pressed { border-color: #404040 #ffffff #ffffff #404040; background: #c0c0c0; font-weight: normal; }")
        main.addLayout(actions)
        self.dashboard_content = content
        body_layout.addWidget(content,1)
        self.settings_panel = self.build_settings_panel(); self.settings_panel.hide(); body_layout.addWidget(self.settings_panel,1)
        outer.addWidget(body,1); self.setCentralWidget(root); self.setStatusBar(QStatusBar()); self.statusBar().showMessage("준비됨")

    def build_settings_panel(self):
        panel = QWidget(); layout = QVBoxLayout(panel); layout.setContentsMargins(12, 0, 0, 0)
        title = QLabel("⚙ 설정"); title.setStyleSheet("font-size:25px;font-weight:bold;color:#153d70"); layout.addWidget(title)
        folder_box = QGridLayout(); folder_box.addWidget(QLabel("폴더 설정"), 0, 0, 1, 3)
        for i, label in enumerate(["감시할 다운로드 폴더", "임시 처리 폴더", "분류 저장 폴더"], 1):
            folder_box.addWidget(QLabel(label), i, 0); edit = QLineEdit(self.path_edits[i-1].text()); self.settings_path_edits = getattr(self, "settings_path_edits", []) + [edit]; folder_box.addWidget(edit, i, 1)
            button = QPushButton("폴더 선택"); button.clicked.connect(lambda _, e=edit: self.choose_folder(e)); folder_box.addWidget(button, i, 2)
        layout.addWidget(self.card(folder_box))
        ai = QGridLayout(); ai.addWidget(QLabel("AI 및 OCR"), 0, 0, 1, 2); ai.addWidget(QLabel("사용 모델"),1,0); self.settings_model_combo=QComboBox(); self.settings_model_combo.addItems([self.model_combo.itemText(i) for i in range(self.model_combo.count())]); self.settings_model_combo.setCurrentIndex(self.model_combo.currentIndex()); self.settings_model_combo.currentIndexChanged.connect(lambda i: self.model_combo.setCurrentIndex(i)); ai.addWidget(self.settings_model_combo,1,1)
        ai.addWidget(QLabel("검토 기준 신뢰도"),2,0); self.threshold_spin=QSpinBox(); self.threshold_spin.setRange(50,100); self.threshold_spin.setSuffix("%"); self.threshold_spin.setValue(round(self.config.get("fallback_threshold",.85)*100)); ai.addWidget(self.threshold_spin,2,1)
        self.ocr_check=QCheckBox("스캔 PDF 자동 OCR 사용"); self.ocr_check.setChecked(True); ai.addWidget(self.ocr_check,3,0,1,2); ai.addWidget(QLabel("OCR 최대 페이지"),4,0); self.ocr_pages=QSpinBox(); self.ocr_pages.setRange(1,50); self.ocr_pages.setValue(5); ai.addWidget(self.ocr_pages,4,1); layout.addWidget(self.card(ai))
        scan = QVBoxLayout(); scan.addWidget(QLabel("스캔 동작")); self.skip_duplicate=QCheckBox("이미 처리한 파일 건너뛰기"); self.skip_duplicate.setChecked(True); self.skip_done=QCheckBox("분류 완료 파일 건너뛰기"); self.skip_done.setChecked(True); self.background=QCheckBox("백그라운드로 실행"); self.background.setChecked(True)
        for box in (self.skip_duplicate,self.skip_done,self.background): scan.addWidget(box)
        layout.addWidget(self.card(scan)); layout.addStretch(); buttons=QHBoxLayout(); save=QPushButton("저장"); save.setObjectName("primary"); save.clicked.connect(self.save_settings_page); reset=QPushButton("기본값 복원"); reset.clicked.connect(self.reset_settings_page); cancel=QPushButton("취소"); cancel.clicked.connect(lambda: self.change_page(0)); buttons.addStretch(); buttons.addWidget(save); buttons.addWidget(reset); buttons.addWidget(cancel); layout.addLayout(buttons); return panel

    def change_page(self, row):
        is_settings = row == 2
        self.dashboard_content.setVisible(not is_settings); self.settings_panel.setVisible(is_settings)

    def save_settings_page(self):
        self.config["fallback_threshold"] = self.threshold_spin.value() / 100
        for source, target in zip(self.settings_path_edits, self.path_edits): target.setText(source.text())
        CONFIG_PATH.write_text(json.dumps(self.config, ensure_ascii=False, indent=2), encoding="utf-8"); self.save_settings(); self.statusBar().showMessage("설정을 저장했습니다.")

    def reset_settings_page(self):
        self.threshold_spin.setValue(85); self.ocr_pages.setValue(5); self.ocr_check.setChecked(True); self.skip_duplicate.setChecked(True); self.skip_done.setChecked(True); self.background.setChecked(True)

    def choose_folder(self, edit):
        folder = QFileDialog.getExistingDirectory(self, "폴더 선택", edit.text())
        if folder: edit.setText(folder); self.save_settings()

    def update_services(self):
        try:
            with urllib.request.urlopen(self.config.get("ollama_endpoint", "http://127.0.0.1:11434") + "/api/tags", timeout=1):
                ollama_ok = True
        except Exception:
            ollama_ok = False
        tesseract_ok = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe").exists()
        ollama_dot = "#008000" if ollama_ok else "#c00000"
        tesseract_dot = "#008000" if tesseract_ok else "#c00000"
        self.ollama_label.setText(f"Ollama (AI 분석)  <span style='color:{ollama_dot}'>●</span> {('연결됨' if ollama_ok else '연결 안 됨')}")
        self.tesseract_label.setText(f"Tesseract OCR  <span style='color:{tesseract_dot}'>●</span> {('연결됨' if tesseract_ok else '연결 안 됨')}")
        self.ollama_label.setStyleSheet("color:#000000;font-weight:normal")
        self.tesseract_label.setStyleSheet("color:#000000;font-weight:normal")

    def load_models(self):
        current = self.config.get("ollama_model", "")
        models = []
        try:
            result = subprocess.run(["ollama", "list"], capture_output=True, text=True, encoding="utf-8", timeout=2)
            models = [line.split()[0] for line in result.stdout.splitlines()[1:] if line.strip()]
        except (OSError, subprocess.SubprocessError):
            pass
        if current and current not in models: models.insert(0, current)
        for model in models:
            display = "Qwen3.5-9B" if "DeepSeek-V4-Pro-Qwen3.5-9B" in model else ("Qwen3-4B" if model == "qwen3:4b" else model)
            self.model_combo.addItem(display, model)
        index = max(0, self.model_combo.findData(current)); self.model_combo.setCurrentIndex(index)

    def model_changed(self):
        model = self.model_combo.currentData()
        if not model: return
        self.config["ollama_model"] = model
        CONFIG_PATH.write_text(json.dumps(self.config, ensure_ascii=False, indent=2), encoding="utf-8")
        self.save_settings()

    def save_settings(self):
        if not hasattr(self, "path_edits"): return
        GUI_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        GUI_SETTINGS_PATH.write_text(json.dumps({"input_dir": self.path_edits[0].text(), "staging_dir": self.path_edits[1].text(), "output_dir": self.path_edits[2].text()}, ensure_ascii=False, indent=2), encoding="utf-8")

    def closeEvent(self, event):
        self.save_settings()
        if self.watch_process and self.watch_process.poll() is None: self.watch_process.terminate()
        if self.scan_process and self.scan_process.state() != QProcess.NotRunning: self.scan_process.kill()
        event.accept()

    def db(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True); db = sqlite3.connect(DB_PATH); db.row_factory = sqlite3.Row; return db

    def refresh(self):
        with self.db() as db: rows = db.execute("SELECT id,source_path,category,confidence,status,reason,error FROM classifications ORDER BY id DESC").fetchall()
        counts = {"CLASSIFIED":0,"REVIEW_REQUIRED":0,"CONFIRMED":0}
        wanted = {"전체": None, "분류 완료": "CLASSIFIED", "검토 필요": "REVIEW_REQUIRED", "승인 완료": "CONFIRMED"}[self.filter_combo.currentText()] if hasattr(self, "filter_combo") else None
        rows = [row for row in rows if wanted is None or row["status"] == wanted]
        self.table.setUpdatesEnabled(False); self.table.blockSignals(True); sorting = self.table.isSortingEnabled(); self.table.setSortingEnabled(False); self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            self.set_result_row(r, row)
            counts[row["status"]] = counts.get(row["status"],0)+1
        self.table.setSortingEnabled(sorting); self.table.blockSignals(False); self.table.setUpdatesEnabled(True)
        for key, value in counts.items():
            if key in self.stat_labels: self.stat_labels[key].setText(str(value))
        self.stat_labels["TOTAL"].setText(str(len(rows)))

    def set_result_row(self, row_index, row):
        values = [row["id"], Path(row["source_path"]).name, row["category"] or "-",
                  f"{(row['confidence'] or 0):.0%}", row["status"],
                  row["reason"] or row["error"] or "-"]
        for column, value in enumerate(values):
            self.table.setItem(row_index, column, QTableWidgetItem(str(value)))

    def selected_id(self):
        items = self.table.selectedItems()
        return int(items[0].text()) if items else None

    def selected_ids(self):
        return [int(self.table.item(row, 0).text()) for row in sorted({item.row() for item in self.table.selectedItems()})]

    def show_selected(self):
        row = self.table.currentRow()
        if row < 0: return
        values = [self.table.item(row,c).text() for c in range(self.table.columnCount())]
        record_id = int(values[0]); source = None
        with self.db() as db: record = db.execute("SELECT source_path FROM classifications WHERE id=?", (record_id,)).fetchone(); source = record["source_path"] if record else None
        content = ""
        preview_status = values[4]
        if source and Path(source).exists():
            try:
                source_path = Path(source)
                if preview_status == "FAILED":
                    content = "(분류에 실패한 파일입니다. 본문 미리보기를 생략합니다.)"
                elif source_path.suffix.lower() == ".pdf":
                    import pymupdf
                    with pymupdf.open(source_path) as document:
                        content = "\n".join(page.get_text() for page in document[:3])[:3000]
                    if not content.strip():
                        content = "(스캔 PDF입니다. OCR은 백그라운드 분류 작업에서만 실행됩니다.)"
                else:
                    from main import extract_text
                    content = extract_text(source_path)[:800]
                if len(content) >= 800:
                    content = content[:800].rstrip() + "\n... (미리보기는 앞부분만 표시됩니다.)"
            except Exception as exc: content = f"미리보기 불가: {exc}"
        self.preview.setPlainText(f"파일: {values[1]}\n경로: {source or '-'}\n분류: {values[2]}\n신뢰도: {values[3]}\n상태: {values[4]}\n\n분류 근거:\n{values[5]}\n\n--- 파일 내용 미리보기 ---\n{content or '(추출 가능한 내용이 없습니다.)'}")

    def scan(self):
        if self.scan_process and self.scan_process.state() != QProcess.NotRunning:
            self.scan_process.kill(); self.scan_process = None; self.scan_button.setText("스캔 시작"); self.progress_title.setText("스캔 중지됨"); self.statusBar().showMessage("스캔을 중지했습니다."); return
        input_path = Path(self.path_edits[0].text())
        total = sum(1 for path in input_path.rglob("*") if path.is_file() and path.suffix.lower() in self.config["input_extensions"]) if input_path.is_dir() else 0
        self.scan_total = total; self.scan_done = 0; self.scan_title_time = __import__("time").monotonic()
        self.progress_title.setText("스캔 진행 중"); self.progress_count.setText(f"처리 파일: 0 / {total}"); self.progress_bar.setValue(0); self.progress_current.setText("현재 처리 파일: 준비 중...")
        self.scan_process = QProcess(self); self.scan_process.setWorkingDirectory(str(ROOT))
        python_exe = Path(sys.executable).with_name("python.exe")
        self.scan_process.setProgram(str(python_exe if python_exe.exists() else sys.executable))
        self.scan_process.setArguments([str(ROOT/"main.py"), "scan", "--input", self.path_edits[0].text()])
        self.scan_process.readyReadStandardOutput.connect(self.scan_output); self.scan_process.readyReadStandardError.connect(self.scan_output); self.scan_process.errorOccurred.connect(self.scan_error); self.scan_process.finished.connect(self.scan_finished)
        self.scan_process.start(); self.scan_button.setText("스캔 중지"); self.statusBar().showMessage("스캔 준비 중...")

    def scan_error(self, error):
        self.scan_button.setText("스캔 시작")
        self.statusBar().showMessage(f"스캔 실행 오류: {self.scan_process.errorString() if self.scan_process else error}")

    def scan_output(self):
        if not self.scan_process: return
        text = bytes(self.scan_process.readAllStandardOutput()).decode("utf-8", errors="replace")
        text += bytes(self.scan_process.readAllStandardError()).decode("utf-8", errors="replace")
        message = " ".join(text.split())
        if message:
            for line in text.splitlines():
                if line.startswith("분석 중:"):
                    self.scan_done += 1; self.progress_current.setText(f"현재 처리 파일: {line.split(':', 1)[1].strip()}")
                    percent = int((self.scan_done / self.scan_total) * 100) if self.scan_total else 0; self.progress_bar.setValue(min(percent, 99)); self.progress_count.setText(f"처리 파일: {self.scan_done} / {self.scan_total}")
            self.statusBar().showMessage(message[-220:])

    def scan_finished(self):
        code = self.scan_process.exitCode() if self.scan_process else -1
        self.scan_button.setText("스캔 시작"); self.progress_title.setText("스캔 완료" if code == 0 else "스캔 실패"); self.progress_bar.setValue(100 if code == 0 else self.progress_bar.value()); self.progress_count.setText(f"처리 파일: {self.scan_done} / {self.scan_total}"); self.progress_current.setText("현재 처리 파일: 완료"); self.statusBar().showMessage("스캔 완료" if code == 0 else f"스캔 종료 코드: {code}"); self.scan_process.deleteLater(); self.scan_process = None; self.refresh()

    def toggle_watch(self):
        if self.watch_process and self.watch_process.poll() is None:
            self.watch_process.terminate(); self.watch_process = None; self.watch_button.setText("감시 시작"); self.watch_label.setText("●  감시 중지"); self.statusBar().showMessage("폴더 감시를 중지했습니다.")
        else:
            self.watch_process = subprocess.Popen([sys.executable, str(ROOT/"main.py"), "watch", "--input", self.path_edits[0].text()], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.watch_button.setText("감시 중지"); self.watch_label.setText("●  감시 중"); self.statusBar().showMessage("폴더 감시를 시작했습니다.")

    def run_cli(self, args):
        result = subprocess.run([sys.executable, str(ROOT/"main.py"), *args], capture_output=True, text=True, encoding="utf-8")
        self.statusBar().showMessage((result.stdout or result.stderr).strip()[-180:]); self.refresh()

    def approve(self):
        record_ids = self.selected_ids()
        if not record_ids: return QMessageBox.information(self,"알림","승인할 파일을 선택하세요.")
        self.run_cli(["approve", *[str(value) for value in record_ids], "--target", self.path_edits[2].text()])

    def undo(self):
        record_id = self.selected_id()
        if record_id is not None: self.run_cli(["undo", str(record_id)])

    def delete_records(self):
        dialog = QDialog(self); dialog.setWindowTitle("전체 기록 삭제 확인"); dialog.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog); dialog.setFixedSize(390, 150); dialog.setAttribute(Qt.WA_StyledBackground, True); dialog.setStyleSheet("QDialog { background:#c0c0c0; border:2px solid; border-color:#ffffff #404040 #404040 #ffffff; }")
        outer = QVBoxLayout(dialog); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        title = QLabel("  전체 기록 삭제 확인"); title.setFixedHeight(23); title.setStyleSheet("background:#000080;color:#ffffff;font-weight:bold;padding:2px"); outer.addWidget(title)
        title_line = QFrame(); title_line.setFrameShape(QFrame.HLine); title_line.setFrameShadow(QFrame.Sunken); outer.addWidget(title_line)
        body = QVBoxLayout(); body.setContentsMargins(16, 10, 16, 8); body.addWidget(QLabel("분류 기록을 모두 삭제할까요?\n원본 파일은 삭제되지 않습니다."))
        buttons = QHBoxLayout(); buttons.setContentsMargins(0, 0, 8, 0); buttons.addStretch(); yes = QPushButton("예"); no = QPushButton("아니오"); yes.setFixedSize(64, 28); no.setFixedSize(64, 28); buttons.addWidget(yes); buttons.addWidget(no); body.addLayout(buttons); outer.addLayout(body)
        yes.clicked.connect(dialog.accept); no.clicked.connect(dialog.reject); dialog.exec()
        if dialog.result() == QDialog.Accepted: self.run_cli(["delete"])

    def revise(self):
        record_id = self.selected_id()
        if record_id is None: return QMessageBox.information(self,"알림","수정할 파일을 선택하세요.")
        category, accepted = QInputDialog.getItem(self, "분류 수정", "카테고리:", self.config["categories"], 0, False)
        if accepted: self.run_cli(["revise", str(record_id), "--category", category])


if __name__ == "__main__":
    app = QApplication(sys.argv); window = SorterWindow(); window.show()
    if "--scan-input" in sys.argv:
        index = sys.argv.index("--scan-input")
        if index + 1 < len(sys.argv):
            window.path_edits[0].setText(sys.argv[index + 1])
            QTimer.singleShot(300, window.scan)
    sys.exit(app.exec())
