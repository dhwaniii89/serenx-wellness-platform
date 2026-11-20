"""Dummy demo data. Runs only when the database is empty.

Demo logins (fake data only):
  Doctor : dr.meera@demo.com  / Doctor@123
  Patient: riya@demo.com      / Patient@123   (doing well, full streaks)
  Patient: kabir@demo.com     / Patient@123   (missed days, one flagged response)
"""
import json
import random
from datetime import date, timedelta

from . import ai, auth, db, logic

DOCTOR_PW = "Doctor@123"
PATIENT_PW = "Patient@123"


def _user(role, name, email, pw, **kw) -> int:
    h, s = auth.hash_password(pw)
    return db.ex(
        """INSERT INTO users (role, name, email, pw_hash, salt, specialization, bio, age, doctor_id, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (role, name, email, h, s, kw.get("specialization", ""), kw.get("bio", ""),
         kw.get("age"), kw.get("doctor_id"), db.now()),
    )


def _assessment(doctor_id, title, desc, questions) -> int:
    aid = db.ex("INSERT INTO assessments (doctor_id, title, description, created_at) VALUES (?,?,?,?)",
                (doctor_id, title, desc, db.now()))
    for i, (text, qtype, opts) in enumerate(questions):
        db.ex("INSERT INTO questions (assessment_id, position, text, qtype, options) VALUES (?,?,?,?,?)",
              (aid, i, text, qtype, json.dumps(opts)))
    return aid


def _goal(doctor_id, title, desc) -> int:
    return db.ex("INSERT INTO goals (doctor_id, title, description, created_at) VALUES (?,?,?,?)",
                 (doctor_id, title, desc, db.now()))


def _assign_a(aid, pid, freq, start) -> int:
    return db.ex("INSERT INTO a_assign (assessment_id, patient_id, frequency, start_date, created_at) VALUES (?,?,?,?,?)",
                 (aid, pid, freq, start.isoformat(), db.now()))


def _assign_g(gid, pid, freq, start) -> int:
    return db.ex("INSERT INTO g_assign (goal_id, patient_id, frequency, start_date, created_at) VALUES (?,?,?,?,?)",
                 (gid, pid, freq, start.isoformat(), db.now()))


def _fill_assessment(assign_id, assessment_id, title, past_dues, rng, skip, mood, texts, flag_on=None):
    """Create past submissions. mood(i, n) -> rating 1-5. skip(i, n) -> True to leave a day empty."""
    qs = db.q("SELECT * FROM questions WHERE assessment_id=? ORDER BY position", (assessment_id,))
    n = len(past_dues)
    for i, d in enumerate(past_dues):
        if skip(i, n):
            continue
        answers, qa = {}, []
        for q in qs:
            opts = json.loads(q["options"])
            if q["qtype"] == "rating":
                v = str(max(1, min(5, mood(i, n) + rng.choice([-1, 0, 0, 1]))))
            elif q["qtype"] == "multiple_choice":
                v = opts[min(len(opts) - 1, max(0, mood(i, n) - 2 + rng.choice([0, 1])))]
            else:
                v = texts[i % len(texts)] if flag_on != i else "Feeling hopeless lately and I can't sleep."
            answers[str(q["id"])] = v
            qa.append({"question_id": q["id"], "question": q["text"], "qtype": q["qtype"], "answer": v})
        flagged = int(ai.safety_flag([x["answer"] for x in qa if x["qtype"] == "text"]))
        db.ex(
            """INSERT INTO a_sub (assign_id, due_date, submitted_at, answers, summary, flagged)
               VALUES (?,?,?,?,?,?)""",
            (assign_id, d.isoformat(), f"{d.isoformat()}T20:15:00", json.dumps(answers),
             ai.offline_summary(title, qa), flagged),
        )


def _fill_goal(assign_id, past_dues, rng, skip, notes):
    n = len(past_dues)
    for i, d in enumerate(past_dues):
        if skip(i, n):
            continue
        done = rng.random() > 0.15
        db.ex(
            """INSERT INTO g_log (assign_id, due_date, progress, completed, notes, updated_at)
               VALUES (?,?,?,?,?,?)""",
            (assign_id, d.isoformat(), 100 if done else 60, int(done),
             notes[i % len(notes)] if i % 2 == 0 else "", f"{d.isoformat()}T19:00:00"),
        )


def seed() -> None:
    if db.q("SELECT 1 FROM users LIMIT 1"):
        return
    rng = random.Random(7)
    today = date.today()

    meera = _user("doctor", "Dr. Meera Shah", "dr.meera@demo.com", DOCTOR_PW,
                  specialization="Clinical Psychologist",
                  bio="Helps adults with stress, sleep and everyday emotional wellbeing. 12 years of experience.")
    arjun = _user("doctor", "Dr. Arjun Rao", "dr.arjun@demo.com", DOCTOR_PW,
                  specialization="Wellness Physician",
                  bio="Focus on lifestyle, mindfulness and habit-building.")
    riya = _user("patient", "Riya Patel", "riya@demo.com", PATIENT_PW, age=24, doctor_id=meera)
    kabir = _user("patient", "Kabir Mehta", "kabir@demo.com", PATIENT_PW, age=29, doctor_id=meera)
    _user("patient", "Ananya Iyer", "ananya@demo.com", PATIENT_PW, age=31, doctor_id=arjun)

    checkin = _assessment(meera, "Daily Emotional Check-in", "A quick daily look at mood and sleep.", [
        ("How is your mood today? (1 = very low, 5 = very good)", "rating", []),
        ("How many hours did you sleep last night?", "multiple_choice", ["Less than 4", "4-6", "6-8", "More than 8"]),
        ("Anything on your mind today?", "text", []),
    ])
    weekly = _assessment(meera, "Weekly Stress & Sleep Review", "A weekly look at stress and sleep quality.", [
        ("How stressed did you feel this week? (1 = not at all, 5 = extremely)", "rating", []),
        ("How good was your sleep quality this week? (1 = poor, 5 = excellent)", "rating", []),
        ("How often did you wake up during the night?", "multiple_choice",
         ["Never", "Once or twice a week", "Most nights", "Every night"]),
        ("What helped or hurt your week the most?", "text", []),
    ])
    meditate = _goal(meera, "Meditate for 10 minutes", "Sit quietly and focus on your breathing.")
    walk = _goal(meera, "Walk for 20 minutes", "A gentle walk outdoors if possible.")
    gratitude = _goal(meera, "Gratitude journal", "Write three things you are thankful for.")

    texts_good = ["Felt calmer after my walk.", "Busy day but manageable.", "Looking forward to the weekend.",
                  "Slept well, feeling fresh."]
    texts_low = ["Work deadlines are heavy.", "Tired and low on energy.", "Not much motivation today."]
    notes = ["Felt peaceful afterwards.", "Hard to focus but I finished.", "Walked by the river.", "Short but done."]

    for pid, start_back, good in ((riya, 14, True), (kabir, 14, False)):
        a_daily = _assign_a(checkin, pid, "daily", today - timedelta(days=start_back))
        a_week = _assign_a(weekly, pid, "weekly", today - timedelta(days=start_back))
        g_med = _assign_g(meditate, pid, "daily", today - timedelta(days=start_back))
        g_walk = _assign_g(walk, pid, "daily", today - timedelta(days=start_back))
        g_grat = _assign_g(gratitude, pid, "weekly", today - timedelta(days=start_back))

        def past(freq, start_back=start_back):
            return logic.due_dates(today - timedelta(days=start_back), freq, today)[:-1]  # today stays pending

        if good:
            mood = lambda i, n: 2 + round(2 * i / max(1, n - 1))      # slowly improving 2 -> 4
            skip = lambda i, n: False
            _fill_assessment(a_daily, checkin, "Daily Emotional Check-in", past("daily"), rng, skip, mood, texts_good)
            _fill_assessment(a_week, weekly, "Weekly Stress & Sleep Review", past("weekly"), rng, skip, mood, texts_good)
            _fill_goal(g_med, past("daily"), rng, skip, notes)
            _fill_goal(g_walk, past("daily"), rng, lambda i, n: i % 5 == 4, notes)
            _fill_goal(g_grat, past("weekly"), rng, skip, notes)
        else:
            mood = lambda i, n: 3 - round(1.5 * i / max(1, n - 1))   # slowly declining 3 -> 1/2
            skip = lambda i, n: i >= n - 5 and i % 2 == 0            # skipping more recently
            dailies = past("daily")
            _fill_assessment(a_daily, checkin, "Daily Emotional Check-in", dailies, rng, skip, mood,
                             texts_low, flag_on=len(dailies) - 1)
            _fill_assessment(a_week, weekly, "Weekly Stress & Sleep Review", past("weekly"), rng,
                             lambda i, n: False, mood, texts_low)
            _fill_goal(g_med, past("daily"), rng, lambda i, n: i >= n - 6, notes)
            _fill_goal(g_walk, past("daily"), rng, lambda i, n: i >= n - 4 or i % 3 == 0, notes)
            _fill_goal(g_grat, past("weekly"), rng, lambda i, n: i == n - 1, notes)


def seed_wellness() -> None:
    """Add demo mood and journal entries once, also to databases created before these features existed."""
    if db.q("SELECT 1 FROM mood_log LIMIT 1"):
        return
    today = date.today()
    people = {u["email"]: u["id"] for u in db.q("SELECT id, email FROM users WHERE role='patient'")}
    rng = random.Random(7)
    plans = {"riya@demo.com": lambda i, n: min(5, 3 + (i * 2) // n + rng.choice([0, 0, 1])),
             "kabir@demo.com": lambda i, n: max(1, 3 - (i * 2) // n - rng.choice([0, 0, 1])),
             "ananya@demo.com": lambda i, n: rng.choice([3, 3, 4, 4, 2])}
    notes = {5: "Great day", 4: "Felt good after a walk", 2: "Tired and stressed", 1: "Hard day"}
    n = 24
    for email, fn in plans.items():
        uid = people.get(email)
        if not uid:
            continue
        for i in range(n):
            if rng.random() < 0.15:
                continue
            day = (today - timedelta(days=n - i)).isoformat()
            m = int(max(1, min(5, fn(i, n))))
            db.ex("INSERT OR IGNORE INTO mood_log (user_id, day, mood, note, updated_at) VALUES (?,?,?,?,?)",
                  (uid, day, m, notes.get(m, ""), db.now()))
    riya = people.get("riya@demo.com")
    if riya:
        db.ex("INSERT INTO journal (user_id, created_at, text, source, reflection, flagged) VALUES (?,?,?,?,?,0)",
              (riya, (today - timedelta(days=2)).isoformat() + "T20:10:00",
               "Went for a walk after work and felt calmer. I want to keep doing this every evening.", "typed",
               "There is a lot of warmth in this entry. Noticing what went well helps you find it again. "
               "What would you like to repeat this week?"))
