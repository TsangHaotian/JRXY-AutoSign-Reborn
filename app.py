"""
今日校园查寝签到工具 - tkinter桌面版
薄GUI层，业务逻辑委托给core.CpdailyClient
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import os
import uuid
from datetime import datetime
from PIL import Image, ImageTk

import requests

from core import CpdailyClient, BASE_UA


# ==================== 主题色 ====================

COLOR_PRIMARY = '#2b5c8a'
COLOR_PRIMARY_LIGHT = '#4a8bc2'
COLOR_BG = '#f0f4f8'
COLOR_CARD = '#ffffff'
COLOR_TEXT = '#1a2332'
COLOR_TEXT_SECONDARY = '#6b7a8f'
COLOR_SUCCESS = '#27ae60'
COLOR_DANGER = '#e74c3c'
COLOR_WARNING = '#f39c12'
COLOR_BORDER = '#dce3ed'

FONT_TITLE = ('Microsoft YaHei', 14, 'bold')
FONT_NORMAL = ('Microsoft YaHei', 10)
FONT_SMALL = ('Microsoft YaHei', 9)
FONT_BOLD = ('Microsoft YaHei', 10, 'bold')


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f'今日校园查寝签到 v2.3')
        self.root.geometry('960x960')
        self.root.minsize(860, 900)
        self.root.configure(bg=COLOR_BG)

        # 核心客户端
        self.client = CpdailyClient.from_config()
        self.client.on_log = self._core_log

        self.login_thread = None
        self.poll_stop = False
        self.signing = False
        self.photo_path = ''
        self.current_tasks = []
        self.user_info = {}  # 登录后存储用户信息
        self.log_messages = []

        self._build_ui()
        self._init_school()

    # ==================== UI 构建 ====================

    def _build_header(self, parent):
        """顶部标题区"""
        header = tk.Frame(parent, bg=COLOR_PRIMARY, height=50)
        header.pack(fill='x')
        header.pack_propagate(False)

        tk.Label(header, text='🏫 今日校园查寝签到', fg='white', bg=COLOR_PRIMARY,
                 font=FONT_TITLE).pack(side='left', padx=20, pady=8)

    def _build_login_card(self, parent):
        """登录卡片（左二维码 + 右信息）"""
        card = tk.Frame(parent, bg=COLOR_CARD, highlightbackground=COLOR_BORDER,
                        highlightthickness=1, padx=15, pady=12)
        card.pack(fill='x', padx=12, pady=(12, 0))

        # 标题行
        tk.Label(card, text='🔐 登录认证', font=FONT_BOLD, bg=COLOR_CARD,
                 fg=COLOR_TEXT).pack(anchor='w')

        # 左右布局
        body = tk.Frame(card, bg=COLOR_CARD)
        body.pack(fill='x', pady=6)

        # 左侧：二维码
        left = tk.Frame(body, bg=COLOR_CARD)
        left.pack(side='left', fill='y')
        self.qr_label = tk.Label(left, bg=COLOR_CARD)
        self.qr_label.pack(pady=(10, 0))
        self.btn_login = tk.Button(left, text='📱 扫码登录', font=FONT_NORMAL,
                                   bg=COLOR_PRIMARY, fg='white', relief='flat',
                                   activebackground=COLOR_PRIMARY_LIGHT,
                                   command=self.start_login, state='disabled',
                                   width=16, height=1)
        self.btn_login.pack(pady=(8, 2))
        self.btn_switch = tk.Button(left, text='🔄 切换账号', font=FONT_SMALL,
                                    bg='white', fg=COLOR_TEXT, relief='flat',
                                    highlightbackground=COLOR_BORDER,
                                    command=self.switch_account, state='disabled',
                                    width=16)
        self.btn_switch.pack()

        # 右侧：登录状态 + 信息
        right = tk.Frame(body, bg=COLOR_CARD, padx=15)
        right.pack(side='left', fill='both', expand=True)

        self.login_status_title = tk.Label(right, text='状态', font=FONT_BOLD,
                                           bg=COLOR_CARD, fg=COLOR_TEXT_SECONDARY,
                                           anchor='w')
        self.login_status_title.pack(fill='x')

        self.login_status = tk.StringVar(value='正在初始化...')
        tk.Label(right, textvariable=self.login_status, font=FONT_NORMAL,
                 bg=COLOR_CARD, fg=COLOR_PRIMARY, anchor='w',
                 wraplength=400).pack(fill='x', pady=(2, 8))

        # 用户信息（登录后显示）
        self.user_frame = tk.Frame(right, bg=COLOR_CARD)
        self.user_label = tk.Label(self.user_frame, bg=COLOR_CARD,
                                   font=FONT_NORMAL, fg=COLOR_TEXT,
                                   wraplength=400, justify='left')
        self.user_label.pack(anchor='w')
        self.session_label = tk.Label(self.user_frame, bg=COLOR_CARD,
                                      font=FONT_SMALL, fg=COLOR_TEXT_SECONDARY)
        self.session_label.pack(anchor='w', pady=(2, 0))

    def _build_config_card(self, parent):
        """配置卡片"""
        card = tk.Frame(parent, bg=COLOR_CARD, highlightbackground=COLOR_BORDER,
                        highlightthickness=1, padx=15, pady=10)
        card.pack(fill='x', padx=12, pady=(8, 0))

        tk.Label(card, text='⚙️ 签到配置', font=FONT_BOLD, bg=COLOR_CARD,
                 fg=COLOR_TEXT).pack(anchor='w')

        row = tk.Frame(card, bg=COLOR_CARD)
        row.pack(fill='x', pady=4)

        tk.Label(row, text='签到校区', font=FONT_NORMAL, bg=COLOR_CARD,
                 fg=COLOR_TEXT).pack(side='left')
        self.campus_var = tk.StringVar(value=self.client.campus)
        campus_menu = ttk.Combobox(row, textvariable=self.campus_var,
                                   values=list(self.client.campuses.keys()),
                                   state='readonly', width=12, font=FONT_NORMAL)
        campus_menu.pack(side='left', padx=(8, 20))

        tk.Label(row, text='签到照片', font=FONT_NORMAL, bg=COLOR_CARD,
                 fg=COLOR_TEXT).pack(side='left')
        self.photo_label = tk.Label(row, text='未选择（非必选）', font=FONT_NORMAL,
                                    bg=COLOR_CARD, fg=COLOR_TEXT_SECONDARY)
        self.photo_label.pack(side='left', padx=(8, 4))
        ttk.Button(row, text='浏览', command=self._choose_photo, width=6).pack(side='left')

    def _build_task_card(self, parent):
        """任务卡片"""
        card = tk.Frame(parent, bg=COLOR_CARD, highlightbackground=COLOR_BORDER,
                        highlightthickness=1, padx=15, pady=10)
        card.pack(fill='both', expand=True, padx=12, pady=(8, 0))

        # 标题行 + 按钮（按钮放在右侧）
        title_row = tk.Frame(card, bg=COLOR_CARD)
        title_row.pack(fill='x')
        tk.Label(title_row, text='📋 查寝任务', font=FONT_BOLD, bg=COLOR_CARD,
                 fg=COLOR_TEXT).pack(side='left')

        self.task_count_label = tk.Label(title_row, text='', font=FONT_SMALL,
                                         bg=COLOR_CARD, fg=COLOR_TEXT_SECONDARY)
        self.task_count_label.pack(side='left', padx=8)

        self.btn_sign = tk.Button(title_row, text='✅ 签到选中', font=FONT_BOLD,
                                  bg=COLOR_SUCCESS, fg='white', relief='flat',
                                  command=self.start_sign, state='disabled',
                                  width=12)
        self.btn_sign.pack(side='right', padx=(4, 0))

        self.btn_refresh = tk.Button(title_row, text='🔄 刷新', font=FONT_NORMAL,
                                     bg='white', fg=COLOR_TEXT, relief='flat',
                                     highlightbackground=COLOR_BORDER,
                                     command=self.refresh_tasks, state='disabled',
                                     width=8)
        self.btn_refresh.pack(side='right')

        # 表格
        columns = ('status', 'sender', 'time')
        self.task_tree = ttk.Treeview(card, columns=columns, show='tree', height=3,
                                      selectmode='browse')
        self.task_tree.heading('#0', text='任务名称')
        self.task_tree.heading('status', text='状态')
        self.task_tree.heading('sender', text='发布人')
        self.task_tree.heading('time', text='签到时段')
        self.task_tree.column('#0', width=200, minwidth=160)
        self.task_tree.column('status', width=50, minwidth=45, anchor='center')
        self.task_tree.column('sender', width=160, minwidth=120)
        self.task_tree.column('time', width=180, minwidth=150)
        self.task_tree.bind('<<TreeviewSelect>>', self._on_task_select)

        scrollbar = ttk.Scrollbar(card, orient='vertical', command=self.task_tree.yview)
        self.task_tree.configure(yscrollcommand=scrollbar.set)
        self.task_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        self.sign_info_label = tk.Label(card, text='', font=FONT_SMALL,
                                        bg=COLOR_CARD, fg=COLOR_TEXT_SECONDARY)
        self.sign_info_label.pack(anchor='w', pady=(4, 0))

    def _build_log_card(self, parent):
        """日志卡片"""
        card = tk.Frame(parent, bg=COLOR_CARD, highlightbackground=COLOR_BORDER,
                        highlightthickness=1, padx=15, pady=8)
        card.pack(fill='both', padx=12, pady=(8, 12))

        tk.Label(card, text='📝 运行日志', font=FONT_BOLD, bg=COLOR_CARD,
                 fg=COLOR_TEXT).pack(anchor='w')

        self.log_text = tk.Text(card, height=18, font=('Consolas', 9),
                                bg='#f7f9fc', fg=COLOR_TEXT, relief='flat',
                                state='disabled', wrap='word')
        scrollbar = ttk.Scrollbar(card, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side='left', fill='both', expand=True, pady=(4, 0))
        scrollbar.pack(side='right', fill='y', pady=(4, 0))

    def _build_footer(self, parent):
        """底部信息"""
        footer = tk.Frame(parent, bg=COLOR_BG, height=24)
        footer.pack(fill='x')
        footer.pack_propagate(False)
        tk.Label(footer, text=f'v2.3 | {self.client.school_name} | 基于 MPL-2.0 开源',
                 font=('Microsoft YaHei', 8), bg=COLOR_BG,
                 fg=COLOR_TEXT_SECONDARY).pack(pady=3)

    def _build_ui(self):
        container = tk.Frame(self.root, bg=COLOR_BG)
        container.pack(fill='both', expand=True)

        self._build_header(container)
        self._build_login_card(container)
        self._build_config_card(container)
        self._build_task_card(container)
        self._build_log_card(container)
        self._build_footer(container)

    # ==================== 工具方法 ====================

    def _core_log(self, msg):
        """来自core的日志"""
        now = datetime.now().strftime('%H:%M:%S')
        self.log_messages.append((now, msg))

    def log(self, msg):
        """写入日志区"""
        now = datetime.now().strftime('%H:%M:%S')
        self.log_messages.append((now, msg))
        def _append():
            self.log_text.configure(state='normal')
            self.log_text.insert('end', f'[{now}] {msg}\n')
            self.log_text.see('end')
            self.log_text.configure(state='disabled')
        self.root.after(0, _append)

    def set_status(self, text, is_ok=False, is_err=False):
        """更新登录状态"""
        self.root.after(0, lambda: self.login_status.set(text))

    def show_qr(self, path):
        try:
            img = Image.open(path).resize((180, 180))
            # 加白边框
            bordered = Image.new('RGB', (190, 190), 'white')
            bordered.paste(img, (5, 5))
            photo = ImageTk.PhotoImage(bordered)
            self.qr_label.configure(image=photo)
            self.qr_label.image = photo
        except:
            pass

    def clear_qr(self):
        self.qr_label.configure(image='')

    def update_user_info(self):
        """登录后更新用户信息（显示学校、校区、会话时间）"""
        def _update():
            school = self.client.school_name
            campus = self.client.campus
            now = datetime.now().strftime('%Y-%m-%d %H:%M')

            lines = [
                f'🏫 {school}',
                f'📍 {campus}',
            ]
            self.user_label.configure(text='  |  '.join(lines))
            self.session_label.configure(text=f'🕐 会话时间: {now}  ·  状态: 有效')

            if not self.user_frame.winfo_ismapped():
                self.user_frame.pack(fill='x', pady=(4, 0))
        self.root.after(0, _update)

    def update_task_count(self, unsigned, signed):
        def _update():
            total = unsigned + signed
            if total == 0:
                self.task_count_label.configure(text='(暂无任务)')
            else:
                self.task_count_label.configure(
                    text=f'(未签 {unsigned} / 已签 {signed} / 共 {total})')
        self.root.after(0, _update)

    def _choose_photo(self):
        path = filedialog.askopenfilename(title='选择签到照片',
                                          filetypes=[('图片', '*.jpg *.jpeg *.png')])
        if path:
            self.photo_path = path
            self.photo_label.configure(text=os.path.basename(path)[:16],
                                       fg=COLOR_TEXT)

    def _on_task_select(self, _event):
        sel = self.task_tree.selection()
        if sel:
            item = self.task_tree.item(sel[0])
            vals = item['values']
            if vals and vals[0] == '❌':
                self.btn_sign.configure(state='normal')
                self.sign_info_label.configure(text='')
            else:
                self.btn_sign.configure(state='disabled')
                if vals:
                    self.sign_info_label.configure(text='已签到，无需重复')
        else:
            self.btn_sign.configure(state='disabled')
            self.sign_info_label.configure(text='')

    # ==================== 学校初始化 ====================

    def _init_school(self):
        threading.Thread(target=self._do_init_school, daemon=True).start()

    def _do_init_school(self):
        try:
            self.log('正在获取学校信息...')
            self.client.init_school()
            self.log(f'学校: {self.client.school_name}')
            self.log(f'域名: {self.client.campus_host}')
            self.set_status('准备就绪，请登录')
            self.root.after(0, lambda: self.btn_login.configure(state='normal'))
            if self.client.logged_in:
                self.set_status('✅ 已登录（恢复会话）', is_ok=True)
                self.root.after(0, lambda: self.btn_switch.configure(state='normal'))
                self.root.after(0, lambda: self.btn_refresh.configure(state='normal'))
                self.refresh_tasks()
        except Exception as e:
            self.log(f'初始化失败: {e}')
            self.set_status('初始化失败', is_err=True)

    def switch_account(self):
        """切换账号：清除会话 -> 重新扫码"""
        if self.signing:
            return
        if not messagebox.askyesno('切换账号', '确定切换账号吗？\n当前登录会话将被清除。'):
            return
        self.client._clear_session()
        self.client.logged_in = False
        self.client.session = requests.session()
        self.client.session.headers = {'User-Agent': BASE_UA}
        self.client.device_id = str(uuid.uuid4())

        # 恢复UI状态
        self.current_tasks = []
        self.root.after(0, lambda: self.task_tree.delete(*self.task_tree.get_children()))
        self.root.after(0, lambda: self.task_count_label.configure(text=''))
        self.root.after(0, lambda: self.btn_refresh.configure(state='disabled'))
        self.root.after(0, lambda: self.btn_switch.configure(state='disabled'))
        self.root.after(0, lambda: self.btn_login.configure(state='normal', text='📱 扫码登录'))
        self.root.after(0, self.clear_qr)
        self.set_status('会话已清除，请重新登录')
        self.log('已清除登录会话，请重新扫码登录')

    # ==================== 扫码登录 ====================

    def start_login(self):
        if self.login_thread and self.login_thread.is_alive():
            return
        self.btn_login.configure(state='disabled', text='登录中...')
        self.login_thread = threading.Thread(target=self._do_login, daemon=True)
        self.login_thread.start()

    def _do_login(self):
        try:
            self.log('正在获取二维码...')
            uuid, img_bytes = self.client.get_qr_image()
            self.log('二维码已生成，请用今日校园APP扫描')
            self.set_status('等待扫码...')

            qr_path = 'qrcode_login.png'
            with open(qr_path, 'wb') as f:
                f.write(img_bytes)
            self.root.after(0, lambda: self.show_qr(qr_path))

            def on_status(msg):
                self.set_status(msg)
                self.log(msg)

            success = self.client.poll_qr_login(uuid, on_status=on_status)

            if success:
                self.set_status('✅ 登录成功', is_ok=True)
                self.root.after(0, self.clear_qr)
                self.root.after(0, lambda: self.btn_login.configure(
                    state='disabled', text='✅ 已登录'))
                self.root.after(0, lambda: self.btn_switch.configure(state='normal'))
                self.root.after(0, lambda: self.btn_refresh.configure(state='normal'))
                self.refresh_tasks()
            else:
                self.set_status('扫码超时', is_err=True)
                self.root.after(0, self.clear_qr)
                self.root.after(0, lambda: self.btn_login.configure(
                    state='normal', text='📱 扫码登录'))
                self.root.after(0, lambda: self.btn_switch.configure(state='disabled'))
        except Exception as e:
            self.log(f'登录异常: {e}')
            self.set_status('登录失败', is_err=True)
            self.root.after(0, self.clear_qr)
            self.root.after(0, lambda: self.btn_login.configure(
                state='normal', text='📱 扫码登录'))

    # ==================== 刷新任务 ====================

    def refresh_tasks(self):
        self.btn_refresh.configure(state='disabled', text='刷新中...')
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        try:
            self.log('正在获取查寝任务...')
            result = self.client.list_tasks()
            self.current_tasks = result['all']
            unsigned = result['unsigned']
            signed = result['signed']

            self.update_task_count(len(unsigned), len(signed))
            self.update_user_info()

            def _update():
                self.task_tree.delete(*self.task_tree.get_children())
                for t in unsigned:
                    sender = t.get('senderUserName', '')
                    tr = f"{t.get('singleTaskBeginTime','')}-{t.get('singleTaskEndTime','')}"
                    self.task_tree.insert('', 'end', text=t['taskName'],
                                          values=('❌', sender, tr))
                for t in signed:
                    sender = t.get('senderUserName', '')
                    tr = f"{t.get('singleTaskBeginTime','')}-{t.get('singleTaskEndTime','')}"
                    self.task_tree.insert('', 'end', text=t['taskName'],
                                          values=('✅', sender, tr))
                if not result['all']:
                    self.task_tree.insert('', 'end', text='暂无查寝任务',
                                          values=('', '', ''))

            self.root.after(0, _update)
            self.log(f'今日: 未签到{len(unsigned)}个, 已签到{len(signed)}个')
        except Exception as e:
            self.log(f'获取任务失败: {e}')
        finally:
            self.root.after(0, lambda: self.btn_refresh.configure(
                state='normal', text='🔄 刷新'))

    # ==================== 签到 ====================

    def start_sign(self):
        if self.signing:
            return
        sel = self.task_tree.selection()
        if not sel:
            messagebox.showwarning('提示', '请先选择一个未签到任务')
            return
        item = self.task_tree.item(sel[0])
        vals = item['values']
        if not vals or vals[0] != '❌':
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

        if not messagebox.askyesno('确认签到', f'确定签到「{task_name}」吗？\n'
                                   f'校区: {self.campus_var.get()}'):
            return

        self.signing = True
        self.btn_sign.configure(state='disabled', text='签到中...')
        self.sign_info_label.configure(text='正在提交...', fg=COLOR_WARNING)
        threading.Thread(target=self._do_sign, args=(task,), daemon=True).start()

    def _do_sign(self, task):
        try:
            campus = self.campus_var.get()
            result = self.client.sign_task(task, campus=campus, photo_path=self.photo_path)
            if result['success']:
                self.set_status('✅ 签到成功', is_ok=True)
                self.log('✅ 签到成功!')
                self.root.after(0, lambda: messagebox.showinfo('成功', '签到成功!'))
                self.refresh_tasks()
            else:
                self.set_status('签到失败', is_err=True)
                self.log(f'❌ 签到失败: {result["message"]}')
                self.root.after(0, lambda: messagebox.showerror(
                    '失败', f'签到失败: {result["message"]}'))
        except Exception as e:
            self.log(f'签到出错: {e}')
            self.set_status('签到出错', is_err=True)
            self.root.after(0, lambda: messagebox.showerror('错误', f'签到出错: {e}'))
        finally:
            self.signing = False
            self.root.after(0, lambda: self.btn_sign.configure(
                state='normal', text='✅ 签到选中'))
            self.root.after(0, lambda: self.sign_info_label.configure(text=''))

    # ==================== 启动 ====================

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    app = App()
    app.run()
