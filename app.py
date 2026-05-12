"""
今日校园查寝签到 - PyQt5桌面版
专业界面，线程安全，业务逻辑委托给core.CpdailyClient
"""
import sys
import os
import traceback
from datetime import datetime
from PyQt5.QtCore import (QThread, pyqtSignal, Qt, QByteArray, QBuffer,
                          QIODevice)
from PyQt5.QtGui import QPixmap, QIcon, QFont, QTextCursor
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QComboBox,
                             QTableWidget, QTableWidgetItem, QHeaderView,
                             QTextEdit, QMessageBox, QFileDialog,
                             QGroupBox, QGridLayout, QFrame)

from core import CpdailyClient


# ==================== 工作线程 ====================

class LoginWorker(QThread):
    """扫码登录工作线程：获取二维码 + 轮询"""
    qr_ready = pyqtSignal(bytes)     # 二维码图片bytes
    status_update = pyqtSignal(str)  # 状态文字
    login_result = pyqtSignal(bool)  # 成功/失败

    def __init__(self, client):
        super().__init__()
        self.client = client
        self._cancel = False

    def run(self):
        try:
            self.status_update.emit('获取二维码...')
            uuid, img_bytes = self.client.get_qr_image()
            self.qr_ready.emit(img_bytes)
            self.status_update.emit('等待扫码...')

            def on_status(msg):
                if not self._cancel:
                    self.status_update.emit(msg)

            ok = self.client.poll_qr_login(uuid, on_status=on_status)
            self.login_result.emit(ok)
        except Exception as e:
            self.status_update.emit(f'登录失败: {e}')
            self.login_result.emit(False)

    def cancel(self):
        self._cancel = True


class TaskWorker(QThread):
    """一次性任务线程（查任务/签到等）"""
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, client, method_name, *args):
        super().__init__()
        self.client = client
        self.method_name = method_name
        self.args = args

    def run(self):
        try:
            method = getattr(self.client, self.method_name)
            result = method(*self.args)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(f'{self.method_name} 失败: {e}\n{traceback.format_exc()}')


# ==================== 主窗口 ====================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('今日校园查寝签到')
        self.resize(780, 680)
        self.setMinimumSize(700, 600)

        # 业务核心
        self.client = CpdailyClient.from_config()
        self.client.on_log = self._on_client_log

        # 状态
        self.current_tasks = []
        self.photo_path = ''
        self.login_worker = None
        self.task_worker = None

        self._build_ui()
        self._init_school()

    # ==================== UI 构建 ====================

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # ---- 顶部：标题 + 状态 ----
        top = QHBoxLayout()
        self.lbl_title = QLabel('今日校园查寝签到')
        self.lbl_title.setStyleSheet('font-size:18px; font-weight:bold; color:#1a1a1a;')
        top.addWidget(self.lbl_title)

        self.lbl_status = QLabel('初始化中...')
        self.lbl_status.setStyleSheet('color:#888; font-size:13px;')
        top.addWidget(self.lbl_status)
        top.addStretch()
        layout.addLayout(top)

        # ---- 登录卡片 ----
        grp_login = QGroupBox('登录认证')
        login_layout = QHBoxLayout(grp_login)

        # 左侧：二维码
        self.lbl_qr = QLabel()
        self.lbl_qr.setFixedSize(160, 160)
        self.lbl_qr.setAlignment(Qt.AlignCenter)
        self.lbl_qr.setStyleSheet('background:#f5f5f5; border:1px solid #ddd; border-radius:8px;')
        login_layout.addWidget(self.lbl_qr)

        # 右侧：信息
        right = QVBoxLayout()
        self.lbl_login_info = QLabel('尚未登录')
        self.lbl_login_info.setStyleSheet('font-size:14px; color:#555;')
        right.addWidget(self.lbl_login_info)
        right.addStretch()

        self.btn_login = QPushButton('扫码登录')
        self.btn_login.setFixedWidth(160)
        self.btn_login.setStyleSheet(
            'QPushButton { background:#0078d4; color:white; border:none; '
            'border-radius:4px; padding:8px 20px; font-size:14px; }'
            'QPushButton:hover { background:#106ebe; }'
            'QPushButton:disabled { background:#ccc; }')
        self.btn_login.clicked.connect(self._start_login)
        right.addWidget(self.btn_login, alignment=Qt.AlignLeft)

        login_layout.addLayout(right)
        layout.addWidget(grp_login)

        # ---- 配置行 ----
        cfg_layout = QHBoxLayout()

        cfg_layout.addWidget(QLabel('签到校区:'))
        self.cmb_campus = QComboBox()
        for name in self.client.campuses:
            self.cmb_campus.addItem(name, name)
        idx = self.cmb_campus.findText(self.client.campus)
        if idx >= 0:
            self.cmb_campus.setCurrentIndex(idx)
        self.cmb_campus.setFixedWidth(120)
        cfg_layout.addWidget(self.cmb_campus)

        cfg_layout.addSpacing(20)

        cfg_layout.addWidget(QLabel('签到照片:'))
        self.lbl_photo = QLabel('未选择')
        self.lbl_photo.setStyleSheet('color:#999;')
        cfg_layout.addWidget(self.lbl_photo)
        self.btn_photo = QPushButton('浏览...')
        self.btn_photo.clicked.connect(self._choose_photo)
        self.btn_photo.setFixedWidth(80)
        cfg_layout.addWidget(self.btn_photo)

        cfg_layout.addStretch()
        layout.addLayout(cfg_layout)

        # ---- 分割线 ----
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet('color:#e0e0e0;')
        layout.addWidget(sep1)

        # ---- 任务表标题行 ----
        task_header = QHBoxLayout()
        self.lbl_task_count = QLabel('查寝任务')
        self.lbl_task_count.setStyleSheet('font-size:14px; font-weight:bold;')
        task_header.addWidget(self.lbl_task_count)
        task_header.addStretch()

        self.btn_refresh = QPushButton('刷新')
        self.btn_refresh.setFixedWidth(80)
        self.btn_refresh.clicked.connect(self._refresh_tasks)
        self.btn_refresh.setEnabled(False)
        task_header.addWidget(self.btn_refresh)

        self.btn_sign = QPushButton('签到选中')
        self.btn_sign.setStyleSheet(
            'QPushButton { background:#107c10; color:white; border:none; '
            'border-radius:4px; padding:6px 16px; font-size:13px; }'
            'QPushButton:hover { background:#138c13; }'
            'QPushButton:disabled { background:#ccc; }')
        self.btn_sign.clicked.connect(self._start_sign)
        self.btn_sign.setEnabled(False)
        task_header.addWidget(self.btn_sign)
        layout.addLayout(task_header)

        # ---- 任务表格 ----
        self.task_table = QTableWidget(0, 4)
        self.task_table.setHorizontalHeaderLabels(['状态', '任务名称', '发布人', '签到时段'])
        self.task_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.task_table.setColumnWidth(0, 70)
        self.task_table.setColumnWidth(2, 130)
        self.task_table.setColumnWidth(3, 200)
        self.task_table.setSelectionBehavior(self.task_table.SelectRows)
        self.task_table.setSelectionMode(self.task_table.SingleSelection)
        self.task_table.setEditTriggers(self.task_table.NoEditTriggers)
        self.task_table.setAlternatingRowColors(True)
        self.task_table.verticalHeader().setVisible(False)
        self.task_table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.task_table)

        # ---- 日志 ----
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet('color:#e0e0e0;')
        layout.addWidget(sep2)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(140)
        self.log_text.setStyleSheet(
            'background:#1e1e1e; color:#d4d4d4; font-family:Consolas; font-size:11px; padding:6px;')
        layout.addWidget(self.log_text)

    # ==================== 日志 & 状态 ====================

    def _on_client_log(self, msg):
        """来自core的日志（可能来自工作线程）"""
        self.log(msg)

    def log(self, msg):
        now = datetime.now().strftime('%H:%M:%S')
        self.log_text.append(f'[{now}] {msg}')
        self.log_text.moveCursor(QTextCursor.End)

    def set_status(self, text, is_ok=False, is_err=False):
        color = '#107c10' if is_ok else ('#d32f2f' if is_err else '#888')
        self.lbl_status.setStyleSheet(f'color:{color}; font-size:13px;')
        self.lbl_status.setText(text)

    # ==================== 学校初始化 ====================

    def _init_school(self):
        self.set_status('正在初始化...')
        worker = TaskWorker(self.client, 'init_school')
        worker.finished.connect(self._on_init_done)
        worker.error.connect(lambda msg: self._on_error('初始化', msg))
        worker.start()

    def _on_init_done(self, data):
        self.log(f'学校: {self.client.school_name}')
        self.log(f'域名: {self.client.campus_host}')
        self.btn_login.setEnabled(True)
        if self.client.logged_in:
            self.set_status('已登录（恢复会话）', is_ok=True)
            self.btn_login.setEnabled(False)
            self.btn_login.setText('已登录')
            self.btn_refresh.setEnabled(True)
            self._refresh_tasks()
        else:
            self.set_status('准备就绪')

    # ==================== 扫码登录 ====================

    def _start_login(self):
        if self.login_worker and self.login_worker.isRunning():
            return
        self.btn_login.setEnabled(False)
        self.btn_login.setText('登录中...')
        self.lbl_qr.clear()

        self.login_worker = LoginWorker(self.client)

        def on_qr(img_bytes):
            pixmap = QPixmap()
            pixmap.loadFromData(img_bytes)
            pixmap = pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.lbl_qr.setPixmap(pixmap)

        def on_status(msg):
            self.set_status(msg)
            self.log(msg)

        def on_result(ok):
            self.lbl_qr.clear()
            if ok:
                self.set_status('已登录', is_ok=True)
                self.log('登录成功')
                self.btn_login.setText('已登录')
                self.btn_login.setEnabled(False)
                self.btn_refresh.setEnabled(True)
                self._refresh_tasks()
            else:
                self.set_status('登录失败', is_err=True)
                self.btn_login.setText('扫码登录')
                self.btn_login.setEnabled(True)

        self.login_worker.qr_ready.connect(on_qr)
        self.login_worker.status_update.connect(on_status)
        self.login_worker.login_result.connect(on_result)
        self.login_worker.start()

    # ==================== 刷新任务 ====================

    def _refresh_tasks(self):
        self.btn_refresh.setEnabled(False)
        self.btn_sign.setEnabled(False)
        self.set_status('获取任务...')
        self.log('正在获取查寝任务...')

        worker = TaskWorker(self.client, 'list_tasks')
        worker.finished.connect(self._on_tasks_loaded)
        worker.error.connect(lambda msg: self._on_error('获取任务', msg))
        worker.start()

    def _on_tasks_loaded(self, result):
        unsigned = result['unsigned']
        signed = result['signed']
        self.current_tasks = result['all']

        # 标记状态
        unsigned_ids = {t['signInstanceWid'] for t in unsigned}
        for t in self.current_tasks:
            t['_unsigned'] = t['signInstanceWid'] in unsigned_ids

        # 填充表格
        self.task_table.setRowCount(len(self.current_tasks))
        for i, t in enumerate(self.current_tasks):
            is_u = t.get('_unsigned', False)
            status_text = '❌ 未签到' if is_u else '✅ 已签到'
            item_status = QTableWidgetItem(status_text)
            item_status.setForeground(Qt.red if is_u else Qt.darkGreen)

            self.task_table.setItem(i, 0, item_status)
            self.task_table.setItem(i, 1, QTableWidgetItem(t.get('taskName', '')))
            self.task_table.setItem(i, 2, QTableWidgetItem(t.get('senderUserName', '')))
            tr = f"{t.get('singleTaskBeginTime','')} - {t.get('singleTaskEndTime','')}"
            self.task_table.setItem(i, 3, QTableWidgetItem(tr))

        self.lbl_task_count.setText(f'查寝任务（未签{len(unsigned)} / 已签{len(signed)}）')
        self.set_status(f'未签{len(unsigned)} 已签{len(signed)}')
        self.log(f'获取完成: 未签{len(unsigned)}, 已签{len(signed)}')
        self.btn_refresh.setEnabled(True)

    # ==================== 签到 ====================

    def _on_selection_changed(self):
        rows = self.task_table.selectionModel().selectedRows()
        if rows:
            row = rows[0].row()
            if row < len(self.current_tasks):
                t = self.current_tasks[row]
                self.btn_sign.setEnabled(t.get('_unsigned', False))
                return
        self.btn_sign.setEnabled(False)

    def _start_sign(self):
        rows = self.task_table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        task = self.current_tasks[row]

        reply = QMessageBox.question(self, '确认签到',
                                     f'签到「{task.get("taskName")}」？\n'
                                     f'校区：{self.cmb_campus.currentText()}',
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        self.btn_sign.setEnabled(False)
        self.btn_sign.setText('签到中...')
        self.set_status('正在签到...')

        campus = self.cmb_campus.currentText()
        worker = TaskWorker(self.client, 'sign_task', task, campus, self.photo_path)
        worker.finished.connect(self._on_sign_done)
        worker.error.connect(lambda msg: self._on_error('签到', msg))
        worker.start()

    def _on_sign_done(self, result):
        self.btn_sign.setText('签到选中')
        if result['success']:
            self.log('✅ 签到成功')
            self.set_status('签到成功', is_ok=True)
            QMessageBox.information(self, '成功', '签到成功！')
            self._refresh_tasks()
        else:
            self.log(f'❌ 签到失败: {result["message"]}')
            self.set_status('签到失败', is_err=True)
            QMessageBox.warning(self, '失败', f'签到失败: {result["message"]}')
            self.btn_sign.setEnabled(True)

    # ==================== 其他 ====================

    def _choose_photo(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择签到照片',
                                               '', '图片 (*.jpg *.jpeg *.png)')
        if path:
            self.photo_path = path
            self.lbl_photo.setText(os.path.basename(path))
            self.lbl_photo.setStyleSheet('color:#333;')

    def _on_error(self, action, msg):
        self.log(f'{action}失败: {msg}')
        self.set_status(f'{action}失败', is_err=True)
        self.btn_refresh.setEnabled(True)
        self.btn_sign.setText('签到选中')
        self.btn_sign.setEnabled(True)

    def closeEvent(self, event):
        if self.login_worker and self.login_worker.isRunning():
            self.login_worker.cancel()
            self.login_worker.wait(2000)
        if self.task_worker and self.task_worker.isRunning():
            self.task_worker.wait(2000)
        event.accept()


# ==================== 启动 ====================

def main():
    # 防崩溃：禁用ANGLE/DirectX，软件渲染
    import os as _os
    _os.environ['QT_OPENGL'] = 'software'
    _os.environ['QT_QUICK_BACKEND'] = 'software'
    _os.environ['QMLSCENE_DEVICE'] = 'softwarecontext'
    _os.environ['QT_ANGLE_PLATFORM'] = ''

    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
