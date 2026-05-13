# 今日校园查寝签到工具

基于 [ZimoLoveShuang/auto-sign](https://github.com/ZimoLoveShuang/auto-sign) 改造的今日校园查寝签到工具。  
重新设计了架构：`core.py` 共享业务逻辑，`app.py` 桌面版，`main.py` 命令行版。

## 声明

本项目仅供学习交流，如作他用所承受的任何直接、间接法律责任一概与作者无关。

## 功能

- 扫码登录（CAS认证），**会话持久化**（一次扫码，7天内免登录）
- 查看今日查寝任务
- 模拟手机APP签到（DES+AES加密，真实UA，固定校区定位）
- 多校区支持
- 桌面版 + 命令行版 双入口

## 适配学校

- **新疆师范大学** — 昆仑校区 / 温泉校区

## 使用方法

### 安装依赖

```bash
pip install -r requirements.txt
```

### 桌面版

```bash
python app.py
```

1. 选择校区 → 点击扫码登录 → 今日校园APP扫描二维码
2. 自动显示查寝任务
3. 选照片（如需）→ 选中任务 → 签到

### 命令行版

```bash
# 首次需要扫码登录
python main.py login

# 列出任务
python main.py list

# 签到（按序号或名称）
python main.py sign                    # 默认签第一个未签
python main.py sign --index 0          # 签第1个
python main.py sign --name "晚间"      # 按名称匹配
python main.py sign --photo a.jpg      # 带照片签到

# 静默模式（使用已保存会话，适合云端/定时任务）
python main.py --headless list
python main.py --headless sign --index 0 --photo a.jpg

# 查看登录状态
python main.py status
```

## 项目结构

```
├── core.py        # 业务核心（加密、登录、任务、签到）
├── app.py         # tkinter桌面版
├── main.py        # 命令行版
├── config.yml     # 配置（学校、校区、密钥）
├── .session_cookies.json  # 登录会话文件（自动生成）
└── requirements.txt
```

## ⚠️ 当前已知问题 —— 急寻英雄好汉

### 症状

签到时报错：**"今日校园版本过低，请更新至最新版本！"**

### 病因

今日校园 9.9.11 换了加密密钥，项目里用的 DES key（`XCE927==`）和 AES key（`SASEoK4Pa5d4SssO`）是 2022 年的老古董，已经被服务端拉黑。

### 想治好它，你需要

1. 一台 root 过的 Android 手机
2. 装上今日校园 9.9.11（APK 在项目 `apk/` 目录下）
3. 跑 Frida hook 加密函数，把新的 key 捞出来
4. 更新 `core.py` 里的 des_key 和 aes_key
5. 发个 PR 救万民于水火

项目里已经备好了 Frida hook 脚本（`hook_key.js`）、frida-server 文件，甚至连模拟器都试了一圈（雷电 9 闪退、雷电 14 闪退、MuMu 也闪退），最后发现这破 App 的 IJM 加密保护会检测模拟器环境，真机才能跑。

**如果你有 root 手机 + 会玩 Frida，欢迎来搞。** 搞定了你就是这个项目的大恩人，新疆师范大学的学子会记住你的。

## 技术说明

| 项目 | 说明 |
|------|------|
| 加密方式 | DES(AES) + AES-CBC + MD5 签名 |
| APP版本 | cpdaily/wisedu 9.9.11 |
| 定位方式 | 校区固定经纬度（无需GPS） |
| 会话有效期 | 7天 |
| 当前密钥状态 | ❌ 已失效，等待勇士提取新 key |

## 许可证

MPL-2.0
