/**
 * dashboard.js — Library + Parent Dashboard
 * Handles: fetching profiles, stories, rendering library grid,
 * rendering dashboard stats, theme/age breakdowns, story search.
 */

const Library = (() => {
  let allStories = [];
  let currentProfileId = null;
  let currentThemeFilter = '';

  async function init() {
    // Wait for App's /api/me check before checking auth state (race condition fix)
    await App.authReady;

    if (!App.isAuthenticated()) {
      const notice = document.getElementById('libraryAuthNotice');
      if (notice) notice.classList.remove('hidden');
      return;
    }

    const main = document.getElementById('libraryMain');
    if (main) main.classList.remove('hidden');

    await loadProfilesAndStories();
  }

  async function loadProfilesAndStories() {
    try {
      const profsRes = await fetch('/api/profiles');
      const profsData = await profsRes.json();
      const profiles = profsData.profiles || [];

      renderProfileTabs(profiles);

      if (profiles.length > 0) {
        await loadStoriesForProfile(profiles[0].id);
      } else {
        renderEmptyState();
      }
    } catch (e) {
      console.error('Library load error:', e);
    }
  }

  function renderProfileTabs(profiles) {
    const tabs = document.getElementById('profileTabs');
    if (!tabs) return;

    if (profiles.length === 0) {
      tabs.innerHTML = `<span class="text-small text-muted">No profiles yet — <a href="/app">create a story</a> to add one!</span>`;
      return;
    }

    tabs.innerHTML = profiles.map((p, i) => `
      <div class="profile-tab ${i === 0 ? 'active' : ''}"
           onclick="Library.switchProfile('${p.id}', this)"
           data-profile-id="${p.id}">
        <div class="profile-avatar" style="background:${p.avatar_color}">
          ${App.escapeHtml(p.name[0].toUpperCase())}
        </div>
        ${App.escapeHtml(p.name)}
      </div>
    `).join('');
  }

  async function switchProfile(profileId, tabEl) {
    currentProfileId = profileId;
    document.querySelectorAll('#profileTabs .profile-tab').forEach(t => {
      t.classList.toggle('active', t.dataset.profileId === profileId);
    });
    await loadStoriesForProfile(profileId);
  }

  async function loadStoriesForProfile(profileId) {
    currentProfileId = profileId;
    try {
      const res = await fetch(`/api/stories/${profileId}`);
      const data = await res.json();
      allStories = data.stories || [];
      renderStories(allStories);
    } catch (e) {
      console.error('Failed to load stories:', e);
    }
  }

  function filterByTheme(theme) {
    currentThemeFilter = theme;
    document.querySelectorAll('#themeFilterChips .chip').forEach(c => {
      c.classList.toggle('selected', (c.dataset.theme || '') === theme);
    });
    const filtered = theme
      ? allStories.filter(s => s.theme === theme)
      : allStories;
    renderStories(filtered);
  }

  function renderStories(stories) {
    const grid = document.getElementById('storiesGrid');
    const empty = document.getElementById('libraryEmpty');
    if (!grid) return;

    if (stories.length === 0) {
      grid.innerHTML = '';
      empty && empty.classList.remove('hidden');
      return;
    }

    empty && empty.classList.add('hidden');

    grid.innerHTML = stories.map(s => {
      const emoji = App.themeEmoji(s.theme);
      const date = App.formatDate(s.created_at);
      const chars = (s.characters || []).map(c => c.name).filter(n => n).join(', ');

      return `
        <div class="story-card" onclick="window.location.href='/story/${s.id}'" role="button" tabindex="0"
             onkeydown="if(event.key==='Enter') window.location.href='/story/${s.id}'">
          <span class="story-card-emoji">${emoji}</span>
          <div class="story-card-title">${App.escapeHtml(s.title)}</div>
          <div class="story-card-moral">${App.escapeHtml(s.moral || 'A magical adventure…')}</div>
          <div class="story-card-meta">
            <span>${chars ? '🎭 ' + App.escapeHtml(chars) : ''}</span>
            <span>📅 ${date}</span>
          </div>
          <div style="margin-top:0.75rem; display:flex; gap:0.4rem; flex-wrap:wrap;">
            <span class="story-badge" style="font-size:0.75rem;">${App.ageLabel(s.age_group)}</span>
            <span class="story-badge" style="font-size:0.75rem;">${App.escapeHtml(s.theme || '')}</span>
          </div>
        </div>
      `;
    }).join('');
  }

  function renderEmptyState() {
    const grid = document.getElementById('storiesGrid');
    const empty = document.getElementById('libraryEmpty');
    if (grid) grid.innerHTML = '';
    if (empty) empty.classList.remove('hidden');
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('libraryMain') !== null) {
      init();
    }
  });

  return { init, switchProfile, filterByTheme };
})();


const Dashboard = (() => {
  let allStories = [];
  let filteredStories = [];

  async function init() {
    // Wait for App's /api/me check before checking auth state (race condition fix)
    await App.authReady;

    if (!App.isAuthenticated()) {
      const notice = document.getElementById('dashAuthNotice');
      if (notice) notice.classList.remove('hidden');
      return;
    }

    const content = document.getElementById('dashContent');
    if (content) content.classList.remove('hidden');

    await loadData();
    await loadAiStatus();
  }

  async function loadAiStatus() {
    const container = document.getElementById('aiStatusContainer');
    const dot = document.getElementById('aiStatusDot');
    const text = document.getElementById('aiStatusText');

    if (!container || !dot || !text) return;

    try {
      const res = await fetch('/api/ai-status');
      const data = await res.json();

      container.classList.remove('hidden');

      if (data.token_valid) {
        dot.className = 'status-dot online';
        text.textContent = `AI Painter: Online (${data.token_user})`;
        text.title = `Models in pool: ${data.paint_pool_models.join(', ')}`;
      } else {
        dot.className = 'status-dot offline';
        text.textContent = `AI Painter: Offline (${data.token_error || 'Check Space Secrets'})`;
        text.title = 'Hugging Face Token is missing or invalid. Check your Space Settings.';
        App.showToast('warning', 'AI Painter is offline. Check Space Secrets for HF_TOKEN.');
      }
    } catch (e) {
      console.error('Failed to fetch AI status:', e);
      dot.className = 'status-dot warning';
      text.textContent = 'AI Painter: Connection Error';
    }
  }

  async function runAiTest() {
    const btn = document.getElementById('btnRunAiTest');
    if (!btn) return;

    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '🕒 Painting...';
    
    App.showToast('info', 'Starting AI Painter test... please wait about 15-20s.');

    try {
      const res = await fetch('/api/test-paint');
      const data = await res.json();

      if (data.success) {
        App.showToast('success', `Success! Illustration generated: ${data.image_url}`);
        if (confirm('AI Painter test successful! Would you like to view the test illustration?')) {
          window.open(data.full_path, '_blank');
        }
      } else {
        App.showToast('error', `Test Failed: ${data.message}`);
        console.error('AI Test Failure Details:', data);
        
        let auditMsg = `AI Painter Test Failed.\n\nERROR: ${data.message}\n\nDETAILED AUDIT LOG:\n`;
        if (data.audit_log) {
          data.audit_log.forEach(log => {
            auditMsg += `• [${log.model}] Status: ${log.status} - ${log.message}\n`;
          });
        }
        auditMsg += `\nHint: ${data.hint}`;
        
        alert(auditMsg);
      }
    } catch (e) {
      console.error('AI Test Error:', e);
      App.showToast('error', 'Critical Error: Could not connect to the diagnostic endpoint.');
    } finally {
      btn.disabled = false;
      btn.innerHTML = originalText;
    }
  }

  async function loadData() {
    try {
      const res = await fetch('/api/dashboard');
      const data = await res.json();

      if (!res.ok) {
        App.showToast('error', data.error || 'Failed to load dashboard');
        return;
      }

      const stats = data.stats || {};
      allStories = data.stories || [];
      filteredStories = [...allStories];

      renderStats(stats);
      renderBreakdowns(stats);
      renderProfileProgress(data.profiles_ml || []);
      renderStories(allStories);
    } catch (e) {
      console.error('Dashboard load error:', e);
    }
  }

  function renderStats(stats) {
    const setNum = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.textContent = val;
    };

    setNum('statStories', stats.total_stories || 0);
    setNum('statProfiles', stats.profile_count || 0);
    setNum('statThemes', Object.keys(stats.theme_counts || {}).length);
    setNum('statSettings', Object.keys(stats.setting_counts || {}).length);
  }

  // ── Vocabulary / Reader Progress ────────────────────────────────────────
  function renderProfileProgress(profilesML) {
    const section = document.getElementById('readerProgress');
    const container = document.getElementById('profileProgressCards');
    if (!section || !container || profilesML.length === 0) return;

    section.style.display = 'block';

    const hintMeta = {
      introductory: { label: 'Simple',      color: '#10b981', pct: 33  },
      grade_level:  { label: 'Grade Level', color: '#6366f1', pct: 60  },
      stretch:      { label: 'Advanced',    color: '#a855f7', pct: 90  },
      '':           { label: '—',           color: '#4b5563', pct: 50  },
    };

    container.innerHTML = profilesML.map(p => {
      const vocabPct   = Math.round((p.vocabulary_score / 10) * 100);
      const levelMeta  = hintMeta[p.vocabulary_hint] || hintMeta[''];
      const qaPct      = Math.round((p.question_accuracy || 0) * 100);

      // Mini progression chart — SVG bars (oldest → newest)
      const prog = p.vocab_progression || [];
      const bars = prog.map((item, i) => {
        const meta  = hintMeta[item.vocabulary_hint] || hintMeta[''];
        const h     = meta.pct;           // bar height %
        const x     = (i / Math.max(prog.length, 1)) * 100;
        const w     = Math.max(4, 90 / Math.max(prog.length, 1));
        const title = App.escapeHtml(`${item.title} — ${meta.label}`);
        return `<rect x="${x.toFixed(1)}%" y="${100 - h}%" width="${(w - 1).toFixed(1)}%"
          height="${h}%" fill="${meta.color}" rx="2" opacity="0.9">
          <title>${title}</title></rect>`;
      }).join('');

      const svgChart = prog.length > 0
        ? `<svg viewBox="0 0 100 40" preserveAspectRatio="none" style="width:100%;height:48px;display:block;">${bars}</svg>`
        : `<p class="vocab-no-data">Generate stories to see vocabulary progression</p>`;

      const coldNote = p.is_cold_start
        ? `<p class="vocab-cold-start">🌱 Building profile — ${p.total_stories_completed}/3 stories for personalised recommendations</p>`
        : '';

      return `
        <div class="vocab-progress-card">
          <div class="vocab-card-header">
            <div class="profile-avatar" style="background:${p.avatar_color}; width:36px; height:36px; font-size:1rem; border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:700; flex-shrink:0;">
              ${App.escapeHtml(p.profile_name[0].toUpperCase())}
            </div>
            <div style="flex:1; min-width:0;">
              <div style="font-weight:700; font-size:1rem;">${App.escapeHtml(p.profile_name)}</div>
              <div class="text-small text-muted">${App.ageLabel(p.age_group)}</div>
            </div>
            <span class="vocab-level-badge" style="background:${levelMeta.color}22; color:${levelMeta.color}; border:1px solid ${levelMeta.color}44;">
              ${levelMeta.label}
            </span>
          </div>

          <div class="vocab-score-row">
            <span class="vocab-score-label">📖 Vocabulary Score</span>
            <span class="vocab-score-value">${p.vocabulary_score.toFixed(1)} / 10</span>
          </div>
          <div class="vocab-bar-track">
            <div class="vocab-bar-fill" style="width:${vocabPct}%; background:${levelMeta.color};"></div>
          </div>

          <div class="vocab-meta-grid">
            <div class="vocab-meta-item">
              <span class="vocab-meta-icon">📚</span>
              <div>
                <div class="vocab-meta-value">${p.reading_level_label}</div>
                <div class="vocab-meta-key">Reading Level</div>
              </div>
            </div>
            <div class="vocab-meta-item">
              <span class="vocab-meta-icon">✅</span>
              <div>
                <div class="vocab-meta-value">${qaPct}%</div>
                <div class="vocab-meta-key">Question Accuracy</div>
              </div>
            </div>
            <div class="vocab-meta-item">
              <span class="vocab-meta-icon">🏆</span>
              <div>
                <div class="vocab-meta-value">${p.total_stories_completed}</div>
                <div class="vocab-meta-key">Stories Finished</div>
              </div>
            </div>
          </div>

          ${coldNote}

          <div class="vocab-progression-section">
            <div class="vocab-progression-label">Story Vocabulary Progression</div>
            <div class="vocab-progression-legend">
              <span style="color:#10b981;">■ Simple</span>
              <span style="color:#6366f1;">■ Grade Level</span>
              <span style="color:#a855f7;">■ Advanced</span>
            </div>
            <div class="vocab-chart-wrap">${svgChart}</div>
          </div>
        </div>
      `;
    }).join('');
  }

  function renderBreakdowns(stats) {
    // Theme breakdown
    const themeEl = document.getElementById('themeBreakdown');
    if (themeEl) {
      const counts = stats.theme_counts || {};
      const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
      const sorted = Object.entries(counts).sort(([, a], [, b]) => b - a);

      if (sorted.length === 0) {
        themeEl.innerHTML = `<p class="text-muted text-small">No stories yet.</p>`;
      } else {
        themeEl.innerHTML = sorted.map(([theme, count]) => {
          const pct = Math.round((count / total) * 100);
          return `
            <div style="margin-bottom:0.75rem;">
              <div style="display:flex; justify-content:space-between; margin-bottom:0.3rem;">
                <span style="font-size:0.9rem; font-weight:600;">${App.themeEmoji(theme)} ${App.escapeHtml(theme)}</span>
                <span class="text-small text-muted">${count} ${count === 1 ? 'story' : 'stories'}</span>
              </div>
              <div style="background:var(--color-surface-2); border-radius:999px; height:8px; overflow:hidden;">
                <div style="background:var(--grad-primary); height:100%; width:${pct}%; border-radius:999px; transition: width 0.6s ease;"></div>
              </div>
            </div>
          `;
        }).join('');
      }
    }

    // Age breakdown
    const ageEl = document.getElementById('ageBreakdown');
    if (ageEl) {
      const counts = stats.age_counts || {};
      const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
      const ageConfig = [
        { key: '3-5', label: '🐣 Ages 3–5', color: '#10b981' },
        { key: '6-8', label: '🌱 Ages 6–8', color: '#6366f1' },
        { key: '9-12', label: '🌳 Ages 9–12', color: '#a855f7' }
      ];

      ageEl.innerHTML = ageConfig.map(({ key, label, color }) => {
        const count = counts[key] || 0;
        const pct = Math.round((count / total) * 100);
        return `
          <div style="margin-bottom:0.75rem;">
            <div style="display:flex; justify-content:space-between; margin-bottom:0.3rem;">
              <span style="font-size:0.9rem; font-weight:600;">${label}</span>
              <span class="text-small text-muted">${count} ${count === 1 ? 'story' : 'stories'}</span>
            </div>
            <div style="background:var(--color-surface-2); border-radius:999px; height:8px; overflow:hidden;">
              <div style="background:${color}; height:100%; width:${pct}%; border-radius:999px; transition: width 0.6s ease;"></div>
            </div>
          </div>
        `;
      }).join('');
    }
  }

  function renderStories(stories) {
    const listEl = document.getElementById('dashStoriesList');
    const emptyEl = document.getElementById('dashEmpty');

    if (!listEl) return;

    if (stories.length === 0) {
      listEl.innerHTML = '';
      emptyEl && emptyEl.classList.remove('hidden');
      return;
    }

    emptyEl && emptyEl.classList.add('hidden');

    listEl.innerHTML = stories.map(s => {
      const date = App.formatDate(s.created_at);
      const chars = (s.characters || []).map(c => c.name).filter(n => n).join(', ');

      return `
        <div class="dashboard-story-row" onclick="window.location.href='/story/${s.id}'" role="button" tabindex="0">
          <span style="font-size:1.5rem;">${App.themeEmoji(s.theme)}</span>
          <div style="flex:1; min-width:0;">
            <div style="font-weight:700; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
              ${App.escapeHtml(s.title)}
            </div>
            <div class="text-small text-muted">
              ${chars ? '🎭 ' + App.escapeHtml(chars) + ' · ' : ''}
              📅 ${date}
            </div>
          </div>
          <div class="dashboard-profile-badge">
            <div class="profile-avatar" style="background:${s.avatar_color}; width:24px; height:24px; font-size:0.7rem;">
              ${s.profile_name ? App.escapeHtml(s.profile_name[0].toUpperCase()) : '?'}
            </div>
            <span class="text-small" style="color:var(--text-secondary);">${App.escapeHtml(s.profile_name || '')}</span>
          </div>
          <span class="story-badge" style="font-size:0.75rem; white-space:nowrap;">${App.escapeHtml(s.theme || '')}</span>
        </div>
      `;
    }).join('');
  }

  function filterStories(query) {
    const q = query.toLowerCase().trim();
    filteredStories = q
      ? allStories.filter(s =>
          s.title.toLowerCase().includes(q) ||
          (s.theme || '').toLowerCase().includes(q) ||
          (s.profile_name || '').toLowerCase().includes(q) ||
          (s.characters || []).some(c => c.name.toLowerCase().includes(q))
        )
      : [...allStories];
    renderStories(filteredStories);
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('dashContent') !== null) {
      init();
    }
  });

  return { init, filterStories, runAiTest };
})();
