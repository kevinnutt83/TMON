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

	document.addEventListener('DOMContentLoaded', function () {
		const ajaxUrl = (window.tmonUcRefresh && tmonUcRefresh.ajax_url) || (window.ajaxurl || '/wp-admin/admin-ajax.php');
		const nonce = (window.tmonUcRefresh && tmonUcRefresh.nonce) || (document.querySelector('input[name="_wpnonce"]') || {}).value || '';

		function findRowCellForSite(site) {
			// try a data attribute first
			let el = document.querySelector(`[data-uc-site="${site}"] .uc-devices-count`);
			if (el) return el;
			// try row containing the URL text, then find .uc-devices-count in same row
			const rows = Array.from(document.querySelectorAll('table tr'));
			for (const r of rows) {
				if (r.textContent && r.textContent.indexOf(site) !== -1) {
					const cell = r.querySelector('.uc-devices-count');
					if (cell) return cell;
					// fallback: return the last cell in row
					return r.querySelector('td:last-child');
				}
			}
			return null;
		}

		function renderStatus(targetEl, html, isError) {
			if (!targetEl) {
				// fallback: append to body as temporary toast
				let tmp = document.getElementById('tmon-uc-refresh-toast');
				if (!tmp) {
					tmp = document.createElement('div');
					tmp.id = 'tmon-uc-refresh-toast';
					tmp.style.cssText = 'position:fixed;right:12px;bottom:12px;max-width:360px;z-index:9999;padding:8px;border-radius:6px;background:#fff;border:1px solid #888;box-shadow:0 2px 8px rgba(0,0,0,.2);font-size:13px';
					document.body.appendChild(tmp);
				}
				tmp.innerHTML = html;
				tmp.style.borderColor = isError ? '#d33' : '#2c9';
				if (isError) tmp.style.background = '#fff7f7'; else tmp.style.background = '#f7fff7';
				return;
			}
			let statusEl = targetEl.querySelector('.uc-refresh-status');
			if (!statusEl) {
				statusEl = document.createElement('div');
				statusEl.className = 'uc-refresh-status';
				statusEl.style.fontSize = '12px';
				statusEl.style.marginTop = '4px';
				targetEl.appendChild(statusEl);
			}
			statusEl.innerHTML = html;
			statusEl.style.color = isError ? '#b00' : '#060';
		}

		async function refreshSite(site, btn) {
			if (!site) return;
			const cell = findRowCellForSite(site) || btn.parentElement;
			// spinner
			const spinner = document.createElement('span');
			spinner.className = 'uc-refresh-spinner';
			spinner.textContent = ' ⏳';
			btn.disabled = true;
			btn.appendChild(spinner);
			try {
				const form = new FormData();
				form.append('action', 'tmon_refresh_site_count');
				form.append('site', site);
				form.append('_wpnonce', nonce);
				const res = await fetch(ajaxUrl, { method: 'POST', body: form, credentials: 'same-origin' });
				const text = await res.text();
				let json = null;
				try { json = JSON.parse(text); } catch (e) { json = null; }
				if (res.ok && json && json.success) {
					const count = (json.data && (json.data.count !== undefined)) ? json.data.count : 'OK';
					renderStatus(cell, `<strong>Devices:</strong> ${count}`, false);
				} else {
					// Prefer structured error returned by handler
					let msg = '';
					if (json && json.data) {
						if (json.data.message) msg += `<div>${escapeHtml(json.data.message)}</div>`;
						if (Array.isArray(json.data.errors) && json.data.errors.length) {
							msg += '<ul style="margin:6px 0;padding-left:18px">';
							json.data.errors.forEach(e => { msg += `<li>${escapeHtml(String(e))}</li>`; });
							msg += '</ul>';
						} else if (json.data.errors) {
							msg += `<div>${escapeHtml(String(json.data.errors))}</div>`;
						}
					}
					if (!msg) {
						msg = `<div>HTTP ${res.status}: ${escapeHtml(text.slice(0, 400) || res.statusText || 'Unknown')}</div>`;
					}
					renderStatus(cell, `<strong>Error</strong>${msg}`, true);
				}
			} catch (err) {
				renderStatus(cell, `<strong>Network error:</strong> ${escapeHtml(String(err))}`, true);
			} finally {
				btn.disabled = false;
				try { spinner.remove(); } catch (e) {}
			}
		}

		function escapeHtml(s) {
			return String(s).replace(/[&<>"']/g, function (m) {
				return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[m];
			});
		}

		// Attach to any per-row refresh buttons: <button class="uc-refresh-btn" data-site="https://...">
		document.body.addEventListener('click', function (ev) {
			const btn = ev.target.closest && ev.target.closest('.uc-refresh-btn');
			if (!btn) return;
			ev.preventDefault();
			const site = btn.dataset.site || btn.getAttribute('data-site') || '';
			refreshSite(site, btn);
		});

		// Intercept the form-based global refresh (if present) to show status details from server
		const globalForm = document.querySelector('form button[name="tmon_refresh_counts"]');
		if (globalForm) {
			globalForm.addEventListener('click', function (ev) {
				// Let the form submit normally for now, but attempt to fetch results via AJAX if button has data-site attr
				// If admin page implements per-site refresh buttons, users will use those
				// Optionally prevent default here and do collective AJAX if needed in future
			});
		}
	});
})();
