import cv2

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from valve_gui.camera import VideoSource, apply_frame_transform
from valve_gui.config_store import normalise_lock_geometry_regions, save_app_config
from valve_gui.lock_geometry import analyze_lock_geometry_regions, draw_lock_geometry_overlay


def default_lock_geometry_region(index: int, region=None):
    data = {
        "id": f"lock_roi_{index}",
        "name": f"ROI {index}",
        "enabled": True,
        "x": 0.35,
        "y": 0.35,
        "w": 0.25,
        "h": 0.20,
        "base_line_y": None,
        "red_line_y": None,
        "split_line_y": None,
        "gap_threshold_px": 6,
        "dark_threshold_ratio": 0.25,
        "dark_gray_threshold": 70,
        "mode": "both",
        "metal_edge_count": 1,
    }
    if region:
        data.update(region)
    return normalise_lock_geometry_regions([data])[0]


class LockGeometryCanvas(QLabel):
    def __init__(self, camera_config, on_region_added=None):
        super().__init__("No Signal")
        self.camera_config = camera_config
        self.on_region_added = on_region_added
        self.frame = None
        self.image_rect = QRect()
        self.drag_start = None
        self.drag_current = None
        self._cached_scaled: QPixmap | None = None
        self._cached_widget_size = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(640, 420)
        self.setObjectName("cameraImage")
        self.setMouseTracking(True)

    def set_frame(self, frame):
        self.frame = frame
        self._cached_scaled = None
        self.repaint_frame()

    def repaint_frame(self):
        if self.frame is None:
            self.clear()
            self.setText("No Signal")
            return
        current_size = (self.width(), self.height())
        if self._cached_scaled is None or self._cached_widget_size != current_size:
            rgb = cv2.cvtColor(self.frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            image = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
            self._cached_scaled = QPixmap.fromImage(image).scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._cached_widget_size = current_size
        scaled = self._cached_scaled
        canvas = QPixmap(self.size())
        canvas.fill(QColor("#ffffff"))
        painter = QPainter(canvas)
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        self.image_rect = QRect(x, y, scaled.width(), scaled.height())
        painter.drawPixmap(self.image_rect.topLeft(), scaled)
        self.draw_regions(painter)
        if self.drag_start and self.drag_current:
            painter.setPen(QPen(QColor("#176b5d"), 2, Qt.PenStyle.DashLine))
            painter.drawRect(QRect(self.drag_start, self.drag_current).normalized() & self.image_rect)
        painter.end()
        self.setPixmap(canvas)

    def draw_regions(self, painter):
        painter.setFont(QFont(painter.font().family(), 8))
        for region in getattr(self.camera_config, "lock_geometry_regions", []):
            rect = self.region_to_widget_rect(region)
            color = QColor("#176b5d") if region.get("enabled", True) else QColor("#7c8d96")
            painter.setPen(QPen(color, 2))
            painter.drawRect(rect)
            painter.drawText(rect.adjusted(5, 5, -5, -5), Qt.AlignmentFlag.AlignTop, region.get("name", "ROI"))
            self.draw_line(painter, rect, region.get("split_line_y"), QColor("#999999"))
            self.draw_line(painter, rect, region.get("red_line_y"), QColor("#ef4444"))
            self.draw_line(painter, rect, region.get("base_line_y"), QColor("#eab308"))

    def draw_line(self, painter, rect, ratio, color):
        if ratio is None:
            return
        y = rect.top() + int(float(ratio) * rect.height())
        painter.setPen(QPen(color, 1))
        painter.drawLine(rect.left(), y, rect.right(), y)

    def region_to_widget_rect(self, region):
        x = self.image_rect.left() + int(region["x"] * self.image_rect.width())
        y = self.image_rect.top() + int(region["y"] * self.image_rect.height())
        width = int(region["w"] * self.image_rect.width())
        height = int(region["h"] * self.image_rect.height())
        return QRect(x, y, width, height)

    def widget_rect_to_region(self, rect):
        clipped = rect.normalized() & self.image_rect
        if clipped.width() < 8 or clipped.height() < 8:
            return None
        return {
            "x": (clipped.left() - self.image_rect.left()) / self.image_rect.width(),
            "y": (clipped.top() - self.image_rect.top()) / self.image_rect.height(),
            "w": clipped.width() / self.image_rect.width(),
            "h": clipped.height() / self.image_rect.height(),
        }

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self.image_rect.contains(event.position().toPoint()):
            return
        if not getattr(self.camera_config, "lock_geometry_enabled", False):
            return
        self.drag_start = event.position().toPoint()
        self.drag_current = self.drag_start

    def mouseMoveEvent(self, event):
        if self.drag_start:
            self.drag_current = event.position().toPoint()
            self.repaint_frame()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self.drag_start:
            return
        self.drag_current = event.position().toPoint()
        region = self.widget_rect_to_region(QRect(self.drag_start, self.drag_current))
        self.drag_start = None
        self.drag_current = None
        if region and self.on_region_added:
            self.on_region_added(region)
        self.repaint_frame()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._cached_scaled = None
        self.repaint_frame()


class LockGeometryCameraEditor(QWidget):
    def __init__(self, camera_config, state):
        super().__init__()
        self.camera_config = camera_config
        self.state = state
        self.source = None
        self.loading = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.canvas = LockGeometryCanvas(camera_config, self.add_region_from_canvas)
        layout.addWidget(self.canvas, 5)

        side = QGroupBox("鎖緊幾何檢測")
        side.setObjectName("regionSidePanel")
        side_layout = QVBoxLayout(side)
        self.enable_box = QCheckBox("啟用本相機鎖緊幾何檢測")
        self.enable_box.setChecked(getattr(camera_config, "lock_geometry_enabled", False))
        self.enable_box.stateChanged.connect(self.toggle_enabled)
        side_layout.addWidget(self.enable_box)

        actions = QHBoxLayout()
        self.add_button = QPushButton("新增 ROI")
        self.delete_button = QPushButton("刪除選取")
        self.add_button.clicked.connect(self.add_default_region)
        self.delete_button.clicked.connect(self.delete_selected_region)
        actions.addWidget(self.add_button)
        actions.addWidget(self.delete_button)
        side_layout.addLayout(actions)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["名稱", "狀態", "模式", "X", "Y", "W", "H"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.load_selected_region)
        side_layout.addWidget(self.table, 1)

        form_group = QGroupBox("ROI 參數")
        form = QFormLayout(form_group)
        self.name_edit = QLineEdit()
        self.name_edit.editingFinished.connect(self.save_form_to_region)
        self.region_enabled = QCheckBox("啟用")
        self.region_enabled.stateChanged.connect(self.save_form_to_region)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("間隙", "gap")
        self.mode_combo.addItem("暗區", "dark")
        self.mode_combo.addItem("兩者", "both")
        self.mode_combo.currentIndexChanged.connect(self.save_form_to_region)
        self.gap_spin = QSpinBox()
        self.gap_spin.setRange(0, 500)
        self.gap_spin.valueChanged.connect(self.save_form_to_region)
        self.dark_ratio_spin = QDoubleSpinBox()
        self.dark_ratio_spin.setRange(0.0, 1.0)
        self.dark_ratio_spin.setSingleStep(0.01)
        self.dark_ratio_spin.setDecimals(3)
        self.dark_ratio_spin.valueChanged.connect(self.save_form_to_region)
        self.dark_gray_spin = QSpinBox()
        self.dark_gray_spin.setRange(0, 255)
        self.dark_gray_spin.valueChanged.connect(self.save_form_to_region)
        self.edge_count_spin = QSpinBox()
        self.edge_count_spin.setRange(1, 5)
        self.edge_count_spin.valueChanged.connect(self.save_form_to_region)
        form.addRow("名稱", self.name_edit)
        form.addRow("ROI 狀態", self.region_enabled)
        form.addRow("判斷模式", self.mode_combo)
        form.addRow("間隙門檻 px", self.gap_spin)
        form.addRow("暗區比例門檻", self.dark_ratio_spin)
        form.addRow("暗區灰階門檻", self.dark_gray_spin)
        form.addRow("金屬邊緣線數", self.edge_count_spin)

        self.base_auto, self.base_value = self.line_controls(form, "基準線")
        self.red_disabled, self.red_value = self.line_controls(form, "紅線", disabled_label="停用")
        self.split_auto, self.split_value = self.line_controls(form, "分割線")
        side_layout.addWidget(form_group)

        self.analysis_label = QLabel("尚未分析")
        self.analysis_label.setWordWrap(True)
        side_layout.addWidget(self.analysis_label)
        layout.addWidget(side, 5)
        self.refresh_table()
        self.update_controls_enabled()

    def line_controls(self, form, label, disabled_label="自動"):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        toggle = QCheckBox(disabled_label)
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 1.0)
        spin.setSingleStep(0.01)
        spin.setDecimals(3)
        toggle.stateChanged.connect(self.save_form_to_region)
        spin.valueChanged.connect(self.save_form_to_region)
        layout.addWidget(toggle)
        layout.addWidget(spin)
        form.addRow(label, row)
        return toggle, spin

    def start(self):
        self.stop()
        self.source = VideoSource(
            f"相機 {self.camera_config.slot}",
            self.camera_config.device_index,
            self.state.use_simulation,
            getattr(self.camera_config, "focus_mode", "auto"),
            getattr(self.camera_config, "manual_focus_value", 120),
        )

    def stop(self):
        if self.source:
            self.source.release()
            self.source = None

    def update_frame(self):
        if not self.source:
            return
        frame = self.source.read()
        if frame is None:
            self.canvas.setText(self.source.last_error or "無影像")
            return
        frame = apply_frame_transform(
            frame,
            flip_horizontal=self.camera_config.flip_horizontal,
            flip_vertical=self.camera_config.flip_vertical,
            rotation_degrees=self.camera_config.rotation_degrees,
        )
        analyses = analyze_lock_geometry_regions(frame, getattr(self.camera_config, "lock_geometry_regions", []))
        preview = draw_lock_geometry_overlay(frame.copy(), analyses, show_result=True)
        self.canvas.set_frame(preview)
        self.update_analysis_label(analyses)

    def update_analysis_label(self, analyses):
        if not analyses:
            self.analysis_label.setText("尚未設定啟用中的幾何 ROI")
            return
        text = []
        for analysis in analyses:
            name = analysis.region_config.get("name", "ROI")
            result = analysis.result
            text.append(
                f"{name}: {result.prediction} / gap {result.gap_px if result.gap_px is not None else '--'}px / "
                f"dark {result.dark_ratio:.3f}"
            )
        self.analysis_label.setText("\n".join(text))

    def toggle_enabled(self, _state=None):
        self.camera_config.lock_geometry_enabled = self.enable_box.isChecked()
        self.update_controls_enabled()
        self.save()

    def update_controls_enabled(self):
        enabled = self.enable_box.isChecked()
        self.add_button.setEnabled(enabled)
        self.delete_button.setEnabled(enabled)
        self.table.setEnabled(enabled)

    def next_region_index(self):
        return len(getattr(self.camera_config, "lock_geometry_regions", [])) + 1

    def add_default_region(self):
        self.add_region_from_canvas(None)

    def add_region_from_canvas(self, region):
        index = self.next_region_index()
        new_region = default_lock_geometry_region(index, region)
        self.camera_config.lock_geometry_regions.append(new_region)
        self.refresh_table()
        self.table.selectRow(self.table.rowCount() - 1)
        self.canvas.repaint_frame()
        self.save()

    def selected_region(self):
        row = self.table.currentRow()
        regions = getattr(self.camera_config, "lock_geometry_regions", [])
        if row < 0 or row >= len(regions):
            return None
        return regions[row]

    def refresh_table(self, keep_row=None):
        current = self.table.currentRow() if keep_row is None else keep_row
        self.table.setRowCount(0)
        for row, region in enumerate(getattr(self.camera_config, "lock_geometry_regions", [])):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(region.get("name", f"ROI {row + 1}")))
            self.table.setItem(row, 1, QTableWidgetItem("啟用" if region.get("enabled", True) else "停用"))
            self.table.setItem(row, 2, QTableWidgetItem(self.mode_label(region.get("mode", "both"))))
            self.table.setItem(row, 3, QTableWidgetItem(f"{region.get('x', 0.0):.3f}"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{region.get('y', 0.0):.3f}"))
            self.table.setItem(row, 5, QTableWidgetItem(f"{region.get('w', 0.0):.3f}"))
            self.table.setItem(row, 6, QTableWidgetItem(f"{region.get('h', 0.0):.3f}"))
        if 0 <= current < self.table.rowCount():
            self.table.selectRow(current)
        else:
            self.load_selected_region()

    def mode_label(self, mode):
        return {"gap": "間隙", "dark": "暗區", "both": "兩者"}.get(mode, "兩者")

    def load_selected_region(self):
        region = self.selected_region()
        self.loading = True
        enabled = region is not None
        for widget in [
            self.name_edit,
            self.region_enabled,
            self.mode_combo,
            self.gap_spin,
            self.dark_ratio_spin,
            self.dark_gray_spin,
            self.edge_count_spin,
            self.base_auto,
            self.base_value,
            self.red_disabled,
            self.red_value,
            self.split_auto,
            self.split_value,
        ]:
            widget.setEnabled(enabled)
        if region:
            self.name_edit.setText(region.get("name", "ROI"))
            self.region_enabled.setChecked(region.get("enabled", True))
            self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData(region.get("mode", "both"))))
            self.gap_spin.setValue(int(region.get("gap_threshold_px", 6)))
            self.dark_ratio_spin.setValue(float(region.get("dark_threshold_ratio", 0.25)))
            self.dark_gray_spin.setValue(int(region.get("dark_gray_threshold", 70)))
            self.edge_count_spin.setValue(int(region.get("metal_edge_count", 1)))
            self.set_line_controls(self.base_auto, self.base_value, region.get("base_line_y"))
            self.set_line_controls(self.red_disabled, self.red_value, region.get("red_line_y"))
            self.set_line_controls(self.split_auto, self.split_value, region.get("split_line_y"))
        self.loading = False

    def set_line_controls(self, toggle, spin, value):
        auto = value is None
        toggle.setChecked(auto)
        spin.setEnabled(not auto)
        spin.setValue(0.5 if value is None else float(value))

    def save_form_to_region(self, *_args):
        if self.loading:
            return
        region = self.selected_region()
        if region is None:
            return
        region["name"] = self.name_edit.text().strip() or region.get("name", "ROI")
        region["enabled"] = self.region_enabled.isChecked()
        region["mode"] = self.mode_combo.currentData() or "both"
        region["gap_threshold_px"] = self.gap_spin.value()
        region["dark_threshold_ratio"] = self.dark_ratio_spin.value()
        region["dark_gray_threshold"] = self.dark_gray_spin.value()
        region["metal_edge_count"] = self.edge_count_spin.value()
        region["base_line_y"] = None if self.base_auto.isChecked() else self.base_value.value()
        region["red_line_y"] = None if self.red_disabled.isChecked() else self.red_value.value()
        region["split_line_y"] = None if self.split_auto.isChecked() else self.split_value.value()
        self.base_value.setEnabled(not self.base_auto.isChecked())
        self.red_value.setEnabled(not self.red_disabled.isChecked())
        self.split_value.setEnabled(not self.split_auto.isChecked())
        self.camera_config.lock_geometry_regions = normalise_lock_geometry_regions(
            self.camera_config.lock_geometry_regions
        )
        self.refresh_table(keep_row=self.table.currentRow())
        self.canvas.repaint_frame()
        self.save()

    def delete_selected_region(self):
        row = self.table.currentRow()
        regions = getattr(self.camera_config, "lock_geometry_regions", [])
        if row < 0 or row >= len(regions):
            return
        del regions[row]
        self.refresh_table()
        self.canvas.repaint_frame()
        self.save()

    def save(self):
        save_app_config(self.state)


class LockGeometrySettingsPage(QWidget):
    def __init__(self, state, on_logout=None):
        super().__init__()
        self.state = state
        self.on_logout = on_logout
        self.editors = []
        self.active_editor = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frames)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self.on_tab_changed)
        layout.addWidget(self.tabs, 1)

    def refresh(self):
        self.stop()
        self.tabs.clear()
        self.editors = []
        for camera in self.state.inspection_cameras:
            editor = LockGeometryCameraEditor(camera, self.state)
            self.editors.append(editor)
            self.tabs.addTab(editor, f"相機 {camera.slot}")
        self.start()

    def start(self):
        self.start_current_editor()
        self.timer.start(33)

    def stop(self):
        self.timer.stop()
        for editor in self.editors:
            editor.stop()
        self.active_editor = None

    def on_tab_changed(self, _index):
        if self.timer.isActive():
            self.start_current_editor()

    def start_current_editor(self):
        current = self.tabs.currentWidget()
        next_editor = current if current in self.editors else None
        if self.active_editor == next_editor:
            return
        if self.active_editor:
            self.active_editor.stop()
        self.active_editor = next_editor
        if self.active_editor:
            self.active_editor.start()

    def update_frames(self):
        current = self.tabs.currentWidget()
        if current and hasattr(current, "update_frame"):
            current.update_frame()

    def save_lock_geometry_settings(self):
        save_app_config(self.state)
        QMessageBox.information(self, "儲存完成", "鎖緊幾何檢測設定已儲存。")
        return True

    def logout(self):
        self.stop()
        if self.on_logout:
            self.on_logout()
