"""FastAPI backend for the Doctor-Patient Wellness Platform."""
import json
import sqlite3
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import ai, auth, db, logic

Frequency = Literal["once", "daily", "weekly", "monthly"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    from .seed import seed, seed_wellness

    seed()
    seed_wellness()
    yield


app = FastAPI(title="Wellness Platform API", lifespan=lifespan)


# ============================================================ helpers
def _public(u: dict) -> dict:
    out = {k: v for k, v in u.items() if k not in ("pw_hash", "salt")}
    if u["role"] == "patient" and u.get("doctor_id"):
        d = db.q("SELECT id, name, specialization, bio FROM users WHERE id=?", (u["doctor_id"],))
        out["doctor"] = d[0] if d else None
    return out


def _questions(assessment_id: int) -> list[dict]:
    rows = db.q("SELECT * FROM questions WHERE assessment_id=? ORDER BY position", (assessment_id,))
    for r in rows:
        r["options"] = json.loads(r["options"] or "[]")
    return rows


def _qa(assessment_id: int, answers: dict) -> list[dict]:
    return [
        {"question_id": q["id"], "question": q["text"], "qtype": q["qtype"],
         "answer": answers.get(str(q["id"]), "")}
        for q in _questions(assessment_id)
    ]


def _my_patient(doctor: dict, pid: int) -> dict:
    rows = db.q("SELECT * FROM users WHERE id=? AND role='patient' AND doctor_id=?", (pid, doctor["id"]))
    if not rows:
        raise HTTPException(404, "Patient not found or not connected to you.")
    return rows[0]


def _today() -> date:
    return date.today()


# ------------------------------------------------ assessment instances
def _assess_items(pid: int, today: date) -> dict:
    rows = db.q(
        """SELECT a.id AS assign_id, a.assessment_id, a.frequency, a.start_date, t.title, t.description
           FROM a_assign a JOIN assessments t ON t.id = a.assessment_id WHERE a.patient_id=?""",
        (pid,),
    )
    pending, upcoming, streaks = [], [], []
    missed7 = due_total = done_total = 0
    for r in rows:
        start = date.fromisoformat(r["start_date"])
        dues = logic.due_dates(start, r["frequency"], today)
        subs = {s["due_date"] for s in db.q("SELECT due_date FROM a_sub WHERE assign_id=?", (r["assign_id"],))}
        due_total += len(dues)
        done_total += sum(1 for d in dues if d.isoformat() in subs)
        if dues:
            cur = dues[-1]
            if cur.isoformat() not in subs:
                pending.append({**r, "due_date": cur.isoformat(), "questions": _questions(r["assessment_id"])})
            missed7 += sum(1 for d in dues[:-1] if d > today - timedelta(days=7) and d.isoformat() not in subs)
            streaks.append({"title": r["title"], "kind": "assessment", "streak": logic.streak(dues, subs)})
        nd = logic.next_due(start, r["frequency"], today)
        if nd:
            upcoming.append({"assign_id": r["assign_id"], "title": r["title"],
                             "frequency": r["frequency"], "due_date": nd.isoformat()})
    return {"pending": pending, "upcoming": sorted(upcoming, key=lambda x: x["due_date"]),
            "missed7": missed7, "due_total": due_total, "done_total": done_total, "streaks": streaks}


# ------------------------------------------------------- goal instances
def _goal_items(pid: int, today: date) -> dict:
    rows = db.q(
        """SELECT g.id AS assign_id, g.goal_id, g.frequency, g.start_date, t.title, t.description
           FROM g_assign g JOIN goals t ON t.id = g.goal_id WHERE g.patient_id=?""",
        (pid,),
    )
    current, upcoming, streaks = [], [], []
    missed7 = due_total = done_total = 0
    for r in rows:
        start = date.fromisoformat(r["start_date"])
        dues = logic.due_dates(start, r["frequency"], today)
        logs = {l["due_date"]: l for l in db.q("SELECT * FROM g_log WHERE assign_id=?", (r["assign_id"],))}
        done = {d for d, l in logs.items() if l["completed"]}
        due_total += len(dues)
        done_total += sum(1 for d in dues if d.isoformat() in done)
        if dues:
            cur = dues[-1]
            log = logs.get(cur.isoformat())
            current.append({**r, "due_date": cur.isoformat(),
                            "progress": log["progress"] if log else 0,
                            "completed": bool(log and log["completed"]),
                            "notes": log["notes"] if log else ""})
            missed7 += sum(1 for d in dues[:-1] if d > today - timedelta(days=7) and d.isoformat() not in done)
            streaks.append({"title": r["title"], "kind": "goal", "streak": logic.streak(dues, done)})
        nd = logic.next_due(start, r["frequency"], today)
        if nd:
            upcoming.append({"assign_id": r["assign_id"], "title": r["title"],
                             "frequency": r["frequency"], "due_date": nd.isoformat()})
    return {"current": current, "upcoming": sorted(upcoming, key=lambda x: x["due_date"]),
            "missed7": missed7, "due_total": due_total, "done_total": done_total, "streaks": streaks}


def _trend(pid: int) -> list[dict]:
    """Average rating answer per submission, for the mood chart."""
    subs = db.q(
        """SELECT s.id, s.due_date, s.answers, a.assessment_id, t.title
           FROM a_sub s JOIN a_assign a ON a.id = s.assign_id
           JOIN assessments t ON t.id = a.assessment_id
           WHERE a.patient_id=? ORDER BY s.due_date, s.id""",
        (pid,),
    )
    rating_ids: dict[int, list[str]] = {}
    out = []
    for s in subs:
        if s["assessment_id"] not in rating_ids:
            rating_ids[s["assessment_id"]] = [
                str(q["id"]) for q in _questions(s["assessment_id"]) if q["qtype"] == "rating"
            ]
        answers = json.loads(s["answers"])
        vals = []
        for qid in rating_ids[s["assessment_id"]]:
            try:
                vals.append(int(answers[qid]))
            except (KeyError, TypeError, ValueError):
                pass
        if vals:
            out.append({"date": s["due_date"], "title": s["title"], "value": round(sum(vals) / len(vals), 2)})
    return out


def _flagged_unreviewed(pid: int) -> int:
    return db.q(
        """SELECT COUNT(*) AS n FROM a_sub s JOIN a_assign a ON a.id = s.assign_id
           WHERE a.patient_id=? AND s.flagged=1 AND s.reviewed=0""",
        (pid,),
    )[0]["n"]


def _overview(p: dict, today: date) -> dict:
    a, g = _assess_items(p["id"], today), _goal_items(p["id"], today)
    trend = _trend(p["id"])
    due = a["due_total"] + g["due_total"]
    done = a["done_total"] + g["done_total"]
    missed = a["missed7"] + g["missed7"]
    flagged = _flagged_unreviewed(p["id"])
    latest = trend[-1]["value"] if trend else None
    reasons = []
    if flagged:
        reasons.append(f"{flagged} response(s) flagged for review")
    if missed >= 3:
        reasons.append(f"Missed {missed} tasks in the last 7 days")
    if latest is not None and latest <= 2:
        reasons.append(f"Low recent rating ({latest}/5)")
    return {
        "id": p["id"], "name": p["name"], "age": p["age"], "email": p["email"],
        "pending_assessments": len(a["pending"]),
        "open_goals": sum(1 for x in g["current"] if not x["completed"]),
        "missed_7d": missed,
        "completion_rate": round(100 * done / due) if due else None,
        "latest_rating": latest, "flagged": flagged,
        "needs_attention": bool(reasons), "reasons": reasons,
    }


# ============================================================ schemas
class RegisterIn(BaseModel):
    role: Literal["doctor", "patient"]
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=120)
    password: str = Field(min_length=6, max_length=100)
    specialization: str = ""
    bio: str = ""
    age: Optional[int] = Field(default=None, ge=1, le=120)
    doctor_id: Optional[int] = None


class LoginIn(BaseModel):
    email: str
    password: str


class QuestionIn(BaseModel):
    text: str = Field(min_length=3)
    qtype: Literal["multiple_choice", "rating", "text"]
    options: list[str] = []


class AssessmentIn(BaseModel):
    title: str = Field(min_length=3, max_length=100)
    description: str = ""
    questions: list[QuestionIn] = Field(min_length=1)


class GoalIn(BaseModel):
    title: str = Field(min_length=3, max_length=100)
    description: str = ""


class AssignAssessmentIn(BaseModel):
    assessment_id: int
    patient_ids: list[int] = Field(min_length=1)
    frequency: Frequency
    start_date: Optional[date] = None


class AssignGoalIn(BaseModel):
    goal_id: int
    patient_ids: list[int] = Field(min_length=1)
    frequency: Frequency
    start_date: Optional[date] = None


class AiGenerateIn(BaseModel):
    topic: str = Field(min_length=3, max_length=400)
    n: int = 6


class SubmitIn(BaseModel):
    assign_id: int
    due_date: date
    answers: dict[str, str | int]


class GoalUpdateIn(BaseModel):
    assign_id: int
    due_date: date
    progress: int = Field(ge=0, le=100)
    completed: bool = False
    notes: str = ""


# ============================================================ public
@app.get("/health")
def health():
    return {"ok": True, "ai": ai.mode()}


@app.get("/doctors")
def list_doctors():
    return db.q("SELECT id, name, specialization, bio FROM users WHERE role='doctor' ORDER BY name")


@app.post("/register")
def register(body: RegisterIn):
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "Please enter a valid email.")
    if db.q("SELECT 1 FROM users WHERE email=?", (email,)):
        raise HTTPException(409, "This email is already registered.")
    doctor_id = None
    if body.role == "patient":
        if not body.doctor_id or not db.q("SELECT 1 FROM users WHERE id=? AND role='doctor'", (body.doctor_id,)):
            raise HTTPException(422, "Please choose a doctor to consult.")
        doctor_id = body.doctor_id
    pw_hash, salt = auth.hash_password(body.password)
    uid = db.ex(
        """INSERT INTO users (role, name, email, pw_hash, salt, specialization, bio, age, doctor_id, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (body.role, body.name.strip(), email, pw_hash, salt, body.specialization.strip(),
         body.bio.strip(), body.age, doctor_id, db.now()),
    )
    user = db.q("SELECT * FROM users WHERE id=?", (uid,))[0]
    return {"token": auth.create_token(uid), "user": _public(user)}


@app.post("/login")
def login(body: LoginIn):
    rows = db.q("SELECT * FROM users WHERE email=?", (body.email.strip().lower(),))
    if not rows or not auth.verify_password(body.password, rows[0]["pw_hash"], rows[0]["salt"]):
        raise HTTPException(401, "Wrong email or password.")
    return {"token": auth.create_token(rows[0]["id"]), "user": _public(rows[0])}


@app.get("/me")
def me(user: dict = Depends(auth.current_user)):
    return _public(user)


# ============================================================ doctor
@app.get("/patients")
def patients(doctor: dict = Depends(auth.doctor_only)):
    rows = db.q("SELECT * FROM users WHERE role='patient' AND doctor_id=? ORDER BY name", (doctor["id"],))
    today = _today()
    return [_overview(p, today) for p in rows]


@app.get("/patients/{pid}")
def patient_detail(pid: int, doctor: dict = Depends(auth.doctor_only)):
    p = _my_patient(doctor, pid)
    today = _today()
    a, g = _assess_items(pid, today), _goal_items(pid, today)

    subs = db.q(
        """SELECT s.id, s.due_date, s.submitted_at, s.answers, s.summary, s.flagged, s.reviewed,
                  a.assessment_id, a.frequency, t.title
           FROM a_sub s JOIN a_assign a ON a.id = s.assign_id
           JOIN assessments t ON t.id = a.assessment_id
           WHERE a.patient_id=? ORDER BY s.submitted_at DESC""",
        (pid,),
    )
    submissions = [
        {"id": s["id"], "title": s["title"], "frequency": s["frequency"], "due_date": s["due_date"],
         "submitted_at": s["submitted_at"], "summary": s["summary"],
         "flagged": bool(s["flagged"]), "reviewed": bool(s["reviewed"]),
         "answers": _qa(s["assessment_id"], json.loads(s["answers"]))}
        for s in subs
    ]
    goal_history = db.q(
        """SELECT l.due_date, l.progress, l.completed, l.notes, l.updated_at, t.title, g.frequency
           FROM g_log l JOIN g_assign g ON g.id = l.assign_id JOIN goals t ON t.id = g.goal_id
           WHERE g.patient_id=? ORDER BY l.due_date DESC, l.id DESC""",
        (pid,),
    )
    return {
        "profile": {k: p[k] for k in ("id", "name", "email", "age", "created_at")},
        "overview": _overview(p, today),
        "pending_assessments": [{"title": x["title"], "frequency": x["frequency"], "due_date": x["due_date"]}
                                for x in a["pending"]],
        "current_goals": g["current"],
        "upcoming": sorted(a["upcoming"] + g["upcoming"], key=lambda x: x["due_date"]),
        "submissions": submissions,
        "goal_history": goal_history,
        "trend": _trend(pid),
        "streaks": a["streaks"] + g["streaks"],
    }


@app.post("/patients/{pid}/weekly-report")
def weekly_report(pid: int, doctor: dict = Depends(auth.doctor_only)):
    p = _my_patient(doctor, pid)
    today = _today()
    since = (today - timedelta(days=7)).isoformat()
    ov = _overview(p, today)
    trend = _trend(pid)
    recent = [t["value"] for t in trend if t["date"] > since]
    before = [t["value"] for t in trend if t["date"] <= since][-7:]
    goals_done = db.q(
        """SELECT COUNT(*) AS n FROM g_log l JOIN g_assign g ON g.id = l.assign_id
           WHERE g.patient_id=? AND l.completed=1 AND l.due_date>?""", (pid, since))[0]["n"]
    a_done = db.q(
        """SELECT COUNT(*) AS n FROM a_sub s JOIN a_assign a ON a.id = s.assign_id
           WHERE a.patient_id=? AND s.due_date>?""", (pid, since))[0]["n"]
    facts = {
        "avg_rating_this_week": round(sum(recent) / len(recent), 2) if recent else None,
        "avg_rating_before": round(sum(before) / len(before), 2) if before else None,
        "assessments_done_7d": a_done, "goals_done_7d": goals_done,
        "missed_7d": ov["missed_7d"], "flagged_unreviewed": ov["flagged"],
        "overall_completion_percent": ov["completion_rate"],
    }
    return ai.weekly_report(p["name"], facts)


@app.get("/submissions")
def recent_submissions(limit: int = 15, doctor: dict = Depends(auth.doctor_only)):
    rows = db.q(
        """SELECT s.id, s.due_date, s.submitted_at, s.summary, s.flagged, s.reviewed, s.answers,
                  a.assessment_id, t.title, u.id AS patient_id, u.name AS patient_name
           FROM a_sub s JOIN a_assign a ON a.id = s.assign_id
           JOIN assessments t ON t.id = a.assessment_id
           JOIN users u ON u.id = a.patient_id
           WHERE u.doctor_id=? ORDER BY s.submitted_at DESC LIMIT ?""",
        (doctor["id"], max(1, min(limit, 100))),
    )
    return [{"id": r["id"], "title": r["title"], "patient_id": r["patient_id"],
             "patient_name": r["patient_name"], "due_date": r["due_date"],
             "submitted_at": r["submitted_at"], "summary": r["summary"],
             "flagged": bool(r["flagged"]), "reviewed": bool(r["reviewed"]),
             "answers": _qa(r["assessment_id"], json.loads(r["answers"]))} for r in rows]


@app.post("/submissions/{sid}/review")
def mark_reviewed(sid: int, doctor: dict = Depends(auth.doctor_only)):
    ok = db.q(
        """SELECT s.id FROM a_sub s JOIN a_assign a ON a.id = s.assign_id
           JOIN users u ON u.id = a.patient_id WHERE s.id=? AND u.doctor_id=?""",
        (sid, doctor["id"]),
    )
    if not ok:
        raise HTTPException(404, "Submission not found.")
    db.ex("UPDATE a_sub SET reviewed=1 WHERE id=?", (sid,))
    return {"ok": True}


# ---- assessments
def _validate_questions(qs: list[QuestionIn]) -> None:
    for q in qs:
        if q.qtype == "multiple_choice" and len([o for o in q.options if o.strip()]) < 2:
            raise HTTPException(422, f"Multiple choice question needs at least 2 options: '{q.text[:40]}'")


@app.post("/assessments")
def create_assessment(body: AssessmentIn, doctor: dict = Depends(auth.doctor_only)):
    _validate_questions(body.questions)
    aid = db.ex(
        "INSERT INTO assessments (doctor_id, title, description, created_at) VALUES (?,?,?,?)",
        (doctor["id"], body.title.strip(), body.description.strip(), db.now()),
    )
    for i, q in enumerate(body.questions):
        opts = [o.strip() for o in q.options if o.strip()] if q.qtype == "multiple_choice" else []
        db.ex(
            "INSERT INTO questions (assessment_id, position, text, qtype, options) VALUES (?,?,?,?,?)",
            (aid, i, q.text.strip(), q.qtype, json.dumps(opts)),
        )
    return {"id": aid}


@app.get("/assessments")
def list_assessments(doctor: dict = Depends(auth.doctor_only)):
    rows = db.q("SELECT * FROM assessments WHERE doctor_id=? ORDER BY id DESC", (doctor["id"],))
    for r in rows:
        r["questions"] = _questions(r["id"])
    return rows


@app.post("/assessments/assign")
def assign_assessment(body: AssignAssessmentIn, doctor: dict = Depends(auth.doctor_only)):
    if not db.q("SELECT 1 FROM assessments WHERE id=? AND doctor_id=?", (body.assessment_id, doctor["id"])):
        raise HTTPException(404, "Assessment not found.")
    start = (body.start_date or _today()).isoformat()
    for pid in body.patient_ids:
        _my_patient(doctor, pid)
        db.ex(
            "INSERT INTO a_assign (assessment_id, patient_id, frequency, start_date, created_at) VALUES (?,?,?,?,?)",
            (body.assessment_id, pid, body.frequency, start, db.now()),
        )
    return {"assigned_to": len(body.patient_ids)}


# ---- goals
@app.post("/goals")
def create_goal(body: GoalIn, doctor: dict = Depends(auth.doctor_only)):
    gid = db.ex(
        "INSERT INTO goals (doctor_id, title, description, created_at) VALUES (?,?,?,?)",
        (doctor["id"], body.title.strip(), body.description.strip(), db.now()),
    )
    return {"id": gid}


@app.get("/goals")
def list_goals(doctor: dict = Depends(auth.doctor_only)):
    return db.q("SELECT * FROM goals WHERE doctor_id=? ORDER BY id DESC", (doctor["id"],))


@app.post("/goals/assign")
def assign_goal(body: AssignGoalIn, doctor: dict = Depends(auth.doctor_only)):
    if not db.q("SELECT 1 FROM goals WHERE id=? AND doctor_id=?", (body.goal_id, doctor["id"])):
        raise HTTPException(404, "Goal not found.")
    start = (body.start_date or _today()).isoformat()
    for pid in body.patient_ids:
        _my_patient(doctor, pid)
        db.ex(
            "INSERT INTO g_assign (goal_id, patient_id, frequency, start_date, created_at) VALUES (?,?,?,?,?)",
            (body.goal_id, pid, body.frequency, start, db.now()),
        )
    return {"assigned_to": len(body.patient_ids)}


# ---- AI
@app.post("/ai/generate-assessment")
def ai_generate(body: AiGenerateIn, doctor: dict = Depends(auth.doctor_only)):
    return ai.generate_assessment(body.topic, body.n)


# ============================================================ patient
@app.get("/my/assessments")
def my_assessments(patient: dict = Depends(auth.patient_only)):
    a = _assess_items(patient["id"], _today())
    return {"pending": a["pending"], "upcoming": a["upcoming"]}


@app.post("/my/assessments/submit")
def submit_assessment(body: SubmitIn, patient: dict = Depends(auth.patient_only)):
    rows = db.q(
        """SELECT a.*, t.title FROM a_assign a JOIN assessments t ON t.id = a.assessment_id
           WHERE a.id=? AND a.patient_id=?""",
        (body.assign_id, patient["id"]),
    )
    if not rows:
        raise HTTPException(404, "Assessment not found.")
    a = rows[0]
    dues = logic.due_dates(date.fromisoformat(a["start_date"]), a["frequency"], _today())
    if body.due_date not in dues:
        raise HTTPException(422, "This assessment is not due yet.")

    questions = _questions(a["assessment_id"])
    answers: dict[str, str] = {}
    for q in questions:
        v = body.answers.get(str(q["id"]))
        if q["qtype"] == "text":
            answers[str(q["id"])] = str(v or "").strip()
            continue
        if v in (None, ""):
            raise HTTPException(422, f"Please answer: {q['text']}")
        if q["qtype"] == "rating":
            try:
                n = int(v)
            except ValueError:
                raise HTTPException(422, "Ratings must be numbers from 1 to 5.")
            if not 1 <= n <= 5:
                raise HTTPException(422, "Ratings must be between 1 and 5.")
            answers[str(q["id"])] = str(n)
        else:
            if str(v) not in q["options"]:
                raise HTTPException(422, f"Invalid choice for: {q['text']}")
            answers[str(q["id"])] = str(v)

    qa = _qa(a["assessment_id"], answers)
    flagged = ai.safety_flag([str(x["answer"]) for x in qa if x["qtype"] == "text"])
    summary = ai.summarize(a["title"], qa)
    try:
        db.ex(
            """INSERT INTO a_sub (assign_id, due_date, submitted_at, answers, summary, flagged)
               VALUES (?,?,?,?,?,?)""",
            (a["id"], body.due_date.isoformat(), db.now(), json.dumps(answers), summary, int(flagged)),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(409, "You already submitted this one.")
    return {"ok": True}


@app.get("/my/assessments/history")
def my_assessment_history(patient: dict = Depends(auth.patient_only)):
    subs = db.q(
        """SELECT s.id, s.due_date, s.submitted_at, s.answers, a.assessment_id, a.frequency, t.title
           FROM a_sub s JOIN a_assign a ON a.id = s.assign_id
           JOIN assessments t ON t.id = a.assessment_id
           WHERE a.patient_id=? ORDER BY s.submitted_at DESC""",
        (patient["id"],),
    )
    return [{"id": s["id"], "title": s["title"], "frequency": s["frequency"], "due_date": s["due_date"],
             "submitted_at": s["submitted_at"],
             "answers": _qa(s["assessment_id"], json.loads(s["answers"]))} for s in subs]


@app.get("/my/goals")
def my_goals(patient: dict = Depends(auth.patient_only)):
    g = _goal_items(patient["id"], _today())
    return {"current": g["current"], "upcoming": g["upcoming"]}


@app.post("/my/goals/update")
def update_goal(body: GoalUpdateIn, patient: dict = Depends(auth.patient_only)):
    rows = db.q("SELECT * FROM g_assign WHERE id=? AND patient_id=?", (body.assign_id, patient["id"]))
    if not rows:
        raise HTTPException(404, "Goal not found.")
    g = rows[0]
    dues = logic.due_dates(date.fromisoformat(g["start_date"]), g["frequency"], _today())
    if body.due_date not in dues:
        raise HTTPException(422, "This goal is not due yet.")
    progress = 100 if body.completed else body.progress
    completed = 1 if (body.completed or progress >= 100) else 0
    existing = db.q("SELECT id FROM g_log WHERE assign_id=? AND due_date=?", (g["id"], body.due_date.isoformat()))
    if existing:
        db.ex("UPDATE g_log SET progress=?, completed=?, notes=?, updated_at=? WHERE id=?",
              (progress, completed, body.notes.strip(), db.now(), existing[0]["id"]))
    else:
        db.ex("INSERT INTO g_log (assign_id, due_date, progress, completed, notes, updated_at) VALUES (?,?,?,?,?,?)",
              (g["id"], body.due_date.isoformat(), progress, completed, body.notes.strip(), db.now()))
    return {"ok": True}


@app.get("/my/goals/history")
def my_goal_history(patient: dict = Depends(auth.patient_only)):
    return db.q(
        """SELECT l.due_date, l.progress, l.completed, l.notes, l.updated_at, t.title, g.frequency
           FROM g_log l JOIN g_assign g ON g.id = l.assign_id JOIN goals t ON t.id = g.goal_id
           WHERE g.patient_id=? ORDER BY l.due_date DESC, l.id DESC""",
        (patient["id"],),
    )


@app.get("/my/progress")
def my_progress(patient: dict = Depends(auth.patient_only)):
    today = _today()
    pid = patient["id"]
    a, g = _assess_items(pid, today), _goal_items(pid, today)
    submitted = db.q(
        "SELECT COUNT(*) AS n FROM a_sub s JOIN a_assign x ON x.id=s.assign_id WHERE x.patient_id=?", (pid,)
    )[0]["n"]
    goals_done = db.q(
        "SELECT COUNT(*) AS n FROM g_log l JOIN g_assign x ON x.id=l.assign_id WHERE x.patient_id=? AND l.completed=1",
        (pid,),
    )[0]["n"]
    notes = db.q(
        "SELECT COUNT(*) AS n FROM g_log l JOIN g_assign x ON x.id=l.assign_id WHERE x.patient_id=? AND l.notes<>''",
        (pid,),
    )[0]["n"]
    streaks = a["streaks"] + g["streaks"]
    best = max([s["streak"] for s in streaks], default=0)
    due = a["due_total"] + g["due_total"]
    done = a["done_total"] + g["done_total"]
    rate = round(100 * done / due) if due else 0
    badges = [
        ("leaf", "First Step", "Submit your first assessment", submitted >= 1),
        ("flame", "On a Roll", "Reach a 3-day streak", best >= 3),
        ("bolt", "Week Warrior", "Reach a 7-day streak", best >= 7),
        ("target", "Goal Getter", "Complete 5 goals", goals_done >= 5),
        ("pen", "Reflective", "Write 3 goal notes", notes >= 3),
        ("star", "Consistent", "80%+ completion (min. 5 tasks)", due >= 5 and rate >= 80),
    ]
    return {
        "points": submitted * 10 + goals_done * 5,
        "best_streak": best, "streaks": streaks, "completion_rate": rate,
        "badges": [{"icon": i, "name": n, "desc": d, "earned": e} for i, n, d, e in badges],
        "trend": _trend(pid),
    }


# ============================================================ wellness extras
class MoodIn(BaseModel):
    mood: int = Field(ge=1, le=5)
    note: str = Field(default="", max_length=300)


class JournalIn(BaseModel):
    text: str = Field(min_length=3, max_length=4000)
    source: Literal["typed", "voice"] = "typed"


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


def _month_range(month: Optional[str]) -> tuple[str, date, date]:
    today = _today()
    try:
        y, m = (int(x) for x in month.split("-")) if month else (today.year, today.month)
        first = date(y, m, 1)
    except (ValueError, AttributeError):
        raise HTTPException(400, "month must look like 2026-11")
    nxt = date(y + (m == 12), 1 if m == 12 else m + 1, 1)
    return first.strftime("%Y-%m"), first, nxt - timedelta(days=1)


def _mood_month(uid: int, month: Optional[str]) -> dict:
    key, first, last = _month_range(month)
    rows = db.q("SELECT day, mood, note FROM mood_log WHERE user_id=? AND day BETWEEN ? AND ? ORDER BY day",
                (uid, first.isoformat(), last.isoformat()))
    vals = [r["mood"] for r in rows]
    today = _today().isoformat()
    todays = db.q("SELECT mood, note FROM mood_log WHERE user_id=? AND day=?", (uid, today))
    return {
        "month": key, "first_weekday": first.weekday(), "days_in_month": last.day,
        "days": rows, "logged": len(rows),
        "average": round(sum(vals) / len(vals), 1) if vals else None,
        "today": todays[0] if todays else None,
    }


@app.post("/my/mood")
def log_mood(body: MoodIn, patient: dict = Depends(auth.patient_only)):
    day = _today().isoformat()
    db.ex(
        """INSERT INTO mood_log (user_id, day, mood, note, updated_at) VALUES (?,?,?,?,?)
           ON CONFLICT(user_id, day) DO UPDATE SET mood=excluded.mood, note=excluded.note, updated_at=excluded.updated_at""",
        (patient["id"], day, body.mood, body.note.strip(), db.now()),
    )
    crisis = ai.safety_flag([body.note])
    return {"day": day, "mood": body.mood, "label": ai.MOOD_LABELS[body.mood],
            "crisis": crisis, "help": ai.CRISIS_MESSAGE if crisis else ""}


@app.get("/my/mood")
def my_mood(month: Optional[str] = None, patient: dict = Depends(auth.patient_only)):
    return _mood_month(patient["id"], month)


@app.get("/patients/{pid}/mood")
def patient_mood(pid: int, month: Optional[str] = None, doctor: dict = Depends(auth.doctor_only)):
    _my_patient(doctor, pid)
    return _mood_month(pid, month)


@app.post("/my/journal")
def add_journal(body: JournalIn, patient: dict = Depends(auth.patient_only)):
    today = db.q("SELECT mood FROM mood_log WHERE user_id=? AND day=?", (patient["id"], _today().isoformat()))
    res = ai.reflect_journal(body.text.strip(), today[0]["mood"] if today else None)
    jid = db.ex(
        "INSERT INTO journal (user_id, created_at, text, source, reflection, flagged) VALUES (?,?,?,?,?,?)",
        (patient["id"], db.now(), body.text.strip(), body.source, res["reflection"], int(res["crisis"])),
    )
    return {"id": jid, **res}


@app.get("/my/journal")
def my_journal(patient: dict = Depends(auth.patient_only)):
    return db.q("SELECT id, created_at, text, source, reflection, flagged FROM journal "
                "WHERE user_id=? ORDER BY id DESC LIMIT 30", (patient["id"],))


@app.delete("/my/journal/{jid}")
def delete_journal(jid: int, patient: dict = Depends(auth.patient_only)):
    db.ex("DELETE FROM journal WHERE id=? AND user_id=?", (jid, patient["id"]))
    return {"ok": True}


@app.get("/my/companion")
def companion_history(patient: dict = Depends(auth.patient_only)):
    rows = db.q("SELECT role, content, created_at FROM chat_msgs WHERE user_id=? ORDER BY id DESC LIMIT 40",
                (patient["id"],))
    return {"messages": rows[::-1], "mode": ai.mode()}


@app.post("/my/companion")
def companion_send(body: ChatIn, patient: dict = Depends(auth.patient_only)):
    uid = patient["id"]
    hist = db.q("SELECT role, content FROM chat_msgs WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,))[::-1]
    mood = db.q("SELECT mood FROM mood_log WHERE user_id=? ORDER BY day DESC LIMIT 1", (uid,))
    ctx = f"first name {patient['name'].split()[0]}" + (f"; last logged mood: {ai.MOOD_LABELS[mood[0]['mood']]}" if mood else "")
    res = ai.companion_reply(hist, body.message.strip(), ctx)
    db.ex("INSERT INTO chat_msgs (user_id, role, content, created_at) VALUES (?,?,?,?)",
          (uid, "user", body.message.strip(), db.now()))
    db.ex("INSERT INTO chat_msgs (user_id, role, content, created_at) VALUES (?,?,?,?)",
          (uid, "assistant", res["reply"], db.now()))
    return res


@app.delete("/my/companion")
def companion_clear(patient: dict = Depends(auth.patient_only)):
    db.ex("DELETE FROM chat_msgs WHERE user_id=?", (patient["id"],))
    return {"ok": True}


@app.get("/my/reminders")
def my_reminders(patient: dict = Depends(auth.patient_only)):
    """Smart reminders worked out from the patient's own data each time the app opens (rule-based)."""
    today, pid = _today(), patient["id"]
    a, g = _assess_items(pid, today), _goal_items(pid, today)
    open_goals = [x for x in g["current"] if not x["completed"]]
    out = []
    streak_items = [s for s in a["streaks"] + g["streaks"] if s["streak"] >= 2]
    todo = len(a["pending"]) + len(open_goals)
    if todo and streak_items:
        best = max(streak_items, key=lambda s: s["streak"])
        out.append({"tone": "sun", "icon": "flame", "title": "Protect your streak",
                    "text": f"{best['title']} is on a {best['streak']} day streak. Finish today's tasks to keep it."})
    if a["pending"]:
        out.append({"tone": "forest", "icon": "clipboard", "title": f"{len(a['pending'])} assessment(s) due",
                    "text": ", ".join(x["title"] for x in a["pending"][:2]) + ". It takes a couple of minutes."})
    if open_goals:
        out.append({"tone": "leaf", "icon": "target", "title": f"{len(open_goals)} goal(s) to log",
                    "text": ", ".join(x["title"] for x in open_goals[:2]) + "."})
    if not db.q("SELECT 1 FROM mood_log WHERE user_id=? AND day=?", (pid, today.isoformat())):
        out.append({"tone": "teal", "icon": "heart", "title": "How are you feeling today?",
                    "text": "Add today's mood to your calendar. One tap is enough."})
    last_j = db.q("SELECT created_at FROM journal WHERE user_id=? ORDER BY id DESC LIMIT 1", (pid,))
    if last_j and (today - date.fromisoformat(last_j[0]["created_at"][:10])).days >= 3:
        out.append({"tone": "lime", "icon": "pen", "title": "A moment to write",
                    "text": "You have not journaled for a few days. Even two lines help."})
    miss = a["missed7"] + g["missed7"]
    if miss >= 3:
        out.append({"tone": "coral", "icon": "alert", "title": "A few tasks slipped this week",
                    "text": f"{miss} missed in the last 7 days. Start with one small task today."})
    return {"reminders": out, "count": len(out)}
