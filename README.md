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

## 项目演化史

### 项目起源
本项目源自 [ZimoLoveShuang/auto-sign](https://github.com/ZimoLoveShuang/auto-sign)（GitHub 上一个通用的今日校园签到框架），经 [CarltonHere/auto-cpdaily](https://github.com/CarltonHere/auto-cpdaily) 继续维护后，被我拉过来针对新疆师范大学做定制。

老项目是一个纯命令行工具，支持签到、信息收集、工作日志等多种任务类型，依赖 YAML 配置驱动，适合服务器定时任务场景。

### 我接手后干了什么

**删掉的：**
- 整个 `actions/` 模块（CAS 登录、IAP 登录、信息收集、工作日志、多端推送）——老项目功能太多太杂，我只关心查寝签到
- 旧的入口文件 `index.py` 和一堆推送模块

**新增的：**
- `app.py` — 完整的 tkinter 桌面版 GUI
- `core.py` — 把查寝签到的业务逻辑抽成独立模块，GUI 和 CLI 共用
- `main.py` — 保留命令行入口，支持静默签到（适合定时任务）

**改的：**
- 配置大幅精简，只保留新疆师范大学
- 坐标从固定值改成随机微偏（模拟真实定位浮动）
- 设备 ID 持久化（同一账号固定设备，不再每次生成新的）
- 签到流程加入随机延迟（模拟人类操作节奏）
- UI 来回折腾了几轮（tkinter → PyQt5 → PySide6 → 最终回到 tkinter）

### 和老项目比，核心差异

| 方面 | 老项目 | 现在 |
|------|--------|------|
| 定位 | 通用签到框架，适配多学校多任务 | 专攻新师大查寝签到 |
| 交互 | 纯命令行 | GUI 桌面版为主，CLI 为辅 |
| 代码结构 | 功能分散在 actions/ 多个文件 | 逻辑集中 core.py + app.py |
| 依赖 | 有腾讯云 OCR、多个推送 SDK | 只保留核心加密和网络库 |
| 签到方式 | 定时脚本 | 手动点按钮，也可命令行静默跑 |

### 当前进度

**已实现的：**
- ✅ CAS 扫码登录 + 会话持久化（7天免登录）
- ✅ 查寝任务列表拉取和展示
- ✅ 查寝签到提交（带照片上传）
- ✅ 完整模拟手机标头（UA、Cpdaily 协议头、加密 extension）
- ✅ 人类行为模拟（随机延迟、坐标微偏、固定设备 ID）
- ✅ 桌面版 GUI + 命令行双入口
- ✅ 切换账号

**卡住的地方：**
- ❌ 签到提交时服务端返回"版本过低" — 今日校园 9.9.11 换了加密 key，老的 `XCE927==`（DES）和 `SASEoK4Pa5d4SssO`（AES）被拉黑
- ❌ APK 有 IJM 加密保护，所有模拟器（雷电 9、雷电 14、MuMu）全部闪退，Frida 跑不了
- ❌ 没有 root 真机，新 key 提取不出来

**距离一个正常能用的签到工具，就差一步：**
拿到今日校园 9.9.11 的新 DES key 和 AES key，更新到 `core.py`。换 key 即复活，没有别的坑。

## 许可证

MPL-2.0
