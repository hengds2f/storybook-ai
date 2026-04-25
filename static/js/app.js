/**
 * app.js — Global application orchestration
 * Handles: auth state, auth modal, toast notifications, navbar dynamic rendering
 */

const App = (() => {
  let currentUser = null;
  let authModalTab = 'login';

  // ── Auth-ready promise ─────────────────────────────────────────────────
  // Resolves the moment auth state is known (synchronously from INITIAL_AUTH).
  let _authReadyResolve;
  const authReady = new Promise(resolve => { _authReadyResolve = resolve; });

  // ── Init ────────────────────────────────────────────────────────────────
  function init() {
    const prevAuth = isAuthenticated();

    // 1. Read server-injected session state SYNCHRONOUSLY — no fetch needed.
    //    Flask bakes window.INITIAL_AUTH into every HTML response from the
    //    session cookie, so we know auth state before any JS runs.
    if (window.INITIAL_AUTH) {
      currentUser = window.INITIAL_AUTH;
    } else {
      currentUser = null;
    }

    // Resolve authReady immediately — page-specific scripts can now check
    // isAuthenticated() without any async wait.
    _authReadyResolve();

    renderNavbar();
    highlightActiveNav();
    initHamburger();

    // 2. Background refresh: silently re-validate the session with the server.
    //    This keeps the client in sync if the session expires between page loads.
    const initialId = currentUser ? currentUser.id : null;

    checkAuth().then(() => {
      const newId = currentUser ? currentUser.id : null;
      // ONLY re-render if the state actually changed. This prevents "flickering"
      // if the background fetch fails or acts differently than the initial load.
      if (initialId !== newId) {
        renderNavbar();
      }
    });
  }

  async function checkAuth() {
    try {
      const res = await fetch('/api/me');
      if (!res.ok) return; // Ignore server errors during background refresh

      const data = await res.json();
      if (data.authenticated) {
        currentUser = { id: data.user_id, username: data.username };
      } else {
        // If the server says we're not authenticated, but we HAD a user from INITIAL_AUTH,
        // we might be in an iframe with third-party cookies blocked for AJAX but not the page request.
        // For now, we trust the server's word if it's a valid JSON response.
        currentUser = null;
      }
    } catch (e) {
      // Network error (e.g. offline) — keep existing state from INITIAL_AUTH
      console.warn('Background auth check failed:', e);
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
        currentUser = { id: data.user_id, username: data.username };
        closeAuthModal();
        renderNavbar();
        showToast('success', `Welcome back, ${data.username}! 👋`);
        // Navigate to /app — session cookie is fresh, builder will load correctly
        setTimeout(() => { window.location.href = '/app'; }, 700);
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
        currentUser = { id: data.user_id, username: data.username };
        closeAuthModal();
        renderNavbar();
        showToast('success', `Welcome, ${data.username}! Let’s create your first story 🎉`);
        // Navigate to /app — session cookie is fresh, builder will load correctly
        setTimeout(() => { window.location.href = '/app'; }, 700);
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
  function showStoryLoading(subtext = '', progress = null) {
    const el = document.getElementById('storyLoadingOverlay');
    if (!el) return;
    el.classList.add('visible');
    
    if (subtext) {
      const sub = document.getElementById('storyLoadingSubtext');
      if (sub) sub.textContent = subtext;
    }
    
    if (progress !== null) {
      const bar = document.getElementById('storyProgressBar');
      if (bar) bar.style.width = `${progress}%`;
    }
  }

  function hideStoryLoading() {
    const el = document.getElementById('storyLoadingOverlay');
    if (el) {
      el.classList.remove('visible');
      // Reset progress for next time
      const bar = document.getElementById('storyProgressBar');
      if (bar) bar.style.width = '0%';
    }
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

  // ── Hamburger / Mobile Nav ─────────────────────────────────────────────
  function initHamburger() {
    const btn = document.getElementById('hamburgerBtn');
    if (!btn) return;
    btn.addEventListener('click', toggleMobileNav);
  }

  function toggleMobileNav() {
    const btn = document.getElementById('hamburgerBtn');
    const nav = document.getElementById('mobileNav');
    const overlay = document.getElementById('mobileNavOverlay');
    if (!btn || !nav) return;
    const isOpen = nav.classList.toggle('open');
    overlay && overlay.classList.toggle('open', isOpen);
    btn.classList.toggle('open', isOpen);
    btn.setAttribute('aria-expanded', isOpen);
  }

  function closeMobileNav() {
    const btn = document.getElementById('hamburgerBtn');
    const nav = document.getElementById('mobileNav');
    const overlay = document.getElementById('mobileNavOverlay');
    if (!nav) return;
    nav.classList.remove('open');
    overlay && overlay.classList.remove('open');
    btn && btn.classList.remove('open');
    btn && btn.setAttribute('aria-expanded', 'false');
  }

  // ── Boot ───────────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', init);

  return {
    init, checkAuth, getCurrentUser, isAuthenticated, authReady,
    openAuthModal, closeAuthModal, switchAuthTab,
    handleLogin, handleRegister, logout, onCreateStory,
    showToast, showStoryLoading, hideStoryLoading,
    escapeHtml, formatDate, themeEmoji, settingEmoji, ageLabel,
    closeMobileNav, toggleMobileNav
  };
})();
