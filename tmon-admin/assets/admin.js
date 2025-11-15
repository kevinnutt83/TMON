(function () {
	'use strict';

	const NOTICE_KEY = 'tmon_leaflet_notice_dismissed';

	function log(msg) { if (window.console && console.log) console.log('tmon-admin: ' + msg); }
	function warn(msg) { if (window.console && console.warn) console.warn('tmon-admin: ' + msg); }

	function showAdminNotice(message) {
		// do not show if dismissed
		if (window.localStorage && window.localStorage.getItem(NOTICE_KEY) === '1') return;

		const wrap = document.querySelector('.wrap.tmon-admin') || document.querySelector('.wrap');
		if (!wrap) return;

		const notice = document.createElement('div');
		notice.className = 'notice notice-warning is-dismissible tmon-admin-notice';
		notice.innerHTML = '<p>' + message + '</p>';
		// Add a dismiss button that sets localStorage
		const dismiss = document.createElement('button');
		dismiss.type = 'button';
		dismiss.className = 'notice-dismiss';
		dismiss.innerHTML = '<span class="screen-reader-text">Dismiss this notice.</span>';
		notice.appendChild(dismiss);

		wrap.insertBefore(notice, wrap.firstChild);

		dismiss.addEventListener('click', function () {
			try { window.localStorage.setItem(NOTICE_KEY, '1'); } catch (e) {}
			if (notice && notice.parentNode) notice.parentNode.removeChild(notice);
		});
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
		return new Promise(function (resolve) {
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

		// Try to ensure Leaflet; only show a notice when it fails and it's not dismissed.
		ensureLeaflet().then((ok) => {
			if (!ok) {
				showAdminNotice('Leaflet library not found — device map may be disabled. Click "Refresh from paired UC sites" to attempt to fetch known IDs.');
			}
		});

		// Minor UX: disable double-submit on forms quickly.
		document.querySelectorAll('.wrap form').forEach((form) => {
			form.addEventListener('submit', function (e) {
				const btn = form.querySelector('input[type="submit"], button[type="submit"], .button-primary');
				if (btn && !btn.disabled) {
					btn.disabled = true;
					setTimeout(() => { btn.disabled = false; }, 4000);
				}
			}, { passive: true });
		});
	});
})();
