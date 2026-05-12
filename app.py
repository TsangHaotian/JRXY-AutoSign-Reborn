"""
今日校园查寝任务查看器 - tkinter桌面版
扫码登录后查看每天的查寝任务，不提交签到
"""
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import json
import time
import re
import requests
import os
from io import BytesIO
from PIL import Image, ImageTk
from bs4 import BeautifulSoup

requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

# 配置
SCHOOL_NAME = '新疆师范大学'
QR_FILE = 'qrcode_login.png'

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f'今日校园查寝 - {SCHOOL_NAME}')
        self.root.geometry('500x650')
        self.root.resizable(False, False)

        # 状态变量
        self.session = requests.session()
        self.session.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 8.0.0; MI 6 Build/OPR1.170623.027; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/92.0.4515.131 Mobile Safari/537.36 okhttp/3.12.4',
        }
        self.campus_host = None
        self.logged_in = False
        self.login_thread = None
        self.poll_stop = False

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

        # ===== 任务区域 =====
        task_frame = ttk.LabelFrame(self.root, text='今日查寝任务', padding=10)
        task_frame.pack(fill='both', expand=True, padx=10, pady=5)

        self.task_tree = ttk.Treeview(task_frame, columns=('status', 'time'), show='tree', height=6)
        self.task_tree.heading('#0', text='任务名称')
        self.task_tree.heading('status', text='状态')
        self.task_tree.heading('time', text='签到时间')
        self.task_tree.column('#0', width=200)
        self.task_tree.column('status', width=80)
        self.task_tree.column('time', width=140)
        self.task_tree.pack(fill='both', expand=True)

        self.btn_refresh = ttk.Button(task_frame, text='刷新任务', command=self.refresh_tasks, state='disabled')
        self.btn_refresh.pack(pady=5)

        # ===== 日志区域 =====
        log_frame = ttk.LabelFrame(self.root, text='日志', padding=5)
        log_frame.pack(fill='both', padx=10, pady=5)

        self.log_text = tk.Text(log_frame, height=8, width=60, state='disabled')
        scrollbar = ttk.Scrollbar(log_frame, orient='vertical', command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

    # ===== 工具方法 =====
    def log(self, msg):
        import threading
        def _append():
            self.log_text.configure(state='normal')
            now = time.strftime('%H:%M:%S')
            self.log_text.insert('end', f'[{now}] {msg}\n')
            self.log_text.see('end')
            self.log_text.configure(state='disabled')
        self.root.after(0, _append)

    def set_status(self, text):
        self.root.after(0, lambda: self.login_status.set(text))

    def show_qr(self, image_path):
        try:
            img = Image.open(image_path)
            img = img.resize((200, 200))
            photo = ImageTk.PhotoImage(img)
            self.qr_label.configure(image=photo)
            self.qr_label.image = photo
        except:
            pass

    def clear_qr(self):
        self.qr_label.configure(image='')

    # ===== 学校初始化 =====
    def _init_school(self):
        threading.Thread(target=self._do_init_school, daemon=True).start()

    def _do_init_school(self):
        try:
            self.log('获取学校信息...')
            schools = requests.get(
                'https://mobile.campushoy.com/v6/config/guest/tenant/list',
                verify=False, timeout=15
            ).json()['data']

            for item in schools:
                if item['name'] == SCHOOL_NAME:
                    school_id = item['id']
                    join_type = item['joinType']
                    self.log(f'学校: {SCHOOL_NAME}, joinType: {join_type}')
                    break
            else:
                self.log('未找到学校!')
                return

            info = requests.get(
                'https://mobile.campushoy.com/v6/config/guest/tenant/info',
                params={'ids': school_id}, verify=False, timeout=15
            ).json()['data'][0]

            amp_url = info['ampUrl']
            self.campus_host = re.findall(r'\w{4,5}://.*?/', amp_url)[0]
            self.login_url = info['ampUrl']

            # 访问客户端获取CAS重定向URL
            res = self.session.get(self.campus_host.rstrip('/') + '/wec-portal-mobile/client', verify=False, timeout=15)
            self.cas_login_url = res.url
            self.login_host = re.findall(r'\w{4,5}://.*?/', self.cas_login_url)[0]

            self.log(f'校园域名: {self.campus_host}')
            self.set_status('准备就绪，请点击扫码登录')
            self.root.after(0, lambda: self.btn_login.configure(state='normal'))
        except Exception as e:
            self.log(f'初始化失败: {e}')
            self.set_status(f'初始化失败: {e}')

    # ===== 扫码登录 =====
    def start_login(self):
        if self.login_thread and self.login_thread.is_alive():
            return
        self.btn_login.configure(state='disabled')
        self.poll_stop = False
        self.login_thread = threading.Thread(target=self._do_login, daemon=True)
        self.login_thread.start()

    def _do_login(self):
        try:
            self.set_status('获取二维码...')
            self.log('正在获取二维码...')

            # 先访问CAS登录页获取cookie
            self.session.get(self.cas_login_url, verify=False, timeout=15)

            # 获取二维码UUID
            qr_get_url = self.login_host.rstrip('/') + '/authserver/qrCode/get?ts=' + str(int(time.time() * 1000))
            qr_res = self.session.get(qr_get_url, verify=False, timeout=15)
            qr_uuid = qr_res.text.strip()

            if not qr_uuid:
                self.log('获取二维码UUID失败')
                self.set_status('获取二维码失败')
                self.root.after(0, lambda: self.btn_login.configure(state='normal'))
                return

            # 下载二维码图片
            qr_img_url = self.login_host.rstrip('/') + '/authserver/qrCode/code?uuid=' + qr_uuid
            img_res = self.session.get(qr_img_url, verify=False, timeout=15)
            with open(QR_FILE, 'wb') as f:
                f.write(img_res.content)

            self.root.after(0, lambda: self.show_qr(QR_FILE))
            self.set_status('等待扫码...')
            self.log('二维码已生成，请用今日校园APP扫描')

            # 轮询扫码状态
            qr_status_url = self.login_host.rstrip('/') + '/authserver/qrCode/status'
            for i in range(120):
                if self.poll_stop:
                    return
                time.sleep(1)
                try:
                    r = self.session.get(f'{qr_status_url}?uuid={qr_uuid}&ts={int(time.time()*1000)}',
                                        verify=False, timeout=10)
                    status = r.text.strip()

                    if status == '1':
                        self.log('扫码成功!')
                        self.set_status('正在完成登录...')

                        # 提交qrLoginForm
                        time.sleep(1)
                        qr_page = self.session.get(
                            self.login_host.rstrip('/') + '/authserver/login?display=qrLogin',
                            verify=False, timeout=15)
                        soup = BeautifulSoup(qr_page.text, 'html.parser')
                        qr_form = soup.find('form', {'id': 'qrLoginForm'})

                        if qr_form:
                            form_data = {}
                            for inp in qr_form.find_all('input'):
                                name = inp.get('name', '')
                                if name:
                                    form_data[name] = inp.get('value', '')
                            form_data['uuid'] = qr_uuid
                            action = qr_form.get('action', '')
                            submit_url = self.login_host.rstrip('/') + action
                            r = self.session.post(submit_url, data=form_data, verify=False,
                                                  timeout=15, allow_redirects=False)
                            if r.status_code == 302:
                                location = r.headers.get('Location', '')
                                self.session.get(location, verify=False, timeout=15)

                        self.logged_in = True
                        self.set_status('✅ 已登录')
                        self.root.after(0, self.clear_qr)
                        self.root.after(0, lambda: self.btn_refresh.configure(state='normal'))
                        self.refresh_tasks()
                        return

                    elif status == '2' and i % 5 == 0:
                        self.log('手机已扫码，等待确认...')
                        self.set_status('已扫码，请在手机上确认')
                except:
                    pass

            self.log('等待扫码超时')
            self.set_status('扫码超时')
            self.root.after(0, self.clear_qr)
            self.root.after(0, lambda: self.btn_login.configure(state='normal'))

        except Exception as e:
            self.log(f'登录失败: {e}')
            self.set_status(f'登录失败')
            self.root.after(0, self.clear_qr)
            self.root.after(0, lambda: self.btn_login.configure(state='normal'))

    # ===== 刷新任务 =====
    def refresh_tasks(self):
        self.btn_refresh.configure(state='disabled')
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        try:
            self.log('正在获取查寝任务...')
            headers = {'Content-Type': 'application/json'}

            # 查今天
            url = self.campus_host + 'wec-counselor-attendance-apps/student/attendance/getStuAttendacesInOneDay'
            self.session.post(url, headers=headers, data=json.dumps({}), verify=False, timeout=15)
            r = self.session.post(url, headers=headers, data=json.dumps({}), verify=False, timeout=15)
            data = r.json()

            if data.get('code') != '0':
                self.log(f'API返回异常: {data.get("message", "未知")}')
                return

            datas = data['datas']
            unsigned = datas.get('unSignedTasks', [])
            signed = datas.get('signedTasks', [])

            # 也查一下昨天和明天的
            tasks_map = {}
            for date_offset, label in [(-1, '昨天'), (0, '今天'), (1, '明天')]:
                from datetime import datetime, timedelta
                d = (datetime.now() + timedelta(days=date_offset)).strftime('%Y-%m-%d')
                try:
                    self.session.post(url, headers=headers, data=json.dumps({'date': d}), verify=False, timeout=15)
                    r2 = self.session.post(url, headers=headers, data=json.dumps({'date': d}), verify=False, timeout=15)
                    if r2.status_code == 200:
                        d2 = r2.json()
                        if 'datas' in d2:
                            for t in d2['datas'].get('unSignedTasks', []):
                                tname = t['taskName'] + f' ({label})'
                                tasks_map[tname] = ('未签到', t.get('singleTaskBeginTime',''), t)
                            for t in d2['datas'].get('signedTasks', []):
                                tname = t['taskName'] + f' ({label})'
                                tasks_map[tname] = ('已签到', t.get('singleTaskBeginTime',''), t)
                except:
                    pass

            # 更新UI
            def _update_tree():
                self.task_tree.delete(*self.task_tree.get_children())
                if not unsigned and not signed:
                    self.task_tree.insert('', 'end', text='暂无查寝任务', values=('', ''))
                for t in unsigned:
                    name = t['taskName']
                    time_range = f"{t.get('singleTaskBeginTime','')} - {t.get('singleTaskEndTime','')}"
                    self.task_tree.insert('', 'end', text=name, values=('❌ 未签', time_range))
                for t in signed:
                    name = t['taskName']
                    time_range = f"{t.get('singleTaskBeginTime','')} - {t.get('singleTaskEndTime','')}"
                    self.task_tree.insert('', 'end', text=name, values=('✅ 已签', time_range))

            self.root.after(0, _update_tree)
            self.log(f'今日: 未签到{len(unsigned)}个, 已签到{len(signed)}个')

        except Exception as e:
            self.log(f'获取任务失败: {e}')
        finally:
            self.root.after(0, lambda: self.btn_refresh.configure(state='normal'))

    # ===== 启动 =====
    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    app = App()
    app.run()
