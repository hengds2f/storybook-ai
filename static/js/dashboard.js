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
      renderMLOverview(data.ml_overview || {}, data.stats || {});
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

  // ── ML Intelligence Overview ─────────────────────────────────────────────
  function renderMLOverview(mlOverview, stats) {
    const section = document.getElementById('mlOverviewSection');
    if (!section) return;

    const totalStories = stats.total_stories || 0;
    if (totalStories === 0 && (mlOverview.total_learning_events || 0) === 0) return;

    section.style.display = 'block';

    // Model badge: rule_based vs sklearn
    const badge = document.getElementById('mlModelBadge');
    if (badge) {
      const personalised = mlOverview.profiles_personalised || 0;
      const total        = mlOverview.profiles_total || 0;
      badge.textContent  = personalised > 0 ? `${personalised}/${total} Profiles Personalised` : 'Building Profiles…';
    }

    // ML stat cards
    const cardsEl = document.getElementById('mlStatCards');
    if (cardsEl) {
      const mlStats = [
        { icon: '⚡', value: mlOverview.total_learning_events || 0, label: 'Learning Events', color: '#6366f1' },
        { icon: '❓', value: mlOverview.total_questions_answered || 0, label: 'Q&A Sessions', color: '#a855f7' },
        { icon: '📖', value: (mlOverview.avg_vocabulary_score || 0).toFixed(1) + ' / 10', label: 'Avg Vocab Score', color: '#10b981' },
        { icon: '📚', value: (mlOverview.avg_reading_level_score || 0).toFixed(1) + ' / 10', label: 'Avg Reading Level', color: '#3b82f6' },
        { icon: '💡', value: Math.round((mlOverview.avg_engagement_score || 0) * 100) + '%', label: 'Avg Engagement', color: '#f59e0b' },
        { icon: '✅', value: Math.round((mlOverview.avg_question_accuracy || 0) * 100) + '%', label: 'Q&A Accuracy', color: '#10b981' },
        { icon: '🎯', value: mlOverview.stories_ml_adjusted || 0, label: 'ML-Adapted Stories', color: '#ec4899' },
      ];
      cardsEl.innerHTML = mlStats.map(s => `
        <div style="background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08); border-radius:12px; padding:1rem; text-align:center;">
          <div style="font-size:1.6rem; margin-bottom:0.35rem;">${s.icon}</div>
          <div style="font-size:1.35rem; font-weight:800; color:${s.color};">${s.value}</div>
          <div style="font-size:0.72rem; color:var(--text-secondary); margin-top:0.2rem;">${s.label}</div>
        </div>
      `).join('');
    }

    // Complexity distribution
    const complexityEl = document.getElementById('complexityBreakdown');
    if (complexityEl) {
      const counts = mlOverview.complexity_counts || {};
      const total  = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
      const cfg = [
        { key: 'simple',   label: '🌱 Simple',   color: '#10b981', desc: 'Short sentences, basic vocabulary' },
        { key: 'moderate', label: '🌿 Moderate',  color: '#6366f1', desc: 'Mixed sentence lengths, some new words' },
        { key: 'rich',     label: '🌳 Rich',      color: '#a855f7', desc: 'Complex ideas, advanced vocabulary' },
      ];
      complexityEl.innerHTML = cfg.map(({ key, label, color, desc }) => {
        const count = counts[key] || 0;
        const pct   = Math.round((count / total) * 100);
        return `
          <div style="margin-bottom:0.9rem;">
            <div style="display:flex; justify-content:space-between; margin-bottom:0.2rem;">
              <span style="font-size:0.88rem; font-weight:600;">${label}</span>
              <span style="font-size:0.78rem; color:var(--text-secondary);">${count} ${count === 1 ? 'story' : 'stories'} (${pct}%)</span>
            </div>
            <div style="font-size:0.72rem; color:var(--text-muted); margin-bottom:0.3rem;">${desc}</div>
            <div style="background:var(--color-surface-2); border-radius:999px; height:7px; overflow:hidden;">
              <div style="background:${color}; height:100%; width:${pct}%; border-radius:999px; transition:width 0.6s ease;"></div>
            </div>
          </div>
        `;
      }).join('');
    }

    // Vocabulary hint distribution
    const vocabHintEl = document.getElementById('vocabHintBreakdown');
    if (vocabHintEl) {
      const counts = mlOverview.vocab_hint_counts || {};
      const total  = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
      const cfg = [
        { key: 'introductory', label: '🐣 Introductory', color: '#10b981', desc: 'Everyday words, no multi-syllable challenge' },
        { key: 'grade_level',  label: '📖 Grade Level',   color: '#6366f1', desc: '1–2 new words introduced with context clues' },
        { key: 'stretch',      label: '🚀 Stretch',       color: '#a855f7', desc: 'Richer vocabulary; meaning inferred from context' },
      ];
      vocabHintEl.innerHTML = cfg.map(({ key, label, color, desc }) => {
        const count = counts[key] || 0;
        const pct   = Math.round((count / total) * 100);
        return `
          <div style="margin-bottom:0.9rem;">
            <div style="display:flex; justify-content:space-between; margin-bottom:0.2rem;">
              <span style="font-size:0.88rem; font-weight:600;">${label}</span>
              <span style="font-size:0.78rem; color:var(--text-secondary);">${count} ${count === 1 ? 'story' : 'stories'} (${pct}%)</span>
            </div>
            <div style="font-size:0.72rem; color:var(--text-muted); margin-bottom:0.3rem;">${desc}</div>
            <div style="background:var(--color-surface-2); border-radius:999px; height:7px; overflow:hidden;">
              <div style="background:${color}; height:100%; width:${pct}%; border-radius:999px; transition:width 0.6s ease;"></div>
            </div>
          </div>
        `;
      }).join('');
    }
  }

  // ── Vocabulary / Reader Progress ────────────────────────────────────────
  function renderProfileProgress(profilesML) {
    const section = document.getElementById('readerProgress');
    const container = document.getElementById('profileProgressCards');
    if (!section || !container || profilesML.length === 0) return;

    section.style.display = 'block';

    const hintMeta = {
      introductory: { label: 'Simple',      color: '#10b981' },
      grade_level:  { label: 'Grade Level', color: '#6366f1' },
      stretch:      { label: 'Advanced',    color: '#a855f7' },
      '':           { label: '—',           color: '#4b5563' },
    };

    const engagementMeta = {
      high:    { color: '#10b981', icon: '🔥' },
      medium:  { color: '#6366f1', icon: '📗' },
      low:     { color: '#f59e0b', icon: '📙' },
      at_risk: { color: '#ef4444', icon: '⚠️' },
    };

    container.innerHTML = profilesML.map(p => {
      const vocabPct      = Math.round((p.vocabulary_score / 10) * 100);
      const readingPct    = Math.round((p.reading_level_score / 10) * 100);
      const levelMeta     = hintMeta[p.vocabulary_hint] || hintMeta[''];
      const engMeta       = engagementMeta[p.engagement_label] || engagementMeta['medium'];
      const qaPct         = Math.round((p.question_accuracy || 0) * 100);
      const completionPct = Math.round((p.completion_rate || 0) * 100);
      const speedText     = p.reading_speed_wpm ? `${Math.round(p.reading_speed_wpm)} wpm` : '—';

      // ── Vocabulary score trend line (SVG polyline) ──────────────────────
      const prog = p.vocab_progression || [];

      // Trend line: vocabulary_score over stories (1–10 scale → 0–100 svg coords)
      const trendPoints = prog
        .map((item, i) => {
          const score = item.vocabulary_score;
          if (score == null) return null;
          const x = prog.length > 1 ? (i / (prog.length - 1)) * 96 + 2 : 50;
          const y = 98 - ((score - 1) / 9) * 90;
          return `${x.toFixed(1)},${y.toFixed(1)}`;
        })
        .filter(Boolean);

      const trendLine = trendPoints.length >= 2
        ? `<polyline points="${trendPoints.join(' ')}" fill="none" stroke="${levelMeta.color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" opacity="0.9"/>`
        : '';

      const trendDots = trendPoints.map((pt, i) => {
        const [x, y] = pt.split(',');
        const item = prog.filter(it => it.vocabulary_score != null)[i];
        if (!item) return '';
        const title = App.escapeHtml(`${item.title} — Score: ${(item.vocabulary_score || 0).toFixed(1)}`);
        return `<circle cx="${x}" cy="${y}" r="2.5" fill="${levelMeta.color}" opacity="0.85"><title>${title}</title></circle>`;
      }).join('');

      // Horizontal grid lines at 25%, 50%, 75%
      const gridLines = [2.5, 5.5, 7.5].map(lvl => {
        const y = (98 - ((lvl - 1) / 9) * 90).toFixed(1);
        return `<line x1="0" y1="${y}" x2="100" y2="${y}" stroke="rgba(255,255,255,0.07)" stroke-width="0.5"/>`;
      }).join('');

      const svgTrend = prog.length > 0
        ? `<svg viewBox="0 0 100 40" preserveAspectRatio="none" style="width:100%;height:56px;display:block;">
            ${gridLines}${trendLine}${trendDots}
           </svg>`
        : `<p class="vocab-no-data">Generate stories to see vocabulary trend</p>`;

      // ── Vocab quiz score bars ─────────────────────────────────────────
      const quizBars = prog.map((item, i) => {
        const score = item.vocab_quiz_score;
        const h     = score != null ? Math.round(score * 100) : 15;
        const color = score == null  ? '#94a3b8'
                    : score >= 0.7   ? '#10b981'
                    : score >= 0.4   ? '#6366f1'
                    :                  '#ef4444';
        const x = (i / Math.max(prog.length, 1)) * 100;
        const w = Math.max(4, 90 / Math.max(prog.length, 1));
        const pctLabel = score != null ? `${Math.round(score * 100)}%` : 'No quiz';
        return `<rect x="${x.toFixed(1)}%" y="${100 - h}%" width="${(w - 1).toFixed(1)}%"
          height="${h}%" fill="${color}" rx="2" opacity="0.85">
          <title>${App.escapeHtml(item.title)} — ${pctLabel}</title></rect>`;
      }).join('');

      const svgQuiz = prog.length > 0
        ? `<svg viewBox="0 0 100 40" preserveAspectRatio="none" style="width:100%;height:40px;display:block;">${quizBars}</svg>`
        : '';

      // ── Radar / pentagon chart for 5 dimensions ─────────────────────
      const radarSvg = _buildRadarChart(
        [
          { label: 'Vocab',      value: p.vocabulary_score / 10 },
          { label: 'Reading',    value: p.reading_level_score / 10 },
          { label: 'Engagement', value: p.engagement_score },
          { label: 'Q&A',        value: p.question_accuracy },
          { label: 'Completion', value: p.completion_rate },
        ],
        p.avatar_color
      );

      const coldNote = p.is_cold_start
        ? `<p class="vocab-cold-start">🌱 Building profile — ${p.total_stories_completed}/3 stories for personalised recommendations</p>`
        : '';

      const tierBadge = p.reading_level_tier === 'sklearn'
        ? `<span style="font-size:0.65rem; background:rgba(168,85,247,0.15); color:#c084fc; border:1px solid rgba(168,85,247,0.3); border-radius:6px; padding:0.1rem 0.4rem;">sklearn</span>`
        : `<span style="font-size:0.65rem; background:rgba(99,102,241,0.12); color:#818cf8; border:1px solid rgba(99,102,241,0.25); border-radius:6px; padding:0.1rem 0.4rem;">rule-based</span>`;

      return `
        <div class="vocab-progress-card">
          <!-- Header -->
          <div class="vocab-card-header">
            <div class="profile-avatar" style="background:${p.avatar_color}; width:38px; height:38px; font-size:1rem; border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:700; flex-shrink:0;">
              ${App.escapeHtml(p.profile_name[0].toUpperCase())}
            </div>
            <div style="flex:1; min-width:0;">
              <div style="font-weight:700; font-size:1rem; display:flex; align-items:center; gap:0.4rem;">
                ${App.escapeHtml(p.profile_name)}
                ${tierBadge}
              </div>
              <div class="text-small text-muted">${App.ageLabel(p.age_group)}</div>
            </div>
            <span class="vocab-level-badge" style="background:${levelMeta.color}22; color:${levelMeta.color}; border:1px solid ${levelMeta.color}44;">
              ${levelMeta.label}
            </span>
          </div>

          <!-- Radar + key scores side by side -->
          <div style="display:flex; gap:1rem; align-items:flex-start; margin:1rem 0 0.5rem;">
            <div style="flex-shrink:0; width:110px;">${radarSvg}</div>
            <div style="flex:1; display:flex; flex-direction:column; gap:0.5rem;">

              <div>
                <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-bottom:0.2rem;">
                  <span>📖 Vocabulary</span>
                  <span style="font-weight:700; color:${levelMeta.color};">${p.vocabulary_score.toFixed(1)}/10</span>
                </div>
                <div style="background:var(--color-surface-2); border-radius:999px; height:5px; overflow:hidden;">
                  <div style="background:${levelMeta.color}; height:100%; width:${vocabPct}%; border-radius:999px;"></div>
                </div>
              </div>

              <div>
                <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-bottom:0.2rem;">
                  <span>📚 Reading Level</span>
                  <span style="font-weight:700; color:#3b82f6;">${p.reading_level_label}</span>
                </div>
                <div style="background:var(--color-surface-2); border-radius:999px; height:5px; overflow:hidden;">
                  <div style="background:#3b82f6; height:100%; width:${readingPct}%; border-radius:999px;"></div>
                </div>
              </div>

              <div style="display:flex; justify-content:space-between; font-size:0.8rem;">
                <span>${engMeta.icon} Engagement</span>
                <span style="font-weight:700; color:${engMeta.color}; text-transform:capitalize;">${p.engagement_label}</span>
              </div>

            </div>
          </div>

          <!-- Behaviour metrics grid -->
          <div class="vocab-meta-grid" style="grid-template-columns:repeat(4,1fr);">
            <div class="vocab-meta-item">
              <span class="vocab-meta-icon">✅</span>
              <div>
                <div class="vocab-meta-value">${qaPct}%</div>
                <div class="vocab-meta-key">Q&A Accuracy</div>
              </div>
            </div>
            <div class="vocab-meta-item">
              <span class="vocab-meta-icon">🔄</span>
              <div>
                <div class="vocab-meta-value">${completionPct}%</div>
                <div class="vocab-meta-key">Completion</div>
              </div>
            </div>
            <div class="vocab-meta-item">
              <span class="vocab-meta-icon">⚡</span>
              <div>
                <div class="vocab-meta-value">${speedText}</div>
                <div class="vocab-meta-key">Read Speed</div>
              </div>
            </div>
            <div class="vocab-meta-item">
              <span class="vocab-meta-icon">🏆</span>
              <div>
                <div class="vocab-meta-value">${p.total_stories_completed}</div>
                <div class="vocab-meta-key">Finished</div>
              </div>
            </div>
          </div>

          ${coldNote}

          <!-- Vocab score trend -->
          <div class="vocab-progression-section">
            <div class="vocab-progression-label">📈 Vocabulary Score Trend</div>
            <div class="vocab-chart-wrap">${svgTrend}</div>
          </div>

          <!-- Vocab quiz bars -->
          ${prog.length > 0 ? `
          <div class="vocab-progression-section" style="margin-top:0.75rem;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.3rem;">
              <div class="vocab-progression-label">Vocabulary Quiz Scores</div>
              <div class="vocab-progression-legend">
                <span style="color:#10b981;">■ 70%+</span>
                <span style="color:#6366f1;">■ 40-70%</span>
                <span style="color:#ef4444;">■ &lt;40%</span>
                <span style="color:#94a3b8;">■ N/A</span>
              </div>
            </div>
            <div class="vocab-chart-wrap">${svgQuiz}</div>
          </div>` : ''}
        </div>
      `;
    }).join('');
  }

  /** Build a simple pentagon radar SVG for 5 normalised dimensions (0–1). */
  function _buildRadarChart(dims, accentColor) {
    const cx = 50, cy = 50, r = 38;
    const n = dims.length;
    const step = (2 * Math.PI) / n;
    // Start at top (-π/2)
    const pts = dims.map((d, i) => {
      const angle = -Math.PI / 2 + i * step;
      const val = Math.max(0.05, Math.min(1, d.value || 0));
      return {
        ox: cx + r * Math.cos(angle),
        oy: cy + r * Math.sin(angle),
        vx: cx + r * val * Math.cos(angle),
        vy: cy + r * val * Math.sin(angle),
        label: d.label,
        value: d.value,
        angle,
      };
    });

    // Outer polygon
    const outerPoly = pts.map(p => `${p.ox.toFixed(1)},${p.oy.toFixed(1)}`).join(' ');
    // Inner filled polygon
    const innerPoly = pts.map(p => `${p.vx.toFixed(1)},${p.vy.toFixed(1)}`).join(' ');
    // Axis lines
    const axes = pts.map(p => `<line x1="${cx}" y1="${cy}" x2="${p.ox.toFixed(1)}" y2="${p.oy.toFixed(1)}" stroke="rgba(255,255,255,0.12)" stroke-width="0.8"/>`).join('');
    // Labels
    const labels = pts.map(p => {
      const lx = cx + (r + 9) * Math.cos(p.angle);
      const ly = cy + (r + 9) * Math.sin(p.angle);
      return `<text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="middle" dominant-baseline="central" font-size="7" fill="rgba(255,255,255,0.55)">${p.label}</text>`;
    }).join('');
    // Mid ring (50%)
    const midPts = pts.map(p => {
      const angle = p.angle;
      return `${(cx + r * 0.5 * Math.cos(angle)).toFixed(1)},${(cy + r * 0.5 * Math.sin(angle)).toFixed(1)}`;
    }).join(' ');

    return `<svg viewBox="0 0 100 100" style="width:110px;height:110px;">
      <polygon points="${outerPoly}" fill="none" stroke="rgba(255,255,255,0.12)" stroke-width="0.8"/>
      <polygon points="${midPts}" fill="none" stroke="rgba(255,255,255,0.07)" stroke-width="0.6" stroke-dasharray="2,2"/>
      ${axes}
      <polygon points="${innerPoly}" fill="${accentColor}" fill-opacity="0.25" stroke="${accentColor}" stroke-width="1.5" stroke-opacity="0.8"/>
      ${labels}
    </svg>`;
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

  return { init, filterStories, runAiTest, renderMLOverview };
})();
