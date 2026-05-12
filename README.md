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
├── actions/
│   └── utils.py   # 参考工具类
└── requirements.txt
```

## 技术说明

| 项目 | 说明 |
|------|------|
| 加密方式 | DES(AES) + AES-CBC + MD5 签名 |
| APP版本 | cpdaily/wisedu 10.0.13 |
| 定位方式 | 校区固定经纬度（无需GPS） |
| 会话有效期 | 7天 |

## 许可证

MPL-2.0
