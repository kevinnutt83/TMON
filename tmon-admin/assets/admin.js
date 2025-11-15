(function () {
	'use strict';

	const NOTICE_KEY = 'tmon_leaflet_notice_dismissed';

	function log(msg){ if (window.console && console.log) console.log('tmon-admin: ' + msg); }
	function warn(msg){ if (window.console && console.warn) console.warn('tmon-admin: ' + msg); }

	function isNoticeDismissedServer() { return (window.tmon_admin && window.tmon_admin.leaflet_dismissed) ? true : false; }
	function isNoticeDismissedLocal() { try { return window.localStorage && window.localStorage.getItem(NOTICE_KEY) === '1'; } catch(e) { return false; } }
	function setNoticeDismissedLocal() { try { window.localStorage.setItem(NOTICE_KEY, '1'); } catch(e) {} }

	function ajaxDismissServer() {
		if (!(window.tmon_admin && tmon_admin.dismiss_nonce)) return;
		try {
			const body = new URLSearchParams();
			body.set('security', tmon_admin.dismiss_nonce); // check_ajax_referer uses 'security'
			fetch(ajaxurl + '?action=tmon_admin_dismiss_notice', {
				method:'POST', credentials:'same-origin',
				headers:{ 'Content-Type':'application/x-www-form-urlencoded' },
				body: body.toString()
			}).catch(()=>{});
		} catch(e) {}
	}

	function showAdminNotice(message) {
		if (isNoticeDismissedLocal() || isNoticeDismissedServer()) return;
		if (document.querySelector('.tmon-admin-notice')) return;
		const wrap = document.querySelector('.wrap.tmon-admin') || document.querySelector('.wrap');
		if (!wrap) return;
		const notice = document.createElement('div');
		notice.className = 'notice notice-warning is-dismissible tmon-admin-notice';
		notice.innerHTML = '<p>' + message + '</p>';
		const dismiss = document.createElement('button');
		dismiss.type = 'button';
		dismiss.className = 'notice-dismiss';
		dismiss.innerHTML = '<span class="screen-reader-text">Dismiss this notice.</span>';
		notice.appendChild(dismiss);
		wrap.insertBefore(notice, wrap.firstChild);
		dismiss.addEventListener('click', function () {
			setNoticeDismissedLocal();
			ajaxDismissServer();
			if (notice && notice.parentNode) notice.parentNode.removeChild(notice);
		});
	}

	function loadStyle(url) { return new Promise(resolve => { const l=document.createElement('link'); l.rel='stylesheet'; l.href=url; l.onload=()=>resolve(url); l.onerror=()=>resolve(url); document.head.appendChild(l); }); }
	function loadScript(url) { return new Promise((resolve,reject)=>{ const s=document.createElement('script'); s.src=url; s.async=true; s.onload=()=>resolve(url); s.onerror=()=>reject(new Error('failed to load '+url)); document.head.appendChild(s); }); }

	function ensureLeaflet() {
		if (typeof L !== 'undefined') { log('Leaflet present'); return Promise.resolve(true); }
		const css = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
		const js  = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
		return loadStyle(css).then(()=>loadScript(js)).then(()=> typeof L !== 'undefined').catch(()=> false);
	}

	function pageHasMap() {
		if (document.querySelector('#tmon-hierarchy-map')) return true;
		if (document.querySelector('.tmon-hierarchy')) return true;
		if (typeof window.tmon_hierarchy_init === 'function') return true;
		return false;
	}

	document.addEventListener('DOMContentLoaded', function () {
		log('admin.js loaded');

		if (!pageHasMap()) {
			log('No TMON map detected; skipping Leaflet checks.');
			return;
		}

		ensureLeaflet().then(ok=>{
			if (!ok) {
				showAdminNotice('Leaflet library not found — device map may be disabled. Click "Refresh from paired UC sites" to attempt to fetch known IDs.');
				return;
			}
			log('Leaflet ready');
			if (typeof window.tmon_hierarchy_init === 'function') {
				try { window.tmon_hierarchy_init(); } catch(e) { warn('tmon_hierarchy_init failed: '+e.message); }
			}
		});

		// Prevent double submit for a few seconds
		document.querySelectorAll('.wrap form').forEach(form => form.addEventListener('submit', function(){
			const btn = form.querySelector('input[type="submit"], button[type="submit"], .button-primary');
			if (btn) { btn.disabled=true; setTimeout(()=>{btn.disabled=false},4000); }
		}, {passive:true}));
	});
})();
