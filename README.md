---
title: StoryBook AI
emoji: 📚
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: mit
full_width: true
short_description: AI-powered personalized children's story generator
---

# 📚 StoryBook AI

**StoryBook AI** is a personalized AI children's story platform. Parents and children co-create magical stories by selecting characters, settings, themes, and moral lessons — the AI weaves them into a unique, age-appropriate narrative. An adaptive machine-learning engine then tracks each child's reading behaviour and continuously personalises story complexity, vocabulary richness, and quiz challenge to keep every reading session in the *optimal learning zone*.

🔗 **Live demo:** [huggingface.co/spaces/hengds2f/storybook](https://huggingface.co/spaces/hengds2f/storybook)

---

## ✨ Features

### 📖 Story Creation
- 🎭 **Story Parameter Builder** — Choose characters, traits, settings, themes & moral lessons
- 📐 **Age-Adaptive Storytelling** — Vocabulary and complexity tuned for ages 3–5, 6–8, or 9–12
- 🏰 **Structured Narrative Arc** — Introduction → Challenge → Resolution → Moral → Poem
- ⚡ **Async Generation** — Background task with live progress bar; shows *"About 40–60 seconds remaining…"* time hints instead of raw status messages

### 🔊 Read-Aloud Mode
- Sentence-by-sentence highlighting as the story is read
- Play / Pause / Prev / Next sentence controls
- Variable speed slider (0.5× – 2×)
- **10-voice picker** — Female and Male optgroups populated from the browser's Web Speech API voices, with your selection persisted across sessions

### 🧠 Machine Learning Personalisation
Each child profile is tracked across five learning signals:

| Signal | How it works |
|--------|-------------|
| **Vocabulary Score** (0–10) | Starts at an age-group baseline; +0.3 per correct quiz answer, −0.2 per wrong answer. Rolling Bayesian average. |
| **Reading Level** (Pre-K → Grade 6+) | Words-per-minute measured from chapter open to first quiz attempt, benchmarked against grade-level norms. |
| **Engagement Score** (0–1) | Composite of completion rate, replay rate, quiz participation and response time. |
| **Q&A Accuracy** | Per-session quiz correctness rate. |
| **Completion Rate** | Fraction of chapters finished. |

After 3 stories the engine upgrades from rule-based thresholds to a regression model for finer predictions. All five signals are injected into the next story's AI prompt, controlling *complexity level* (Simple / Moderate / Rich) and *vocabulary hint* (Introductory / Grade Level / Stretch).

### ❓ Vocabulary Quiz
- 5 multiple-choice questions per chapter, generated around words chosen from the story text
- Built-in dictionary of 180 + common story words guarantees correct answers without LLM dependency
- Allocator prioritises dictionary words, then falls back to LLM for any remaining slots
- Score feedback shown before the summary screen

### 👨‍👩‍👧 Parent Dashboard
- Stats overview: stories created, profiles, themes, settings
- **ML Science panel** — explains the scoring and personalisation mechanics in plain language
- Per-profile radar chart (Vocab / Reading / Engagement / Q&A / Completion)
- Vocabulary score trend line and quiz score bar chart per story
- Story complexity and vocabulary-level distribution charts
- Full story table with search

### 📚 Story Library
- Stories saved per child profile
- Theme and profile filter tabs
- Quick navigation to any saved story

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11 / Flask |
| Frontend | Vanilla HTML, CSS, JavaScript (no framework) |
| AI – Story Generation | Google Gemini (`gemini-2.0-flash`) |
| AI – Vocabulary Questions | Gemini + 180-word built-in dictionary |
| Database | SQLite (via `sqlite3`) |
| ML Engine | Rule-based thresholds → scikit-learn regression (after 3 stories) |
| Read-Aloud | Web Speech API (browser-native) |
| Deployment | Docker → Hugging Face Spaces |

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- A [Google AI Studio API key](https://aistudio.google.com/app/apikey) for Gemini

### Local Development

```bash
# Clone the repository
git clone https://github.com/hengds2f/storybook-ai.git
cd storybook-ai

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GEMINI_API_KEY=your_gemini_key_here
export SECRET_KEY=any_random_string   # optional, auto-generated if omitted

# Run the application
python app.py
```

The app will be available at `http://localhost:7860`.

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GEMINI_API_KEY` | Google Gemini API key | Yes |
| `SECRET_KEY` | Flask session secret key | No (auto-generated) |

### Docker

```bash
docker build -t storybook-ai .
docker run -p 7860:7860 -e GEMINI_API_KEY=your_key storybook-ai
```

---

## 📁 Project Structure

```
app.py                  # Flask application entry point
config.py               # Environment variable config
routes/
  auth.py               # Registration / login / logout
  story.py              # Story reader page
  dashboard.py          # Parent dashboard + library
  ml.py                 # ML question API endpoints
services/
  llm_service.py        # Gemini story generation
  ml_service.py         # ML scoring + vocab question generation
  story_builder.py      # Story text parser
  bg_tasks.py           # Background story generation thread
  event_tracker.py      # Reading event + question persistence
  storage.py            # SQLite helpers
static/
  js/
    builder.js          # Story creation form + polling
    reader.js           # Story reader + read-aloud + quiz
    dashboard.js        # Dashboard rendering
  css/style.css
templates/              # Jinja2 HTML templates
```

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
