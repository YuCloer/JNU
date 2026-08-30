# ScoutXI 足球球探程序（基础版）

一个可直接在 PyCharm 中运行的本地 Web 应用，让足球球迷查询球员与俱乐部资料，并按位置约束规划、保存自己的阵容。

## 范围

已实现：搜索与筛选、球员详情、俱乐部赛季阵容、4-3-3 / 4-2-3-1 阵容画布、首发/替补/队长、保存、收藏、个人球探报告、同步状态。

明确未实现：高级数据分析、雷达图、视频识别、AI 推荐。

## 本地运行

前置条件：Windows、Python 3.10+ 与 PowerShell。进入 `ScoutXI` 目录后执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

在浏览器打开 http://127.0.0.1:8000 。首次启动会自动创建 `data/scoutxi.db` 并写入本地演示数据。

在 PyCharm 中，将解释器设为项目的 `.venv` 后，直接运行 `run.py` 即可。

不配置 API 也可使用阵容规划、搜索、收藏与球探报告；此时显示的是内置演示数据。

## 配置足球数据 API（可选）

1. 复制示例配置文件：

```powershell
Copy-Item .env.example .env
```

2. 用文本编辑器打开本机的 `.env`，填入至少一个服务端密钥：

```ini
FOOTBALL_DATA_API_TOKEN=你的_football-data.org_密钥
API_FOOTBALL_KEY=你的_API-Football_密钥
```

3. 重启 `python run.py`，打开“数据状态”页面并点击“立即刷新当前名单”。

`FOOTBALL_DATA_API_TOKEN` 用于五大联赛球队、名单、队标和射手榜；可在 [football-data.org](https://www.football-data.org/client/register) 注册并取得 Token。`API_FOOTBALL_KEY` 用于转会记录校验与补充头像；可在 [API-Football](https://dashboard.api-football.com/) 创建密钥。

两个密钥均为可选：程序会优先使用已配置且能提供当前赛季数据的来源。免费套餐通常有每日请求量与赛季访问限制；程序遇到限制会明确报告，而不会把旧赛季数据伪装成最新名单。

## 刷新范围与说明

球员头像和球队队标始终使用远程 URL，不会下载或保存图片到本机。头像只有在公开资料中的当前俱乐部字段与 ScoutXI 当前名单匹配时才会显示；无法核验的旧图片改用中性占位，避免展示旧队服。首页“近期焦点球员”依据五大联赛本赛季进球、助攻进行透明排序，不使用 AI 推荐。

名单同步会覆盖英超、西甲、意甲、德甲、法甲的球队；近期转会记录会作为第二层校验。免费接口受日额度限制时，重复刷新会继续处理尚未完成的球队。

阵容编辑器按位置区域约束首发球员：球场由下向上进攻，GK 固定在底部、后卫在后场、中场在中场、ST 在最前端；不兼容的位置无法进入该区域。

## 常见问题

- **端口被占用**：关闭原先的 `python run.py` 进程，或修改 `run.py` 中的端口。
- **名单未更新**：确认 `.env` 中的密钥已保存，重启服务，再从“数据状态”刷新；免费额度耗尽时等待服务商额度重置。
- **头像/队标不显示**：它们来自公开远程 URL；检查网络连接或稍后重试。

## 安全与隐私

API 密钥只能写在本机 `.env` 中，不能提交到 GitHub；该文件、SQLite 数据库、日志、虚拟环境和 IDE 配置均已被 Git 忽略。程序默认仅监听 `127.0.0.1`。如果改为局域网或公网监听，应先为管理同步接口增加认证。
