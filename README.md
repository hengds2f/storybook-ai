---
title: StoryBook AI
emoji: 📚
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: AI-powered personalized children's story generator
---

# 📚 StoryBook AI

**StoryBook AI** is a personalized children's story generator that combines creativity with artificial intelligence. Parents and children co-create magical stories by selecting characters, settings, themes, and moral lessons — the AI weaves them into a unique, age-appropriate narrative in seconds.

## ✨ Features

- 🎭 **Story Parameter Builder** — Customize characters, traits, settings, themes & moral lessons
- 📖 **Age-Adaptive Storytelling** — Vocabulary and complexity adjusted for ages 3–5, 6–8, or 9–12
- 🏰 **Structured Narrative Arc** — Introduction → Challenge → Resolution → Moral
- 🎨 **Illustrated Chapter Breaks** — AI-generated scene descriptions between chapters
- 📚 **Story Library** — Save and revisit stories per child profile
- 👨‍👩‍👧 **Parent Dashboard** — Review all generated stories across child profiles
- 🔊 **Read-Aloud Mode** — Sentence-by-sentence highlighting with Web Speech API

## 🚀 Getting Started

### Local Development

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/storybook-ai.git
cd storybook-ai

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env and add your HF_TOKEN

# Run the application
python app.py
```

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `HF_TOKEN` | Hugging Face API token ([get one here](https://huggingface.co/settings/tokens)) | Yes |
| `SECRET_KEY` | Flask session secret key | No (auto-generated) |

## 🛠️ Tech Stack

- **Backend**: Python / Flask
- **Frontend**: Vanilla HTML, CSS, JavaScript
- **AI**: Hugging Face Inference API (Llama 3.2 / Mistral)
- **Database**: SQLite
- **Deployment**: Docker → Hugging Face Spaces

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
