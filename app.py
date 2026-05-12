"""
今日校园查寝签到 - 桌面版
仿iOS圆润设计，任务卡片式展示
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import os
import time
from datetime import datetime
from PIL import Image, ImageTk, ImageDraw

from core import CpdailyClient

# ==================== iOS风格主题 ====================
COLOR_BG = '#f2f2f7'
COLOR_CARD = '#ffffff'
COLOR_PRIMARY = '#007aff'
COLOR_DANGER = '#ff3b30'
COLOR_SUCCESS = '#34c759'
COLOR_WARNING = '#ff9500'
COLOR_TEXT = '#1c1c1e'
COLOR_TEXT_SUB = '#8e8e93'
COLOR_SEP = '#e5e5ea'

FONT_TITLE = ('.SF NS Text', 17, 'bold')
FONT_HEAD = ('.SF NS Text', 13, 'semibold')
FONT_BODY = ('.SF NS Text', 12)
FONT_CAPTION = ('.SF NS Text', 11)
FONT_MONO = ('Menlo', 10)

# 备选字体（Windows无SF字体时降级）
try:
    tk.Tk().withdraw()
    tk.Label(text='test', font=FONT_TITLE).destroy()
except:
    FONT_TITLE = ('Microsoft YaHei', 15, 'bold')
    FONT_HEAD = ('Microsoft YaHei', 12, 'bold')
    FONT_BODY = ('Microsoft YaHei', 11)
    FONT_CAPTION = ('Microsoft YaHei', 10)
    FONT_MONO = ('Consolas', 10)


def round_rect(canvas, x1, y1, x2, y2, r=12, **kw):
    """画圆角矩形"""
    points = [x1+r, y1, x2-r, y1,
              x2, y1, x2, y1+r,
              x2, y2-r, x2, y2,
              x2-r, y2, x1+r, y2,
              x1, y2, x1, y2-r,
              x1, y1+r, x1, y1]
    canvas.create_polygon(points, smooth=True, **kw)


class TaskCard(tk.Frame):
    """单个任务卡片"""
    def __init__(self, parent, task, status, on_click=None, **kw):
        super().__init__(parent, bg=COLOR_CARD, **kw)
        self.task = task
        self.status = status  # 'unsigned' or 'signed'
        self.on_click = on_click

        self.configure(highlightbackground=COLOR_SEP, highlightthickness=0)
        self.pack(fill='x', padx=0, pady=4)

        # 左侧状态色条
        bar_color = COLOR_DANGER if status == 'unsigned' else COLOR_SUCCESS
        bar = tk.Frame(self, bg=bar_color, width=4)
        bar.pack(side='left', fill='y')
        bar.pack_propagate(False)

        # 内容
        body = tk.Frame(self, bg=COLOR_CARD, padx=12, pady=10)
        body.pack(side='left', fill='x', expand=True)

        # 标题行
        title_row = tk.Frame(body, bg=COLOR_CARD)
        title_row.pack(fill='x')

        status_text = '未签到' if status == 'unsigned' else '已签到'
        status_color = COLOR_DANGER if status == 'unsigned' else COLOR_SUCCESS
        tk.Label(title_row, text=status_text, font=FONT_CAPTION,
                 fg=status_color, bg=COLOR_CARD).pack(side='right')

        tk.Label(title_row, text=task.get('taskName', '未知任务'),
                 font=FONT_BODY, fg=COLOR_TEXT, bg=COLOR_CARD,
                 anchor='w').pack(side='left')

        # 信息行
        info_row = tk.Frame(body, bg=COLOR_CARD)
        info_row.pack(fill='x', pady=(4, 0))

        sender = task.get('senderUserName', '系统')
        time_str = f"{task.get('singleTaskBeginTime','')} 至 {task.get('singleTaskEndTime','')}"

        tk.Label(info_row, text=f'👤 {sender}', font=FONT_CAPTION,
                 fg=COLOR_TEXT_SUB, bg=COLOR_CARD).pack(anchor='w')
        tk.Label(info_row, text=f'🕐 {time_str}', font=FONT_CAPTION,
                 fg=COLOR_TEXT_SUB, bg=COLOR_CARD).pack(anchor='w', pady=(1, 0))

        # 选中指示器
        if status == 'unsigned':
            self.select_indicator = tk.Canvas(self, width=24, height=24,
                                              bg=COLOR_CARD, highlightthickness=0)
            self.select_indicator.pack(side='right', padx=(0, 12))
            self._circle = self.select_indicator.create_oval(3, 3, 21, 21,
                                                             outline=COLOR_SEP, width=2)
            self._fill = None
        else:
            self.select_indicator = None

        # 点击绑定
        for child in [self, body, title_row, info_row]:
            for widget in [child] + child.winfo_children():
                widget.bind('<Button-1>', self._on_click)
                break

    def _on_click(self, e):
        if self.on_click:
            self.on_click(self)

    def set_selected(self, selected):
        if self.select_indicator is None:
            return
        if selected:
            self.select_indicator.delete(self._circle)
            self._fill = self.select_indicator.create_oval(3, 3, 21, 21,
                                                           fill=COLOR_PRIMARY, outline='')
            inner = self.select_indicator.create_oval(8, 8, 16, 16,
                                                      fill='white', outline='')
        else:
            self.select_indicator.delete('all')
            self._circle = self.select_indicator.create_oval(3, 3, 21, 21,
                                                             outline=COLOR_SEP, width=2)


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('今日校园')
        self.root.geometry('400x780')
        self.root.minsize(380, 700)
        self.root.configure(bg=COLOR_BG)

        self.client = CpdailyClient.from_config()
        self.client.on_log = self._core_log

        self.login_thread = None
        self.poll_stop = False
        self.signing = False
        self.photo_path = ''
        self.current_tasks = []
        self.selected_card = None
        self.task_cards = []
        self.log_messages = []

        self._build_ui()
        self._init_school()

    # ==================== UI ====================

    def _make_card(self, parent, title, content_widget, padding=12):
        """生成一个iOS风格卡片容器"""
        outer = tk.Frame(parent, bg=COLOR_BG)
        outer.pack(fill='x', padx=12, pady=4)
        outer.pack_propagate(False)

        # 白色卡片
        card = tk.Frame(outer, bg=COLOR_CARD)
        card.pack(fill='x')
        # 圆角效果用mask（PIL画圆角图片垫底）
        # 直接使用Frame的padding制造圆角假象

        if title:
            tk.Label(card, text=title, font=FONT_HEAD, bg=COLOR_CARD,
                     fg=COLOR_TEXT).pack(anchor='w', padx=14, pady=(12, 2))
        return card

    def _build_header(self, parent):
        header = tk.Frame(parent, bg=COLOR_BG)
        header.pack(fill='x', pady=(8, 0))

        tk.Label(header, text='查寝签到', font=FONT_TITLE,
                 fg=COLOR_TEXT, bg=COLOR_BG).pack(padx=16, anchor='w')

        self.status_text = tk.StringVar(value='初始化中')
        tk.Label(header, textvariable=self.status_text, font=FONT_CAPTION,
                 fg=COLOR_TEXT_SUB, bg=COLOR_BG).pack(padx=16, anchor='w')

    def _build_info_section(self, parent):
        """登录状态 + 用户信息"""
        card = tk.Frame(parent, bg=COLOR_CARD, padx=14, pady=10)
        card.pack(fill='x', padx=12, pady=4)

        # 状态行
        self.info_canvas = tk.Canvas(card, height=1, bg=COLOR_SEP,
                                     highlightthickness=0)
        self.info_canvas.pack(fill='x', pady=(0, 8))

        # 登录区域
        login_row = tk.Frame(card, bg=COLOR_CARD)
        login_row.pack(fill='x')

        self.btn_login = tk.Button(login_row, text='扫码登录', font=FONT_BODY,
                                   bg=COLOR_PRIMARY, fg='white', relief='flat',
                                   command=self.start_login, state='disabled',
                                   width=12, bd=0, padx=8, pady=4)
        self.btn_login.pack(side='right')

        self.status_label = tk.Label(login_row, text='准备就绪', font=FONT_BODY,
                                     fg=COLOR_TEXT_SUB, bg=COLOR_CARD)
        self.status_label.pack(side='left')

        # 二维码（默认隐藏）
        self.qr_frame = tk.Frame(card, bg=COLOR_CARD)
        self.qr_label = tk.Label(self.qr_frame, bg=COLOR_CARD)

        # 用户信息（登录后显示）
        self.user_frame = tk.Frame(card, bg=COLOR_CARD)
        self.user_label = tk.Label(self.user_frame, font=FONT_CAPTION,
                                   fg=COLOR_TEXT_SUB, bg=COLOR_CARD,
                                   justify='left', anchor='w')
        self.user_label.pack(fill='x')

        # 配置区（校区+照片）
        cfg_row = tk.Frame(card, bg=COLOR_CARD)
        cfg_row.pack(fill='x', pady=(6, 0))

        tk.Label(cfg_row, text='校区', font=FONT_CAPTION, bg=COLOR_CARD,
                 fg=COLOR_TEXT_SUB).pack(side='left')
        self.campus_var = tk.StringVar(value=self.client.campus)
        cm = ttk.Combobox(cfg_row, textvariable=self.campus_var,
                          values=list(self.client.campuses.keys()),
                          state='readonly', width=10, font=FONT_CAPTION)
        cm.pack(side='left', padx=(4, 12))

        tk.Label(cfg_row, text='照片', font=FONT_CAPTION, bg=COLOR_CARD,
                 fg=COLOR_TEXT_SUB).pack(side='left')
        self.photo_label = tk.Label(cfg_row, text='无', font=FONT_CAPTION,
                                    fg=COLOR_TEXT_SUB, bg=COLOR_CARD)
        self.photo_label.pack(side='left', padx=(4, 4))
        tk.Button(cfg_row, text='选择', font=FONT_CAPTION,
                  command=self._choose_photo, bd=0, relief='flat',
                  bg='#e8e8ed', padx=8, pady=2).pack(side='left')

    def _build_task_section(self, parent):
        """任务区域 — 卡片列表"""
        # 标题行
        header = tk.Frame(parent, bg=COLOR_BG)
        header.pack(fill='x', padx=16, pady=(8, 2))

        tk.Label(header, text='今日任务', font=FONT_HEAD, bg=COLOR_BG,
                 fg=COLOR_TEXT).pack(side='left')

        self.task_count_label = tk.Label(header, font=FONT_CAPTION,
                                         bg=COLOR_BG, fg=COLOR_TEXT_SUB)
        self.task_count_label.pack(side='left', padx=6)

        # 操作按钮
        btn_frame = tk.Frame(header, bg=COLOR_BG)
        btn_frame.pack(side='right')

        self.btn_refresh = tk.Button(btn_frame, text='刷新', font=FONT_CAPTION,
                                     command=self.refresh_tasks, state='disabled',
                                     bd=0, relief='flat', bg='#e8e8ed',
                                     padx=10, pady=2)
        self.btn_refresh.pack(side='left', padx=2)

        self.btn_sign = tk.Button(btn_frame, text='签到', font=FONT_CAPTION,
                                  command=self.start_sign, state='disabled',
                                  bd=0, relief='flat', bg=COLOR_PRIMARY, fg='white',
                                  padx=14, pady=2)
        self.btn_sign.pack(side='left', padx=2)

        # 任务卡片容器（Scrollable）
        canvas = tk.Canvas(parent, bg=COLOR_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient='vertical', command=canvas.yview)
        self.task_container = tk.Frame(canvas, bg=COLOR_BG)

        self.task_container.bind('<Configure>',
                                 lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=self.task_container, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side='left', fill='both', expand=True, padx=12)
        scrollbar.pack(side='right', fill='y')

        self.task_scroll = canvas

    def _build_log_section(self, parent):
        """日志区域"""
        card = tk.Frame(parent, bg=COLOR_CARD, padx=12, pady=8)
        card.pack(fill='x', padx=12, pady=4)

        tk.Label(card, text='日志', font=FONT_HEAD, bg=COLOR_CARD,
                 fg=COLOR_TEXT).pack(anchor='w')

        self.log_text = tk.Text(card, height=5, font=FONT_MONO,
                                bg='#f8f8fa', fg=COLOR_TEXT_SUB,
                                relief='flat', state='disabled',
                                bd=0, padx=4, pady=4)
        self.log_text.pack(fill='x', pady=(4, 0))

    def _build_footer(self, parent):
        tk.Label(parent, text='v2.0 基于MPL-2.0开源', font=FONT_CAPTION,
                 bg=COLOR_BG, fg=COLOR_TEXT_SUB).pack(pady=6)

    def _build_ui(self):
        container = tk.Frame(self.root, bg=COLOR_BG)
        container.pack(fill='both', expand=True)

        self._build_header(container)
        self._build_info_section(container)
        self._build_task_section(container)
        self._build_log_section(container)
        self._build_footer(container)

    # ==================== 方法 ====================

    def _core_log(self, msg):
        now = datetime.now().strftime('%H:%M:%S')
        self.log_messages.append((now, msg))

    def log(self, msg):
        now = datetime.now().strftime('%H:%M:%S')
        self.log_messages.append((now, msg))

        def _append():
            self.log_text.configure(state='normal')
            self.log_text.insert('end', f'{msg}\n')
            self.log_text.see('end')
            self.log_text.configure(state='disabled')
        self.root.after(0, _append)

    def set_status(self, text, is_ok=False, is_err=False):
        def _update():
            self.status_label.configure(text=text)
            if is_ok:
                self.status_text.set('✅ 已登录')
            elif is_err:
                self.status_text.set('❌ ' + text)
            else:
                self.status_text.set(text)
        self.root.after(0, _update)

    def show_qr(self, path):
        try:
            img = Image.open(path).resize((160, 160))
            # 圆角
            mask = Image.new('L', (160, 160), 0)
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle([(0, 0), (159, 159)], radius=16, fill=255)
            img.putalpha(mask)
            photo = ImageTk.PhotoImage(img)

            self.qr_label.configure(image=photo)
            self.qr_label.image = photo
            self.qr_frame.pack(fill='x', pady=(8, 0))
        except:
            pass

    def clear_qr(self):
        self.qr_label.configure(image='')
        self.qr_frame.pack_forget()

    def update_user_info(self):
        def _update():
            now = datetime.now().strftime('%m/%d %H:%M')
            campus = self.campus_var.get()
            self.user_label.configure(
                text=f'{self.client.school_name} · {campus} · {now}')
            self.user_frame.pack(fill='x', pady=(6, 0))
        self.root.after(0, _update)

    def update_task_count(self, unsigned, signed):
        def _update():
            t = unsigned + signed
            if t == 0:
                self.task_count_label.configure(text='暂无')
            else:
                self.task_count_label.configure(text=f'未签{unsigned} 已签{signed}')
        self.root.after(0, _update)

    def rebuild_task_cards(self):
        """重建任务卡片"""
        for w in self.task_container.winfo_children():
            w.destroy()
        self.task_cards = []
        self.selected_card = None
        self.btn_sign.configure(state='disabled')

        if not self.current_tasks:
            tk.Label(self.task_container, text='暂无查寝任务', font=FONT_BODY,
                     fg=COLOR_TEXT_SUB, bg=COLOR_BG).pack(pady=20)
            return

        for t in self.current_tasks:
            is_unsigned = t in [x for x in self.current_tasks
                                if t.get('signStatus') == '0' or
                                not any(t2.get('signInstanceWid') == t.get('signInstanceWid')
                                        for tasks in [self.current_tasks]
                                        for t2 in tasks
                                        if t2.get('signStatus') == '1')]

            # 更简单的判断：从list_tasks的返回判断
            # 会在refresh时设置is_unsigned属性

    def _choose_photo(self):
        path = filedialog.askopenfilename(title='选择照片',
                                          filetypes=[('图片', '*.jpg *.jpeg *.png')])
        if path:
            self.photo_path = path
            self.photo_label.configure(text=os.path.basename(path)[:10], fg=COLOR_TEXT)

    def on_card_click(self, card):
        if card.status != 'unsigned':
            return
        if self.selected_card:
            self.selected_card.set_selected(False)
        card.set_selected(True)
        self.selected_card = card
        self.btn_sign.configure(state='normal')

    # ==================== 学校初始化 ====================

    def _init_school(self):
        threading.Thread(target=self._do_init_school, daemon=True).start()

    def _do_init_school(self):
        try:
            self.log('获取学校信息...')
            self.client.init_school()
            self.log(f'学校: {self.client.school_name}')
            self.set_status('准备就绪')
            self.root.after(0, lambda: self.btn_login.configure(state='normal'))
            if self.client.logged_in:
                self.set_status('已登录（恢复会话）', is_ok=True)
                self.root.after(0, lambda: self.btn_refresh.configure(state='normal'))
                self.refresh_tasks()
        except Exception as e:
            self.log(f'初始化失败: {e}')
            self.set_status('初始化失败', is_err=True)

    # ==================== 登录 ====================

    def start_login(self):
        if self.login_thread and self.login_thread.is_alive():
            return
        self.btn_login.configure(state='disabled', text='获取中...')
        self.login_thread = threading.Thread(target=self._do_login, daemon=True)
        self.login_thread.start()

    def _do_login(self):
        try:
            self.log('获取二维码...')
            uuid, img_bytes = self.client.get_qr_image()
            self.set_status('等待扫码')

            qr_path = 'qrcode_login.png'
            with open(qr_path, 'wb') as f:
                f.write(img_bytes)
            self.root.after(0, lambda: self.show_qr(qr_path))

            def on_status(msg):
                self.set_status(msg)
                self.log(msg)

            success = self.client.poll_qr_login(uuid, on_status=on_status)

            if success:
                self.set_status('已登录', is_ok=True)
                self.log('登录成功')
                self.root.after(0, self.clear_qr)
                self.root.after(0, lambda: self.btn_login.configure(
                    state='disabled', text='已登录'))
                self.root.after(0, lambda: self.btn_refresh.configure(state='normal'))
                self.refresh_tasks()
            else:
                self.set_status('扫码超时', is_err=True)
                self.root.after(0, self.clear_qr)
                self.root.after(0, lambda: self.btn_login.configure(
                    state='normal', text='扫码登录'))
        except Exception as e:
            self.log(f'登录失败: {e}')
            self.set_status('登录失败', is_err=True)
            self.root.after(0, self.clear_qr)
            self.root.after(0, lambda: self.btn_login.configure(
                state='normal', text='扫码登录'))

    # ==================== 刷新任务 ====================

    def refresh_tasks(self):
        self.btn_refresh.configure(state='disabled', text='...')
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        try:
            self.log('获取查寝任务...')
            result = self.client.list_tasks()
            self.current_tasks = result['all']

            # 标记状态
            unsigned_ids = {t['signInstanceWid'] for t in result['unsigned']}
            for t in self.current_tasks:
                t['_unsigned'] = t['signInstanceWid'] in unsigned_ids

            self.update_task_count(len(result['unsigned']), len(result['signed']))
            self.update_user_info()

            def _rebuild():
                for w in self.task_container.winfo_children():
                    w.destroy()
                self.task_cards = []
                self.selected_card = None
                self.btn_sign.configure(state='disabled')

                if not self.current_tasks:
                    tk.Label(self.task_container, text='暂无查寝任务',
                             font=FONT_BODY, fg=COLOR_TEXT_SUB,
                             bg=COLOR_BG).pack(pady=20)
                    return

                for t in self.current_tasks:
                    status = 'unsigned' if t.get('_unsigned') else 'signed'
                    card = TaskCard(self.task_container, t, status,
                                    on_click=self.on_card_click)
                    self.task_cards.append(card)

            self.root.after(0, _rebuild)
            self.log(f'未签{len(result["unsigned"])}, 已签{len(result["signed"])}')
        except Exception as e:
            self.log(f'获取失败: {e}')
        finally:
            self.root.after(0, lambda: self.btn_refresh.configure(
                state='normal', text='刷新'))

    # ==================== 签到 ====================

    def start_sign(self):
        if self.signing or not self.selected_card:
            return

        task = self.selected_card.task
        if not messagebox.askyesno('确认', f'签到「{task.get("taskName")}」？'):
            return

        self.signing = True
        self.btn_sign.configure(state='disabled', text='签到中...')
        threading.Thread(target=self._do_sign, args=(task,), daemon=True).start()

    def _do_sign(self, task):
        try:
            campus = self.campus_var.get()
            result = self.client.sign_task(task, campus=campus, photo_path=self.photo_path)
            if result['success']:
                self.log('✅ 签到成功')
                self.set_status('签到成功', is_ok=True)
                self.root.after(0, lambda: messagebox.showinfo('成功', '签到成功!'))
                self.refresh_tasks()
            else:
                self.log(f'❌ 签到失败: {result["message"]}')
                self.set_status('签到失败', is_err=True)
                self.root.after(0, lambda: messagebox.showerror('失败', result['message']))
        except Exception as e:
            self.log(f'签到出错: {e}')
            self.set_status('签到出错', is_err=True)
        finally:
            self.signing = False
            self.root.after(0, lambda: self.btn_sign.configure(state='normal', text='签到'))

    # ==================== 启动 ====================

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    app = App()
    app.run()
