/**
 * app.js — Global application orchestration
 * Handles: auth state, auth modal, toast notifications, navbar dynamic rendering
 */

const App = (() => {
  let currentUser = null;
  let authModalTab = 'login';

  // ── Auth-ready promise ─────────────────────────────────────────────────
  // Resolves once the initial /api/me check is complete.
  // Page-specific scripts (builder, dashboard) MUST await this before
  // calling isAuthenticated() to avoid the race condition.
  let _authReadyResolve;
  const authReady = new Promise(resolve => { _authReadyResolve = resolve; });

  // ── Init ────────────────────────────────────────────────────────────────
  async function init() {
    await checkAuth();
    _authReadyResolve();   // Signal that auth state is now known
    renderNavbar();
    highlightActiveNav();
  }

  async function checkAuth() {
    try {
      const res = await fetch('/api/me');
      const data = await res.json();
      if (data.authenticated) {
        currentUser = { id: data.user_id, username: data.username };
      } else {
        currentUser = null;
      }
    } catch (e) {
      currentUser = null;
    }
  }

  function getCurrentUser() { return currentUser; }
  function isAuthenticated() { return currentUser !== null; }

  // ── Navbar rendering ───────────────────────────────────────────────────
  function renderNavbar() {
    const authEl = document.getElementById('navbarAuth');
    if (!authEl) return;

    if (currentUser) {
      authEl.innerHTML = `
        <div style="display:flex; align-items:center; gap:0.75rem;">
          <span style="color:var(--text-secondary); font-size:0.9rem; font-weight:600;">
            👋 ${escapeHtml(currentUser.username)}
          </span>
          <button class="btn btn-ghost btn-sm" onclick="App.logout()">Sign Out</button>
        </div>
      `;
    } else {
      authEl.innerHTML = `
        <button class="btn btn-ghost btn-sm" onclick="App.openAuthModal('login')">Sign In</button>
        <button class="btn btn-primary btn-sm" onclick="App.openAuthModal('register')">Register</button>
      `;
    }
  }

  function highlightActiveNav() {
    const path = window.location.pathname;
    document.querySelectorAll('.nav-link').forEach(link => {
      link.classList.remove('active');
      const href = link.getAttribute('href');
      if (href && path.startsWith(href) && href !== '/') {
        link.classList.add('active');
      }
    });
  }

  // ── Auth Modal ─────────────────────────────────────────────────────────
  function openAuthModal(tab = 'login') {
    const overlay = document.getElementById('authModal');
    if (!overlay) return;
    overlay.classList.add('open');
    switchAuthTab(tab);
    document.addEventListener('keydown', onEscapeAuth);
  }

  function closeAuthModal() {
    const overlay = document.getElementById('authModal');
    if (overlay) overlay.classList.remove('open');
    document.removeEventListener('keydown', onEscapeAuth);
  }

  function onEscapeAuth(e) {
    if (e.key === 'Escape') closeAuthModal();
  }

  function switchAuthTab(tab) {
    authModalTab = tab;
    const loginForm = document.getElementById('loginForm');
    const registerForm = document.getElementById('registerForm');
    const tabLogin = document.getElementById('tabLogin');
    const tabRegister = document.getElementById('tabRegister');

    if (tab === 'login') {
      loginForm && loginForm.classList.remove('hidden');
      registerForm && registerForm.classList.add('hidden');
      tabLogin && tabLogin.classList.replace('btn-ghost', 'btn-primary');
      tabRegister && tabRegister.classList.replace('btn-primary', 'btn-ghost');
    } else {
      loginForm && loginForm.classList.add('hidden');
      registerForm && registerForm.classList.remove('hidden');
      tabLogin && tabLogin.classList.replace('btn-primary', 'btn-ghost');
      tabRegister && tabRegister.classList.replace('btn-ghost', 'btn-primary');
    }
  }

  async function handleLogin(e) {
    e.preventDefault();
    const username = document.getElementById('loginUsername').value.trim();
    const password = document.getElementById('loginPassword').value;
    const errEl = document.getElementById('loginError');
    const spinner = document.getElementById('loginSpinner');
    const btn = document.getElementById('loginSubmit');

    errEl.style.display = 'none';
    spinner.classList.remove('hidden');
    btn.disabled = true;

    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      const data = await res.json();

      if (res.ok) {
        currentUser = { username: data.username };
        closeAuthModal();
        await checkAuth();
        renderNavbar();
        showToast('success', `Welcome back, ${data.username}! 👋`);
        // Reload to re-run page-specific init with auth state now known
        // Stay on current page (so /app stays on /app)
        setTimeout(() => location.reload(), 600);
      } else {
        errEl.textContent = data.error || 'Login failed';
        errEl.style.display = 'block';
      }
    } catch (err) {
      errEl.textContent = 'Network error — please try again';
      errEl.style.display = 'block';
    } finally {
      spinner.classList.add('hidden');
      btn.disabled = false;
    }
  }

  async function handleRegister(e) {
    e.preventDefault();
    const username = document.getElementById('regUsername').value.trim();
    const password = document.getElementById('regPassword').value;
    const errEl = document.getElementById('registerError');
    const spinner = document.getElementById('registerSpinner');
    const btn = document.getElementById('registerSubmit');

    errEl.style.display = 'none';
    spinner.classList.remove('hidden');
    btn.disabled = true;

    try {
      const res = await fetch('/api/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      const data = await res.json();

      if (res.ok) {
        currentUser = { username: data.username };
        closeAuthModal();
        await checkAuth();
        renderNavbar();
        showToast('success', `Account created! Welcome, ${data.username}! 🎉`);
        // Stay on current page after register so user lands on /app if they registered there
        setTimeout(() => location.reload(), 600);
      } else {
        errEl.textContent = data.error || 'Registration failed';
        errEl.style.display = 'block';
      }
    } catch (err) {
      errEl.textContent = 'Network error — please try again';
      errEl.style.display = 'block';
    } finally {
      spinner.classList.add('hidden');
      btn.disabled = false;
    }
  }

  async function logout() {
    await fetch('/api/logout', { method: 'POST' });
    currentUser = null;
    renderNavbar();
    showToast('info', 'Signed out. See you soon! 👋');
    setTimeout(() => location.href = '/', 500);
  }

  // ── CTA handler ────────────────────────────────────────────────────────
  function onCreateStory() {
    if (isAuthenticated()) {
      window.location.href = '/app';
    } else {
      openAuthModal('register');
    }
  }

  // ── Toast Notifications ────────────────────────────────────────────────
  function showToast(type, message, duration = 4000) {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const icons = { success: '✅', error: '❌', info: 'ℹ️' };
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span>${icons[type] || 'ℹ️'}</span> <span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);

    // Trigger animation
    requestAnimationFrame(() => {
      requestAnimationFrame(() => toast.classList.add('show'));
    });

    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 400);
    }, duration);
  }

  // ── Story loading overlay ──────────────────────────────────────────────
  function showStoryLoading() {
    const el = document.getElementById('storyLoadingOverlay');
    if (el) el.classList.add('visible');
  }

  function hideStoryLoading() {
    const el = document.getElementById('storyLoadingOverlay');
    if (el) el.classList.remove('visible');
  }

  // ── Helpers ────────────────────────────────────────────────────────────
  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function formatDate(isoStr) {
    if (!isoStr) return '';
    const d = new Date(isoStr);
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  }

  function themeEmoji(theme) {
    const map = {
      friendship: '💛', courage: '🦁', honesty: '🌟', kindness: '💗',
      perseverance: '💪', sharing: '🎁', teamwork: '🏆',
      respect: '🌸', creativity: '🎨', curiosity: '🔭'
    };
    return map[theme] || '📖';
  }

  function settingEmoji(setting) {
    if (!setting) return '🌍';
    if (setting.includes('forest')) return '🌲';
    if (setting.includes('space')) return '🚀';
    if (setting.includes('underwater') || setting.includes('ocean')) return '🌊';
    if (setting.includes('castle') || setting.includes('medieval')) return '🏰';
    if (setting.includes('city')) return '🏙️';
    if (setting.includes('mountain')) return '⛰️';
    if (setting.includes('desert')) return '🏜️';
    if (setting.includes('robot')) return '🤖';
    if (setting.includes('cloud')) return '🌈';
    return '🌍';
  }

  function ageLabel(ageGroup) {
    return { '3-5': 'Ages 3–5', '6-8': 'Ages 6–8', '9-12': 'Ages 9–12' }[ageGroup] || 'Ages 6–8';
  }

  // Close modals on overlay click
  document.addEventListener('click', (e) => {
    if (e.target.id === 'authModal') closeAuthModal();
    if (e.target.id === 'authModalClose') closeAuthModal();
  });

  // ── Boot ───────────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', init);

  return {
    init, checkAuth, getCurrentUser, isAuthenticated, authReady,
    openAuthModal, closeAuthModal, switchAuthTab,
    handleLogin, handleRegister, logout, onCreateStory,
    showToast, showStoryLoading, hideStoryLoading,
    escapeHtml, formatDate, themeEmoji, settingEmoji, ageLabel
  };
})();
