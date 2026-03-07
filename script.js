// Configuration
const GITHUB_RELEASE_URL = 'https://github.com/abhijitreang/GridDock/releases';

// DOM Ready
document.addEventListener('DOMContentLoaded', () => {
  initParticles();
  initNavigation();
  initModal();
  initScrollAnimations();
  initCitation();
});

// Confetti Particle System
function initParticles() {
  const canvas = document.getElementById('particle-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  let particles = [];
  const COLORS = [
    '#1a73e8', '#7c3aed', '#ef4444', '#f59e0b',
    '#10b981', '#ec4899', '#6366f1', '#f97316',
    '#06b6d4', '#8b5cf6'
  ];

  function resize() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
  }

  function createParticles() {
    particles = [];
    const count = Math.floor((canvas.width * canvas.height) / 18000);
    for (let i = 0; i < count; i++) {
      particles.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        size: Math.random() * 4 + 1.5,
        color: COLORS[Math.floor(Math.random() * COLORS.length)],
        speedX: (Math.random() - 0.5) * 0.3,
        speedY: (Math.random() - 0.5) * 0.3,
        rotation: Math.random() * 360,
        rotSpeed: (Math.random() - 0.5) * 2,
        shape: Math.random() > 0.5 ? 'circle' : 'rect',
        opacity: Math.random() * 0.5 + 0.25,
      });
    }
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    particles.forEach(p => {
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate((p.rotation * Math.PI) / 180);
      ctx.globalAlpha = p.opacity;
      ctx.fillStyle = p.color;

      if (p.shape === 'circle') {
        ctx.beginPath();
        ctx.arc(0, 0, p.size, 0, Math.PI * 2);
        ctx.fill();
      } else {
        ctx.fillRect(-p.size, -p.size * 0.4, p.size * 2, p.size * 0.8);
      }

      ctx.restore();

      // Move
      p.x += p.speedX;
      p.y += p.speedY;
      p.rotation += p.rotSpeed;

      // Wrap around
      if (p.x < -10) p.x = canvas.width + 10;
      if (p.x > canvas.width + 10) p.x = -10;
      if (p.y < -10) p.y = canvas.height + 10;
      if (p.y > canvas.height + 10) p.y = -10;
    });

    requestAnimationFrame(draw);
  }

  resize();
  createParticles();
  draw();

  window.addEventListener('resize', () => {
    resize();
    createParticles();
  });
}

// Navigation
function initNavigation() {
  const hamburger = document.getElementById('nav-hamburger');
  const navLinks = document.getElementById('nav-links');

  if (hamburger && navLinks) {
    hamburger.addEventListener('click', () => {
      navLinks.classList.toggle('open');
      hamburger.setAttribute('aria-expanded',
        navLinks.classList.contains('open') ? 'true' : 'false'
      );
    });

    // Close mobile nav on link click
    navLinks.querySelectorAll('a').forEach(link => {
      link.addEventListener('click', () => {
        navLinks.classList.remove('open');
        hamburger.setAttribute('aria-expanded', 'false');
      });
    });
  }
}

// Download Modal
function initModal() {
  const overlay = document.getElementById('download-modal');
  if (!overlay) return;

  const modal = overlay.querySelector('.modal');
  const form = document.getElementById('download-form');
  const closeBtn = overlay.querySelector('.modal-close');

  // Open triggers
  document.querySelectorAll('[data-open-modal]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      openModal();
    });
  });

  // Close triggers
  closeBtn.addEventListener('click', closeModal);
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) closeModal();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
  });

  function openModal() {
    overlay.classList.add('open');
    document.body.style.overflow = 'hidden';
    // Focus first input after animation
    setTimeout(() => {
      const firstInput = form.querySelector('input');
      if (firstInput) firstInput.focus();
    }, 350);
  }

  function closeModal() {
    overlay.classList.remove('open');
    document.body.style.overflow = '';
  }

  // Form submission
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    if (!validateForm(form)) return;

    const data = {
      name: form.querySelector('#form-name').value.trim(),
      email: form.querySelector('#form-email').value.trim(),
      institute: form.querySelector('#form-institute').value.trim(),
      timestamp: new Date().toISOString(),
    };

    // Store submissions locally
    const submissions = JSON.parse(localStorage.getItem('GridDock_downloads') || '[]');
    submissions.push(data);
    localStorage.setItem('GridDock_downloads', JSON.stringify(submissions));

    // Show success then redirect
    const submitBtn = form.querySelector('.form-submit');
    submitBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Redirecting to download...';
    submitBtn.disabled = true;

    setTimeout(() => {
      window.open(GITHUB_RELEASE_URL, '_blank');
      closeModal();
      form.reset();
      submitBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Download GridDock';
      submitBtn.disabled = false;
    }, 1200);
  });
}

function validateForm(form) {
  let valid = true;
  const fields = [
    { id: 'form-name', msg: 'Please enter your full name' },
    { id: 'form-email', msg: 'Please enter a valid email address' },
    { id: 'form-institute', msg: 'Please enter your institute name' },
  ];

  fields.forEach(({ id, msg }) => {
    const input = form.querySelector(`#${id}`);
    const errorEl = input.nextElementSibling;
    const value = input.value.trim();

    if (!value) {
      input.classList.add('error');
      if (errorEl) {
        errorEl.textContent = msg;
        errorEl.style.display = 'block';
      }
      valid = false;
    } else if (id === 'form-email' && !isValidEmail(value)) {
      input.classList.add('error');
      if (errorEl) {
        errorEl.textContent = 'Please enter a valid email address';
        errorEl.style.display = 'block';
      }
      valid = false;
    } else {
      input.classList.remove('error');
      if (errorEl) errorEl.style.display = 'none';
    }
  });

  return valid;
}

function isValidEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

// Scroll Animations
function initScrollAnimations() {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
        }
      });
    },
    { threshold: 0.15, rootMargin: '0px 0px -40px 0px' }
  );

  document.querySelectorAll('.fade-in').forEach(el => observer.observe(el));
}

// Citation Tabs & Copy
function initCitation() {
  const tabs = document.querySelectorAll('.citation-tab');
  const apaContent = document.getElementById('citation-apa');
  const bibtexContent = document.getElementById('citation-bibtex');
  const copyBtn = document.getElementById('copy-citation');

  if (!tabs.length || !apaContent || !bibtexContent) return;

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');

      const format = tab.dataset.format;
      if (format === 'apa') {
        apaContent.style.display = 'block';
        bibtexContent.style.display = 'none';
      } else {
        apaContent.style.display = 'none';
        bibtexContent.style.display = 'block';
      }
    });
  });

  if (copyBtn) {
    copyBtn.addEventListener('click', () => {
      const activeTab = document.querySelector('.citation-tab.active');
      const format = activeTab ? activeTab.dataset.format : 'apa';
      let text;

      if (format === 'apa') {
        text = apaContent.textContent.trim();
      } else {
        text = bibtexContent.querySelector('pre').textContent.trim();
      }

      navigator.clipboard.writeText(text).then(() => {
        copyBtn.classList.add('copied');
        const originalHTML = copyBtn.innerHTML;
        copyBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Copied!';
        setTimeout(() => {
          copyBtn.innerHTML = originalHTML;
          copyBtn.classList.remove('copied');
        }, 2000);
      });
    });
  }
}

// Live input validation (clear errors on type)
document.addEventListener('input', (e) => {
  if (e.target.matches('.form-group input')) {
    if (e.target.value.trim()) {
      e.target.classList.remove('error');
      const errorEl = e.target.nextElementSibling;
      if (errorEl) errorEl.style.display = 'none';
    }
  }
});
