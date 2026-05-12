"""
今日校园查寝签到 - 业务核心模块
纯业务逻辑，无GUI/CLI依赖，供app.py和main.py共享
"""
import json
import time
import re
import os
import uuid
import base64
import hashlib
import urllib.parse
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from pyDes import des, CBC, PAD_PKCS5
from Crypto.Cipher import AES
from requests_toolbelt import MultipartEncoder

requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

# ==================== 加密函数 ====================

def des_encrypt(s, key='XCE927=='):
    iv = b"\x01\x02\x03\x04\x05\x06\x07\x08"
    k = des(key, CBC, iv, pad=None, padmode=PAD_PKCS5)
    return base64.b64encode(k.encrypt(s)).decode()


def aes_encrypt(data, key='SASEoK4Pa5d4SssO'):
    iv = b'\x01\x02\x03\x04\x05\x06\x07\x08\x09\x01\x02\x03\x04\x05\x06\x07'
    aes = AES.new(key.encode(), AES.MODE_CBC, iv)
    pad_len = AES.block_size - (len(data) % AES.block_size)
    data += chr(pad_len) * pad_len
    text = aes.encrypt(data.encode())
    return base64.encodebytes(text).decode().strip()


def md5(s):
    return hashlib.md5(s.encode()).hexdigest()


# ==================== API路径 ====================

SIGN_API = 'wec-counselor-attendance-apps/student/attendance/submitSign'
DETAIL_API = 'wec-counselor-attendance-apps/student/attendance/detailSignInstance'
LIST_API = 'wec-counselor-attendance-apps/student/attendance/getStuAttendacesInOneDay'
UPLOAD_POLICY_API = 'wec-counselor-sign-apps/stu/obs/getUploadPolicy'
PREVIEW_API = 'wec-counselor-sign-apps/stu/sign/previewAttachment'

# ==================== UA ====================

APP_UA = ('Mozilla/5.0 (Linux; Android 8.0.0; MI 6 Build/OPR1.170623.027; wv) '
          'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/92.0.4515.131 '
          'Mobile Safari/537.36 okhttp/3.12.4 cpdaily/10.0.13 wisedu/10.0.13')
BASE_UA = ('Mozilla/5.0 (Linux; Android 8.0.0; MI 6 Build/OPR1.170623.027; wv) '
           'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/92.0.4515.131 '
           'Mobile Safari/537.36 okhttp/3.12.4')

# ==================== 默认校区坐标 ====================

DEFAULT_CAMPUSES = {
    '昆仑校区': {'lon': '87.611253', 'lat': '43.820482'},
    '温泉校区': {'lon': '87.658041', 'lat': '43.875216'},
}


# ==================== CpdailyClient ====================

class CpdailyClient:
    """今日校园查寝签到客户端 — 业务核心"""

    def __init__(self, school_name='新疆师范大学', campus='昆仑校区',
                 des_key='XCE927==', aes_key='SASEoK4Pa5d4SssO',
                 cookie_file='.session_cookies.json'):
        self.school_name = school_name
        self.campus = campus
        self.des_key = des_key
        self.aes_key = aes_key
        self.cookie_file = cookie_file
        self.campuses = dict(DEFAULT_CAMPUSES)

        self.session = requests.session()
        self.session.headers = {'User-Agent': BASE_UA}

        self.campus_host = None   # https://xjnu.campusphere.net/
        self.login_host = None    # https://authserver.xjnu.edu.cn/
        self.cas_login_url = None # CAS登录页完整URL
        self.school_id = None
        self.logged_in = False

    # -------- 日志钩子（外部可覆盖） --------

    def on_log(self, msg):
        """日志回调，GUI/CLI各自实现"""
        pass

    def log(self, msg):
        self.on_log(msg)

    # -------- 学校初始化 --------

    def init_school(self):
        """获取学校域名和CAS登录地址"""
        self.log('获取学校信息...')

        schools = self.session.get(
            'https://mobile.campushoy.com/v6/config/guest/tenant/list',
            verify=False, timeout=15).json()['data']

        for item in schools:
            if item['name'] == self.school_name:
                self.school_id = item['id']
                self.log(f'学校: {self.school_name}, joinType: {item["joinType"]}')
                break
        else:
            raise Exception(f'未找到学校: {self.school_name}')

        info = self.session.get(
            'https://mobile.campushoy.com/v6/config/guest/tenant/info',
            params={'ids': self.school_id}, verify=False, timeout=15
        ).json()['data'][0]

        self.campus_host = re.findall(r'\w{4,5}://.*?/', info['ampUrl'])[0]
        res = self.session.get(self.campus_host.rstrip('/') + '/wec-portal-mobile/client',
                               verify=False, timeout=15)
        self.cas_login_url = res.url
        self.login_host = re.findall(r'\w{4,5}://.*?/', self.cas_login_url)[0]

        self.log(f'校园域名: {self.campus_host}')

        # 尝试恢复已保存的会话
        if self._load_session():
            self.log('已恢复上次登录会话')
            self.logged_in = True

        return {
            'school_id': self.school_id,
            'campus_host': self.campus_host,
            'cas_login_url': self.cas_login_url,
            'login_host': self.login_host,
        }

    # -------- 会话持久化 --------

    def _save_session(self):
        """保存当前会话到文件"""
        try:
            data = {
                'cookies': [
                    {'name': c.name, 'value': c.value, 'domain': c.domain,
                     'path': c.path, 'secure': c.secure, 'rest': {'HttpOnly': c.has_nonstandard_attr('HttpOnly')}}
                    for c in self.session.cookies
                ],
                'campus_host': self.campus_host,
                'login_host': self.login_host,
                'cas_login_url': self.cas_login_url,
                'school_name': self.school_name,
                'campus': self.campus,
                'saved_at': datetime.now().isoformat(),
            }
            with open(self.cookie_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f'保存会话失败: {e}')

    def _load_session(self):
        """从文件恢复会话，返回是否成功"""
        if not os.path.exists(self.cookie_file):
            return False
        try:
            with open(self.cookie_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 检查过期时间（7天）
            saved_at = data.get('saved_at', '')
            if saved_at:
                saved_time = datetime.fromisoformat(saved_at)
                if datetime.now() - saved_time > timedelta(days=7):
                    self.log('会话已过期（超过7天），请重新登录')
                    self._clear_session()
                    return False

            # 恢复cookie
            from http.cookiejar import Cookie
            for c in data.get('cookies', []):
                rest = c.get('rest', {})
                cookie = Cookie(
                    version=0, name=c['name'], value=c['value'],
                    port=None, port_specified=False,
                    domain=c.get('domain', ''), domain_specified=bool(c.get('domain')),
                    domain_initial_dot=False,
                    path=c.get('path', '/'), path_specified=True,
                    secure=c.get('secure', False), expires=None,
                    discard=True, comment=None, comment_url=None,
                    rest=rest,
                )
                self.session.cookies.set_cookie(cookie)

            # 恢复状态
            self.campus_host = data.get('campus_host')
            self.login_host = data.get('login_host')
            self.cas_login_url = data.get('cas_login_url')
            self.campus = data.get('campus', self.campus)

            if self.campus_host:
                return True
        except Exception as e:
            self.log(f'恢复会话失败: {e}')
        return False

    def _clear_session(self):
        """清除本地会话文件"""
        try:
            if os.path.exists(self.cookie_file):
                os.remove(self.cookie_file)
        except:
            pass

    # -------- 会话验证 --------

    def is_session_valid(self):
        """验证当前会话是否有效"""
        if not self.campus_host or not self.logged_in:
            return False
        try:
            url = self.campus_host.rstrip('/') + '/wec-counselor-attendance-apps/student/attendance/getStuAttendacesInOneDay'
            r = self.session.post(url, headers={'Content-Type': 'application/json'},
                                  data=json.dumps({}), verify=False, timeout=10)
            return r.status_code == 200 and 'unSignedTasks' in r.text
        except:
            return False

    # -------- 扫码登录 --------

    def get_qr_image(self):
        """获取二维码，返回 (uuid, image_bytes)"""
        self.session.get(self.cas_login_url, verify=False, timeout=15)

        qr_get_url = (self.login_host.rstrip('/') +
                      '/authserver/qrCode/get?ts=' + str(int(time.time() * 1000)))
        qr_uuid = self.session.get(qr_get_url, verify=False, timeout=15).text.strip()
        if not qr_uuid:
            raise Exception('获取二维码UUID失败')

        qr_img_url = (self.login_host.rstrip('/') +
                      '/authserver/qrCode/code?uuid=' + qr_uuid)
        img_res = self.session.get(qr_img_url, verify=False, timeout=15)
        return qr_uuid, img_res.content

    def poll_qr_login(self, uuid, on_status=None):
        """轮询等待扫码，返回是否成功"""
        qr_status_url = self.login_host.rstrip('/') + '/authserver/qrCode/status'
        for i in range(120):
            time.sleep(1)
            try:
                r = self.session.get(
                    f'{qr_status_url}?uuid={uuid}&ts={int(time.time()*1000)}',
                    verify=False, timeout=10)
                status = r.text.strip()
                if status == '1':
                    if on_status:
                        on_status('扫码成功!')
                    time.sleep(1)

                    # 提交qrLoginForm完成CAS认证
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
                        form_data['uuid'] = uuid
                        action = qr_form.get('action', '')
                        r = self.session.post(
                            self.login_host.rstrip('/') + action,
                            data=form_data, verify=False, timeout=15, allow_redirects=False)
                        if r.status_code == 302:
                            self.session.get(r.headers['Location'], verify=False, timeout=15)

                    self.logged_in = True
                    self._save_session()
                    return True

                elif status == '2':
                    if on_status and i % 5 == 0:
                        on_status('已扫码，请在手机上确认...')
            except:
                pass
        return False

    def login_qr(self, on_status=None):
        """完整扫码登录流程，返回 (success, qr_image_bytes)"""
        try:
            if on_status:
                on_status('获取二维码...')
            self.log('正在获取二维码...')
            uuid, img_bytes = self.get_qr_image()

            if on_status:
                on_status('等待扫码...')
            self.log('二维码已生成，请用今日校园APP扫描')

            success = self.poll_qr_login(uuid, on_status)
            if success:
                self.log('✅ 登录成功')
                if on_status:
                    on_status('✅ 已登录')
                return True, img_bytes
            else:
                self.log('❌ 扫码超时')
                if on_status:
                    on_status('扫码超时')
                return False, img_bytes
        except Exception as e:
            self.log(f'登录失败: {e}')
            if on_status:
                on_status(f'登录失败')
            return False, b''

    # -------- 任务操作 --------

    def list_tasks(self):
        """获取今日查寝任务"""
        headers = {'Content-Type': 'application/json'}
        url = self.campus_host + LIST_API

        # 第一次请求（获取MOD_AUTH_CAS）
        self.session.post(url, headers=headers, data=json.dumps({}), verify=False, timeout=15)
        # 第二次请求（真实数据）
        r = self.session.post(url, headers=headers, data=json.dumps({}), verify=False, timeout=15)
        data = r.json()

        if data.get('code') != '0':
            raise Exception(f'API异常: {data.get("message", "未知")}')

        # 刷新cookie
        self._save_session()

        return {
            'unsigned': data['datas'].get('unSignedTasks', []),
            'signed': data['datas'].get('signedTasks', []),
            'all': data['datas'].get('unSignedTasks', []) + data['datas'].get('signedTasks', []),
        }

    def get_task_detail(self, sign_instance_wid, sign_wid):
        """获取任务详情"""
        headers = {'Content-Type': 'application/json'}
        r = self.session.post(
            self.campus_host + DETAIL_API,
            headers=headers,
            data=json.dumps({
                'signInstanceWid': sign_instance_wid,
                'signWid': sign_wid,
            }),
            verify=False, timeout=15
        ).json()
        return r.get('datas', {})

    # -------- 签到操作 --------

    def _upload_photo(self, photo_path):
        """上传照片到OSS，返回fileName"""
        res = self.session.post(
            self.campus_host + UPLOAD_POLICY_API,
            headers={'content-type': 'application/json'},
            data=json.dumps({'fileType': 1}),
            verify=False, timeout=15).json()
        datas = res.get('datas')
        if not datas:
            raise Exception('获取上传凭证失败')

        fileName = datas.get('fileName') + '.jpg'
        upload_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:50.0) Gecko/20100101 Firefox/50.0',
        }
        multipart = MultipartEncoder(fields={
            'key': fileName, 'policy': datas.get('policy'),
            'AccessKeyId': datas.get('accessid'),
            'signature': datas.get('signature'),
            'x-obs-acl': 'public-read',
            'file': ('blob', open(photo_path, 'rb'), 'image/jpg'),
        })
        upload_headers['Content-Type'] = multipart.content_type
        self.session.post(datas.get('host'), headers=upload_headers,
                          data=multipart, verify=False, timeout=30)
        return fileName

    def _get_photo_url(self, fileName):
        """获取照片访问URL"""
        r = self.session.post(
            self.campus_host + PREVIEW_API,
            headers={'content-type': 'application/json'},
            data=json.dumps({'ossKey': fileName}),
            verify=False, timeout=15).json()
        return r.get('datas', '')

    def sign_task(self, task, campus=None, photo_path=''):
        """签到指定任务，返回 {'success': bool, 'message': str}"""
        if campus is None:
            campus = self.campus
        coords = self.campuses[campus]
        lon = coords['lon']
        lat = coords['lat']
        address = f'{self.school_name}({campus})'

        self.log(f'校区: {campus} ({lon}, {lat})')

        # 1. 获取任务详情
        self.log('正在获取任务详情...')
        task_detail = self.get_task_detail(task['signInstanceWid'], task['signWid'])

        # 2. 构建表单
        form = {'signInstanceWid': task['signInstanceWid']}

        if task_detail.get('isPhoto') == 1:
            self.log('任务需要照片')
            if not photo_path or not os.path.exists(photo_path):
                return {'success': False, 'message': '该任务需要照片但未选择'}
            self.log('正在上传照片...')
            fileName = self._upload_photo(photo_path)
            form['signPhotoUrl'] = self._get_photo_url(fileName)
            self.log('照片上传完成')
        else:
            form['signPhotoUrl'] = ''

        if task_detail.get('isNeedExtra') == 1:
            extra_values = []
            for field in task_detail.get('extraField', []):
                for item in field.get('extraFieldItems', []):
                    if item.get('isSelected', False):
                        extra_values.append({
                            'extraFieldItemValue': item['content'],
                            'extraFieldItemWid': item['wid'],
                        })
                        break
            form['extraFieldItems'] = extra_values

        form['longitude'] = lon
        form['latitude'] = lat
        form['isMalposition'] = task_detail.get('isMalposition', 0)
        form['abnormalReason'] = ''
        form['position'] = address
        form['uaIsCpadaily'] = True
        form['signVersion'] = '1.0.0'

        # 3. 加密提交
        self.log('正在加密并提交签到...')
        extension = {
            "lon": lon, "model": "MI 6",
            "appVersion": "10.0.13", "systemVersion": "8.0.0",
            "userId": '', "systemName": "android",
            "lat": lat, "deviceId": str(uuid.uuid1()),
        }

        body_string = aes_encrypt(json.dumps(form), self.aes_key)
        submit_data = {
            'version': 'first_v3',
            'calVersion': 'firstv',
            'bodyString': body_string,
            'sign': md5(urllib.parse.urlencode(form) + '&' + self.aes_key),
        }
        submit_data.update(extension)

        sign_headers = {
            'User-Agent': APP_UA,
            'CpdailyStandAlone': '0',
            'extension': '1',
            'Cpdaily-Extension': des_encrypt(json.dumps(extension), self.des_key),
            'Content-Type': 'application/json; charset=utf-8',
            'Accept-Encoding': 'gzip',
            'Host': re.findall(r'//(.*?)/', self.campus_host)[0],
            'Connection': 'Keep-Alive',
        }

        res = self.session.post(
            self.campus_host + SIGN_API,
            headers=sign_headers,
            data=json.dumps(submit_data),
            verify=False, timeout=15
        ).json()

        msg = res.get('message', '')
        success = msg == 'SUCCESS'
        if success:
            self.log('✅ 签到成功!')
        else:
            self.log(f'❌ 签到失败: {msg}')

        self._save_session()
        return {'success': success, 'message': msg}

    # -------- 配置加载 --------

    @staticmethod
    def load_config(config_path='config.yml'):
        """从YAML加载配置，返回dict"""
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = yaml.load(f, Loader=yaml.FullLoader)
        return cfg or {}

    @staticmethod
    def from_config(config_path='config.yml'):
        """从YAML文件创建CpdailyClient实例"""
        cfg = CpdailyClient.load_config(config_path)
        client = CpdailyClient(
            school_name=cfg.get('schoolName', '新疆师范大学'),
            campus=cfg.get('defaultCampus', '昆仑校区'),
            des_key=cfg.get('desKey', 'XCE927=='),
            aes_key=cfg.get('aesKey', 'SASEoK4Pa5d4SssO'),
            cookie_file=cfg.get('cookieFile', '.session_cookies.json'),
        )
        # 加载自定义校区坐标
        campuses = cfg.get('campuses', {})
        if campuses:
            client.campuses.update(campuses)
        return client
