// ── ClipSlop Main JS ─────────────────────────────────────────────────────

// Update queue badge from stats
async function refreshStats() {
  try {
    const res  = await fetch('/api/stats');
    const data = await res.json();
    const badge = document.getElementById('queue-count');
    if (badge) badge.textContent = data.pending_review ?? 0;
  } catch (e) { /* silent */ }
}

// Fetch clips from Twitch + Kick
async function fetchClips() {
  const btn = document.getElementById('fetch-btn') || document.querySelector('[onclick="fetchClips()"]');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Fetching...'; }

  try {
    const res  = await fetch('/api/fetch-clips', { method: 'POST' });
    const data = await res.json();

    if (data.errors && data.errors.length > 0) {
      showToast('⚠ ' + data.errors.join(' | '), 'error');
    } else if (data.new_clips === 0) {
      showToast('No new clips found (all already fetched)', 'info');
    } else {
      showToast(`✓ Fetched ${data.new_clips} new clip${data.new_clips !== 1 ? 's' : ''}!`, 'success');
      setTimeout(() => location.reload(), 1200);
    }
  } catch (e) {
    showToast('Fetch failed: ' + e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '⬇ Fetch Clips'; }
  }
}

// Stub: replaced in Parts 4-6
function uploadAll() {
  showToast('↑ Upload pipeline coming in Parts 4–6!', 'info');
}

// ── Toast Notifications ───────────────────────────────────────────────────
function showToast(msg, type = 'info') {
  const existing = document.getElementById('cf-toast');
  if (existing) existing.remove();

  const colors = { success: '#53fc18', error: '#ef4444', info: '#f97316' };
  const t = document.createElement('div');
  t.id = 'cf-toast';
  t.textContent = msg;
  Object.assign(t.style, {
    position:   'fixed',
    bottom:     '28px',
    right:      '28px',
    background: '#1e1e26',
    border:     `1px solid ${colors[type] ?? colors.info}`,
    color:      '#f0eee8',
    padding:    '12px 20px',
    borderRadius: '10px',
    fontFamily: "'Syne', sans-serif",
    fontSize:   '13px',
    fontWeight: '600',
    boxShadow:  '0 0 20px rgba(0,0,0,0.4)',
    zIndex:     '9999',
    animation:  'fadeUp 0.25s ease',
  });
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

// ── Init ──────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  refreshStats();
  setInterval(refreshStats, 15000);
});

// ── Scheduler badge on sidebar (optional future use) ──────────────────────
async function pollScheduler() {
  try {
    const res  = await fetch('/api/scheduler/status');
    const data = await res.json();
    // Update queue badge with pending count from stats
    const statsRes  = await fetch('/api/stats');
    const statsData = await statsRes.json();
    const badge = document.getElementById('queue-count');
    if (badge) badge.textContent = statsData.pending_review ?? 0;
  } catch(e) {}
}

// Poll every 30s to keep stats fresh during long uploads/runs
setInterval(pollScheduler, 30000);
