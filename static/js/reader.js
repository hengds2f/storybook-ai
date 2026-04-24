/**
 * reader.js — Story Reader + Read-Aloud Mode
 * Handles: story loading, chapter rendering, Web Speech API,
 * sentence tokenization, sentence highlighting, play/pause/stop.
 */

const Reader = (() => {
  let story = null;
  let sentences = [];
  let currentSentenceIdx = 0;
  let isReading = false;
  let utterance = null;
  let speechRate = 0.9;
  let isPaused = false;
  let readerSessionId = null;    // one UUID per page-load reading session
  const _questions = new Map(); // sectionIdx → { questionId, startTime }
  const _vocabState = new Map(); // sectionIdx → { ids[], curr, correct, startTime }

  const CHAPTER_ICONS = {
    'Introduction': ['🌅', '📖', '🌟'],
    'Challenge': ['⚡', '🌊', '🎭'],
    'Resolution': ['🌈', '✨', '🏆'],
    'Moral': ['💫', '🌙', '💡'],
    'Poem': ['📜', '🎵', '✨']
  };

  // ── Init ───────────────────────────────────────────────────────────────
  async function init() {
    const storyId = window.STORY_ID;
    if (!storyId || storyId === 'None') {
      showError();
      return;
    }

    if (!App.isAuthenticated()) {
      // Redirect to home if not authenticated
      App.showToast('info', 'Please sign in to read stories');
      window.location.href = '/';
      return;
    }

    await loadStory(storyId);
  }

  async function loadStory(storyId) {
    try {
      const res = await fetch(`/api/stories/detail/${storyId}`);
      const data = await res.json();

      if (!res.ok || !data.story) {
        showError();
        return;
      }

      story = data.story;
      // Unique session ID so question answers can be correlated with reading events
      readerSessionId = typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : (Math.random().toString(36) + Math.random().toString(36)).slice(2, 34);
      renderStory();
      buildSentenceIndex();
    } catch (e) {
      console.error('Failed to load story:', e);
      showError();
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────
  function renderStory() {
    if (!story) return;

    const content = story.content;
    const params = story.parameters || {};

    // Hide loader, show content
    document.getElementById('storyLoadingState').style.display = 'none';
    document.getElementById('storyContent').style.display = 'block';

    // Title
    document.getElementById('storyTitle').textContent = story.title || 'Untitled Story';
    document.title = `${story.title} — StoryBook AI`;

    // Age tag
    const ageTag = document.getElementById('storyAgeTag');
    if (ageTag) ageTag.textContent = App.ageLabel(story.age_group || params.age_group || '6-8');

    // Meta badges
    const metaEl = document.getElementById('storyMeta');
    if (metaEl) {
      const theme = params.theme || '';
      const setting = params.setting || '';
      const chars = (params.characters || []).map(c => c.name).filter(n => n).join(', ');
      const profileName = story.profile_name || '';
      const date = App.formatDate(story.created_at);

      metaEl.innerHTML = [
        profileName && `<span class="story-badge">👤 ${App.escapeHtml(profileName)}</span>`,
        theme && `<span class="story-badge">${App.themeEmoji(theme)} ${App.escapeHtml(theme)}</span>`,
        setting && `<span class="story-badge">${App.settingEmoji(setting)} ${App.escapeHtml(setting)}</span>`,
        chars && `<span class="story-badge">🎭 ${App.escapeHtml(chars)}</span>`,
        date && `<span class="story-badge">📅 ${date}</span>`,
      ].filter(Boolean).join('');
    }

    // Render sections
    const sectionsEl = document.getElementById('storySections');
    const sections = content.sections || [];

    sectionsEl.innerHTML = sections.map((section, idx) => {
      const icons = CHAPTER_ICONS[section.title] || ['📖'];
      const icon = icons[idx % icons.length];
      let contentHtml = '';
      if (section.title === 'Poem') {
        const lines = (section.content || '').split('\n').filter(l => l.trim().length > 0);
        contentHtml = `<div class="poem-format" style="text-align: center; font-style: italic; font-size: 1.25rem; line-height: 1.8; margin: 3rem 0; color: var(--text-primary); font-family: 'Merriweather', serif;">` +
                      lines.map(l => `${App.escapeHtml(l.trim())}<br>`).join('') +
                      `</div>`;
      } else {
        contentHtml = (section.content || '').split('\n\n')
          .filter(p => p.trim().length > 0)
          .map(p => `<p>${App.escapeHtml(p.trim())}</p>`)
          .join('');
      }

      return `
        <div class="chapter-break" id="chapter-${idx}">
          <div class="chapter-number">Chapter ${idx + 1}</div>
          <div class="chapter-title">${App.escapeHtml(section.title)}</div>
          
          ${section.image_url ? `
            <div class="chapter-illustration">
              <img src="/static/${section.image_url}" alt="${App.escapeHtml(section.title)}" class="story-img" loading="lazy" />
            </div>
          ` : `
            <div class="chapter-icons">${icon}</div>
            <script>console.warn("Illustration missing for chapter: ${App.escapeHtml(section.title)}");</script>
          `}

          ${section.scene_description && section.title !== 'Poem' ? `
            <div class="scene-description">
              🎨 ${App.escapeHtml(section.scene_description)}
            </div>
          ` : ''}
        </div>
        <div class="story-content-block" id="sectionContent-${idx}">
          ${contentHtml}
        </div>
        ${section.question_ids && section.question_ids.length > 0 ? `
        <div class="question-card vocab-quiz-card" id="q-card-${idx}">
          <button class="question-trigger vocab-quiz-trigger" onclick="Reader.startVocabQuiz(${idx})">
            📚 Vocabulary Quiz &middot; ${section.question_ids.length} words
          </button>
          <div class="question-body" id="q-body-${idx}" style="display:none;"></div>
        </div>` : ''}
      `;
    }).join('');
  }

  // Build a flat list of all sentences across all sections (for read-aloud)
  function buildSentenceIndex() {
    sentences = [];
    const blocks = document.querySelectorAll('.story-content-block');

    blocks.forEach(block => {
      // Get all text nodes
      const fullText = block.innerText;
      const sentenceArr = tokenizeSentences(fullText);

      block.innerHTML = sentenceArr.map((s, i) => {
        const globalIdx = sentences.length;
        sentences.push({ element: null, text: s, blockEl: block });
        return `<span class="sentence" data-idx="${globalIdx}">${App.escapeHtml(s)} </span>`;
      }).join('');
    });

    // Map sentences to their span elements
    document.querySelectorAll('.sentence').forEach(span => {
      const idx = parseInt(span.dataset.idx);
      if (sentences[idx]) sentences[idx].element = span;
    });

    // Update total count
    const totalEl = document.getElementById('ralTotal');
    if (totalEl) totalEl.textContent = sentences.length;
  }

  function tokenizeSentences(text) {
    // Split on sentence-ending punctuation
    const raw = text.replace(/\n+/g, ' ').split(/(?<=[.!?])\s+/);
    return raw.map(s => s.trim()).filter(s => s.length > 0);
  }

  // ── Read-Aloud ─────────────────────────────────────────────────────────
  function toggleReadAloud() {
    if (!('speechSynthesis' in window)) {
      App.showToast('error', 'Read-aloud is not supported in your browser');
      return;
    }

    if (isReading) {
      stopReadAloud();
    } else {
      startReadAloud();
    }
  }

  function startReadAloud() {
    if (sentences.length === 0) {
      App.showToast('info', 'No content to read');
      return;
    }

    isReading = true;
    isPaused = false;
    currentSentenceIdx = 0;

    // Show controls bar
    document.getElementById('readAloudBar').classList.add('visible');
    document.getElementById('readAloudBtn').textContent = '⏹ Stop Reading';
    document.getElementById('ralPlayPause').textContent = '⏸ Pause';

    speakSentence(currentSentenceIdx);
  }

  function speakSentence(idx) {
    if (idx >= sentences.length || !isReading) {
      finishReadAloud();
      return;
    }

    currentSentenceIdx = idx;
    highlightSentence(idx);
    updateProgress();

    window.speechSynthesis.cancel();

    utterance = new SpeechSynthesisUtterance(sentences[idx].text);
    utterance.rate = speechRate;
    utterance.pitch = 1.0;
    utterance.volume = 1.0;

    // Pick a good voice
    const voices = window.speechSynthesis.getVoices();
    const preferred = voices.find(v =>
      v.name.includes('Google UK English Female') ||
      v.name.includes('Samantha') ||
      v.name.includes('Karen') ||
      (v.lang.startsWith('en') && v.localService)
    );
    if (preferred) utterance.voice = preferred;

    utterance.onend = () => {
      if (isReading && !isPaused) {
        setTimeout(() => speakSentence(idx + 1), 100);
      }
    };

    utterance.onerror = (e) => {
      if (e.error !== 'interrupted') {
        console.error('Speech error:', e);
      }
    };

    window.speechSynthesis.speak(utterance);
  }

  function highlightSentence(idx) {
    // Remove previous highlight
    document.querySelectorAll('.sentence.highlighted').forEach(el => {
      el.classList.remove('highlighted');
    });

    const sent = sentences[idx];
    if (sent && sent.element) {
      sent.element.classList.add('highlighted');
      sent.element.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }

  function updateProgress() {
    const curEl = document.getElementById('ralCurrent');
    const totEl = document.getElementById('ralTotal');
    if (curEl) curEl.textContent = currentSentenceIdx + 1;
    if (totEl) totEl.textContent = sentences.length;
  }

  function togglePlayPause() {
    if (!isReading) return;

    if (isPaused) {
      // Resume
      isPaused = false;
      window.speechSynthesis.resume();
      document.getElementById('ralPlayPause').textContent = '⏸ Pause';
    } else {
      // Pause
      isPaused = true;
      window.speechSynthesis.pause();
      document.getElementById('ralPlayPause').textContent = '▶ Resume';
    }
  }

  function prevSentence() {
    if (!isReading) return;
    const newIdx = Math.max(0, currentSentenceIdx - 1);
    isPaused = false;
    document.getElementById('ralPlayPause').textContent = '⏸ Pause';
    speakSentence(newIdx);
  }

  function nextSentence() {
    if (!isReading) return;
    const newIdx = Math.min(sentences.length - 1, currentSentenceIdx + 1);
    isPaused = false;
    document.getElementById('ralPlayPause').textContent = '⏸ Pause';
    speakSentence(newIdx);
  }

  function stopReadAloud() {
    isReading = false;
    isPaused = false;
    window.speechSynthesis.cancel();
    document.querySelectorAll('.sentence.highlighted').forEach(el => el.classList.remove('highlighted'));
    document.getElementById('readAloudBar').classList.remove('visible');
    document.getElementById('readAloudBtn').textContent = '🔊 Read Aloud';
  }

  function finishReadAloud() {
    isReading = false;
    isPaused = false;
    document.querySelectorAll('.sentence.highlighted').forEach(el => el.classList.remove('highlighted'));
    document.getElementById('readAloudBar').classList.remove('visible');
    document.getElementById('readAloudBtn').textContent = '🔊 Read Aloud';
    App.showToast('success', 'Story finished! 🌟');
  }

  function setSpeed(val) {
    speechRate = parseFloat(val);
    const label = document.getElementById('ralSpeedLabel');
    if (label) label.textContent = `${speechRate.toFixed(1)}×`;

    // If currently speaking, restart current sentence with new speed
    if (isReading && !isPaused) {
      speakSentence(currentSentenceIdx);
    }
  }

  // ── Interactive Questions ──────────────────────────────────────────────

  async function showQuestion(idx, questionId) {
    const card = document.getElementById(`q-card-${idx}`);
    const body = document.getElementById(`q-body-${idx}`);
    if (!card || !body) return;

    const trigger = card.querySelector('.question-trigger');
    if (trigger) trigger.style.display = 'none';
    body.style.display = 'block';
    body.innerHTML = '<p class="question-loading">Loading question…</p>';

    try {
      const res = await fetch(`/api/ml/questions/${encodeURIComponent(questionId)}`);
      if (!res.ok) {
        body.innerHTML = '<p class="question-loading">Question not available.</p>';
        return;
      }
      const q = await res.json();
      _questions.set(idx, { questionId, startTime: Date.now() });

      const typeLabels = {
        comprehension: '💭 Comprehension Check',
        prediction:    '🔮 What Happens Next?',
        reflection:    '🌟 Think About It'
      };
      const typeLabel = typeLabels[q.question_type] || '🤔 Question';

      body.innerHTML = `
        <div class="question-type-label">${typeLabel}</div>
        <p class="question-text">${App.escapeHtml(q.question_text)}</p>
        <div class="question-options" id="q-opts-${idx}"></div>
        <div class="question-feedback" id="q-feedback-${idx}" style="display:none;"></div>
      `;

      // Build option buttons via DOM to avoid template-literal escaping issues
      const optsEl = document.getElementById(`q-opts-${idx}`);
      (q.options || []).forEach(opt => {
        const btn = document.createElement('button');
        btn.className = 'question-option';
        btn.textContent = opt;
        btn.addEventListener('click', () => _submitAnswer(idx, opt));
        optsEl.appendChild(btn);
      });
    } catch (e) {
      console.error('Failed to load question:', e);
      body.innerHTML = '<p class="question-loading">Question not available.</p>';
    }
  }

  async function _submitAnswer(idx, answer) {
    const qData = _questions.get(idx);
    if (!qData) return;
    const { questionId, startTime } = qData;
    const responseTimeMs = Date.now() - startTime;

    // Lock all options immediately
    const optsEl = document.getElementById(`q-opts-${idx}`);
    if (optsEl) optsEl.querySelectorAll('.question-option').forEach(btn => { btn.disabled = true; });

    try {
      const res = await fetch(`/api/ml/questions/${encodeURIComponent(questionId)}/answer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          profile_id:       story.profile_id,
          session_id:       readerSessionId,
          answer:           answer,
          response_time_ms: responseTimeMs,
        }),
      });
      const data = await res.json();

      // Colour correct / incorrect options
      // data.correct_answer is a letter ("A"/"B"/"C") — match against "A. option text"
      const correctLetter = (data.correct_answer || '').trim().toUpperCase();
      let correctFullText = '';
      if (optsEl) {
        optsEl.querySelectorAll('.question-option').forEach(btn => {
          const btnTxt = btn.textContent.trim();
          if (correctLetter && btnTxt.toUpperCase().startsWith(correctLetter + '.')) {
            btn.classList.add('correct');
            correctFullText = btnTxt;
          } else if (btnTxt === answer.trim() && !data.is_correct) {
            btn.classList.add('incorrect');
          }
        });
      }

      // Show feedback — append the full correct option text when the answer was wrong
      const feedbackEl = document.getElementById(`q-feedback-${idx}`);
      if (feedbackEl) {
        feedbackEl.style.display = 'block';
        feedbackEl.className = `question-feedback ${data.is_correct ? 'correct' : 'incorrect'}`;
        let msg = data.feedback || (data.is_correct ? '✅ Correct!' : '❌ Not quite — keep reading!');
        if (!data.is_correct && correctFullText) {
          msg += ' ' + correctFullText;
        }
        feedbackEl.textContent = msg;
      }
    } catch (e) {
      console.error('Failed to submit answer:', e);
    }
  }

  // ── Vocabulary Quiz (multi-question) ──────────────────────────────────

  function startVocabQuiz(idx) {
    const section = story.content.sections[idx];
    const ids = (section && section.question_ids) || [];
    if (ids.length === 0) return;

    const card = document.getElementById(`q-card-${idx}`);
    const body = document.getElementById(`q-body-${idx}`);
    if (!card || !body) return;

    const trigger = card.querySelector('.vocab-quiz-trigger');
    if (trigger) trigger.style.display = 'none';
    body.style.display = 'block';

    _vocabState.set(idx, { ids, curr: 0, correct: 0, startTime: Date.now() });
    _showVocabQuestion(idx);
  }

  async function _showVocabQuestion(idx) {
    const state = _vocabState.get(idx);
    if (!state) return;
    const { ids, curr } = state;
    const questionId = ids[curr];
    const body = document.getElementById(`q-body-${idx}`);
    if (!body) return;

    body.innerHTML = '<p class="question-loading">Loading word…</p>';

    try {
      const res = await fetch(`/api/ml/questions/${encodeURIComponent(questionId)}`);
      if (!res.ok) {
        body.innerHTML = '<p class="question-loading">Question not available.</p>';
        return;
      }
      const q = await res.json();
      state.qStartTime = Date.now();

      body.innerHTML = `
        <div class="vocab-quiz-header">
          <span class="vocab-quiz-progress">Word ${curr + 1} / ${ids.length}</span>
          <span class="vocab-quiz-label">📖 Vocabulary Quiz</span>
        </div>
        <p class="question-text">${App.escapeHtml(q.question_text)}</p>
        <div class="question-options" id="vq-opts-${idx}"></div>
        <div class="question-feedback" id="vq-feedback-${idx}" style="display:none;"></div>
        <div id="vq-next-${idx}" style="display:none;"></div>
      `;

      const optsEl = document.getElementById(`vq-opts-${idx}`);
      (q.options || []).forEach(opt => {
        const btn = document.createElement('button');
        btn.className = 'question-option';
        btn.textContent = opt;
        btn.addEventListener('click', () => _submitVocabAnswer(idx, opt, questionId));
        optsEl.appendChild(btn);
      });
    } catch (e) {
      console.error('Failed to load vocab question:', e);
      body.innerHTML = '<p class="question-loading">Question not available.</p>';
    }
  }

  async function _submitVocabAnswer(idx, answer, questionId) {
    const state = _vocabState.get(idx);
    if (!state) return;
    const responseTimeMs = Date.now() - (state.qStartTime || state.startTime);

    const optsEl = document.getElementById(`vq-opts-${idx}`);
    if (optsEl) optsEl.querySelectorAll('.question-option').forEach(btn => { btn.disabled = true; });

    try {
      const res = await fetch(`/api/ml/questions/${encodeURIComponent(questionId)}/answer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          profile_id:       story.profile_id,
          session_id:       readerSessionId,
          answer:           answer,
          response_time_ms: responseTimeMs,
        }),
      });
      const data = await res.json();

      const correctLetter = (data.correct_answer || '').trim().toUpperCase();
      let correctFullText = '';
      if (optsEl) {
        optsEl.querySelectorAll('.question-option').forEach(btn => {
          const t = btn.textContent.trim();
          if (correctLetter && t.toUpperCase().startsWith(correctLetter + '.')) {
            btn.classList.add('correct');
            correctFullText = t;
          } else if (t === answer.trim() && !data.is_correct) {
            btn.classList.add('incorrect');
          }
        });
      }

      if (data.is_correct) state.correct += 1;

      const feedbackEl = document.getElementById(`vq-feedback-${idx}`);
      if (feedbackEl) {
        feedbackEl.style.display = 'block';
        feedbackEl.className = `question-feedback ${data.is_correct ? 'correct' : 'incorrect'}`;
        let msg = data.is_correct ? '✅ Correct!' : '❌ Not quite.';
        if (!data.is_correct && correctFullText) msg += ' The answer was: ' + correctFullText;
        feedbackEl.textContent = msg;
      }

      // Advance to next question after a short delay
      const nextEl = document.getElementById(`vq-next-${idx}`);
      if (nextEl) {
        const isLast = (state.curr >= state.ids.length - 1);
        nextEl.style.display = 'block';
        if (!isLast) {
          const btn = document.createElement('button');
          btn.className = 'vocab-next-btn';
          btn.textContent = 'Next Word →';
          btn.addEventListener('click', () => {
            state.curr += 1;
            _showVocabQuestion(idx);
          });
          nextEl.appendChild(btn);
        } else {
          _showVocabScore(idx);
        }
      }
    } catch (e) {
      console.error('Failed to submit vocab answer:', e);
    }
  }

  function _showVocabScore(idx) {
    const state = _vocabState.get(idx);
    if (!state) return;
    const { correct, ids } = state;
    const total = ids.length;
    const pct = Math.round((correct / total) * 100);

    let emoji = '⭐';
    let msg   = 'Good effort!';
    if (pct === 100)      { emoji = '🏆'; msg = 'Perfect score!'; }
    else if (pct >= 80)   { emoji = '🌟'; msg = 'Excellent!'; }
    else if (pct >= 60)   { emoji = '✨'; msg = 'Great work!'; }
    else if (pct >= 40)   { emoji = '👍'; msg = 'Keep it up!'; }

    const body = document.getElementById(`q-body-${idx}`);
    if (body) {
      body.innerHTML = `
        <div class="vocab-score-card">
          <div class="vocab-score-emoji">${emoji}</div>
          <div class="vocab-score-label">${msg}</div>
          <div class="vocab-score-fraction">You got <strong>${correct} / ${total}</strong> words correct!</div>
          <div class="vocab-score-bar-wrap">
            <div class="vocab-score-bar-fill" style="width:${pct}%;"></div>
          </div>
        </div>
      `;
    }
  }

  // ── Delete Story ───────────────────────────────────────────────────────
  async function deleteStory() {
    if (!story) return;
    if (!confirm('Delete this story? This cannot be undone.')) return;

    try {
      const res = await fetch(`/api/stories/delete/${story.id}`, { method: 'DELETE' });
      if (res.ok) {
        App.showToast('success', 'Story deleted');
        window.location.href = '/library';
      } else {
        App.showToast('error', 'Failed to delete story');
      }
    } catch (e) {
      App.showToast('error', 'Network error');
    }
  }

  function showError() {
    document.getElementById('storyLoadingState').style.display = 'none';
    document.getElementById('storyContent').style.display = 'none';
    document.getElementById('storyErrorState').style.display = 'block';
  }

  // Cancel speech when leaving page
  window.addEventListener('beforeunload', () => {
    window.speechSynthesis.cancel();
  });

  // ── Boot ───────────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', init);

  return {
    init, toggleReadAloud, startReadAloud, stopReadAloud,
    togglePlayPause, prevSentence, nextSentence, setSpeed,
    deleteStory, showQuestion, startVocabQuiz
  };
})();
