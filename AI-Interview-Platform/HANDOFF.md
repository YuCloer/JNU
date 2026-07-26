# HANDOFF - AI-Interview-Platform

> Last updated: 2026-07-26
> Context: Session focused on trace-driven bug fixes, true SSE streaming, error handling hardening, and plan-document gap closure.

---

## Architecture Overview

```
backend/services/resume_parser.py  -- Resume parsing (4-layer pipeline)
backend/services/jd_matcher.py     -- JD skill extraction + weighted matching
backend/services/interview_agent.py -- Interview agent (LangGraph)
backend/schemas.py                 -- Pydantic models (ResumeSchema etc.)
backend/routers/resume.py          -- Upload + parse endpoint
backend/routers/jd.py              -- JD match endpoint
backend/routers/interview.py       -- SSE streaming interview
frontend/src/views/UploadView.vue  -- Resume display
frontend/src/views/MatchView.vue   -- Match result (3-dimension bars)
```

---

## Resume Parsing Pipeline (resume_parser.py)

Flow: `raw PDF bytes -> _extract_pdf -> _preprocess_text -> LLM -> _sanitize_llm_output -> pydantic -> post-processing`

### Layer 1: Multi-column PDF Detection (_extract_page_columns)

- Uses pdfplumber `extract_words()` to get x-coordinates
- Builds 50-bin histogram of word x-positions
- Finds widest vertical gap in 25%-75% region
- If gap >= 2 bins: splits page into left/right crops
- Extracts wider column (main content) first, sidebar second
- Falls back to normal `extract_text()` for single-column PDFs

### Layer 2: Preprocessing (_preprocess_text)

- Collapses whitespace
- `_reassemble_courses()`: merges course lines broken by multi-column extraction; collects email/phone noise lines and re-inserts them at top
- `_clean_github_links()`: merges broken GitHub paths in sidebar "open source projects" section, marks them as "repo: xxx" so LLM doesn't treat them as project names

### Layer 3: LLM Extraction + Sanitize

- Prompt: few-shot example (short, 3B model can't follow long instructions)
- `_sanitize_llm_output()` converts common LLM format errors BEFORE pydantic validation:
  - `skills: [{name, level}]` -> `["Python", "SQL"]`
  - `languages: [{language, level}]` -> `["English CET-6"]`
  - `internships` key -> renamed to `experiences`
  - `projects[].tech_stack: list` -> joined string
  - `experiences[].description: list` -> joined string
  - `education[].end_date` non-date text -> cleared

### Layer 4: Post-processing

- `_ensure_name()`: validates LLM name, falls back to regex
- `_regex_email()` / `_regex_phone()`: extracted from raw_text BEFORE preprocessing (safety net)
- `_filter_skills()`: whitelist approach - only passes known techs (60+), Chinese tech whitelist, or strict tech-like patterns
- `_courses_to_skills()`: COURSE_SKILL_MAP (35+ courses) infers skills from course names
- `_regex_languages()`: detects language section, matches certs (CET/DELF/JLPT) to correct language
- `_regex_education()` / `_regex_experiences()` / `_regex_projects()`: fallback if LLM fails

### Known Quirks

- qwen2.5:3b often outputs skills as objects, languages as dicts, tech_stack as arrays
- Multi-column PDFs from Canva/Figma resumes have sidebar width ~30% of page
- The "core courses" line gets split by email/phone in multi-column extraction
- Windows Python needs `python -X utf8` to avoid GBK encoding errors in tests

---

## JD Matching Algorithm (jd_matcher.py)

### Skill Extraction (extract_jd_skills)

- LLM extraction with simplified few-shot prompt
- `_filter_non_skills()`: rejects sentences (>10 chars Chinese, >20 chars English), verb-prefix phrases, conjunction phrases
- `_keyword_fallback()`: 80+ keyword dictionary + 16 implicit inference rules
- **Both LLM and rules ALWAYS merge** (not fallback-only)
- Short English keywords (<=3 chars) use word-boundary regex to avoid false matches (R, PR)

### Dynamic Skill Weights (_compute_skill_weights)

```
weight = proficiency_weight * specificity_weight
```

Proficiency (from JD context around skill mention, +/- 40 chars):
- "proficient/expert/familiar" -> 1.0
- "able to/have experience" -> 0.7
- "understand/preferred" -> 0.4
- not found -> 0.6

Specificity (skill type):
- Specific tools (Python, SQL, Docker...) -> 1.0
- Methodologies (Prompt Engineering...) -> 0.8
- Generic categories (AI tools, data analysis...) -> 0.6

### Position Matching (match_position)

Three weighted dimensions:
- Education: 20% (degree level comparison)
- Skills: 50% (weighted match rate, not simple count)
- Experience: 30% (keyword overlap in projects/experiences vs JD)

Returns `dimensions.skills.weights` dict for frontend display.

---

## Recent Changes (2026-07-26 session)

1. **Education date sanitization** - start_date now strips non-date suffixes ("2018 至今" → "2018"); end_date normalizes "2027 届" → "2027", preserves "2025.06" format
2. **True SSE streaming** - interview router now uses `llm.astream()` via `astream_next_question()` for real token-by-token delivery (was fake char-by-char after sync generation)
3. **SSE error handling** - backend sends `{'error': ...}` event when Ollama unreachable; frontend handles it gracefully
4. **SSE buffer parsing** - frontend InterviewView now buffers partial SSE lines across network chunks (prevents JSON parse errors on split packets)
5. **Health check** - `/api/health` now actually invokes LLM to verify Ollama connectivity (returns "degraded" status on failure)
6. **Resume parse timeout** - `/resume/parse` wrapped in `asyncio.wait_for(timeout=60)` to avoid infinite hang
7. **Frontend languages display** - UploadView now shows parsed language abilities (was missing)
8. **GitHub link cleanup improved** - second pass now catches plain "User/Repo" and "User/Org/Repo" patterns without github.com prefix
9. **Interview chat fallback** - if astream fails mid-stream, degrades to sync `get_next_question()` instead of crashing

## Previous Session Changes (2026-07-25)

1. Multi-column PDF detection - word x-coordinate histogram, column split, main-first ordering
2. GitHub link cleanup - sidebar "open source projects" merged and marked as repos
3. Email/phone preservation - noise lines collected during course reassembly, re-inserted at top; raw_text safety net
4. LLM sanitize layer - prevents pydantic crash from format variations
5. Language extraction - regex fallback with cert-to-language mapping
6. Course-to-skill inference - COURSE_SKILL_MAP with 35+ entries
7. Whitelist skill filtering - rejects all non-tech garbage
8. Dynamic skill weights - proficiency x specificity replaces equal weighting
9. JD extraction merge - LLM + rules always combined
10. JD prompt simplification - few-shot format for 3B model
11. README updated - reflects all above changes

---

## Pending / Known Issues

- [x] ~~LLM outputs `education.end_date` as non-date text~~ → Fixed: sanitize now normalizes both start_date and end_date
- [x] ~~Projects from LLM may have GitHub paths as `role` field~~ → Fixed: sanitize catches github.com and slash-path patterns in role
- [x] ~~Frontend `MatchView.vue` doesn't display per-skill weights~~ → Fixed: weights shown as `×0.85` superscript on skill tags
- [ ] `_clean_github_links` handles "GitHub / User / Org / Repo" and plain "User/Repo" formats; exotic link formats (GitLab, Gitee) untested
- [ ] Three-column PDFs not supported (only two-column detection)
- [ ] `interview_agent.py` evaluate_round is synchronous (blocks event loop during eval) — acceptable for 3B model latency
- [ ] TTS voice output not implemented (marked optional in plan, MVP skippable)
- [ ] User accounts / history not implemented (explicitly excluded from MVP in plan)

---

## How to Run

```bash
# Backend
cd backend
pip install -r requirements.txt  # includes pdfplumber>=0.11.0
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

Requires: Ollama running with `qwen2.5:3b` model pulled.

---

## Git

Repo: `https://github.com/YuCloer/JNU` (project is subdirectory `AI-Interview-Platform/`)
Push script: `git_push.bat` + `git_exclude.txt` (in outputs folder, copy to same dir and double-click)

---

## Key Files Quick Reference

| File | Purpose | Lines |
|------|---------|-------|
| `backend/services/resume_parser.py` | Resume parsing pipeline | ~800 |
| `backend/services/jd_matcher.py` | JD extraction + weighted matching | ~310 |
| `backend/schemas.py` | Pydantic models | ~73 |
| `backend/routers/jd.py` | Match endpoint (calls match_position) | ~40 |
| `frontend/src/views/MatchView.vue` | Match result display | ~200 |
| `frontend/src/views/UploadView.vue` | Resume preview | ~150 |
