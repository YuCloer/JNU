# Grade Checker Guard

A Windows-first CLI for monitoring newly published university grades and calculating GPA locally.

The tool automates the repetitive parts of checking an academic portal while keeping credentials, session data, and grade history on the local machine.

## What it does

- polls the EMAP academic system for new grade records;
- de-duplicates records by course, grade, and semester;
- sends optional Server酱 notifications when new grades appear;
- calculates semester, academic-year, and cumulative GPA;
- supports one-off checks as well as a long-running daemon.

## Design highlights

- **Authentication** — Playwright drives CAS login and keeps browser state in a project-local profile.
- **Session recovery** — expired sessions are re-authenticated through a fresh browser context with bounded retry backoff.
- **Data protection** — cookies and grade history use AES-256-GCM; the encryption key is protected with Windows DPAPI.
- **Deterministic calculations** — GPA is computed from the portal's returned grade-point field; repeated courses use the highest recorded point.
- **Operational safety** — API tokens, local databases, browser profiles, logs, and virtual environments are excluded from version control.

## Technology

Python · Playwright · HTTPX · Click · Pydantic Settings · Loguru · Cryptography · Windows DPAPI

## Quick start

Requirements: Windows 10/11, Python 3.11+, and Google Chrome.

```powershell
pip install -r requirements.txt
playwright install chromium
Copy-Item config.example.json config.json
```

Complete the local configuration, then use:

```powershell
python main.py login
python main.py check
python main.py daemon
python main.py gpa --all
```

The first login is interactive because the CAS slider challenge requires user participation.

## Configuration

```json
{
  "serverchan_token": "your-token",
  "base_url": "https://jw.jnu.edu.cn",
  "check_interval_minutes": 10,
  "chrome_user_data_dir": ""
}
```

Keep `config.json` local. Never commit tokens, cookies, passwords, or browser profiles.

## Project structure

```
Grade-Watcher/
├── app/
│   ├── core/       # authentication, fetching, comparison, GPA
│   ├── notify/     # Server酱 and Windows Toast
│   └── utils/      # configuration, encryption, logging
├── tests/
├── main.py
└── config.example.json
```

## Known constraints

- CAS slider verification is intentionally manual.
- The tool targets Windows because its key-protection path uses DPAPI.
- The academic portal API may change and require adapter updates.
- Server酱 delivery is optional and depends on the configured provider.
