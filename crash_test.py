"""测试：从QThread发信号到主线程操作QTextEdit是否崩溃"""
import os, sys
os.environ['QT_OPENGL'] = 'software'
os.environ['QT_QUICK_BACKEND'] = 'software'
os.environ['QSG_RENDERER_LOOP'] = 'basic'
os.environ['QT_ANGLE_PLATFORM'] = 'swiftshader'

sys.path.insert(0, os.path.dirname(__file__))
from PySide6.QtCore import QThread, Signal, QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QTextEdit, QVBoxLayout, QWidget
from PySide6.QtGui import QTextCursor

app = QApplication(sys.argv)

class Worker(QThread):
    sig = Signal(str)
    done = Signal()
    def run(self):
        self.sig.emit('log from thread')
        self.done.emit()

w = QMainWindow()
c = QWidget()
w.setCentralWidget(c)
l = QVBoxLayout(c)
te = QTextEdit()
l.addWidget(te)

def on_sig(msg):
    te.append(msg)
    te.moveCursor(QTextCursor.End)

worker = Worker()
worker.sig.connect(on_sig)
worker.done.connect(lambda: (print('done'), QTimer.singleShot(500, app.quit)))
w.show()
worker.start()
print('started')
app.exec()
print('ALL OK')
