# SERENX: Your Wellness, Our Priority.

*Personalized care for a healthier tomorrow.*

A doctor–patient wellness platform.

A web app where doctors assign **assessments** and **wellness goals** to their patients, patients complete them and track progress, and **Generative AI** helps doctors create assessments and understand responses.

Built with **Python · FastAPI · Streamlit · SQLite · Claude API**.

- Live app: `<add your Streamlit URL>`
- Demo video: `<add your video link>`

## New wellness features (patient app, Wellness tab)

- **Mood calendar**: log one mood a day (Very low to Great) with an optional note. A colour-coded month calendar shows patterns. The doctor sees each patient's calendar in Patients, Progress.
- **Voice wellness journal**: speak (English, Hindi or Gujarati, using the browser's speech recognition in Chrome or Edge) or type. AI returns a short, kind reflection. Entries are private from the doctor.
- **AI wellness companion**: a supportive chat for general wellbeing. It never diagnoses or mentions medicine, and it tells the person to see their doctor for medical questions.
- **Smart reminders**: shown on Home when the app opens, worked out from the patient's own data (streak at risk, tasks due, no mood logged, no journal for 3 days, missed tasks). They are rule-based and in-app only. Email or push messages would need a scheduler or paid service.
- **Safety**: if a journal entry, note or chat message contains worrying words, the AI is skipped and a fixed message with emergency (112) and Tele-MANAS (14416) numbers is shown.

Test: `python tests/test_wellness.py`

## Demo accounts (dummy data only)

| Role | Email | Password |
|---|---|---|
| Doctor | `dr.meera@demo.com` | `Doctor@123` |
| Patient (doing well) | `riya@demo.com` | `Patient@123` |
| Patient (needs attention) | `kabir@demo.com` | `Patient@123` |

## Features

**Required**
- Doctor and patient registration. Patients pick a doctor from a list and are connected automatically.
- Doctor dashboard: connected patients, patient profiles, create assessments (multiple choice, 1–5 rating, text) and goals, assign to one or many patients, set frequency (one-time / daily / weekly / monthly), view submissions, responses and goal history.
- Patient dashboard: connected doctor, pending assessments, goals with progress / completion / notes, upcoming items, full history.
- **AI assessment creation**: describe a topic, AI writes the questions, the doctor edits and saves.
- **AI assessment summary**: every submission gets an informational summary shown beside the original answers. The prompt forbids diagnosis and treatment advice, and a disclaimer is shown on screen.

**Extras**
- **Mobile-app style forest-green design**: floating bottom navigation, progress card, insight banner, daily plan timeline and line icons. It works on phones and desktops.
- **Streaks and badges** for patients, plus points.
- **Mood trend chart** built from rating answers (patient and doctor views).
- **"Needs attention" panel** for doctors: missed tasks, low ratings, flagged responses.
- **Safety flag**: written answers with worrying words (for example "hopeless") are marked for doctor review until the doctor clicks *Mark as reviewed*.
- **AI weekly progress report** per patient, written only from computed facts.

## Run it locally

```bash
git clone <your-repo-url>
cd wellness-platform
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# optional, for real AI (the app also works without it in offline demo mode)
export ANTHROPIC_API_KEY="your-key"                     # Windows: set ANTHROPIC_API_KEY=your-key

streamlit run app.py
```

Open http://localhost:8501. The FastAPI backend starts automatically inside the same process, and demo data is created on first run.
API docs (while running): http://127.0.0.1:8765/docs

Run the end-to-end test: `python tests/test_workflow.py`

## Deploy on Streamlit Community Cloud (free)

1. Push this folder to a **public GitHub repo** (the `.gitignore` already keeps keys and the database out).
2. Go to share.streamlit.io, click **New app**, pick the repo, main file `app.py`.
3. In **Advanced settings → Secrets** paste:
   ```toml
   ANTHROPIC_API_KEY = "your-key"
   AI_MODEL = "claude-sonnet-5-5"
   ```
4. Deploy and copy the public URL.

Note: free Streamlit hosting resets the SQLite file when the app restarts, so demo data is re-created automatically. Accounts you register during a demo may disappear after a restart.

## How to use (the 10-step workflow)

1. **Register as a doctor**: *Register as doctor* tab.
2. **Register as a patient**: *Register as patient* tab.
3. **Select a doctor**: choose from the list in step 1 of patient registration.
4. **Auto-connected**: log in as the doctor → Patients shows the new patient.
5. **Assign work**: Assessments → create one (or use AI), Goals → create one, then Assign.
6. **Recurring**: pick *Daily / Weekly / Monthly* when assigning.
7. **Patient completes**: log in as the patient → Assessments and Goals.
8. **Progress**: back as the doctor → Overview and Patients show progress, charts and history.
9. **AI assessment**: Assessments → type a topic → *Generate questions*.
10. **AI summary**: open any submission as the doctor to see the AI summary beside the original answers.

## How recurring assignments work

There is no background scheduler. Each assignment stores a **frequency** and **start date**. When a page loads, the backend calculates which due dates have arrived (`backend/logic.py`). The newest due date with no submission shows as *pending*, earlier unfinished ones count as *missed*. This is simple and keeps working on free hosting that sleeps.

## Project structure

```
app.py              Streamlit UI (starts the backend automatically)
backend/
  main.py           FastAPI endpoints
  db.py             SQLite schema and helpers
  auth.py           password hashing + token sessions
  logic.py          recurrence and streak logic
  ai.py             Claude prompts + offline fallback
  seed.py           dummy demo data
tests/test_workflow.py   end-to-end test of the full workflow
```

## Safety notes

- AI output is informational only. Prompts forbid diagnosis and treatment advice, and the UI shows a disclaimer.
- No real patient data: use dummy data only. API keys live in environment variables or Streamlit secrets, never in the repo.
- The keyword safety flag is a simple aid, not a clinical tool.
