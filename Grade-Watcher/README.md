# JNU-Grade Checker Guard

> 暨南大学成绩监控与 GPA 计算工具 — 自动轮询教务系统，新成绩微信推送，本地 GPA 计算

---

## 一、项目简介

暨南大学教务系统（金智 EMAP）成绩发布后，学生只能被动登录查看。本项目解决两个痛点：

1. **被动等待**：不知道成绩何时发布，需要反复手动登录教务系统查看
2. **无 GPA 汇总**：教务系统不提供学期 GPA 自动计算，学生需手动核算

核心功能：一个本地运行的 Python CLI 工具，自动轮询教务系统，新成绩到达时通过 Server酱推送到微信，并提供学期 / 学年 / 总 GPA 计算。

### 重构来源

本项目由旧项目 **grade-watcher** 重构而来。旧项目已完成代码审计与 EMAP API 逆向分析，核心逻辑经验证后迁移至本项目，并做了以下改进：

| 改进方向 | 旧项目 | 本项目 |
|---------|--------|--------|
| 安全性 | Cookie 明文存储 | AES-256-GCM 加密 + DPAPI 保护密钥 |
| 认证稳定性 | 导航教务 URL 等 302 重定向静默刷新（2h 边界 RST） | 丢弃旧 context，新建干净 context 直接导航 CAS 登录页 |
| 浏览器隔离 | 使用系统 Chrome User Data（与日常浏览冲突） | 项目本地 Chrome Profile（`data/chrome-profile`） |
| GPA 计算 | 仅总绩点 | 学期 / 学年 / 总绩点，同课去重取最高 |
| 推送格式 | 简单文本 | 课程明细 + 课程性质 + 学期/学年/总绩点一条消息 |
| 架构 | 单文件脚本 | 分层模块化（core / notify / utils） |

模块迁移对照：

| 旧模块 | 新模块 | 变更说明 |
|--------|--------|---------|
| `login.py` | `app/core/auth.py` | `launch` → `launch_persistent_context`，本地 Profile |
| `checker.py` | `app/core/fetcher.py` | 去掉 XNXQDM 过滤，单次请求全学期 |
| `notifier.py` | `app/notify/serverchan.py` | 消息格式升级，加入学年绩点 |
| — | `app/core/gpa.py` | 新增，GPA 计算独立模块 |
| — | `app/core/comparator.py` | 新增，三元组去重对比 |
| — | `app/utils/crypto.py` | 新增，AES-256-GCM + DPAPI 加密 |

---

## 二、功能特性

### 2.1 成绩监控与推送

- 守护进程模式，后台定时轮询（默认间隔 10 分钟）
- 自动检测新出成绩，基于「课程名|成绩|学期」三元组去重，避免重复推送
- 通过 Server酱推送到微信，一条消息包含：新出课程明细 + 本学期绩点 + 学年绩点 + 总绩点
- 支持手动单次查询（`python main.py check`）

### 2.2 自动登录与会话保持

- Playwright 浏览器自动化完成 CAS 统一认证
- 首次登录保存全部 Cookie（含 CAS 的 `CASTGC`），加密存盘
- 会话过期（~90 分钟）自动重认证：将 `CASTGC` 注入新浏览器 context，走 CAS 重定向链静默换取新 session，全程无需人工干预
- `CASTGC` 每次使用自动续期，只要守护进程持续运行即可 7×24h 不掉线；仅长期停机导致 `CASTGC` 过期时才需重新登录
- 重认证失败退避重试（30s → 60s → 90s），3 次均失败后推送告警并退出

### 2.3 GPA 计算

- 绩点（XFJD）由教务系统直接返回，本地仅做加权平均
- 公式：**GPA = Σ(绩点 × 学分) / Σ(学分)**
- 同一门课出现多次（挂科重考/补考），只取绩点最高的记录
- 挂科课程（绩点=0）计入学分分母
- 支持学期 GPA / 学年 GPA / 总 GPA 三种维度
- 学年 GPA 规则：第一学期时等于学期绩点，第二学期时等于该学年两学期合计绩点

### 2.4 数据安全

- Cookie 与成绩历史：AES-256-GCM 加密，密钥由 Windows DPAPI 保护，不落盘
- CAS 密码：仅首次登录时手动输入，代码与配置文件零密码存储
- 网络传输：全链路 HTTPS

---

## 三、快速开始

### 3.1 环境要求

- Windows 10/11
- Python 3.11+
- Google Chrome（供 Playwright 驱动完成 CAS 认证）

### 3.2 安装

```bash
# 克隆项目
git clone <repo-url>
cd JNU-Grade Checker Guard

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器驱动
playwright install chromium
```

### 3.3 配置

复制配置模板并填写 Server酱 Token：

```bash
copy config.example.json config.json
```

编辑 `config.json`：

```json
{
    "serverchan_token": "你的Server酱SendKey",
    "base_url": "https://jw.jnu.edu.cn",
    "check_interval_minutes": 10,
    "chrome_user_data_dir": ""
}
```

| 字段 | 说明 |
|------|------|
| `serverchan_token` | Server酱 SendKey（[获取地址](https://sct.ftqq.com/)） |
| `base_url` | 教务系统地址，默认即可 |
| `check_interval_minutes` | 轮询间隔（分钟），建议不低于 10 |
| `chrome_user_data_dir` | Chrome Profile 路径，留空则使用项目本地 `data/chrome-profile` |

### 3.4 使用

```bash
# 首次登录（弹出浏览器，完成 CAS 认证后自动保存 Cookie）
python main.py login

# 单次查询新成绩
python main.py check

# 守护进程，定时轮询（Ctrl+C 停止）
python main.py daemon

# 查看当前学期 GPA
python main.py gpa

# 查看全部学期 GPA
python main.py gpa --all

# 查看指定学期 GPA
python main.py gpa --semester 2025-2026-2
```

---

## 四、推送消息格式

Server酱免费版仅 title 可见，所有信息压缩为一条消息：

**单条新成绩：**
```
新成绩: 高等数学(必修) 85分 绩点3.5 本学期绩点3.54 学年绩点3.48 总绩点3.41
```

**多条新成绩：**
```
新成绩: 高等数学(必修) 85分 绩点3.5 大学物理(选修) 78分 绩点2.8 本学期绩点3.32 学年绩点3.40 总绩点3.41
```

格式规则：以「新成绩: 」开头，逐个罗列「课程名(课程性质) 分数分 绩点X.X」，末尾追加「本学期绩点X.XX 学年绩点X.XX 总绩点X.XX」。

---

## 五、项目结构

```
JNU-Grade Checker Guard/
├── app/
│   ├── core/                  # 核心业务逻辑
│   │   ├── auth.py                # CAS 认证（Playwright persistent context）
│   │   ├── fetcher.py             # 教务 API 数据抓取（单次 POST 全学期）
│   │   ├── comparator.py          # 成绩对比去重（三元组幂等）
│   │   └── gpa.py                 # GPA 计算（学期/学年/总）
│   ├── notify/                # 通知渠道
│   │   ├── serverchan.py          # Server酱推送（默认）
│   │   └── toast.py               # Windows Toast 本地通知（可选）
│   └── utils/                 # 工具模块
│       ├── crypto.py              # AES-256-GCM 加解密 + DPAPI
│       ├── logger.py              # 日志（loguru，按日轮转）
│       └── config.py              # 配置管理（pydantic-settings）
├── data/                      # 加密持久化数据（已 gitignore）
│   ├── cookies.enc                # 加密的 Cookie
│   ├── grades.enc                 # 加密的成绩历史
├── logs/                      # 日志目录（已 gitignore）
├── tests/                     # 单元测试
├── config.json                # 配置文件（已 gitignore）
├── config.example.json        # 配置模板
├── main.py                    # CLI 入口（click）
├── pyproject.toml             # Poetry 项目配置
└── requirements.txt           # pip 依赖清单
```

---

## 六、技术栈

| 组件 | 选型 | 理由 |
|------|------|------|
| 浏览器自动化 | Playwright | 驱动 Chrome 完成 CAS 认证与 CASTGC 静默续期 |
| HTTP 客户端 | httpx | 异步支持，API 简洁 |
| CLI 框架 | click | 简洁清晰，子命令支持 |
| 配置管理 | pydantic-settings + JSON | 类型安全，校验完善 |
| 日志 | loguru | 按日轮转，格式友好 |
| 加密 | cryptography (AES-256-GCM) | 认证加密，防篡改 |
| 本地通知 | win11toast | Windows 11 原生 Toast |
| 包管理 | Poetry / pip | 双模式支持 |

---

## 七、技术方案要点

### 7.1 登录认证

使用 Playwright 驱动 Chrome 打开成绩查询页，未登录时自动跳转 CAS。用户手动完成账号密码与滑块验证码后，程序保存全部 Cookie（含 CAS 的 `CASTGC`）并加密存盘。密码不做任何落盘存储。

### 7.2 重认证策略

EMAP Session 约 90 分钟过期。检测到过期后，将保存的 `CASTGC` 注入全新浏览器 context，导航教务页触发 CAS 302 重定向链，CAS 识别有效 `CASTGC` 后自动签发 ticket 换取新 EMAP session，全程静默、无需人工干预。`CASTGC` 每次使用自动续期，因此守护进程持续运行即可 7×24h 不掉线；仅当 `CASTGC` 真正过期（如长期停机）时才需重新执行 `login`。

### 7.3 成绩查询

单次 POST 请求 `xscjcx.do`，不传 `XNXQDM` 字段即返回全部学期成绩，无需逐学期循环请求。

### 7.4 GPA 计算

绩点由教务 API 的 XFJD 字段直接返回（含五级制课程，无法从分数反推），本地仅做加权平均。同一门课多次出现时取最高绩点记录。

---

## 八、绩点计算规则（暨南大学）

| 分数区间 | 绩点区间 | 计算方式 |
|---------|---------|---------|
| 100~90 | 5.0~4.0 | 绩点 = (分数 - 50) / 10 |
| 89~80 | 3.9~3.0 | 同上 |
| 79~70 | 2.9~2.0 | 同上 |
| 69~60 | 1.9~1.0 | 同上 |
| <60 | 0 | 不及格 |

五级制：优秀(A)=4.5，良好(B)=3.5，中等(C)=2.5，及格(D)=1.5，不及格(E)=0

> 注：百分制换算公式仅供参考，实际绩点以教务 API 返回的 XFJD 为准（五级制课程无法从分数反推绩点）。

---

## 九、安全说明

| 数据 | 存储方式 | 说明 |
|------|---------|------|
| CAS 密码 | Chrome 密码管理器（OS 级加密） | 代码零密码存储 |
| 浏览器 Cookie | AES-256-GCM 加密，密钥由 DPAPI 保护 | 防会话劫持 |
| 成绩历史 | AES-256-GCM 加密 | 隐私保护 |
| Server酱 Token | config.json 明文 | 已 gitignore，用户接受风险 |
| 网络传输 | HTTPS | 防中间人 |

`.gitignore` 已排除：`data/`、`logs/`、`config.json`、`__pycache__/`、`.env`

---

## 十、已知限制

- CAS 滑块验证码必须人工干预，无法全自动登录
- EMAP API 接口可能变更，需关注适配
- Server酱免费版仅 title 可见（已将所有信息压缩至一行）
- 仅支持 Windows（DPAPI 加密依赖 Windows API）

---

## License

MIT
