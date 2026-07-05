"""engine.py -- scoring and plan generation for the study tracker.

Pure Python. No ML training, no external services required. Given a study log
and a fixed syllabus, it computes a priority for every topic using a simple
spaced-repetition heuristic, then builds next-day / next-week / next-month plans.

Core idea
---------
Each time you study a topic you record a confidence (1-5). Low-confidence topics
should resurface quickly; high-confidence ones can wait. A topic becomes "due"
for revision once enough days have passed. Topics you have never logged are
tracked as gaps so they can be scheduled as new learning.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
SYLLABUS_PATH = DATA_DIR / "syllabus.json"
LOG_PATH = DATA_DIR / "log.json"

# Confidence (1-5) -> ideal number of days before a topic should be revised.
# Weak topics come back fast; strong topics can wait longer.
IDEAL_INTERVAL = {1: 1, 2: 2, 3: 4, 4: 7, 5: 14}

CONFIDENCE_LABELS = {
    1: "Just started",
    2: "Shaky",
    3: "Okay",
    4: "Solid",
    5: "Confident",
}


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def load_syllabus() -> dict[str, list[str]]:
    with open(SYLLABUS_PATH) as f:
        return json.load(f)


def load_log() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    with open(LOG_PATH) as f:
        return json.load(f)


def save_log(entries: list[dict]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with open(LOG_PATH, "w") as f:
        json.dump(entries, f, indent=2)


def add_entry(subject: str, subtopic: str, confidence: int,
              notes: str = "", when: date | None = None) -> list[dict]:
    """Append a study entry and persist. Returns the updated log."""
    entries = load_log()
    entries.append({
        "date": (when or date.today()).isoformat(),
        "subject": subject,
        "subtopic": subtopic,
        "confidence": int(confidence),
        "notes": (notes or "").strip(),
    })
    save_log(entries)
    return entries


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def latest_state(entries: list[dict]) -> dict[tuple[str, str], dict]:
    """Collapse the log into the most-recent state per (subject, subtopic)."""
    state: dict[tuple[str, str], dict] = {}
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for e in entries:
        key = (e["subject"], e["subtopic"])
        counts[key] += 1
        d = date.fromisoformat(e["date"])
        cur = state.get(key)
        if cur is None or d >= cur["last_date"]:
            state[key] = {"last_date": d, "confidence": int(e["confidence"])}
    for key, s in state.items():
        s["times_seen"] = counts[key]
    return state


def compute_priorities(syllabus, entries, today=None):
    """Score every subtopic in the syllabus.

    Returns (reviews, new_topics), each a list of dicts sorted by priority.
      reviews    -- already-studied topics, ranked by how overdue + how weak
      new_topics -- topics never logged, in syllabus order
    """
    today = today or date.today()
    state = latest_state(entries)
    reviews, new_topics = [], []

    for subject, subtopics in syllabus.items():
        for sub in subtopics:
            key = (subject, sub)
            st = state.get(key)
            if st is None:
                new_topics.append({
                    "subject": subject,
                    "subtopic": sub,
                    "status": "new",
                })
                continue
            days_since = (today - st["last_date"]).days
            ideal = IDEAL_INTERVAL[st["confidence"]]
            overdue = days_since - ideal
            # More overdue and/or weaker confidence -> higher priority.
            priority = overdue * 2 + (5 - st["confidence"]) * 3
            reviews.append({
                "subject": subject,
                "subtopic": sub,
                "status": "review",
                "confidence": st["confidence"],
                "days_since": days_since,
                "ideal": ideal,
                "overdue": overdue,
                "times_seen": st["times_seen"],
                "last_date": st["last_date"].isoformat(),
                "priority": priority,
            })

    reviews.sort(key=lambda x: x["priority"], reverse=True)
    return reviews, new_topics


# --------------------------------------------------------------------------- #
# Plans
# --------------------------------------------------------------------------- #
def daily_plan(syllabus, entries, today=None, n=5):
    """Plan for tomorrow: due revisions first, remaining slots for new topics."""
    today = today or date.today()
    reviews, new_topics = compute_priorities(syllabus, entries, today)

    due = [r for r in reviews if r["overdue"] >= 0]
    revise = due[: max(1, n - 2)] if due else []
    learn = new_topics[: n - len(revise)]
    # If everything is covered and nothing is due, keep one topic fresh.
    if not revise and not learn and reviews:
        revise = reviews[:1]

    return {
        "for_date": (today + timedelta(days=1)).isoformat(),
        "revise": revise,
        "learn": learn,
    }


def weekly_plan(syllabus, entries, today=None, per_day=4):
    """Spread revisions + new topics over the next 7 days."""
    today = today or date.today()
    reviews, new_topics = compute_priorities(syllabus, entries, today)

    # Include topics that are due or nearly due, highest priority first.
    pool_reviews = [r for r in reviews if r["overdue"] >= -2]
    pool_new = list(new_topics)

    days = []
    for i in range(1, 8):
        d = today + timedelta(days=i)
        items, target_reviews = [], per_day // 2
        for _ in range(target_reviews):
            if pool_reviews:
                items.append(pool_reviews.pop(0))
        while len(items) < per_day and pool_new:
            items.append(pool_new.pop(0))
        while len(items) < per_day and pool_reviews:
            items.append(pool_reviews.pop(0))
        days.append({
            "date": d.isoformat(),
            "weekday": d.strftime("%A"),
            "items": items,
        })
    return days


def monthly_overview(syllabus, entries, today=None):
    """Big-picture coverage: gaps, stale topics, confidence spread."""
    today = today or date.today()
    state = latest_state(entries)
    total = sum(len(v) for v in syllabus.values())
    studied = len(state)

    per_subject, stale, untouched = {}, [], []
    conf_buckets = {i: 0 for i in range(1, 6)}

    for subject, subtopics in syllabus.items():
        done = 0
        for sub in subtopics:
            st = state.get((subject, sub))
            if st is None:
                untouched.append({"subject": subject, "subtopic": sub})
                continue
            done += 1
            conf_buckets[st["confidence"]] += 1
            days_since = (today - st["last_date"]).days
            if days_since >= 14:
                stale.append({
                    "subject": subject,
                    "subtopic": sub,
                    "days_since": days_since,
                    "confidence": st["confidence"],
                })
        per_subject[subject] = {"done": done, "total": len(subtopics)}

    stale.sort(key=lambda x: x["days_since"], reverse=True)
    return {
        "coverage_pct": round(100 * studied / total) if total else 0,
        "studied": studied,
        "total": total,
        "per_subject": per_subject,
        "untouched": untouched,
        "stale": stale,
        "confidence_distribution": conf_buckets,
    }


def current_streak(entries, today=None) -> int:
    """Count consecutive days (ending today or yesterday) with at least one log."""
    today = today or date.today()
    logged_days = {date.fromisoformat(e["date"]) for e in entries}
    if not logged_days:
        return 0
    # Allow the streak to be "alive" if the latest log was today or yesterday.
    start = today if today in logged_days else today - timedelta(days=1)
    if start not in logged_days:
        return 0
    streak, day = 0, start
    while day in logged_days:
        streak += 1
        day -= timedelta(days=1)
    return streak


# --------------------------------------------------------------------------- #
# Optional: AI narrative (degrades gracefully if unavailable)
# --------------------------------------------------------------------------- #
def _build_prompt(daily, weekly, monthly) -> str:
    return (
        "You are a concise interview-prep coach. Based on the structured study "
        "data below, write a short, motivating plan in three sections: "
        "**Tomorrow**, **This Week**, **This Month**. Keep it practical and brief "
        "(a few bullets each). Do not invent topics beyond those given.\n\n"
        f"TOMORROW (structured): {json.dumps(daily)}\n\n"
        f"THIS WEEK (structured): {json.dumps(weekly)}\n\n"
        f"THIS MONTH (structured): {json.dumps(monthly)}\n"
    )


def narrative_plan(daily, weekly, monthly, api_key=None):
    """Turn the structured plans into a friendly writeup using Gemini.

    Returns None if no key or the SDK isn't installed, so the app can fall back
    to the rule-based view. Set GEMINI_API_KEY (or GOOGLE_API_KEY) to enable.
    """
    import os

    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        return None
    try:
        from google import genai
    except ImportError:
        return None
    try:
        client = genai.Client(api_key=key)
        resp = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=_build_prompt(daily, weekly, monthly),
        )
        return resp.text
    except Exception:
        return None
