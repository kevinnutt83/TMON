(function () {
	'use strict';

	const NOTICE_KEY = 'tmon_leaflet_notice_dismissed';

	function log(msg) { if (window.console && console.log) console.log('tmon-admin: ' + msg); }
	function warn(msg) { if (window.console && console.warn) console.warn('tmon-admin: ' + msg); }

	function showAdminNotice(message) {
		// Do not show if already dismissed locally or server says it's dismissed
		if (window.localStorage && window.localStorage.getItem(NOTICE_KEY) === '1') return;
		if (window.tmon_admin && window.tmon_admin.leaflet_dismissed) return;

		// Avoid duplicates
		if (document.querySelector('.tmon-admin-notice')) return;

		const wrap = document.querySelector('.wrap.tmon-admin') || document.querySelector('.wrap');
		if (!wrap) return;

		const notice = document.createElement('div');
		notice.className = 'notice notice-warning is-dismissible tmon-admin-notice';
		notice.innerHTML = '<p>' + message + '</p>';
		// Dismiss button (WordPress style)
		const dismiss = document.createElement('button');
		dismiss.type = 'button';
		dismiss.className = 'notice-dismiss';
		dismiss.innerHTML = '<span class="screen-reader-text">Dismiss this notice.</span>';
		notice.appendChild(dismiss);

		wrap.insertBefore(notice, wrap.firstChild);

		// Wire dismissal: local + server
		dismiss.addEventListener('click', function () {
			try { window.localStorage.setItem(NOTICE_KEY, '1'); } catch (e) { /* ignore */ }
			// async call to persist per-user preference
			if (window.tmon_admin && tmon_admin.dismiss_nonce) {
				fetch(ajaxurl + '?action=tmon_admin_dismiss_notice', {
					method: 'POST',
					credentials: 'same-origin',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' },
					body: 'nonce=' + encodeURIComponent(tmon_admin.dismiss_nonce)
				}).catch(()=>{});
			}
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
		// Only attempt CDN in admin for the map if needed
		const cssUrl = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
		const jsUrl = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
		return loadStyle(cssUrl).then(() => loadScript(jsUrl)).then(() => {
			return (typeof window.L !== 'undefined');
		}).catch(() => false);
	}

	// When DOM ready: wire small behaviors
	document.addEventListener('DOMContentLoaded', function () {
		log('admin.js loaded');

		// Only show the Leaflet notice if a hierarchy map placeholder exists
		const mapSelectors = ['#tmon-hierarchy-map', '.tmon-hierarchy', '.tmon-map'];
		let hasMap = mapSelectors.some(sel => !!document.querySelector(sel));
		// Some pages may add maps dynamically; also consider existence of tmon_hierarchy_init function
		if (!hasMap && typeof window.tmon_hierarchy_init === 'function') hasMap = true;

		if (!hasMap) {
			// Nothing map-related on this page; don't show notices or try to load Leaflet.
			log('No TMON hierarchy map placeholder found; skipping Leaflet checks.');
			return;
		}

		// If Leaflet missing, try to load it; only show notice if unable to load.
		ensureLeaflet().then(ok => {
			if (!ok) {
				showAdminNotice('Leaflet library not found — device map may be disabled. Click "Refresh from paired UC sites" to attempt to fetch known IDs.');
			} else {
				log('Leaflet available.');
				// initialize hierarchy if available
				if (typeof window.tmon_hierarchy_init === 'function') {
					try { window.tmon_hierarchy_init(); } catch(e) { warn('tmon_hierarchy_init failed: ' + e.message); }
				}
			}
		});
	});
})();
