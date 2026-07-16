# 暨南大学教务处成绩监控

自动轮询暨南大学教务系统成绩，发现新成绩时通过微信推送通知。

## 功能

- 可以自动登录暨大 CAS 统一身份认证（Playwright 浏览器，需要手动完成滑块验证码）
- 定时轮询成绩 API，检测新增成绩
- 通过 Server酱 推送到微信（免费版每天 5 条）
- CAS 静默重认证：EMAP session 约 90 分钟过期，程序自动用 CAS Cookie 续期，减少手动登录次数
- 多条新成绩自动合并为一条推送，避免浪费推送额度

## 环境要求

- Python 3.10+
- Windows / macOS / Linux（需有图形界面，登录时会打开浏览器）

## 安装

```bash
# 1. 克隆项目
git clone https://github.com/YuCloer/JNU.git
cd JNU/Grade-Watcher

# 2. 安装依赖
pip install -r requirements.txt

# 3. 安装 Playwright 浏览器
playwright install chromium
```

## 配置

编辑 `config.json`：

```json
{
    "serverchan_token": "你的Server酱SendKey",
    "base_url": "https://jw.jnu.edu.cn",
    "username": "你的学号",
    "password": "你的密码",
    "check_interval_minutes": 10,
    "cookie_file": "cookies.json",
    "grades_file": "grades_history.json"
}
```

**Server酱 SendKey 获取方式：**

1. 访问 [sct.ftqq.com](https://sct.ftqq.com/)，微信扫码登录
2. 进入「SendKey」页面，复制你的 SendKey
3. 粘贴到 `config.json` 的 `serverchan_token` 字段

## 使用方法

### 首次登录（获取 Cookie）

```bash
python main.py login
```

会打开 Chromium 浏览器并跳转到 CAS 登录页。账号密码会自动填写，你只需要完成滑块验证码，然后点击登录。登录成功并确认成绩页面加载后，回到终端按 Enter，Cookie 会被保存到本地。

### 手动查询一次

```bash
python main.py check
```

用保存的 Cookie 查询当前学期成绩，有新成绩会打印出来并推送到微信。

### 发送测试通知

```bash
python main.py test
```

发一条测试消息到微信，验证 Server酱配置是否正确。

### 后台持续监控

```bash
python main.py daemon
```

启动后台监控，每隔 `check_interval_minutes` 分钟检查一次成绩。有新成绩会自动推送到微信。按 `Ctrl+C` 停止。

## 工作原理

```
login.py    ──  Playwright 打开浏览器 → CAS 登录 → 保存 Cookie
checker.py  ──  requests + Cookie → 调用 EMAP 成绩 API → 对比历史 → 检测新成绩
notifier.py ──  Server酱 API → 推送到微信
main.py     ──  整合以上三个模块，提供 CLI 命令
```

成绩 API 使用暨大金智 EMAP 教务系统的 `/jwapp/sys/cjcx/modules/cjcx/xscjcx.do` 接口，通过 POST 请求查询当前学期成绩。首次运行会记录所有已有成绩作为基线，之后每次查询只推送新增的成绩。

## 常见问题

**Q: Cookie 过期了怎么办？**

程序会自动尝试 CAS 静默重认证。如果 CAS 也过期了（目前还没遇到），终端会提示你重新运行 `python main.py login`。

**Q: 推送提示「Cookie 已过期」？**

运行 `python main.py login` 重新登录即可。

**Q: 查询返回空数据？**

可能是学期切换期间 API 尚未更新，等几天再试。也可以检查 `debug_response.json` 看 API 原始返回。

**Q: 免费版 Server酱每天只能发 5 条，够用吗？**

程序会自动合并多条新成绩为一条推送，按照教务处出成绩的速度，一般一天就3到4个科目。如果担心额度不够，可以考虑升级 Server酱付费版，或者把时间改成1小时推送一次。

## 项目结构

```
├── main.py            # 主程序入口，提供 login/check/test/daemon 命令
├── login.py           # 登录模块，Playwright + CAS 认证
├── checker.py         # 成绩查询模块，调用 EMAP API
├── notifier.py        # 通知模块，Server酱微信推送
├── config.json        # 配置文件（需自行填写）
├── requirements.txt   # Python 依赖
└── .gitignore         # Git 忽略规则
```

## 免责声明

本项目为AI生成。仅供学习交流使用。请妥善保管自己的账号密码，不要将包含真实凭据的 `config.json` 和 `cookies.json` 上传到公开仓库。使用本工具产生的一切后果由使用者自行承担。
