# 📚 Interview Prep Tracker

A personal study tracker for IT/CS interview prep. You log what you studied each
day with a confidence rating; it looks back over your history and tells you what
to focus on **tomorrow, this week, and this month** — prioritising weak and
stale topics and flagging syllabus gaps.

No quizzes. No ML training. Just a self-report log + a spaced-repetition-style
priority formula + a clean UI.

## How it works

- **Log today** — pick a subject/topic, rate your confidence 1–5, add a note.
- **Priority engine** (`engine.py`) — each topic has an "ideal revision interval"
  based on your last confidence (weak = revisit fast, strong = wait longer). A
  topic becomes *due* once enough days pass. Never-logged topics are tracked as
  gaps.
- **My plan** — the app schedules due revisions first, fills remaining slots with
  new topics, and spreads everything across the next day / week / month.
- **Overview** — coverage by subject, confidence spread, stale-topic warnings.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Opens at `http://localhost:8501`.

## Deploy (free)

Push this folder to a GitHub repo, then go to
[share.streamlit.io](https://share.streamlit.io), point it at `app.py`, and
deploy. Zero config.

> Note: Streamlit Community Cloud's filesystem is ephemeral, so `data/log.json`
> may reset on redeploy. Use the **Download / Restore log.json** buttons in the
> sidebar to back up and reload your history. (To make it fully persistent
> later, swap the flat-file log in `engine.py` for SQLite or a hosted DB.)

## Customise the syllabus

Edit `data/syllabus.json` — it's just `{ "Subject": ["Topic", ...] }`. Add,
remove, or rename anything; the engine adapts automatically.

## Optional: AI-written plan

The **✨ Write it up with AI** toggle turns the structured plan into a friendly
summary via Gemini. Set an API key first:

```bash
export GEMINI_API_KEY="your-key"   # never paste the key into code/chat
```

or add it to `.streamlit/secrets.toml`. Without a key, the app just shows the
rule-based plan.

## Files

| File | Purpose |
|------|---------|
| `app.py` | Streamlit UI |
| `engine.py` | Scoring + plan generation (pure Python) |
| `data/syllabus.json` | Your topic list |
| `data/log.json` | Your study history (auto-created) |
| `requirements.txt` | Dependencies |
