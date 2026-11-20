"""End-to-end test of the 10-step workflow from the project brief.

Run:  python -m pytest -q   (or)   python tests/test_workflow.py
"""
import os
import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ.pop("ANTHROPIC_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402


def H(token):
    return {"Authorization": f"Bearer {token}"}


def run():
    with TestClient(app) as c:
        # 1. register doctor
        r = c.post("/register", json={"role": "doctor", "name": "Dr Test", "email": "doc@t.com",
                                      "password": "secret1", "specialization": "Psych"})
        assert r.status_code == 200, r.text
        doc, doc_id = r.json()["token"], r.json()["user"]["id"]

        # 3. patient must pick a doctor
        r = c.post("/register", json={"role": "patient", "name": "Pat One", "email": "pat@t.com", "password": "secret1"})
        assert r.status_code == 422
        docs = c.get("/doctors").json()
        assert any(d["id"] == doc_id for d in docs)

        # 2/3/4. register patient with doctor -> auto connected
        r = c.post("/register", json={"role": "patient", "name": "Pat One", "email": "pat@t.com",
                                      "password": "secret1", "doctor_id": doc_id, "age": 30})
        assert r.status_code == 200, r.text
        pat, pat_id = r.json()["token"], r.json()["user"]["id"]
        assert r.json()["user"]["doctor"]["id"] == doc_id
        assert [p["id"] for p in c.get("/patients", headers=H(doc)).json()] == [pat_id]

        # duplicate email, wrong password, role guards
        assert c.post("/register", json={"role": "doctor", "name": "X Y", "email": "DOC@t.com", "password": "secret1"}).status_code == 409
        assert c.post("/login", json={"email": "doc@t.com", "password": "nope"}).status_code == 401
        assert c.get("/patients", headers=H(pat)).status_code == 403

        # 9. AI generation (offline fallback here)
        gen = c.post("/ai/generate-assessment", json={"topic": "stress and sleep quality", "n": 5}, headers=H(doc)).json()
        assert len(gen["questions"]) == 5 and gen["source"] == "offline-demo"
        types = {q["qtype"] for q in gen["questions"]}
        assert {"rating", "multiple_choice", "text"} <= types

        # 5. assessments + goals
        aid = c.post("/assessments", json={"title": gen["title"], "description": gen["description"],
                                           "questions": gen["questions"]}, headers=H(doc)).json()["id"]
        assert c.post("/assessments", json={"title": "Bad one", "questions": [
            {"text": "Pick one", "qtype": "multiple_choice", "options": ["only"]}]}, headers=H(doc)).status_code == 422
        gid = c.post("/goals", json={"title": "Walk 20 minutes"}, headers=H(doc)).json()["id"]

        # 6. recurring: daily assessment starting 3 days ago, weekly goal, once assessment
        three_ago = (date.today() - timedelta(days=3)).isoformat()
        assert c.post("/assessments/assign", json={"assessment_id": aid, "patient_ids": [pat_id],
                      "frequency": "daily", "start_date": three_ago}, headers=H(doc)).status_code == 200
        assert c.post("/goals/assign", json={"goal_id": gid, "patient_ids": [pat_id],
                      "frequency": "daily"}, headers=H(doc)).status_code == 200
        assert c.post("/assessments/assign", json={"assessment_id": aid, "patient_ids": [9999],
                      "frequency": "once"}, headers=H(doc)).status_code == 404

        # 7. patient sees ONE pending (today's) daily instance and a goal
        mine = c.get("/my/assessments", headers=H(pat)).json()
        assert len(mine["pending"]) == 1
        assert mine["pending"][0]["due_date"] == date.today().isoformat()
        assert mine["upcoming"][0]["due_date"] == (date.today() + timedelta(days=1)).isoformat()
        p = mine["pending"][0]

        # validation: missing answers
        bad = c.post("/my/assessments/submit", json={"assign_id": p["assign_id"], "due_date": p["due_date"],
                     "answers": {}}, headers=H(pat))
        assert bad.status_code == 422

        answers = {}
        for q in p["questions"]:
            answers[str(q["id"])] = (3 if q["qtype"] == "rating" else q["options"][0] if q["qtype"] == "multiple_choice"
                                     else "I feel hopeless lately")
        ok = c.post("/my/assessments/submit", json={"assign_id": p["assign_id"], "due_date": p["due_date"],
                    "answers": answers}, headers=H(pat))
        assert ok.status_code == 200, ok.text
        assert c.post("/my/assessments/submit", json={"assign_id": p["assign_id"], "due_date": p["due_date"],
                      "answers": answers}, headers=H(pat)).status_code == 409
        assert c.get("/my/assessments", headers=H(pat)).json()["pending"] == []
        # not-yet-due date rejected
        future = (date.today() + timedelta(days=2)).isoformat()
        assert c.post("/my/assessments/submit", json={"assign_id": p["assign_id"], "due_date": future,
                      "answers": answers}, headers=H(pat)).status_code == 422

        goals = c.get("/my/goals", headers=H(pat)).json()["current"]
        assert len(goals) == 1 and not goals[0]["completed"]
        g = goals[0]
        assert c.post("/my/goals/update", json={"assign_id": g["assign_id"], "due_date": g["due_date"],
                      "progress": 50, "notes": "halfway"}, headers=H(pat)).status_code == 200
        assert c.get("/my/goals", headers=H(pat)).json()["current"][0]["progress"] == 50
        assert c.post("/my/goals/update", json={"assign_id": g["assign_id"], "due_date": g["due_date"],
                      "progress": 50, "completed": True, "notes": "done!"}, headers=H(pat)).status_code == 200
        assert c.get("/my/goals/history", headers=H(pat)).json()[0]["completed"] == 1

        prog = c.get("/my/progress", headers=H(pat)).json()
        assert prog["points"] == 15 and prog["badges"][0]["earned"]

        # 8/10. doctor sees progress, summary, safety flag
        detail = c.get(f"/patients/{pat_id}", headers=H(doc)).json()
        sub = detail["submissions"][0]
        assert sub["summary"] and sub["flagged"] and not sub["reviewed"]
        assert detail["overview"]["needs_attention"] and detail["overview"]["flagged"] == 1
        assert detail["goal_history"][0]["notes"] == "done!"
        assert c.post(f"/submissions/{sub['id']}/review", headers=H(doc)).status_code == 200
        assert c.get(f"/patients/{pat_id}", headers=H(doc)).json()["overview"]["flagged"] == 0

        rep = c.post(f"/patients/{pat_id}/weekly-report", headers=H(doc)).json()
        assert rep["report"]

        # another doctor cannot see this patient
        r2 = c.post("/register", json={"role": "doctor", "name": "Dr Two", "email": "d2@t.com", "password": "secret1"})
        assert c.get(f"/patients/{pat_id}", headers=H(r2.json()["token"])).status_code == 404

        # seeded demo accounts exist and work
        for email, pw in (("dr.meera@demo.com", "Doctor@123"), ("riya@demo.com", "Patient@123"),
                          ("kabir@demo.com", "Patient@123")):
            assert c.post("/login", json={"email": email, "password": pw}).status_code == 200
        dm = c.post("/login", json={"email": "dr.meera@demo.com", "password": "Doctor@123"}).json()["token"]
        ov = {p["name"]: p for p in c.get("/patients", headers=H(dm)).json()}
        assert not ov["Riya Patel"]["needs_attention"], ov["Riya Patel"]
        assert ov["Kabir Mehta"]["needs_attention"], ov["Kabir Mehta"]
        rp = c.post("/login", json={"email": "riya@demo.com", "password": "Patient@123"}).json()["token"]
        pr = c.get("/my/progress", headers=H(rp)).json()
        assert pr["best_streak"] >= 7 and len(pr["trend"]) > 10, pr["best_streak"]
        print("ALL CHECKS PASSED")


if __name__ == "__main__":
    run()


def test_workflow():
    run()
