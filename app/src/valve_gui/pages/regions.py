import cv2

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
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
from valve_gui.config_store import save_app_config
from valve_gui.model_registry import camera_model_names, ensure_model_configs
from valve_gui.utils import decision_rule_key as _rule_key


class RegionCanvas(QLabel):
    def __init__(
        self,
        camera_config,
        on_regions_changed=None,
        overlay_config=None,
        region_defaults_provider=None,
    ):
        super().__init__("No Signal")
        self.camera_config = camera_config
        self.on_regions_changed = on_regions_changed
        self.overlay_config = overlay_config
        self.region_defaults_provider = region_defaults_provider
        self.mode = "include"
        self.frame = None
        self.frame_size = None
        self.image_rect = QRect()
        self.drag_start = None
        self.drag_current = None
        self._cached_scaled: QPixmap | None = None
        self._cached_widget_size = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(640, 420)
        self.setObjectName("cameraImage")
        self.setMouseTracking(True)

    def set_mode(self, mode):
        self.mode = mode

    def set_frame(self, frame):
        self.frame = frame
        height, width = frame.shape[:2]
        self.frame_size = (width, height)
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
        canvas.fill(QColor("#111827"))
        painter = QPainter(canvas)
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        self.image_rect = QRect(x, y, scaled.width(), scaled.height())
        painter.drawPixmap(self.image_rect.topLeft(), scaled)
        self.draw_regions(painter)
        if self.drag_start and self.drag_current:
            self.draw_drag_rect(painter)
        painter.end()
        self.setPixmap(canvas)

    def draw_regions(self, painter):
        detection_color = getattr(self.overlay_config, "detection_color", "#22c55e")
        exclusion_color = getattr(self.overlay_config, "exclusion_color", "#ef4444")
        self.draw_region_list(painter, self.camera_config.detection_regions, QColor(detection_color), "ROI")
        self.draw_region_list(painter, self.camera_config.exclusion_regions, QColor(exclusion_color), "排除")

    def draw_region_list(self, painter, regions, color, label):
        pen = QPen(color, 3)
        painter.setPen(pen)
        for index, region in enumerate(regions, start=1):
            rect = self.region_to_widget_rect(region)
            painter.drawRect(rect)
            painter.drawText(
                rect.adjusted(6, 6, -6, -6),
                Qt.AlignmentFlag.AlignTop,
                self.format_region_label(label, index, region),
            )

    def format_region_label(self, label, index, region):
        roi_id = region.get("roi_id")
        model_names = region.get("model_names", [])
        base = f"#{roi_id}" if roi_id is not None else f"{label} {index}"
        if model_names:
            return f"{base}: {', '.join(model_names)}"
        return base

    def draw_drag_rect(self, painter):
        color = QColor("#22c55e") if self.mode == "include" else QColor("#ef4444")
        painter.setPen(QPen(color, 2, Qt.PenStyle.DashLine))
        painter.drawRect(QRect(self.drag_start, self.drag_current).normalized() & self.image_rect)

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
        if not getattr(self.camera_config, "region_detection_enabled", False):
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
        if region:
            if self.region_defaults_provider:
                region.update(self.region_defaults_provider() or {})
            if self.mode == "include":
                self.camera_config.detection_regions.append(region)
            else:
                self.camera_config.exclusion_regions.append(region)
            if self.on_regions_changed:
                self.on_regions_changed()
        self.repaint_frame()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._cached_scaled = None
        self.repaint_frame()


class CameraRegionEditor(QWidget):
    def __init__(self, camera_config, state):
        super().__init__()
        self.camera_config = camera_config
        self.state = state
        self.source = None
        self.model_boxes = {}
        self.loading_model_selection = False
        self.loading_decision_controls = False
        self.decision_controls = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        left = QVBoxLayout()
        self.canvas = RegionCanvas(
            camera_config,
            self._on_region_added,
            self.state.region_overlay,
            self.new_region_defaults,
        )
        left.addWidget(self.canvas, 1)

        side = QGroupBox("已標示區域")
        side_layout = QVBoxLayout(side)
        self.enable_box = QCheckBox("啟用本相機範圍辨識")
        self.enable_box.setChecked(getattr(self.camera_config, "region_detection_enabled", False))
        self.enable_box.stateChanged.connect(self.toggle_region_detection)
        side_layout.addWidget(self.enable_box)

        side_layout.addWidget(QLabel("畫框模式"))

        mode_buttons = QHBoxLayout()
        self.include_button = QPushButton("新增辨識區域")
        self.include_button.setCheckable(True)
        self.include_button.setChecked(True)
        self.exclude_button = QPushButton("新增排除區域")
        self.exclude_button.setCheckable(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.include_button)
        self.mode_group.addButton(self.exclude_button)
        self.include_button.clicked.connect(lambda: self.change_mode("include"))
        self.exclude_button.clicked.connect(lambda: self.change_mode("exclude"))
        self.apply_mode_button_style()
        mode_buttons.addWidget(self.include_button)
        mode_buttons.addWidget(self.exclude_button)
        side_layout.addLayout(mode_buttons)

        self.region_table = QTableWidget(0, 7)
        self.region_table.setHorizontalHeaderLabels(["Type", "ROI ID", "X", "Y", "W", "H", "Models"])
        self.region_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.region_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.region_table.itemSelectionChanged.connect(self.load_selected_region_models)
        side_layout.addWidget(self.region_table, 1)

        roi_id_row = QHBoxLayout()
        roi_id_row.addWidget(QLabel("ROI 編號（0=不共用）"))
        self.roi_id_spin = QSpinBox()
        self.roi_id_spin.setRange(0, 99)
        self.roi_id_spin.setSpecialValueText("—")
        self.roi_id_spin.valueChanged.connect(self.save_selected_region_models)
        roi_id_row.addWidget(self.roi_id_spin)
        roi_id_row.addStretch()
        side_layout.addLayout(roi_id_row)

        self.model_group = QGroupBox("Region models")
        self.model_layout = QVBoxLayout(self.model_group)
        self.model_hint = QLabel(
            "Choose one or more models first, then draw a region. Empty means all models."
        )
        self.model_hint.setWordWrap(True)
        self.model_hint.setObjectName("mutedText")
        self.model_layout.addWidget(self.model_hint)
        self.refresh_model_checkboxes()
        side_layout.addWidget(self.model_group)
        side_layout.addWidget(self.build_decision_group())

        actions = QHBoxLayout()
        self.delete_button = QPushButton("刪除選取")
        self.delete_button.clicked.connect(self.delete_selected_region)
        self.clear_button = QPushButton("清除本相機")
        self.clear_button.clicked.connect(self.clear_regions)
        actions.addWidget(self.delete_button)
        actions.addWidget(self.clear_button)
        side_layout.addLayout(actions)

        layout.addLayout(left, 3)
        layout.addWidget(side, 1)
        self.refresh_region_table()
        self.update_region_controls_enabled()

    def _on_region_added(self):
        self.refresh_region_table(keep_selection=True)
        save_app_config(self.state)

    def toggle_region_detection(self, _state=None):
        self.camera_config.region_detection_enabled = self.enable_box.isChecked()
        self.update_region_controls_enabled()
        self.canvas.repaint_frame()
        save_app_config(self.state)

    def update_region_controls_enabled(self):
        enabled = self.enable_box.isChecked()
        self.include_button.setEnabled(enabled)
        self.exclude_button.setEnabled(enabled)
        self.region_table.setEnabled(enabled)
        self.model_group.setEnabled(enabled)
        self.delete_button.setEnabled(enabled)
        self.clear_button.setEnabled(enabled)

    def change_mode(self, mode):
        self.canvas.set_mode(mode)
        self.apply_mode_button_style()

    def apply_mode_button_style(self):
        self.include_button.setStyleSheet(
            "QPushButton { padding: 8px 10px; }"
            "QPushButton:checked { background: #dcfce7; border: 1px solid #22c55e; color: #166534; }"
        )
        self.exclude_button.setStyleSheet(
            "QPushButton { padding: 8px 10px; }"
            "QPushButton:checked { background: #fee2e2; border: 1px solid #ef4444; color: #991b1b; }"
        )

    def start(self):
        self.stop()
        self.source = VideoSource(
            f"CAMERA {self.camera_config.slot}",
            self.camera_config.device_index,
            self.state.use_simulation,
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
        self.canvas.set_frame(frame)

    def available_region_models(self):
        assigned = camera_model_names(self.camera_config)
        if assigned:
            return assigned
        return [model.name for model in self.state.model_configs if getattr(model, "enabled", True)]

    def refresh_model_checkboxes(self):
        for box in self.model_boxes.values():
            box.setParent(None)
        self.model_boxes = {}
        for model_name in self.available_region_models():
            box = QCheckBox(model_name)
            box.stateChanged.connect(self.save_selected_region_models)
            self.model_boxes[model_name] = box
            self.model_layout.addWidget(box)
        if not self.model_boxes:
            self.model_layout.addWidget(QLabel("No enabled models."))

    def build_decision_group(self):
        group = QGroupBox("判定設定")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        global_row = QHBoxLayout()
        global_row.addWidget(QLabel("全域 PASS 信心值門檻"))
        self.global_threshold = QDoubleSpinBox()
        self.global_threshold.setRange(0.0, 1.0)
        self.global_threshold.setSingleStep(0.05)
        self.global_threshold.setDecimals(3)
        self.global_threshold.setValue(self.state.decision.pass_confidence_threshold)
        self.global_threshold.valueChanged.connect(self.persist_decision_settings)
        global_row.addWidget(self.global_threshold)
        global_row.addStretch()
        layout.addLayout(global_row)

        model_names = self.available_region_models()
        if not model_names:
            empty = QLabel("No enabled models.")
            empty.setObjectName("mutedText")
            layout.addWidget(empty)
            return group

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        grid.addWidget(QLabel("模型"), 0, 0)
        grid.addWidget(QLabel("信心值閥值"), 0, 1)
        grid.addWidget(QLabel("必須偵測標籤框數"), 0, 2)

        self.loading_decision_controls = True
        for row, model_name in enumerate(model_names, start=1):
            rule = self.state.decision.model_rules.get(_rule_key(self.camera_config.slot, model_name), {})

            confidence = QDoubleSpinBox()
            confidence.setRange(0.0, 1.0)
            confidence.setSingleStep(0.05)
            confidence.setDecimals(3)
            confidence.setValue(float(rule.get("confidence_threshold", self.state.decision.pass_confidence_threshold)))
            confidence.valueChanged.connect(self.persist_decision_settings)

            count = QComboBox()
            for value in range(0, 21):
                count.addItem(str(value), value)
            required_count = int(rule.get("required_object_count", 1))
            if count.findData(required_count) < 0:
                count.addItem(str(required_count), required_count)
            count.setCurrentIndex(count.findData(required_count))
            count.currentIndexChanged.connect(self.persist_decision_settings)

            self.decision_controls[model_name] = {
                "confidence": confidence,
                "count": count,
            }
            grid.addWidget(QLabel(model_name), row, 0)
            grid.addWidget(confidence, row, 1)
            grid.addWidget(count, row, 2)
        self.loading_decision_controls = False

        layout.addLayout(grid)
        return group

    def persist_decision_settings(self, include_global=True):
        if self.loading_decision_controls:
            return
        if include_global:
            self.state.decision.pass_confidence_threshold = self.global_threshold.value()
        rules = dict(self.state.decision.model_rules)
        prefix = f"{self.camera_config.slot}::"
        for key in list(rules):
            if key.startswith(prefix):
                del rules[key]
        for model_name, controls in self.decision_controls.items():
            rules[_rule_key(self.camera_config.slot, model_name)] = {
                "confidence_threshold": controls["confidence"].value(),
                "required_object_count": int(controls["count"].currentData()),
            }
        self.state.decision.model_rules = rules
        save_app_config(self.state)

    def checked_region_model_names(self):
        return [
            model_name
            for model_name, box in self.model_boxes.items()
            if box.isChecked()
        ]

    def new_region_defaults(self):
        defaults = {"model_names": self.checked_region_model_names()}
        rid = self.roi_id_spin.value()
        defaults["roi_id"] = rid if rid > 0 else None
        return defaults

    def selected_region(self):
        row = self.region_table.currentRow()
        if row < 0:
            return None
        item = self.region_table.item(row, 0)
        if not item:
            return None
        kind, index = item.data(Qt.ItemDataRole.UserRole)
        regions = self.camera_config.detection_regions if kind == "include" else self.camera_config.exclusion_regions
        if index < 0 or index >= len(regions):
            return None
        return regions[index]

    def load_selected_region_models(self):
        region = self.selected_region()
        selected_models = set(region.get("model_names", [])) if region else set()
        self.loading_model_selection = True
        if region:
            for model_name, box in self.model_boxes.items():
                box.setChecked(model_name in selected_models)
            self.roi_id_spin.setValue(region.get("roi_id") or 0)
        self.loading_model_selection = False

    def save_selected_region_models(self, _state=None):
        if self.loading_model_selection:
            return
        region = self.selected_region()
        if region is None:
            return
        region["model_names"] = self.checked_region_model_names()
        rid = self.roi_id_spin.value()
        region["roi_id"] = rid if rid > 0 else None
        self.refresh_region_table(keep_selection=True)
        self.canvas.repaint_frame()
        save_app_config(self.state)

    def format_region_models(self, region):
        model_names = region.get("model_names", [])
        return ", ".join(model_names) if model_names else "All"

    def refresh_region_table(self, keep_selection=False):
        selected = None
        if keep_selection:
            current = self.region_table.item(self.region_table.currentRow(), 0)
            if current:
                selected = current.data(Qt.ItemDataRole.UserRole)
        rows = []
        for index, region in enumerate(self.camera_config.detection_regions):
            rows.append(("include", index, region))
        for index, region in enumerate(self.camera_config.exclusion_regions):
            rows.append(("exclude", index, region))
        self.region_table.setRowCount(0)
        for row_index, (kind, source_index, region) in enumerate(rows):
            self.region_table.insertRow(row_index)
            type_item = QTableWidgetItem("ROI" if kind == "include" else "Exclude")
            type_item.setData(Qt.ItemDataRole.UserRole, (kind, source_index))
            self.region_table.setItem(row_index, 0, type_item)
            roi_id = region.get("roi_id")
            self.region_table.setItem(row_index, 1, QTableWidgetItem(f"#{roi_id}" if roi_id is not None else "—"))
            self.region_table.setItem(row_index, 2, QTableWidgetItem(f"{region['x']:.3f}"))
            self.region_table.setItem(row_index, 3, QTableWidgetItem(f"{region['y']:.3f}"))
            self.region_table.setItem(row_index, 4, QTableWidgetItem(f"{region['w']:.3f}"))
            self.region_table.setItem(row_index, 5, QTableWidgetItem(f"{region['h']:.3f}"))
            self.region_table.setItem(row_index, 6, QTableWidgetItem(self.format_region_models(region)))
            if selected == (kind, source_index):
                self.region_table.selectRow(row_index)
        if not keep_selection:
            self.load_selected_region_models()

    def delete_selected_region(self):
        row = self.region_table.currentRow()
        if row < 0:
            return
        item = self.region_table.item(row, 0)
        if not item:
            return
        kind, index = item.data(Qt.ItemDataRole.UserRole)
        if kind == "include":
            del self.camera_config.detection_regions[index]
        else:
            del self.camera_config.exclusion_regions[index]
        self.refresh_region_table()
        self.canvas.repaint_frame()
        save_app_config(self.state)

    def clear_regions(self):
        self.camera_config.detection_regions = []
        self.camera_config.exclusion_regions = []
        self.refresh_region_table()
        self.canvas.repaint_frame()
        save_app_config(self.state)


class RegionOverlaySettingsPage(QWidget):
    def __init__(self, state, on_changed=None):
        super().__init__()
        self.state = state
        self.on_changed = on_changed
        self.model_color_buttons = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        group = QGroupBox("監視畫面方框顯示")
        group_layout = QVBoxLayout(group)

        self.show_box = QCheckBox("在監視畫面顯示指定範圍方框")
        self.show_box.setChecked(self.state.region_overlay.show_on_monitor)
        self.show_box.stateChanged.connect(self.save_settings)
        group_layout.addWidget(self.show_box)

        detection_row = QHBoxLayout()
        detection_row.addWidget(QLabel("辨識範圍方框顏色"))
        self.detection_button = QPushButton()
        self.detection_button.clicked.connect(lambda: self.choose_color("detection_color"))
        detection_row.addWidget(self.detection_button)
        detection_row.addStretch()
        group_layout.addLayout(detection_row)

        exclusion_row = QHBoxLayout()
        exclusion_row.addWidget(QLabel("排除範圍方框顏色"))
        self.exclusion_button = QPushButton()
        self.exclusion_button.clicked.connect(lambda: self.choose_color("exclusion_color"))
        exclusion_row.addWidget(self.exclusion_button)
        exclusion_row.addStretch()
        group_layout.addLayout(exclusion_row)

        yolo_group = QGroupBox("各 YOLO 模型方框顏色")
        yolo_layout = QVBoxLayout(yolo_group)
        for model in self.state.model_configs:
            if not getattr(model, "enabled", True):
                continue
            row = QHBoxLayout()
            row.addWidget(QLabel(model.name))
            button = QPushButton()
            button.clicked.connect(lambda _checked=False, name=model.name: self.choose_model_color(name))
            self.model_color_buttons[model.name] = button
            row.addWidget(button)
            row.addStretch()
            yolo_layout.addLayout(row)
        if not self.model_color_buttons:
            yolo_layout.addWidget(QLabel("目前沒有已啟用的 YOLO 模型。"))
        group_layout.addWidget(yolo_group)

        layout.addWidget(group)
        layout.addStretch()
        self.refresh_buttons()

    def choose_color(self, field):
        current = QColor(getattr(self.state.region_overlay, field))
        color = QColorDialog.getColor(current, self, "選擇方框顏色")
        if not color.isValid():
            return
        setattr(self.state.region_overlay, field, color.name())
        self.refresh_buttons()
        self.save_settings()

    def choose_model_color(self, model_name):
        current = QColor(self.yolo_color_for_model(model_name))
        color = QColorDialog.getColor(current, self, "選擇 YOLO 模型方框顏色")
        if not color.isValid():
            return
        self.state.region_overlay.yolo_model_colors[model_name] = color.name()
        self.refresh_buttons()
        self.save_settings()

    def save_settings(self):
        self.state.region_overlay.show_on_monitor = self.show_box.isChecked()
        save_app_config(self.state)
        if self.on_changed:
            self.on_changed()

    def refresh_buttons(self):
        self.apply_color_button(self.detection_button, self.state.region_overlay.detection_color)
        self.apply_color_button(self.exclusion_button, self.state.region_overlay.exclusion_color)
        for model_name, button in self.model_color_buttons.items():
            self.apply_color_button(button, self.yolo_color_for_model(model_name))

    def yolo_color_for_model(self, model_name):
        return self.state.region_overlay.yolo_model_colors.get(
            model_name,
            self.state.region_overlay.yolo_color,
        )

    def apply_color_button(self, button, color):
        button.setText(color)
        button.setStyleSheet(
            f"QPushButton {{ background: {color}; color: #111827; border: 1px solid #374151; padding: 8px 14px; }}"
        )


class RegionSettingsPage(QWidget):
    def __init__(self, state, on_logout=None):
        super().__init__()
        self.state = state
        self.on_logout = on_logout
        self.editors = []
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frames)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("指定範圍位置辨識")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        hint = QLabel("拖曳畫面可新增辨識區域或排除區域；綠色為辨識區域，紅色為不需要辨識區域。")
        hint.setObjectName("mutedText")
        layout.addWidget(hint)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

    def refresh(self):
        self.stop()
        ensure_model_configs(self.state)
        self.tabs.clear()
        self.editors = []
        for camera in self.state.inspection_cameras:
            editor = CameraRegionEditor(camera, self.state)
            self.editors.append(editor)
            self.tabs.addTab(editor, f"Camera {camera.slot}")
        self.tabs.addTab(RegionOverlaySettingsPage(self.state, self.repaint_editors), "監視顯示設定")
        self.start()

    def start(self):
        for editor in self.editors:
            editor.start()
        self.timer.start(33)

    def stop(self):
        self.timer.stop()
        for editor in self.editors:
            editor.stop()

    def update_frames(self):
        current = self.tabs.currentWidget()
        if current and hasattr(current, "update_frame"):
            current.update_frame()

    def repaint_editors(self):
        for editor in self.editors:
            editor.canvas.repaint_frame()

    def save_region_settings(self):
        for editor in self.editors:
            editor.persist_decision_settings(include_global=False)
        save_app_config(self.state)
        QMessageBox.information(self, "儲存完成", "指定範圍位置辨識設定已儲存。")

    def logout(self):
        self.stop()
        if self.on_logout:
            self.on_logout()
