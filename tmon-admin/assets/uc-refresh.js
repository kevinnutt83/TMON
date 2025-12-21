(function(){
	// ...small, dependency-free module...
	function makeSpinner() {
		var s = document.createElement('span');
		s.className = 'tmon-spinner';
		s.textContent = '⟳'; // simple spinner glyph
		s.style.marginLeft = '6px';
		return s;
	}
	function setStatus(el, text, cls) {
		try {
			el.textContent = text;
			el.className = 'tmon-uc-refresh-status ' + (cls || '');
		} catch(e){}
	}
	function findCountSpan(site) {
		return document.querySelector('.tmon-dev-count[data-site="'+site+'"]');
	}
	function onClick(e) {
		var btn = e.currentTarget;
		var site = btn.getAttribute('data-site') || '';
		if (!site) return;
		var statusEl = btn.parentNode.querySelector('.tmon-uc-refresh-status');
		var countEl = findCountSpan(site);
		// disable button and show spinner
		btn.disabled = true;
		var spin = makeSpinner();
		statusEl.innerHTML = '';
		statusEl.appendChild(spin);
		setStatus(statusEl, 'Refreshing…', 'tmon-refreshing');

		// build form and post
		var fd = new FormData();
		fd.append('action', 'tmon_refresh_site_count');
		fd.append('site_url', site);
		fd.append('nonce', (window.tmonUcRefresh && tmonUcRefresh.nonce) ? tmonUcRefresh.nonce : '');

		fetch((window.tmonUcRefresh && tmonUcRefresh.ajax_url) ? tmonUcRefresh.ajax_url : '/wp-admin/admin-ajax.php', {
			method: 'POST',
			credentials: 'same-origin',
			body: fd
		}).then(function(r){ return r.json(); })
		.then(function(json){
			if (json && json.success && json.data) {
				var cnt = json.data.count;
				if (cnt === null || cnt === undefined || cnt === '') {
					// Use raw snippet as fallback
					if (countEl) countEl.innerHTML = '<em>n/a</em>';
					setStatus(statusEl, 'No data', 'tmon-refresh-ok');
				} else {
					if (countEl) countEl.textContent = String(cnt);
					setStatus(statusEl, 'OK', 'tmon-refresh-ok');
				}
			} else {
				var msg = (json && json.data && json.data.message) ? json.data.message : (json && json.data ? JSON.stringify(json.data) : (json && json.message ? json.message : 'error'));
				if (countEl) countEl.innerHTML = '<em>n/a</em>';
				setStatus(statusEl, 'Err: '+msg, 'tmon-refresh-err');
			}
		}).catch(function(err){
			if (countEl) countEl.innerHTML = '<em>n/a</em>';
			setStatus(statusEl, 'Network error', 'tmon-refresh-err');
		}).finally(function(){
			btn.disabled = false;
			// hide spinner after a short delay to allow reading
			setTimeout(function(){
				try { var s = statusEl.querySelector('.tmon-spinner'); if (s) s.remove(); } catch(e){}
			}, 900);
		});
	}

	function init() {
		document.querySelectorAll('.tmon-uc-refresh-btn').forEach(function(b){
			b.addEventListener('click', onClick);
		});
	}
	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
	else init();
})();
