(function () {
	'use strict';

	function log(msg) { if (window.console && console.log) console.log('tmon-admin: ' + msg); }
	function warn(msg) { if (window.console && console.warn) console.warn('tmon-admin: ' + msg); }

	// Show a temporary admin notice on the page
	function showAdminNotice(message, type = 'updated') {
		const wrap = document.querySelector('.wrap.tmon-admin') || document.querySelector('.wrap');
		if (!wrap) return;
		const notice = document.createElement('div');
		notice.className = type + ' notice is-dismissible';
		notice.innerHTML = '<p>' + message + '</p>';
		wrap.insertBefore(notice, wrap.firstChild);
		// auto-dismiss
		setTimeout(() => {
			if (notice && notice.parentNode) notice.parentNode.removeChild(notice);
		}, 7000);
	}

	// Helper to dynamically load script or stylesheet
	function loadScript(url) {
		return new Promise(function (resolve, reject) {
			const s = document.createElement('script');
			s.src = url;
			s.async = true;
			s.onload = () => resolve(url);
			s.onerror = () => reject(new Error('Failed to load ' + url));
			document.head.appendChild(s);
		});
	}
	function loadStyle(url) {
		return new Promise((resolve) => {
			const l = document.createElement('link');
			l.rel = 'stylesheet';
			l.href = url;
			l.onload = () => resolve(url);
			l.onerror = () => resolve(url); // stylesheet failures are not fatal
			document.head.appendChild(l);
		});
	}

	// Try to load Leaflet if not present — this fixes "map disabled" UI on many pages.
	// This is best-effort; it will not run if CSP or offline prevents it.
	function ensureLeaflet() {
		if (typeof window.L !== 'undefined') {
			log('Leaflet already present');
			return Promise.resolve(true);
		}
		const cssUrl = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
		const jsUrl = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
		log('Attempting to load Leaflet from CDN...');
		return loadStyle(cssUrl).then(() => loadScript(jsUrl)).then(() => {
			if (typeof window.L !== 'undefined') {
				log('Leaflet loaded successfully');
				return true;
			}
			warn('Leaflet script loaded but L is not defined');
			return false;
		}).catch((err) => {
			warn('Leaflet load failed: ' + (err && err.message ? err.message : 'unknown'));
			return false;
		});
	}

	// When DOM ready: wire small behaviors
	document.addEventListener('DOMContentLoaded', function () {
		log('admin.js loaded');

		// If hierarchy script added a hook (e.g., tmon_hierarchy_init), try to call it after Leaflet available.
		if (typeof window.tmon_hierarchy_init === 'function') {
			if (typeof window.L === 'undefined') {
				ensureLeaflet().then((ok) => {
					try {
						window.tmon_hierarchy_init();
					} catch (e) { warn('tmon_hierarchy_init failed: ' + e.message); }
				});
			} else {
				try { window.tmon_hierarchy_init(); } catch (e) { warn('tmon_hierarchy_init failed: ' + e.message); }
			}
		}

		// Show a small hint to admins when the page lacks Leaflet
		if (typeof window.L === 'undefined') {
			// only show for admin users in provisioning (best-effort)
			if (document.querySelector('.wrap.tmon-admin') || document.querySelector('.wrap')) {
				showAdminNotice('Leaflet library not found — device map may be disabled. Click "Refresh from paired UC sites" to attempt to fetch known IDs.', 'notice');
			}
		}

		// Disable duplicate submits for inline update forms (improve UX)
		document.querySelectorAll('.wrap form').forEach((form) => {
			form.addEventListener('submit', function (e) {
				const btn = form.querySelector('input[type="submit"], button[type="submit"], .button-primary');
				if (btn) {
					btn.disabled = true;
					btn.classList.add('disabled');
					// Re-enable in case of error after a short timeout
					setTimeout(() => { btn.disabled = false; btn.classList.remove('disabled'); }, 5000);
				}
			}, { passive: true });
		});
	});
})();
