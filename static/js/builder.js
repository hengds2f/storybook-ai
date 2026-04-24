/**
 * builder.js — Story Parameter Builder
 * Handles: character management, setting/theme selectors, age group,
 * moral lesson, live preview, profile selection, and story generation.
 */

const Builder = (() => {
  let characters = [{ name: '', traits: [] }];
  let selectedProfileId = null;
  let selectedColor = '#6366f1';
  let mlRec = null;  // cached ML recommendation for currently selected profile

  const AVATAR_COLORS = [
    '#6366f1', '#a855f7', '#ec4899', '#f59e0b',
    '#10b981', '#3b82f6', '#ef4444', '#f97316'
  ];

  const TRAIT_OPTIONS = [
    'Brave', 'Curious', 'Kind', 'Funny', 'Shy',
    'Creative', 'Clever', 'Loyal', 'Adventurous', 'Gentle',
    'Stubborn', 'Cheerful', 'Mischievous', 'Wise', 'Caring'
  ];

  // ── Init ─────────────────────────────────────────────────────────────
  async function init() {
    renderCharacters();
    updatePreview();

    // Custom setting toggle
    const settingSelect = document.getElementById('settingSelect');
    if (settingSelect) {
      settingSelect.addEventListener('change', () => {
        const customGroup = document.getElementById('customSettingGroup');
        customGroup.classList.toggle('hidden', settingSelect.value !== 'custom');
        updatePreview();
      });
    }

    // CRITICAL: wait for App's /api/me check to finish before reading auth state.
    // Without this, isAuthenticated() always returns false (race condition).
    await App.authReady;

    // Load profiles if authenticated
    if (App.isAuthenticated()) {
      await loadProfiles();
    } else {
      // Show auth prompt in profile selector
      const sel = document.getElementById('profileSelector');
      if (sel) {
        sel.innerHTML = `
          <span class="text-small text-muted">
            <button class="btn btn-primary btn-sm" onclick="App.openAuthModal()">Sign in</button>
            to create stories and save to profiles.
          </span>`;
      }
    }

    initColorPicker();
    updatePreview(); // Re-render preview now that auth state is known
  }

  // ── Profile Management ────────────────────────────────────────────────
  async function loadProfiles() {
    try {
      const res = await fetch('/api/profiles');
      const data = await res.json();
      const profiles = data.profiles || [];
      renderProfileSelector(profiles);
    } catch (e) {
      console.error('Failed to load profiles:', e);
    }
  }

  function renderProfileSelector(profiles) {
    const sel = document.getElementById('profileSelector');
    if (!sel) return;

    if (profiles.length === 0) {
      sel.innerHTML = `<span class="text-small text-muted">No profiles yet — add one below!</span>`;
      selectedProfileId = null;
      updatePreview();
      return;
    }

    sel.innerHTML = profiles.map(p => `
      <div class="profile-tab ${selectedProfileId === p.id ? 'active' : ''}"
           onclick="Builder.selectProfile('${App.escapeHtml(p.id)}')"
           data-profile-id="${App.escapeHtml(p.id)}">
        <div class="profile-avatar" style="background:${p.avatar_color}">
          ${App.escapeHtml(p.name[0].toUpperCase())}
        </div>
        ${App.escapeHtml(p.name)}
        <span class="text-small text-muted">(${App.ageLabel(p.age_group)})</span>
      </div>
    `).join('');

    // Auto-select first profile
    if (!selectedProfileId && profiles.length > 0) {
      selectProfile(profiles[0].id, profiles[0]);
    }
  }

  function selectProfile(profileId) {
    selectedProfileId = profileId;
    document.querySelectorAll('.profile-tab').forEach(tab => {
      tab.classList.toggle('active', tab.dataset.profileId === profileId);
    });
    updatePreview(); // immediate render before ML data arrives
    // Fetch ML recommendation in background and update preview when ready
    _fetchMlRecommendation(profileId);
  }

  async function _fetchMlRecommendation(profileId) {
    if (!profileId || !App.isAuthenticated()) { mlRec = null; return; }
    try {
      const res = await fetch(`/api/ml/recommend/${encodeURIComponent(profileId)}`);
      if (res.ok) {
        mlRec = await res.json();
      } else {
        mlRec = null;
      }
    } catch (e) {
      mlRec = null;
    }
    updatePreview(); // re-render now that ML data is available
  }

  function openAddProfile() {
    if (!App.isAuthenticated()) {
      App.openAuthModal();
      return;
    }
    document.getElementById('addProfileModal').classList.add('open');
  }

  function closeAddProfile() {
    document.getElementById('addProfileModal').classList.remove('open');
  }

  async function saveProfile(e) {
    e.preventDefault();
    const name = document.getElementById('profileName').value.trim();
    const ageGroup = document.querySelector('input[name="profileAge"]:checked')?.value || '6-8';
    const errEl = document.getElementById('profileError');
    const spinner = document.getElementById('profileSaveSpinner');

    errEl.classList.add('hidden');
    spinner.classList.remove('hidden');

    try {
      const res = await fetch('/api/profiles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, age_group: ageGroup, avatar_color: selectedColor })
      });
      const data = await res.json();

      if (res.ok) {
        closeAddProfile();
        App.showToast('success', `Profile for ${name} created! 🎉`);
        await loadProfiles();
        selectProfile(data.profile.id);
      } else {
        errEl.textContent = data.error || 'Failed to create profile';
        errEl.classList.remove('hidden');
      }
    } catch (err) {
      errEl.textContent = 'Network error';
      errEl.classList.remove('hidden');
    } finally {
      spinner.classList.add('hidden');
    }
  }

  function initColorPicker() {
    const picker = document.getElementById('colorPicker');
    if (!picker) return;
    picker.innerHTML = AVATAR_COLORS.map((color, i) => `
      <div class="color-swatch ${i === 0 ? 'selected' : ''}"
           style="background:${color};"
           onclick="Builder.selectColor('${color}', this)"
           title="${color}"></div>
    `).join('');
  }

  function selectColor(color, el) {
    selectedColor = color;
    document.querySelectorAll('.color-swatch').forEach(s => s.classList.remove('selected'));
    el.classList.add('selected');
  }

  // ── Character Management ───────────────────────────────────────────────
  function addCharacter() {
    if (characters.length >= 3) {
      App.showToast('info', 'Maximum 3 characters per story!');
      return;
    }
    characters.push({ name: '', traits: [] });
    renderCharacters();
    updatePreview();
  }

  function removeCharacter(index) {
    if (characters.length <= 1) return;
    characters.splice(index, 1);
    renderCharacters();
    updatePreview();
  }

  function renderCharacters() {
    const list = document.getElementById('charactersList');
    if (!list) return;

    list.innerHTML = characters.map((char, i) => `
      <div class="character-card" id="charCard${i}">
        ${characters.length > 1 ? `
          <button class="character-remove" onclick="Builder.removeCharacter(${i})" title="Remove character">✕</button>
        ` : ''}
        <div class="form-group mb-2">
          <label class="form-label" for="charName${i}">Character ${i + 1} Name</label>
          <input type="text" class="form-input" id="charName${i}"
                 value="${App.escapeHtml(char.name)}"
                 placeholder="e.g. Luna, Jack, Mia…"
                 oninput="Builder.updateCharName(${i}, this.value)" />
        </div>
        <div class="form-group">
          <label class="form-label">Personality Traits</label>
          <div class="chip-group">
            ${TRAIT_OPTIONS.map(trait => `
              <div class="chip ${char.traits.includes(trait) ? 'selected' : ''}"
                   onclick="Builder.toggleTrait(${i}, '${trait}')">
                ${trait}
              </div>
            `).join('')}
          </div>
        </div>
      </div>
    `).join('');
  }

  function updateCharName(index, value) {
    characters[index].name = value;
    updatePreview();
  }

  function toggleTrait(charIndex, trait) {
    const char = characters[charIndex];
    const traitIdx = char.traits.indexOf(trait);
    if (traitIdx >= 0) {
      char.traits.splice(traitIdx, 1);
    } else {
      if (char.traits.length >= 4) {
        App.showToast('info', 'Maximum 4 traits per character');
        return;
      }
      char.traits.push(trait);
    }
    // Re-render just the chip that was clicked
    renderCharacters();
    updatePreview();
  }

  // ── Moral Lesson ──────────────────────────────────────────────────────
  function setMoral(text) {
    const input = document.getElementById('moralInput');
    if (input) {
      input.value = text;
      updatePreview();
    }
    // Update chip selection
    document.querySelectorAll('#moralPresets .chip').forEach(c => {
      c.classList.toggle('selected', c.getAttribute('onclick').includes(text.substring(0, 20)));
    });
  }

  // ── Live Preview ──────────────────────────────────────────────────────
  function updatePreview() {
    // Characters
    const charNames = characters
      .map(c => c.name.trim())
      .filter(n => n.length > 0);
    document.getElementById('prevCharacters').textContent =
      charNames.length > 0 ? charNames.join(', ') : '—';

    // Setting — empty string means "AI Recommends"
    const settingSelect = document.getElementById('settingSelect');
    const customSetting = document.getElementById('customSetting');
    let setting = settingSelect?.value ?? '';
    if (setting === 'custom') {
      setting = customSetting?.value || 'Custom setting';
    }
    const settingLabels = {
      'an enchanted forest': '🌲 Enchanted Forest',
      'outer space': '🚀 Outer Space',
      'a magical underwater kingdom': '🌊 Underwater Kingdom',
      'a medieval castle kingdom': '🏰 Medieval Castle',
      'a bustling modern city': '🏙️ Modern City',
      'a cozy mountain village': '⛰️ Mountain Village',
      'a mystical desert with ancient temples': '🏜️ Mystical Desert',
      'a futuristic robot city': '🤖 Robot City',
      'a rainbow cloud kingdom': '🌈 Cloud Kingdom'
    };
    let settingDisplay;
    if (setting === '') {
      const mlSetting = mlRec?.recommendation?.setting;
      settingDisplay = mlSetting ? `🤖 AI picks: ${mlSetting}` : '🤖 AI Recommends';
    } else {
      settingDisplay = settingLabels[setting] || setting || '—';
    }
    document.getElementById('prevSetting').textContent = settingDisplay;

    // Theme — empty string means "AI Recommends"
    const themeSelect = document.getElementById('themeSelect');
    const themeVal = themeSelect?.value ?? '';
    const themeLabels = {
      friendship: '💛 Friendship', courage: '🦁 Courage', honesty: '🌟 Honesty',
      kindness: '💗 Kindness', perseverance: '💪 Perseverance', sharing: '🎁 Sharing',
      teamwork: '🏆 Teamwork', respect: '🌸 Respect', creativity: '🎨 Creativity',
      curiosity: '🔭 Curiosity'
    };
    let themeDisplay;
    if (themeVal === '') {
      const mlTheme = mlRec?.recommendation?.theme;
      themeDisplay = mlTheme ? `🤖 AI picks: ${mlTheme}` : '🤖 AI Recommends';
    } else {
      themeDisplay = themeLabels[themeVal] || themeVal || '—';
    }
    document.getElementById('prevTheme').textContent = themeDisplay;

    // Age
    const ageVal = document.querySelector('input[name="ageGroup"]:checked')?.value || '6-8';
    const ageLabels = { '3-5': '🐣 Ages 3–5 (Short & Simple)', '6-8': '🌱 Ages 6–8 (Fun & Engaging)', '9-12': '🌳 Ages 9–12 (Rich & Detailed)' };
    document.getElementById('prevAge').textContent = ageLabels[ageVal] || ageVal;

    // Moral
    const moral = document.getElementById('moralInput')?.value?.trim();
    document.getElementById('prevMoral').textContent = moral || '—';

    // ML personalisation row
    const mlRow  = document.getElementById('prevMlRow');
    const mlInfo = document.getElementById('prevMlInfo');
    if (mlRow && mlInfo) {
      if (mlRec && selectedProfileId) {
        mlRow.style.display = '';
        const complexity = mlRec.recommendation?.complexity_hint || 'moderate';
        const vocabHint  = mlRec.recommendation?.vocabulary_hint  || 'grade_level';
        const rlLabel    = mlRec.reading_level?.label || 'adapting…';
        const engLabel   = mlRec.engagement?.label   || 'medium';
        if (mlRec.cold_start) {
          mlInfo.innerHTML = `<span style="color:var(--text-muted)">🌱 Building profile — read more stories to unlock full personalisation</span>`;
        } else {
          mlInfo.innerHTML =
            `Reading: <strong>${rlLabel}</strong> · ` +
            `Complexity: <strong>${complexity}</strong> · ` +
            `Engagement: <strong>${engLabel}</strong>`;
        }
      } else {
        mlRow.style.display = 'none';
      }
    }

    // Profile
    const activeTab = document.querySelector('.profile-tab.active');
    document.getElementById('prevProfile').textContent =
      activeTab ? activeTab.textContent.trim() : (App.isAuthenticated() ? 'Select a profile' : 'Sign in required');
  }

  // ── Generate Story ─────────────────────────────────────────────────────
  async function generateStory() {
    if (!App.isAuthenticated()) {
      App.openAuthModal();
      return;
    }

    if (!selectedProfileId) {
      App.showToast('error', 'Please select or create a child profile first!');
      return;
    }

    const settingSelect = document.getElementById('settingSelect');
    const customSetting = document.getElementById('customSetting');
    // Use '' (empty string) when AI Recommends is selected — route will apply ML pick
    let setting = settingSelect?.value ?? '';
    if (setting === 'custom') {
      setting = customSetting?.value?.trim() || '';
    }

    const ageGroup = document.querySelector('input[name="ageGroup"]:checked')?.value || '6-8';
    // Use '' when AI Recommends is selected
    const theme = document.getElementById('themeSelect')?.value ?? '';
    const moral = document.getElementById('moralInput')?.value?.trim() || '';

    const validChars = characters.filter(c => c.name.trim().length > 0);
    if (validChars.length === 0) {
      App.showToast('error', 'Please add at least one character name!');
      return;
    }

    const payload = {
      profile_id: selectedProfileId,
      age_group: ageGroup,
      characters: validChars,
      setting,
      theme,
      moral
    };

    // Show loading overlay
    App.showStoryLoading('Initializing...', 5);
    document.getElementById('generateBtn').disabled = true;

    try {
      const res = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await res.json();

      if (res.status === 202 && data.task_id) {
        // Asynchronous mode
        pollGenerationStatus(data.task_id);
      } else if (res.ok && data.story_id) {
        // Fallback or immediate success (legacy)
        App.showToast('success', 'Story created! 📖');
        window.location.href = `/story/${data.story_id}`;
      } else {
        App.hideStoryLoading();
        App.showToast('error', data.error || 'Failed to generate story');
        document.getElementById('generateBtn').disabled = false;
      }
    } catch (err) {
      App.hideStoryLoading();
      App.showToast('error', 'Network error — please try again');
      document.getElementById('generateBtn').disabled = false;
    }
  }

  async function pollGenerationStatus(taskId) {
    try {
      const res = await fetch(`/api/generate/status/${taskId}`);
      const data = await res.json();
      
      if (!res.ok) {
        App.hideStoryLoading();
        App.showToast('error', data.error || 'Progress tracking failed');
        document.getElementById('generateBtn').disabled = false;
        return;
      }

      if (data.status === 'finished' && data.result_story_id) {
        App.showStoryLoading('Success! Opening your book...', 100);
        setTimeout(() => {
          window.location.href = `/story/${data.result_story_id}`;
        }, 1000);
      } else if (data.status === 'failed') {
        App.hideStoryLoading();
        App.showToast('error', data.status_message || 'Generation failed');
        document.getElementById('generateBtn').disabled = false;
      } else {
        // Still working: Update UI and poll again
        const msg = data.status_message || 'The magic is happening...';
        const progress = data.progress_pct || 10;
        App.showStoryLoading(msg, progress);
        
        // Poll every 3 seconds
        setTimeout(() => pollGenerationStatus(taskId), 3000);
      }
    } catch (err) {
      console.error('Polling error:', err);
      // Wait and try again (don't give up on one network hiccup)
      setTimeout(() => pollGenerationStatus(taskId), 5000);
    }
  }

  // ── Boot ──────────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', init);

  return {
    init, addCharacter, removeCharacter, renderCharacters,
    updateCharName, toggleTrait, setMoral, updatePreview,
    generateStory, selectProfile, loadProfiles,
    openAddProfile, closeAddProfile, saveProfile,
    selectColor, initColorPicker
  };
})();
