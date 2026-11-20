"""Tests for mood calendar, journal, companion, reminders. Run: python tests/test_wellness.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "w.db")
os.environ.pop("ANTHROPIC_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402


def login(c, email, pw):
    r = c.post("/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


with TestClient(app) as c:
    p = login(c, "riya@demo.com", "Patient@123")
    d = login(c, "dr.meera@demo.com", "Doctor@123")

    m = c.get("/my/mood", headers=p).json()
    assert m["logged"] > 5 and m["average"], m            # seeded history
    r = c.post("/my/mood", headers=p, json={"mood": 4, "note": "good"}).json()
    assert r["label"] == "Good" and not r["crisis"]
    assert c.get("/my/mood", headers=p).json()["today"]["mood"] == 4
    c.post("/my/mood", headers=p, json={"mood": 2})        # update same day, no duplicate
    assert c.get("/my/mood", headers=p).json()["today"]["mood"] == 2
    assert c.post("/my/mood", headers=p, json={"mood": 9}).status_code == 422
    assert c.get("/my/mood?month=bad", headers=p).status_code == 400
    assert c.get("/my/mood", headers=d).status_code == 403  # doctors cannot use patient endpoints

    # doctor sees only own patients
    pts = c.get("/patients", headers=d).json()
    assert c.get(f"/patients/{pts[0]['id']}/mood", headers=d).json()["days"]
    other = login(c, "dr.arjun@demo.com", "Doctor@123")
    assert c.get(f"/patients/{pts[0]['id']}/mood", headers=other).status_code == 404

    j = c.post("/my/journal", headers=p, json={"text": "I felt stressed but a walk helped.", "source": "voice"}).json()
    assert j["reflection"] and not j["crisis"]
    j2 = c.post("/my/journal", headers=p, json={"text": "I feel hopeless today"}).json()
    assert j2["crisis"] and "14416" in j2["reflection"]
    assert len(c.get("/my/journal", headers=p).json()) >= 3
    assert c.get("/my/journal", headers=d).status_code == 403

    a = c.post("/my/companion", headers=p, json={"message": "I am anxious about work"}).json()
    assert a["reply"] and not a["crisis"]
    b = c.post("/my/companion", headers=p, json={"message": "i want to die"}).json()
    assert b["crisis"] and "112" in b["reply"]
    assert len(c.get("/my/companion", headers=p).json()["messages"]) == 4
    c.delete("/my/companion", headers=p)
    assert c.get("/my/companion", headers=p).json()["messages"] == []

    rem = c.get("/my/reminders", headers=p).json()
    assert rem["count"] == len(rem["reminders"]) and rem["reminders"]
    k = login(c, "kabir@demo.com", "Patient@123")
    assert any("feeling" in x["title"].lower() for x in c.get("/my/reminders", headers=k).json()["reminders"])
print("WELLNESS CHECKS PASSED")
