// Presentation-only clock check. Fetching and generation remain pure Python.
const stamp = document.getElementById('snapshot-time');
if (stamp && Date.now() - Date.parse(stamp.dateTime) > 72 * 3600000) {
  document.getElementById('stale-warning').hidden = false;
  document.querySelectorAll('.status.observed').forEach(el => {
    el.textContent = '旧记录 · 待核验';
    el.className = 'status stale';
  });
}
