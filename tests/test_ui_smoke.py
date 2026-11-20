"""Smoke test: log in as each demo user and click through every page with Streamlit's AppTest.

Run:  python tests/test_ui_smoke.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "ui.db")
os.environ["BACKEND_PORT"] = "8791"
os.environ.pop("ANTHROPIC_API_KEY", None)

from streamlit.testing.v1 import AppTest  # noqa: E402


def login(at: AppTest, email: str, pw: str) -> AppTest:
    at.text_input[0].set_value(email)
    at.text_input[1].set_value(pw)
    at.button[0].click().run()
    assert not at.exception, at.exception
    assert at.session_state["user"]["email"] == email
    return at


def visit(at: AppTest, pages: list[str]):
    for p in pages:
        at.radio(key="nav").set_value(p).run()
        assert not at.exception, (p, at.exception)
        assert not at.error, (p, [e.value for e in at.error])
        print("  ok:", p)


def main():
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60).run()
    assert not at.exception, at.exception
    print("login page ok")

    print("doctor")
    d = login(at, "dr.meera@demo.com", "Doctor@123")
    visit(d, ["Patients", "Assessments", "Goals", "Assign", "Overview"])

    print("patient (Riya)")
    p = login(AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60).run(), "riya@demo.com", "Patient@123")
    visit(p, ["Assessments", "Goals", "Wellness", "Progress", "Home"])

    print("wellness actions (Riya)")
    p.radio(key="nav").set_value("Wellness").run()
    assert not p.exception, p.exception
    p.radio(key="mood_pick").set_value("Good")
    p.button(key="mood_save").click().run()
    assert not p.exception and not p.error, (p.exception, [e.value for e in p.error])
    p.text_area(key="jr_text").set_value("A calm walk today helped me relax.")
    p.button(key="jr_save").click().run()
    assert not p.exception and not p.error, (p.exception, [e.value for e in p.error])
    p.text_input(key="chat_in").set_value("I feel stressed about exams")
    print("  ok: mood, journal")

    print("patient (Kabir)")
    k = login(AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60).run(), "kabir@demo.com", "Patient@123")
    visit(k, ["Assessments", "Goals", "Wellness", "Progress", "Home"])
    print("UI SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
