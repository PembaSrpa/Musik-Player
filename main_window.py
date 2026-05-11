import math
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QPushButton, QLabel, QSlider, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QApplication, QSizePolicy
)
from PyQt6.QtCore import (
    Qt, QSize, QPoint, QByteArray, QRectF, QTimer, QEvent, QPointF, QMimeData
)
from PyQt6.QtGui import (
    QFont, QPixmap, QIcon, QColor, QPainter,
    QBrush, QPen, QCursor, QPainterPath, QRadialGradient,
    QConicalGradient, QDrag, QLinearGradient
)
from PyQt6.QtSvg import QSvgRenderer

from player import Player, RepeatMode, format_duration
from icons import (
    PLAY_SVG, PAUSE_SVG, PREV_SVG, NEXT_SVG,
    SHUFFLE_SVG, REPEAT_SVG, REPEAT_ONE_SVG,
    VOL_SVG, NOTE_SVG
)

ROW_HEIGHT = 44
SPIN_FPS = 60
RPM = 33.3


def svg_icon(data: bytes, size: int, color: str = "white") -> QIcon:
    colored = data.replace(b'fill="white"', f'fill="{color}"'.encode())
    colored = colored.replace(b'fill="currentColor"', f'fill="{color}"'.encode())
    renderer = QSvgRenderer(QByteArray(colored))
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    renderer.render(painter)
    painter.end()
    return QIcon(px)


def cover_placeholder(size: int = 48) -> QPixmap:
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QBrush(QColor("#2a2a2e")))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, size, size, 8, 8)
    renderer = QSvgRenderer(QByteArray(NOTE_SVG))
    margin = size // 4
    renderer.render(painter, QRectF(margin, margin, size - margin * 2, size - margin * 2))
    painter.end()
    return px


def _make_cd_cursor() -> QCursor:
    size = 32
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx, cy = size / 2, size / 2
    grad = QConicalGradient(cx, cy, 0)
    grad.setColorAt(0.0,  QColor("#b0b8c8"))
    grad.setColorAt(0.25, QColor("#e8eef8"))
    grad.setColorAt(0.5,  QColor("#8090a8"))
    grad.setColorAt(0.75, QColor("#d0d8e8"))
    grad.setColorAt(1.0,  QColor("#b0b8c8"))
    p.setBrush(QBrush(grad))
    p.setPen(QPen(QColor("#666"), 0.5))
    p.drawEllipse(QRectF(1, 1, size - 2, size - 2))
    hole_r = size * 0.09
    p.setBrush(QBrush(QColor("#111113")))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(cx, cy), hole_r, hole_r)
    p.end()
    return QCursor(px, size // 2, size // 2)


_CD_CURSOR: QCursor | None = None


def get_cd_cursor() -> QCursor:
    global _CD_CURSOR
    if _CD_CURSOR is None:
        _CD_CURSOR = _make_cd_cursor()
    return _CD_CURSOR


def make_ctrl_btn(svg: bytes, size: int = 20, btn_size: int = 36, color: str = "white") -> QPushButton:
    btn = QPushButton()
    btn.setIcon(svg_icon(svg, size, color))
    btn.setIconSize(QSize(size, size))
    btn.setFixedSize(btn_size, btn_size)
    btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    btn.setStyleSheet("""
        QPushButton { background: transparent; border: none; border-radius: 8px; }
        QPushButton:hover { background: rgba(255,255,255,0.07); }
        QPushButton:pressed { background: rgba(255,255,255,0.03); }
    """)
    return btn


def make_play_btn(size: int = 44) -> QPushButton:
    btn = QPushButton()
    btn.setFixedSize(size, size)
    btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    btn.setStyleSheet(f"""
        QPushButton {{ background: white; border: none; border-radius: {size // 2}px; }}
        QPushButton:hover {{ background: #e0e0e0; }}
        QPushButton:pressed {{ background: #cccccc; }}
    """)
    return btn


class TitleBar(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
        self._drag_pos = QPoint()
        self._dragging = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)

        dot_size = 12
        self._close_btn = QPushButton()
        self._min_btn = QPushButton()
        self._max_btn = QPushButton()
        for btn, color in zip(
            (self._close_btn, self._min_btn, self._max_btn),
            ("#ff5f57", "#febc2e", "#28c840")
        ):
            btn.setFixedSize(dot_size, dot_size)
            btn.setStyleSheet(f"""
                QPushButton {{ background: {color}; border: none; border-radius: {dot_size // 2}px; }}
                QPushButton:hover {{ background: {color}; border: 1px solid rgba(0,0,0,0.3); }}
            """)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            layout.addWidget(btn)

        win = parent
        self._close_btn.clicked.connect(lambda: win.close() if win else None)
        self._min_btn.clicked.connect(lambda: win.showMinimized() if win else None)
        self._max_btn.clicked.connect(self._toggle_max)

        layout.addStretch()
        lbl = QLabel(title)
        lbl.setFont(QFont("JetBrains Mono", 10))
        lbl.setStyleSheet("color: #888;")
        layout.addWidget(lbl)
        layout.addStretch()

        spacer = QWidget()
        spacer.setFixedWidth(dot_size * 3 + 8)
        layout.addWidget(spacer)
        self.setStyleSheet("background: #111113; border-bottom: 1px solid #222224;")

    def _toggle_max(self):
        win = self.window()
        if win.isMaximized():
            win.showNormal()
        else:
            win.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            self._dragging = True

    def mouseReleaseEvent(self, event):
        self._dragging = False

    def mouseMoveEvent(self, event):
        if self._dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_pos)


class VinylDisk(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumSize(180, 240)
        sp = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)
        self._angle = 0.0
        self._cover: QPixmap | None = None
        self._has_track = False
        self._spin_speed = 0.0
        self._target_speed = 0.0
        self._drop_highlight = False

        self._timer = QTimer(self)
        self._timer.setInterval(1000 // SPIN_FPS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, w: int) -> int:
        return int(w * 1.35)

    def set_cover(self, px: QPixmap | None):
        self._cover = px
        self._has_track = True
        self.update()

    def clear(self):
        self._cover = None
        self._has_track = False
        self.update()

    def set_playing(self, playing: bool):
        self._target_speed = (RPM * 360.0 / 60.0) / SPIN_FPS if playing else 0.0

    def _tick(self):
        diff = self._target_speed - self._spin_speed
        if abs(diff) > 0.0001:
            self._spin_speed += diff * 0.055
        else:
            self._spin_speed = self._target_speed
        if self._spin_speed > 0.0001:
            self._angle = (self._angle + self._spin_speed) % 360.0
            self.update()
        elif self._spin_speed != 0.0:
            self._spin_speed = 0.0
            self.update()

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            self._drop_highlight = True
            event.acceptProposedAction()
            self.update()

    def dragLeaveEvent(self, event):
        self._drop_highlight = False
        self.update()

    def dropEvent(self, event):
        self._drop_highlight = False
        self.update()
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w, h = float(self.width()), float(self.height())

        base_grad = QLinearGradient(0, 0, w, h)
        base_grad.setColorAt(0.0, QColor("#2e2e32"))
        base_grad.setColorAt(0.3, QColor("#252528"))
        base_grad.setColorAt(0.6, QColor("#2e2e32"))
        base_grad.setColorAt(1.0, QColor("#1e1e22"))
        p.setBrush(QBrush(base_grad))
        p.setPen(QPen(QColor("#3a3a40"), 1.5))
        p.drawRoundedRect(QRectF(0, 0, w, h), 12, 12)

        p.save()
        p.setClipRect(QRectF(0, 0, w, h))
        grain_pen = QPen(QColor(180, 180, 200, 8), 0.6)
        p.setPen(grain_pen)
        for i in range(0, int(h), 9):
            p.drawLine(QPointF(0, i), QPointF(w, i + 1))
        p.restore()

        cx = w * 0.44
        cy = h * 0.50
        r  = min(w, h) * 0.38

        shad = QRadialGradient(cx + 4, cy + 6, r * 1.05)
        shad.setColorAt(0, QColor(0, 0, 0, 80))
        shad.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(shad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx + 4, cy + 6), r * 1.05, r * 1.05)

        plat = QRadialGradient(cx - r * 0.2, cy - r * 0.2, r * 1.2)
        plat.setColorAt(0,   QColor("#3a3a3a"))
        plat.setColorAt(0.5, QColor("#222222"))
        plat.setColorAt(1,   QColor("#111111"))
        p.setBrush(QBrush(plat))
        p.setPen(QPen(QColor("#1a1a1a"), 2))
        p.drawEllipse(QPointF(cx, cy), r, r)

        if self._has_track:
            self._draw_vinyl(p, cx, cy, r, spinning=True)
        else:
            self._draw_vinyl(p, cx, cy, r, spinning=False)

        self._draw_tonearm(p, w, h, cx, cy, r)
        self._draw_knob(p, w, h)

        if self._drop_highlight:
            p.setBrush(QBrush(QColor(200, 240, 96, 35)))
            p.setPen(QPen(QColor("#c8f060"), 2, Qt.PenStyle.DashLine))
            p.drawRoundedRect(QRectF(3, 3, w - 6, h - 6), 10, 10)
            p.setFont(QFont("JetBrains Mono", 9))
            p.setPen(QColor("#c8f060"))
            p.drawText(QRectF(0, h * 0.80, w, 22), Qt.AlignmentFlag.AlignCenter, "drop to play")

        p.end()

    def _draw_vinyl(self, p: QPainter, cx: float, cy: float, r: float, spinning: bool):
        p.save()
        p.translate(cx, cy)
        if spinning:
            p.rotate(self._angle)

        for i in range(28):
            frac = i / 28
            gr = r * (0.45 + frac * 0.52) * 0.97
            alpha = int((30 if spinning else 18) + frac * 22)
            p.setPen(QPen(QColor(255, 255, 255, alpha), 0.4))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(0, 0), gr, gr)

        label_r = r * 0.295

        if spinning and self._cover:
            cover_size = int(label_r * 2)
            scaled = self._cover.scaled(
                cover_size, cover_size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            ox = (scaled.width() - cover_size) // 2
            oy = (scaled.height() - cover_size) // 2
            cropped = scaled.copy(ox, oy, cover_size, cover_size)

            clip = QPainterPath()
            clip.addEllipse(QPointF(0, 0), label_r, label_r)
            p.save()
            p.setClipPath(clip)
            p.drawPixmap(int(-label_r), int(-label_r), cropped)
            p.restore()
        else:
            lg = QRadialGradient(0, 0, label_r)
            lg.setColorAt(0,   QColor("#f5f2ed"))
            lg.setColorAt(0.7, QColor("#ece8e2"))
            lg.setColorAt(1,   QColor("#dedad4"))
            p.setBrush(QBrush(lg))
            p.setPen(QPen(QColor("#bbb"), 0.5))
            p.drawEllipse(QPointF(0, 0), label_r, label_r)
            if not spinning:
                p.setFont(QFont("JetBrains Mono", 7))
                p.setPen(QColor("#888"))
                p.drawText(QRectF(-label_r, -10, label_r * 2, 20),
                           Qt.AlignmentFlag.AlignCenter, "drop a song")

        hole_r = r * 0.034
        p.setBrush(QBrush(QColor("#111113")))
        p.setPen(QPen(QColor("#333"), 0.5))
        p.drawEllipse(QPointF(0, 0), hole_r, hole_r)
        p.restore()

    def _draw_tonearm(self, p: QPainter, bw: float, bh: float,
                      cx: float, cy: float, r: float):
        p.save()
        px_x = bw * 0.86
        px_y = bh * 0.16
        piv_r = bw * 0.028

        pg = QRadialGradient(px_x - piv_r * 0.3, px_y - piv_r * 0.3, piv_r)
        pg.setColorAt(0, QColor("#d0d0d0"))
        pg.setColorAt(1, QColor("#606060"))
        p.setBrush(QBrush(pg))
        p.setPen(QPen(QColor("#444"), 1))
        p.drawEllipse(QPointF(px_x, px_y), piv_r, piv_r)

        ae_x = cx + r * 0.72
        ae_y = cy - r * 0.05
        arm_pen = QPen(QColor("#b0b0b0"), bw * 0.016)
        arm_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(arm_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(px_x, px_y)
        ctrl_x = (px_x + ae_x) / 2 + bw * 0.02
        ctrl_y = (px_y + ae_y) / 2 - bh * 0.08
        path.quadTo(ctrl_x, ctrl_y, ae_x, ae_y)
        p.drawPath(path)

        head_len = r * 0.14
        ha = math.radians(-20)
        hx = ae_x + math.cos(ha) * head_len
        hy = ae_y + math.sin(ha) * head_len
        hp = QPen(QColor("#909090"), bw * 0.010)
        hp.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(hp)
        p.drawLine(QPointF(ae_x, ae_y), QPointF(hx, hy))

        np_ = QPen(QColor("#cc4444"), bw * 0.005)
        np_.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(np_)
        p.drawLine(QPointF(hx, hy), QPointF(hx + 4, hy + 6))
        p.restore()

    def _draw_knob(self, p: QPainter, bw: float, bh: float):
        p.save()
        kx, ky, kr = bw * 0.50, bh * 0.91, bw * 0.026
        kg = QRadialGradient(kx - kr * 0.3, ky - kr * 0.3, kr * 1.2)
        kg.setColorAt(0, QColor("#888"))
        kg.setColorAt(1, QColor("#333"))
        p.setBrush(QBrush(kg))
        p.setPen(QPen(QColor("#555"), 1))
        p.drawEllipse(QPointF(kx, ky), kr, kr)
        p.setPen(QPen(QColor("#888"), 1))
        p.drawLine(QPointF(kx, ky - kr * 0.3), QPointF(kx, ky - kr * 0.9))
        p.restore()


class DragSongTable(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(3)
        self.setHorizontalHeaderLabels(["#", "TITLE", "ARTIST"])
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.setColumnWidth(0, 40)
        self.horizontalHeader().setStretchLastSection(False)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setStyleSheet("""
            QTableWidget {
                background: #111113; border: none; color: #ccc;
                font-size: 13px; font-family: 'JetBrains Mono'; outline: none;
            }
            QTableWidget::item { padding: 0 8px; border: none; }
            QTableWidget::item:selected { background: #222226; color: white; }
            QTableWidget::item:hover { background: #1a1a1e; }
            QHeaderView::section {
                background: #111113; color: #555; font-size: 11px;
                font-family: 'JetBrains Mono'; letter-spacing: 1px;
                border: none; border-bottom: 1px solid #222224;
                padding: 0 8px; height: 36px;
            }
            QScrollBar:vertical { background: transparent; width: 6px; }
            QScrollBar::handle:vertical { background: #333; border-radius: 3px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_col_widths(self.width())

    def _apply_col_widths(self, total_w: int):
        scroll_w = self.verticalScrollBar().sizeHint().width()
        available = total_w - 40 - scroll_w
        self.setColumnWidth(1, int(available * 0.60))
        self.setColumnWidth(2, int(available * 0.40))

    def set_column_ratio_maximized(self, total_w: int):
        scroll_w = self.verticalScrollBar().sizeHint().width()
        available = total_w - 40 - scroll_w
        self.setColumnWidth(1, int(available * 0.583))
        self.setColumnWidth(2, int(available * 0.417))

    def startDrag(self, actions):
        row = self.currentRow()
        if row < 0:
            return
        mime = QMimeData()
        mime.setText(str(row))
        drag = QDrag(self)
        drag.setMimeData(mime)
        blank = QPixmap(1, 1)
        blank.fill(Qt.GlobalColor.transparent)
        drag.setPixmap(blank)
        drag.setHotSpot(QPoint(0, 0))

        cursor = get_cd_cursor()
        drag.setDragCursor(cursor.pixmap(), Qt.DropAction.CopyAction)
        drag.setDragCursor(cursor.pixmap(), Qt.DropAction.MoveAction)
        drag.setDragCursor(cursor.pixmap(), Qt.DropAction.IgnoreAction)

        QApplication.setOverrideCursor(cursor)
        drag.exec(Qt.DropAction.CopyAction)
        QApplication.restoreOverrideCursor()

    def append_track(self, track: dict):
        row = self.rowCount()
        self.insertRow(row)
        num = QTableWidgetItem(str(row + 1))
        num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        num.setForeground(QColor("#555"))
        title = QTableWidgetItem(track["title"])
        title.setForeground(QColor("#e0e0e0"))
        artist = QTableWidgetItem(track["artist"])
        artist.setForeground(QColor("#777"))
        self.setItem(row, 0, num)
        self.setItem(row, 1, title)
        self.setItem(row, 2, artist)

    def highlight(self, index: int):
        for row in range(self.rowCount()):
            is_active = row == index
            for col in range(self.columnCount()):
                item = self.item(row, col)
                if not item:
                    continue
                if is_active:
                    item.setBackground(QColor("#1e1e22"))
                    if col == 1:
                        item.setForeground(QColor("white"))
                else:
                    item.setBackground(QColor("transparent"))
                    item.setForeground(
                        QColor("#555") if col == 0 else
                        QColor("#e0e0e0") if col == 1 else
                        QColor("#777")
                    )
        if 0 <= index < self.rowCount():
            self.scrollToItem(self.item(index, 0))


class TurntablePanel(QWidget):
    def __init__(self, player: Player, parent=None):
        super().__init__(parent)
        self._player = player
        self.setStyleSheet("background: #0e0e10;")
        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.disk = VinylDisk()
        layout.addWidget(self.disk, 1)

        self._player.playback_changed.connect(self.disk.set_playing)
        self._player.cover_ready.connect(self._on_cover)
        self._player.track_changed.connect(lambda _: self.disk.set_cover(None))

    def _on_cover(self, px):
        self.disk.set_cover(px)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasText():
            try:
                self._player.play_index(int(event.mimeData().text()))
            except ValueError:
                pass
            event.acceptProposedAction()


class ClickSeekSlider(QSlider):
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            val = int(event.position().x() / self.width() * self.maximum())
            self.setValue(val)
            self.sliderMoved.emit(val)
        super().mousePressEvent(event)


class ControlsBar(QWidget):
    def __init__(self, player: Player, parent=None):
        super().__init__(parent)
        self._player = player
        self._seeking = False
        self.setFixedHeight(110)
        self.setStyleSheet("background: #0d0d0f; border-top: 1px solid #1e1e22;")
        self._build()
        self._connect()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 10, 24, 10)
        root.setSpacing(6)

        seek_row = QHBoxLayout()
        seek_row.setSpacing(10)
        self._lbl_pos = QLabel("0:00")
        self._lbl_dur = QLabel("0:00")
        for lbl in (self._lbl_pos, self._lbl_dur):
            lbl.setFont(QFont("JetBrains Mono", 9))
            lbl.setStyleSheet("color: #555;")
            lbl.setFixedWidth(36)
        self._seek = ClickSeekSlider(Qt.Orientation.Horizontal)
        self._seek.setRange(0, 1000)
        self._seek.setStyleSheet(self._slider_style("#fff", "#333"))
        seek_row.addWidget(self._lbl_pos)
        seek_row.addWidget(self._seek)
        seek_row.addWidget(self._lbl_dur)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(0)

        self._cover = QLabel()
        self._cover.setPixmap(cover_placeholder(48))
        self._cover.setFixedSize(48, 48)
        self._lbl_title = QLabel("Not Playing")
        self._lbl_title.setFont(QFont("JetBrains Mono", 11, QFont.Weight.Bold))
        self._lbl_title.setStyleSheet("color: #f0f0f0;")
        self._lbl_artist = QLabel("")
        self._lbl_artist.setFont(QFont("JetBrains Mono", 9))
        self._lbl_artist.setStyleSheet("color: #666;")

        meta = QVBoxLayout()
        meta.setSpacing(2)
        meta.addWidget(self._lbl_title)
        meta.addWidget(self._lbl_artist)

        left = QHBoxLayout()
        left.setSpacing(12)
        left.addWidget(self._cover)
        left.addLayout(meta)
        left.addStretch()

        self._btn_shuffle = make_ctrl_btn(SHUFFLE_SVG, 18, 34, "#555")
        self._btn_prev    = make_ctrl_btn(PREV_SVG, 20, 34)
        self._btn_play    = make_play_btn(44)
        self._btn_play.setIcon(svg_icon(PLAY_SVG, 22, "#111"))
        self._btn_play.setIconSize(QSize(22, 22))
        self._btn_next    = make_ctrl_btn(NEXT_SVG, 20, 34)
        self._btn_repeat  = make_ctrl_btn(REPEAT_SVG, 18, 34, "#555")

        center = QHBoxLayout()
        center.setSpacing(4)
        for w in (self._btn_shuffle, self._btn_prev, self._btn_play,
                  self._btn_next, self._btn_repeat):
            center.addWidget(w)

        self._vol = QSlider(Qt.Orientation.Horizontal)
        self._vol.setRange(0, 100)
        self._vol.setValue(70)
        self._vol.setFixedWidth(100)
        self._vol.setStyleSheet(self._slider_style("#888", "#333"))
        vol_icon = QLabel()
        vol_icon.setPixmap(svg_icon(VOL_SVG, 16, "#555").pixmap(16, 16))

        right = QHBoxLayout()
        right.addStretch()
        right.addWidget(vol_icon)
        right.addWidget(self._vol)

        btn_row.addLayout(left, 1)
        btn_row.addLayout(center, 0)
        btn_row.addLayout(right, 1)

        root.addLayout(seek_row)
        root.addLayout(btn_row)

    def _connect(self):
        self._btn_prev.clicked.connect(self._player.prev)
        self._btn_play.clicked.connect(self._player.play_pause)
        self._btn_next.clicked.connect(self._player.next)
        self._btn_shuffle.clicked.connect(lambda: self._player.set_shuffle(not self._player.is_shuffle()))
        self._btn_repeat.clicked.connect(self._player.cycle_repeat)
        self._vol.valueChanged.connect(lambda v: self._player.set_volume(v / 100))
        self._seek.sliderPressed.connect(self._on_seek_pressed)
        self._seek.sliderReleased.connect(self._on_seek_released)
        self._seek.sliderMoved.connect(self._on_seek_moved)
        self._player.track_changed.connect(self._on_track)
        self._player.cover_ready.connect(self._on_cover)
        self._player.playback_changed.connect(self._on_playback)
        self._player.position_changed.connect(self._on_position)
        self._player.shuffle_changed.connect(self._sync_shuffle)
        self._player.repeat_changed.connect(self._sync_repeat)

    def set_volume_slider(self, value: float):
        self._vol.blockSignals(True)
        self._vol.setValue(int(value * 100))
        self._vol.blockSignals(False)

    def _on_track(self, track: dict):
        self._lbl_title.setText(track["title"])
        self._lbl_artist.setText(track["artist"])
        self._cover.setPixmap(cover_placeholder(48))

    def _on_cover(self, px):
        if px is not None:
            s = px.scaled(48, 48,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation)
            x = (s.width() - 48) // 2
            y = (s.height() - 48) // 2
            c = s.copy(x, y, 48, 48)
            out = QPixmap(48, 48)
            out.fill(Qt.GlobalColor.transparent)
            pp = QPainter(out)
            pp.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            path.addRoundedRect(0, 0, 48, 48, 6, 6)
            pp.setClipPath(path)
            pp.drawPixmap(0, 0, c)
            pp.end()
            self._cover.setPixmap(out)
        else:
            self._cover.setPixmap(cover_placeholder(48))

    def _on_playback(self, playing: bool):
        self._btn_play.setIcon(svg_icon(PAUSE_SVG if playing else PLAY_SVG, 22, "#111"))
        self._btn_play.setIconSize(QSize(22, 22))

    def _on_position(self, pos: int, dur: int):
        if not self._seeking and dur > 0:
            self._seek.setValue(int(pos / dur * 1000))
        self._lbl_pos.setText(format_duration(pos // 1000))
        self._lbl_dur.setText(format_duration(dur // 1000))

    def _on_seek_pressed(self):
        self._seeking = True

    def _on_seek_moved(self, value: int):
        dur = self._player.duration()
        if dur > 0:
            self._player.seek(int(value / 1000 * dur))

    def _on_seek_released(self):
        dur = self._player.duration()
        if dur > 0:
            self._player.seek(int(self._seek.value() / 1000 * dur))
        self._seeking = False

    def _sync_shuffle(self, enabled: bool):
        color = "#c8f060" if enabled else "#555"
        self._btn_shuffle.setIcon(svg_icon(SHUFFLE_SVG, 18, color))
        self._btn_shuffle.setIconSize(QSize(18, 18))

    def _sync_repeat(self, mode: RepeatMode):
        svg = REPEAT_ONE_SVG if mode == RepeatMode.ONE else REPEAT_SVG
        color = "#555" if mode == RepeatMode.OFF else "#c8f060"
        self._btn_repeat.setIcon(svg_icon(svg, 18, color))
        self._btn_repeat.setIconSize(QSize(18, 18))

    def _slider_style(self, handle: str, groove: str) -> str:
        return f"""
            QSlider::groove:horizontal {{ height: 3px; background: {groove}; border-radius: 2px; }}
            QSlider::handle:horizontal {{
                background: {handle}; width: 12px; height: 12px;
                margin: -5px 0; border-radius: 6px;
            }}
            QSlider::sub-page:horizontal {{ background: {handle}; border-radius: 2px; }}
        """

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            if child is None:
                win = self.window()
                if hasattr(win, 'toggle_disk_view') and not win.isMaximized():
                    win.toggle_disk_view()
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, player: Player):
        super().__init__()
        self._player = player
        self._disk_active = False
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(800, 560)
        self.resize(900, 620)
        self._build()
        self._connect()

    def _build(self):
        root = QWidget()
        root.setStyleSheet("background: #111113;")
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._title_bar = TitleBar("music", self)
        outer.addWidget(self._title_bar)

        self._body = QWidget()
        self._body.setStyleSheet("background: #111113;")
        self._body_layout = QHBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)
        outer.addWidget(self._body, 1)

        self._table = DragSongTable()
        self._tt_normal = TurntablePanel(self._player)
        self._stacked = QStackedWidget()
        self._stacked.addWidget(self._table)
        self._stacked.addWidget(self._tt_normal)
        self._stacked.setCurrentIndex(0)
        self._body_layout.addWidget(self._stacked, 1)

        self._tt_side = TurntablePanel(self._player)
        self._tt_side.setVisible(False)
        self._body_layout.addWidget(self._tt_side, 0)

        self._controls = ControlsBar(self._player)
        outer.addWidget(self._controls)

    def _connect(self):
        self._table.cellDoubleClicked.connect(lambda row, _: self._player.play_index(row))
        self._player.track_changed.connect(self._on_track)
        self._player.track_appended.connect(self._table.append_track)
        for panel in (self._tt_normal, self._tt_side):
            panel.disk.dropEvent = self._make_disk_drop(panel.disk)

    def _make_disk_drop(self, disk: VinylDisk):
        def _drop(event):
            disk._drop_highlight = False
            disk.update()
            if event.mimeData().hasText():
                try:
                    self._player.play_index(int(event.mimeData().text()))
                except ValueError:
                    pass
                event.acceptProposedAction()
        return _drop

    def _on_track(self, track: dict):
        idx = self._player.current_index()
        if idx is not None:
            self._table.highlight(idx)

    def toggle_disk_view(self):
        self._disk_active = not self._disk_active
        self._stacked.setCurrentIndex(1 if self._disk_active else 0)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            QTimer.singleShot(50, self._sync_layout)

    def _sync_layout(self):
        if self.isMaximized():
            self._stacked.setCurrentIndex(0)
            self._disk_active = False
            self._body_layout.setStretch(0, 65)
            self._body_layout.setStretch(1, 35)
            self._tt_side.setVisible(True)
            self._tt_side.update()
            self._tt_side.disk.update()
        else:
            self._tt_side.setVisible(False)
            self._body_layout.setStretch(0, 1)
            self._body_layout.setStretch(1, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.isMaximized() and self._tt_side.isVisible():
            self._table.set_column_ratio_maximized(int(self.width() * 0.65))

    def restore_volume(self):
        self._controls.set_volume_slider(self._player.volume())

    def closeEvent(self, event):
        self._player.save_state()
        event.accept()
