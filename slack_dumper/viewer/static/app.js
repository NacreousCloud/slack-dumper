function openThread(group) {
  const panel = document.getElementById('thread-panel');
  const body = document.getElementById('thread-panel-body');
  panel.classList.remove('hidden');

  const replies = group.replies || [];
  const rootMsg = group.msg;

  const renderMsg = (msg) => `
    <div class="thread-msg">
      <div class="avatar-col">
        ${msg.avatar_url
          ? `<img class="avatar" src="${msg.avatar_url}" alt="">`
          : `<div class="avatar avatar-fallback">${(msg.display_name || msg.user_id || '?')[0].toUpperCase()}</div>`
        }
      </div>
      <div class="thread-msg-content msg-content">
        <div class="msg-meta">
          <span class="msg-username">${msg.display_name || msg.user_id || '알 수 없음'}</span>
          <span class="msg-time">${msg.fmt_ts || ''}</span>
        </div>
        <div class="msg-text">${(msg.text || '').replace(/\n/g, '<br>')}</div>
      </div>
    </div>
  `;

  body.innerHTML = `
    <div style="border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:16px; margin-bottom:16px;">
      ${renderMsg(rootMsg)}
    </div>
    ${replies.map(renderMsg).join('')}
    <div style="color:#9b9b9b; font-size:12px; margin-top:8px;">${replies.length}개의 댓글</div>
  `;
}

function closeThread() {
  document.getElementById('thread-panel').classList.add('hidden');
}

const searchInput = document.getElementById('global-search');
const searchResults = document.getElementById('search-results');

if (searchInput) {
  let timer;
  searchInput.addEventListener('input', () => {
    clearTimeout(timer);
    const q = searchInput.value.trim();
    if (q.length < 2) { searchResults.classList.add('hidden'); return; }
    timer = setTimeout(async () => {
      const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
      const items = await res.json();
      if (!items.length) { searchResults.classList.add('hidden'); return; }
      searchResults.innerHTML = items.map(item => `
        <div class="search-result-item" onclick="location.href='/channel/${item.channel_id}'">
          <div class="search-result-channel">#${item.channel_name || item.channel_id}</div>
          <div class="search-result-text">${item.text?.slice(0, 80) || ''}</div>
        </div>
      `).join('');
      searchResults.classList.remove('hidden');
    }, 300);
  });

  document.addEventListener('click', (e) => {
    if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) {
      searchResults.classList.add('hidden');
    }
  });
}

window.addEventListener('load', () => {
  const area = document.getElementById('messages-area');
  if (area) area.scrollTop = area.scrollHeight;
});
