"""Generative AI helpers (Anthropic Claude API).

If ANTHROPIC_API_KEY is not set, or a call fails, every function falls back to a
simple offline version so the app (and your demo) never breaks.
"""
import json
import os
import re

DISCLAIMER = (
    "AI-generated summary for information only. It is not a medical diagnosis "
    "and not a treatment decision. The doctor should always review the original answers."
)

QTYPES = {"multiple_choice", "rating", "text"}

# Words that make us mark a response "needs doctor review". Deliberately simple and transparent.
SAFETY_PATTERNS = [
    r"hopeless", r"worthless", r"no reason to live", r"end it all", r"kill myself",
    r"suicid", r"self[- ]?harm", r"hurt myself", r"can'?t go on", r"give up on (life|everything)",
    r"don'?t want to (live|be here)", r"want to die",
]


def model() -> str:
    return os.getenv("AI_MODEL", "claude-sonnet-5-5")


def mode() -> str:
    return "claude" if os.getenv("ANTHROPIC_API_KEY") else "offline-demo"


def _ask(system: str, user: str, max_tokens: int = 1500) -> str:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("no API key")
    import anthropic

    client = anthropic.Anthropic(api_key=key)
    resp = client.messages.create(
        model=model(),
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()


def _json_from(text: str):
    m = re.search(r"(\{.*\}|\[.*\])", text, re.S)
    if not m:
        raise ValueError("no JSON in reply")
    return json.loads(m.group(1))


# ---------------------------------------------------------------- safety flag
def safety_flag(texts: list[str]) -> bool:
    blob = " ".join(texts).lower()
    return any(re.search(p, blob) for p in SAFETY_PATTERNS)


# ------------------------------------------------- A. assessment generation
def _clean_questions(raw: list, limit: int) -> list[dict]:
    out = []
    for item in raw:
        text = str(item.get("text", "")).strip()
        qtype = item.get("qtype", "text")
        if not text or qtype not in QTYPES:
            continue
        options = [str(o).strip() for o in item.get("options", []) if str(o).strip()]
        if qtype == "multiple_choice" and len(options) < 2:
            continue
        out.append({"text": text, "qtype": qtype, "options": options if qtype == "multiple_choice" else []})
    return out[:limit]


_LEAD_IN = re.compile(
    r"^\s*(please\s+)?((create|make|generate|build|design|write)\s+)?(an?\s+)?"
    r"((assessment|questionnaire|survey|quiz|check-?in)\s+)?"
    r"((to|for|about|on|that)\s+)?"
    r"((understand|assess|measure|check|track|evaluate|know|learn about|explore)\s+)?"
    r"((a|the|my|their|our)\s+)?(patient'?s?\s+)?",
    re.I,
)


def _topic_from(text: str) -> str:
    """'Create an assessment to understand a patient's stress and sleep quality' -> 'stress and sleep quality'."""
    t = _LEAD_IN.sub("", text.strip()).strip().rstrip(".?! ")
    return t or text.strip().rstrip(".?! ") or "your wellbeing"


def _offline_questions(topic: str, n: int) -> dict:
    t = _topic_from(topic)
    pool = [
        {"text": f"Over the past week, how would you rate your overall {t}? (1 = very poor, 5 = excellent)",
         "qtype": "rating", "options": []},
        {"text": f"How often did {t} affect your daily activities this week?", "qtype": "multiple_choice",
         "options": ["Never", "Rarely", "Sometimes", "Often", "Almost every day"]},
        {"text": f"Describe anything that made {t} better or worse this week.", "qtype": "text", "options": []},
        {"text": "How rested did you feel when you woke up most days? (1 = not at all, 5 = fully rested)",
         "qtype": "rating", "options": []},
        {"text": "How many hours did you usually sleep each night?", "qtype": "multiple_choice",
         "options": ["Less than 4", "4-6", "6-8", "More than 8"]},
        {"text": "How stressed did you feel on a typical day? (1 = calm, 5 = very stressed)", "qtype": "rating", "options": []},
        {"text": "Is there anything you would like your doctor to know before the next visit?", "qtype": "text", "options": []},
    ]
    return {"title": f"{t[:1].upper() + t[1:60]} Assessment", "description": f"Check-in about {t}.",
            "questions": pool[:n]}


def generate_assessment(topic: str, n: int = 6) -> dict:
    n = max(3, min(n, 10))
    system = (
        "You help doctors design short wellness questionnaires. "
        "Reply with JSON only, no extra text, in this exact shape: "
        '{"title": str, "description": str, "questions": [{"text": str, '
        '"qtype": "multiple_choice" | "rating" | "text", "options": [str]}]}. '
        "Rating questions use a 1-5 scale (say so in the question text, options empty). "
        "Multiple choice questions need 3-5 options. Mix the three types. "
        "Use warm, plain, non-clinical language. Never ask the patient to self-diagnose."
    )
    try:
        data = _json_from(_ask(system, f"Topic or objective: {topic}\nNumber of questions: {n}"))
        qs = _clean_questions(data.get("questions", []), n)
        if not qs:
            raise ValueError("no valid questions")
        return {"title": str(data.get("title", "New assessment"))[:100],
                "description": str(data.get("description", ""))[:300],
                "questions": qs, "source": "claude"}
    except Exception:
        res = _offline_questions(topic, n)
        res["source"] = "offline-demo"
        return res


# ----------------------------------------------------- B. response summary
def _rating_values(qa: list[dict]) -> list[int]:
    vals = []
    for x in qa:
        if x["qtype"] == "rating":
            try:
                vals.append(int(x["answer"]))
            except (TypeError, ValueError):
                pass
    return vals


def offline_summary(title: str, qa: list[dict]) -> str:
    ratings = _rating_values(qa)
    parts = [f"The patient completed '{title}'."]
    if ratings:
        avg = sum(ratings) / len(ratings)
        parts.append(f"Rating answers averaged {avg:.1f} out of 5 (lowest {min(ratings)}, highest {max(ratings)}).")
    for x in qa:
        if x["qtype"] == "multiple_choice" and x["answer"]:
            parts.append(f"On \"{x['question']}\" they chose \"{x['answer']}\".")
    texts = [str(x["answer"]).strip() for x in qa if x["qtype"] == "text" and str(x["answer"]).strip()]
    if texts:
        parts.append("In their own words: " + " / ".join(t[:160] for t in texts))
    return " ".join(parts)


def summarize(title: str, qa: list[dict]) -> str:
    system = (
        "You summarise a patient's questionnaire answers for their doctor. "
        "Write 3 to 5 plain sentences, then one line starting 'Worth a look:' naming any answers that stand out. "
        "Be strictly informational. Describe what the patient reported using neutral wording like 'reported' or 'rated'. "
        "NEVER diagnose, name medical conditions, suggest causes, or recommend treatment, medication or next medical steps. "
        "Do not invent anything that is not in the answers."
    )
    lines = "\n".join(f"- ({x['qtype']}) {x['question']} -> {x['answer']}" for x in qa)
    try:
        return _ask(system, f"Assessment: {title}\nAnswers:\n{lines}", 600)
    except Exception:
        return offline_summary(title, qa)


# ------------------------------------------------------ weekly progress report
def weekly_report(patient: str, facts: dict) -> dict:
    """facts: plain numbers computed by the backend; AI only words them nicely."""
    system = (
        "You write a short weekly progress note for a doctor about one patient, using ONLY the facts given. "
        "4 to 6 sentences. Mention trends in ratings, goal completion and missed tasks. "
        "NEVER diagnose, name conditions, or recommend treatment. Neutral, factual tone."
    )
    try:
        text = _ask(system, f"Patient: {patient}\nFacts (JSON):\n{json.dumps(facts, indent=2)}", 500)
        return {"report": text, "source": "claude"}
    except Exception:
        bits = [f"Weekly overview for {patient}."]
        if facts.get("avg_rating_this_week") is not None:
            bits.append(f"Average rating this week: {facts['avg_rating_this_week']} out of 5"
                        + (f" (previous period: {facts['avg_rating_before']})." if facts.get("avg_rating_before") is not None else "."))
        bits.append(f"Assessments submitted: {facts['assessments_done_7d']}. Goals completed: {facts['goals_done_7d']}.")
        bits.append(f"Missed tasks in the last 7 days: {facts['missed_7d']}.")
        if facts.get("flagged_unreviewed"):
            bits.append(f"{facts['flagged_unreviewed']} response(s) are flagged for doctor review.")
        return {"report": " ".join(bits), "source": "offline-demo"}



# ======================================================= WELLNESS EXTRAS
CRISIS_MESSAGE = (
    "I am really sorry you are feeling this way, and I am glad you said it. You deserve support from a real person right now. "
    "If you might hurt yourself or are in immediate danger, call your local emergency number (112 in India) now. "
    "You can also call Tele-MANAS, India's free 24x7 mental health helpline, on 14416 (or 1800-891-4416). "
    "Please also tell someone you trust, or your doctor, how you feel today."
)

COMPANION_DISCLAIMER = (
    "The companion is an AI for general wellness support. It is not a doctor or therapist and cannot diagnose or treat anything."
)

MOOD_LABELS = {1: "Very low", 2: "Low", 3: "Okay", 4: "Good", 5: "Great"}


def _ask_chat(system: str, messages: list[dict], max_tokens: int = 400) -> str:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("no API key")
    import anthropic

    client = anthropic.Anthropic(api_key=key)
    resp = client.messages.create(model=model(), max_tokens=max_tokens, system=system, messages=messages)
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()


def _offline_companion(text: str) -> str:
    t = text.lower()
    if re.search(r"stress|anxious|anxiety|worried|nervous|overwhelm|panic", t):
        return ("That sounds heavy. Try a slow breath right now: in for 4 counts, hold for 4, out for 6, a few times. "
                "What is the one thing worrying you most at the moment?")
    if re.search(r"sleep|tired|insomnia|exhaust", t):
        return ("Being tired makes everything harder. A steady bedtime, no screens for the last 30 minutes and a short walk "
                "in daylight can help. How have your nights been this week?")
    if re.search(r"sad|low|down|lonely|cry", t):
        return ("I am sorry it feels like that. Small steps count: a glass of water, fresh air, or a message to someone you "
                "like. Would you like to tell me what happened today?")
    if re.search(r"happy|good|great|proud|better|excited", t):
        return "That is lovely to hear. What helped today go well? Noticing it makes it easier to repeat."
    return ("Thank you for sharing that. I am here to listen. Tell me a little more about how your day has been, "
            "or try one slow breath and tell me what you notice.")


def companion_reply(history: list[dict], text: str, context: str = "") -> dict:
    """history: [{role, content}] oldest first. Returns {reply, source, crisis}."""
    if safety_flag([text]):
        return {"reply": CRISIS_MESSAGE, "source": "safety-rule", "crisis": True}
    system = (
        "You are SERENX Companion, a warm, calm wellness companion inside a doctor-patient wellness app. "
        "Reply in 2 to 4 short sentences, plain language, and end with one gentle question or one tiny suggestion. "
        "You may offer simple, general wellbeing ideas such as slow breathing, a short walk, a regular sleep routine, "
        "writing thoughts down or talking to someone trusted. "
        "NEVER diagnose, name medical or mental health conditions, suggest causes, or mention medicines or doses. "
        "You are not a doctor or therapist and do not claim to be. "
        "If the person asks for medical advice, say their doctor is the right person and encourage them to bring it up. "
        "If they mention thoughts of self-harm, stop and urge them to contact emergency services or a helpline. "
        + (f"Background facts about the person (use lightly, never list them): {context}" if context else "")
    )
    msgs = [{"role": m["role"], "content": m["content"]} for m in history[-10:]]
    msgs.append({"role": "user", "content": text})
    try:
        return {"reply": _ask_chat(system, msgs), "source": "claude", "crisis": False}
    except Exception:
        return {"reply": _offline_companion(text), "source": "offline-demo", "crisis": False}


def reflect_journal(text: str, mood: int | None = None) -> dict:
    """A short, kind reflection on a journal entry. Never diagnoses."""
    if safety_flag([text]):
        return {"reflection": CRISIS_MESSAGE, "source": "safety-rule", "crisis": True}
    system = (
        "You read one private journal entry and reply to the writer in 2 to 3 warm sentences: reflect back what they "
        "seem to be feeling or valuing, name one positive or one small step, then add one gentle question to think about. "
        "NEVER diagnose, name conditions, suggest causes, or give medical advice or medication information. "
        "Do not invent details that are not in the entry."
    )
    try:
        extra = f"\n(Mood they logged today: {MOOD_LABELS.get(mood)})" if mood else ""
        return {"reflection": _ask(system, f"Journal entry:\n{text}{extra}", 300), "source": "claude", "crisis": False}
    except Exception:
        words = len(text.split())
        t = text.lower()
        if re.search(r"stress|anxious|worried|overwhelm|tired|sad|lonely", t):
            r = ("It sounds like today asked a lot of you. Writing it down is already a kind step. "
                 "What is one small thing that could make tomorrow a little lighter?")
        elif re.search(r"happy|grateful|proud|good|great|calm|enjoy", t):
            r = ("There is a lot of warmth in this entry. Noticing what went well helps you find it again. "
                 "What would you like to repeat this week?")
        else:
            r = (f"Thank you for taking a moment to write ({words} words). Putting thoughts on paper can make them easier to hold. "
                 "What stood out most to you as you wrote this?")
        return {"reflection": r, "source": "offline-demo", "crisis": False}
