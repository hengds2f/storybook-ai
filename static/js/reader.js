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

  const CHAPTER_ICONS = {
    'Introduction': ['🌅', '📖', '🌟'],
    'Challenge': ['⚡', '🌊', '🎭'],
    'Resolution': ['🌈', '✨', '🏆'],
    'Moral': ['💫', '🌙', '💡']
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
      const paragraphs = (section.content || '').split('\n\n')
        .filter(p => p.trim().length > 0)
        .map(p => `<p>${App.escapeHtml(p.trim())}</p>`)
        .join('');

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
          `}

          ${section.scene_description ? `
            <div class="scene-description">
              🎨 ${App.escapeHtml(section.scene_description)}
            </div>
          ` : ''}
        </div>
        <div class="story-content-block" id="sectionContent-${idx}">
          ${paragraphs}
        </div>
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
    deleteStory
  };
})();
