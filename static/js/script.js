/**
 * script.js - PlacementAI Frontend Logic
 * College Placement Prediction System
 */

// ── Theme Toggle ───────────────────────────────
function toggleTheme() {
  const html = document.documentElement;
  const current = html.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  const icon = document.getElementById('themeIcon');
  if (icon) icon.className = next === 'dark' ? 'fas fa-moon' : 'fas fa-sun';
}

// Restore theme on load
(function() {
  const saved = localStorage.getItem('theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
  window.addEventListener('DOMContentLoaded', () => {
    const icon = document.getElementById('themeIcon');
    if (icon) icon.className = saved === 'dark' ? 'fas fa-moon' : 'fas fa-sun';
  });
})();

// ── Active Nav Link ────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const links = document.querySelectorAll('.nav-link');
  const path  = window.location.pathname;
  links.forEach(l => {
    if (l.getAttribute('href') === path) l.classList.add('active');
  });

  // Auto-dismiss flash messages after 4 s
  setTimeout(() => {
    document.querySelectorAll('#flash-container .alert').forEach(a => {
      const bs = bootstrap.Alert.getOrCreateInstance(a);
      bs.close();
    });
  }, 4000);

  // Animate number counters
  document.querySelectorAll('.stat-num,.kpi-val').forEach(el => {
    const target = parseFloat(el.textContent);
    if (isNaN(target)) return;
    let start = 0;
    const step = target / 40;
    const timer = setInterval(() => {
      start = Math.min(start + step, target);
      el.textContent = Number.isInteger(target) ? Math.round(start) : start.toFixed(2);
      if (start >= target) clearInterval(timer);
    }, 20);
  });

  // Form validation
  document.querySelectorAll('form[novalidate]').forEach(form => {
    form.addEventListener('submit', e => {
      if (!form.checkValidity()) {
        e.preventDefault();
        e.stopPropagation();
        form.querySelectorAll(':invalid').forEach(inp => {
          inp.classList.add('is-invalid');
          inp.addEventListener('input', () => inp.classList.remove('is-invalid'), { once: true });
        });
      }
      form.classList.add('was-validated');
    });
  });
});
