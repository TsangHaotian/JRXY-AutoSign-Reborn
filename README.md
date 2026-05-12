# 今日校园查寝任务查看器

基于 [ZimoLoveShuang/auto-sign](https://github.com/ZimoLoveShuang/auto-sign) 项目改造的今日校园查寝任务查看工具。

## 声明

本项目仅供学习交流使用，如作他用所承受的任何直接、间接法律责任一概与作者无关。
如果此项目侵犯了您或者您公司的权益，请立即联系删除。

## 功能

- 扫码登录（适配 CAS 认证学校）
- 查看今日查寝任务（未签到 / 已签到）
- 查看历史任务（昨天 / 今天 / 明天）

本项目**只查看任务数据，不提交签到**。

## 适配学校

目前已适配：
- **新疆师范大学**（CAS 扫码登录）

如需适配其他学校，修改 `app.py` 中的 `SCHOOL_NAME` 变量即可。

## 使用方法

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行

```bash
python app.py
```

### 使用流程

1. 点击 **扫码登录** 按钮
2. 用手机今日校园 APP 扫描弹出的二维码
3. 在手机上确认登录
4. 登录成功后自动获取查寝任务

## 项目结构

```
├── app.py              # 主程序（tkinter 桌面界面）
├── actions/
│   └── utils.py        # 工具类（加密、上传等，供后续扩展）
├── config.yml          # 配置文件
├── requirements.txt    # Python 依赖
└── README.md           # 本文件
```

## 许可证

本项目基于 MPL-2.0 协议开源。
