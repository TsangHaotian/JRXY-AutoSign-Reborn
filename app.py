"""
今日校园查寝签到工具 - tkinter桌面版
薄GUI层，业务逻辑委托给core.CpdailyClient
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import os
from PIL import Image, ImageTk

from core import CpdailyClient


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('今日校园查寝签到')
        self.root.geometry('520x750')
        self.root.resizable(False, False)

        # 核心客户端
        self.client = CpdailyClient.from_config()
        self.client.on_log = self.log

        self.login_thread = None
        self.poll_stop = False
        self.signing = False
        self.photo_path = ''
        self.current_tasks = []

        self._build_ui()
        self._init_school()

    def _build_ui(self):
        # ===== 登录区域 =====
        login_frame = ttk.LabelFrame(self.root, text='登录', padding=10)
        login_frame.pack(fill='x', padx=10, pady=5)

        self.login_status = tk.StringVar(value='正在初始化...')
        ttk.Label(login_frame, textvariable=self.login_status).pack()

        self.qr_label = ttk.Label(login_frame)
        self.qr_label.pack(pady=5)

        self.btn_login = ttk.Button(login_frame, text='扫码登录', command=self.start_login, state='disabled')
        self.btn_login.pack(pady=5)

        # ===== 校区/照片选择 =====
        cfg_frame = ttk.Frame(self.root)
        cfg_frame.pack(fill='x', padx=10, pady=2)

        ttk.Label(cfg_frame, text='校区:').pack(side='left')
        self.campus_var = tk.StringVar(value=self.client.campus)
        campus_menu = ttk.Combobox(cfg_frame, textvariable=self.campus_var,
                                   values=list(self.client.campuses.keys()),
                                   state='readonly', width=12)
        campus_menu.pack(side='left', padx=5)

        ttk.Label(cfg_frame, text=' 照片:').pack(side='left')
        self.photo_label = tk.StringVar(value='(可选)')
        ttk.Label(cfg_frame, textvariable=self.photo_label, width=15).pack(side='left', padx=2)
        ttk.Button(cfg_frame, text='选择', command=self._choose_photo).pack(side='left')

        # ===== 任务区域 =====
        task_frame = ttk.LabelFrame(self.root, text='查寝任务', padding=10)
        task_frame.pack(fill='both', expand=True, padx=10, pady=5)

        self.task_tree = ttk.Treeview(task_frame, columns=('status', 'time'), show='tree', height=5)
        self.task_tree.heading('#0', text='任务名称')
        self.task_tree.heading('status', text='状态')
        self.task_tree.heading('time', text='签到时间')
        self.task_tree.column('#0', width=200)
        self.task_tree.column('status', width=70)
        self.task_tree.column('time', width=160)
        self.task_tree.pack(fill='both', expand=True)
        self.task_tree.bind('<<TreeviewSelect>>', self._on_task_select)

        btn_frame = ttk.Frame(task_frame)
        btn_frame.pack(pady=5)
        self.btn_refresh = ttk.Button(btn_frame, text='刷新任务', command=self.refresh_tasks, state='disabled')
        self.btn_refresh.pack(side='left', padx=5)
        self.btn_sign = ttk.Button(btn_frame, text='签到选中任务', command=self.start_sign, state='disabled')
        self.btn_sign.pack(side='left', padx=5)

        # ===== 日志区域 =====
        log_frame = ttk.LabelFrame(self.root, text='日志', padding=5)
        log_frame.pack(fill='both', padx=10, pady=5)

        self.log_text = tk.Text(log_frame, height=10, width=60, state='disabled')
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

    # ==================== 工具方法 ====================

    def log(self, msg):
        def _append():
            self.log_text.configure(state='normal')
            import time
            now = time.strftime('%H:%M:%S')
            self.log_text.insert('end', f'[{now}] {msg}\n')
            self.log_text.see('end')
            self.log_text.configure(state='disabled')
        self.root.after(0, _append)

    def set_status(self, text):
        self.root.after(0, lambda: self.login_status.set(text))

    def show_qr(self, path):
        try:
            img = Image.open(path).resize((200, 200))
            photo = ImageTk.PhotoImage(img)
            self.qr_label.configure(image=photo)
            self.qr_label.image = photo
        except:
            pass

    def clear_qr(self):
        self.qr_label.configure(image='')

    def _choose_photo(self):
        path = filedialog.askopenfilename(title='选择签到照片',
                                          filetypes=[('图片', '*.jpg *.jpeg *.png')])
        if path:
            self.photo_path = path
            self.photo_label.set(os.path.basename(path)[:12])

    def _on_task_select(self, _event):
        sel = self.task_tree.selection()
        if sel:
            item = self.task_tree.item(sel[0])
            self.btn_sign.configure(state='normal' if item['values'][0] == '❌ 未签' else 'disabled')
        else:
            self.btn_sign.configure(state='disabled')

    # ==================== 学校初始化 ====================

    def _init_school(self):
        threading.Thread(target=self._do_init_school, daemon=True).start()

    def _do_init_school(self):
        try:
            self.client.init_school()
            self.set_status('准备就绪')
            self.root.after(0, lambda: self.btn_login.configure(state='normal'))
            if self.client.logged_in:
                self.set_status('✅ 已登录（恢复会话）')
                self.root.after(0, lambda: self.btn_refresh.configure(state='normal'))
                self.refresh_tasks()
        except Exception as e:
            self.log(f'初始化失败: {e}')
            self.set_status('初始化失败')

    # ==================== 扫码登录 ====================

    def start_login(self):
        if self.login_thread and self.login_thread.is_alive():
            return
        self.btn_login.configure(state='disabled')
        self.login_thread = threading.Thread(target=self._do_login, daemon=True)
        self.login_thread.start()

    def _do_login(self):
        try:
            # 获取并显示二维码
            self.log('正在获取二维码...')
            uuid, img_bytes = self.client.get_qr_image()
            self.log('二维码已生成，请用今日校园APP扫描')
            self.set_status('等待扫码...')

            # 保存并显示二维码
            qr_path = 'qrcode_login.png'
            with open(qr_path, 'wb') as f:
                f.write(img_bytes)
            self.root.after(0, lambda: self.show_qr(qr_path))

            # 轮询扫码
            def on_status(msg):
                self.set_status(msg)
                self.log(msg)

            success = self.client.poll_qr_login(uuid, on_status=on_status)

            if success:
                self.set_status('✅ 已登录')
                self.root.after(0, self.clear_qr)
                self.root.after(0, lambda: self.btn_refresh.configure(state='normal'))
                self.refresh_tasks()
            else:
                self.set_status('扫码超时')
                self.root.after(0, self.clear_qr)
                self.root.after(0, lambda: self.btn_login.configure(state='normal'))
        except Exception as e:
            self.log(f'登录异常: {e}')
            self.set_status('登录失败')
            self.root.after(0, self.clear_qr)
            self.root.after(0, lambda: self.btn_login.configure(state='normal'))

    # ==================== 刷新任务 ====================

    def refresh_tasks(self):
        self.btn_refresh.configure(state='disabled')
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        try:
            self.log('正在获取查寝任务...')
            result = self.client.list_tasks()
            self.current_tasks = result['all']

            def _update():
                self.task_tree.delete(*self.task_tree.get_children())
                for t in result['unsigned']:
                    tr = f"{t.get('singleTaskBeginTime','')} - {t.get('singleTaskEndTime','')}"
                    self.task_tree.insert('', 'end', text=t['taskName'], values=('❌ 未签', tr))
                for t in result['signed']:
                    tr = f"{t.get('singleTaskBeginTime','')} - {t.get('singleTaskEndTime','')}"
                    self.task_tree.insert('', 'end', text=t['taskName'], values=('✅ 已签', tr))
                if not result['all']:
                    self.task_tree.insert('', 'end', text='暂无查寝任务', values=('', ''))

            self.root.after(0, _update)
            self.log(f'今日: 未签到{len(result["unsigned"])}个, 已签到{len(result["signed"])}个')
        except Exception as e:
            self.log(f'获取任务失败: {e}')
        finally:
            self.root.after(0, lambda: self.btn_refresh.configure(state='normal'))

    # ==================== 签到 ====================

    def start_sign(self):
        if self.signing:
            return
        sel = self.task_tree.selection()
        if not sel:
            messagebox.showwarning('提示', '请先选择一个未签到任务')
            return
        item = self.task_tree.item(sel[0])
        if item['values'][0] != '❌ 未签':
            messagebox.showwarning('提示', '该任务已签到')
            return

        task_name = item['text']
        task = None
        for t in self.current_tasks:
            if t['taskName'] == task_name:
                task = t
                break
        if not task:
            messagebox.showerror('错误', '未找到任务数据，请刷新')
            return

        if not messagebox.askyesno('确认签到', f'确定签到"{task_name}"吗？'):
            return

        self.signing = True
        self.btn_sign.configure(state='disabled', text='签到中...')
        threading.Thread(target=self._do_sign, args=(task,), daemon=True).start()

    def _do_sign(self, task):
        try:
            campus = self.campus_var.get()
            result = self.client.sign_task(task, campus=campus, photo_path=self.photo_path)
            if result['success']:
                self.set_status('✅ 签到成功')
                self.root.after(0, lambda: messagebox.showinfo('成功', '签到成功!'))
                self.refresh_tasks()
            else:
                self.set_status('签到失败')
                self.root.after(0, lambda: messagebox.showerror('失败', f'签到失败: {result["message"]}'))
        except Exception as e:
            self.log(f'签到出错: {e}')
            self.set_status('签到出错')
            self.root.after(0, lambda: messagebox.showerror('错误', f'签到出错: {e}'))
        finally:
            self.signing = False
            self.root.after(0, lambda: self.btn_sign.configure(state='normal', text='签到选中任务'))

    # ==================== 启动 ====================

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    app = App()
    app.run()
