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

	// Document ready
	document.addEventListener('DOMContentLoaded', function () {
		log('admin.js loaded');

		// Provide different localization variable fallbacks
		const TMON_VAR = (typeof window.TMON_ADMIN !== 'undefined') ? window.TMON_ADMIN
			: (typeof window.tmon_admin !== 'undefined') ? window.tmon_admin
			: null;

		if (!TMON_VAR) {
			console.warn('TMON_ADMIN localization not present; admin.js will still run but some features may be limited.');
		}

		const restRoot = (TMON_VAR && (TMON_VAR.restRoot || TMON_VAR.rest_root)) ? (TMON_VAR.restRoot || TMON_VAR.rest_root) : (typeof rest_url !== 'undefined' ? rest_url : '');
		const restNonce = TMON_VAR && (TMON_VAR.restNonce || TMON_VAR.rest_nonce) ? (TMON_VAR.restNonce || TMON_VAR.rest_nonce) : '';
		const ajaxUrl   = (TMON_VAR && (TMON_VAR.ajaxUrl || TMON_VAR.ajaxurl)) ? (TMON_VAR.ajaxUrl || TMON_VAR.ajaxurl) : (window.ajaxurl || '/wp-admin/admin-ajax.php');
		const ajaxNonce = (TMON_VAR && (TMON_VAR.nonce || TMON_VAR.noncev)) ? (TMON_VAR.nonce || TMON_VAR.noncev) : '';

		// Save restRoot/nonce/nonce fallbacks on window for other scripts that expect them
		window.TMON_ADMIN_FETCH = { restRoot, restNonce, ajaxUrl, ajaxNonce };

		// Now continue existing code; but change the part which previously aborted manifest fetch:
		if (!pageHasMap()) {
			log('No TMON map detected; skipping Leaflet checks.');
		} else {
			ensureLeaflet().then(ok=>{
				if (!ok) {
					showAdminNotice('Leaflet library not loaded — device map may be disabled. Click "Refresh from paired UC sites" to attempt to fetch known IDs.');
					return;
				}
				log('Leaflet ready');
				if (typeof window.tmon_hierarchy_init === 'function') {
					try { window.tmon_hierarchy_init(); } catch(e) { warn('tmon_hierarchy_init failed: '+e.message); }
				}
			});
		}

		// Prevent double submit for a few seconds
		document.querySelectorAll('.wrap form').forEach(form => form.addEventListener('submit', function(){
			const btn = form.querySelector('input[type="submit"], button[type="submit"], .button-primary');
			if (btn) { btn.disabled=true; setTimeout(()=>{btn.disabled=false},4000); }
		}, {passive:true}));

		// Defensive: ensure any provisioning Role select has canonical options
		(function ensureRoleSelects(){
			var roles = ['base','wifi','remote'];
			document.querySelectorAll('select[name="role"]').forEach(function(sel){
				// quick check: if wifi & remote present already, skip
				var hasWifi = false, hasRemote = false;
				for (var i=0;i<sel.options.length;i++){
					if (sel.options[i].value === 'wifi') hasWifi = true;
					if (sel.options[i].value === 'remote') hasRemote = true;
				}
				if (hasWifi && hasRemote) return;
				var cur = sel.value || '';
				// rebuild safely preserving selection when possible
				sel.innerHTML = '';
				var opt = document.createElement('option'); opt.value=''; opt.text='Select a type'; sel.appendChild(opt);
				roles.forEach(function(r){ var o=document.createElement('option'); o.value=r; o.text=r; if (r===cur) o.selected=true; sel.appendChild(o); });
			});
		})();
	});

	// Fetch manifest modified to use either REST or admin-ajax depending on availability
	(function(){
		let localized = (typeof window.TMON_ADMIN !== 'undefined') ? window.TMON_ADMIN : (typeof window.tmon_admin !== 'undefined' ? window.tmon_admin : null);
		const restRoot = localized ? (localized.restRoot || localized.rest_root || '') : '';
		const restNonce = localized ? (localized.restNonce || '') : '';
		const ajaxUrl = localized ? (localized.ajaxUrl || localized.ajaxurl || window.ajaxurl || '/wp-admin/admin-ajax.php') : (window.ajaxurl || '/wp-admin/admin-ajax.php');
		const ajaxNonce = localized ? (localized.nonce || '') : '';
		const manifestNonce = localized ? (localized.manifestNonce || '') : '';

		async function fetchManifest(repoParam) {
			// If REST root is available, try REST endpoint first
			if (restRoot) {
				try {
					const restUrl = `${restRoot.replace(/\/$/, '')}/tmon-admin/v1/github/manifest?repo=${encodeURIComponent(repoParam)}`;
					const res = await fetch(restUrl, {
						method: 'GET',
						headers: (restNonce ? { 'X-WP-Nonce': restNonce, 'Accept': 'application/json' } : { 'Accept': 'application/json' }),
						credentials: 'same-origin'
					});
					if (res.ok) {
						const json = await res.json();
						if (json && json.success && json.data) {
							console.log('Manifest (REST) success:', json.data);
							displayManifest(json.data);
							return json.data;
						}
						// REST returned structured failure -> fall back to admin-ajax route
						console.log('Manifest (REST) returned no success:', json);
					} else {
						console.warn('Manifest (REST) fetch failed with HTTP', res.status);
					}
				} catch (e) {
					console.warn('Manifest (REST) fetch failed:', e);
				}
			}

			// Fallback to admin-ajax
			try {
				let adminUrl = `${ajaxUrl}?action=tmon_admin_fetch_github_manifest&repo=${encodeURIComponent(repoParam)}`;
				const nonceToSend = manifestNonce || ajaxNonce;
				if (nonceToSend) adminUrl += `&nonce=${encodeURIComponent(nonceToSend)}`;
				const res2 = await fetch(adminUrl, { method: 'GET', credentials: 'same-origin' });
				if (res2.ok) {
					const json2 = await res2.json();
					if (json2 && json2.success) {
						console.log('Manifest (admin-ajax) success:', json2.data);
						displayManifest(json2.data || json2);
						return json2.data || json2;
					}
					console.warn('Manifest (admin-ajax) returned no success:', json2);
				} else {
					console.warn('Manifest (admin-ajax) fetch failed with HTTP', res2.status);
					// If admin-ajax returned 403, it often means missing nonce or unprivileged. Do not throw; fallback gracefully.
				}
			} catch (e) {
				console.warn('Manifest (admin-ajax) fetch failed:', e);
			}
			// NEW UX: notify admin when manifest cannot be fetched and offer Retry + Validator link
			const safeRepo = String(repoParam).replace(/</g,'&lt;').replace(/>/g,'&gt;');
			const msg = 'Failed to fetch firmware manifest for repo: <strong>' + safeRepo + '</strong>. ' +
				'<button id="tmon-manifest-retry" class="button">Retry</button> ' +
				'<a id="tmon-manifest-validate" class="button" href="#" style="margin-left:8px">Validate Endpoints</a>';
			showAdminNotice(msg);
			// Attach retry handler (one-shot)
			function onClick(ev){
				const el = ev.target || ev.srcElement;
				if (!el) return;
				if (el.id === 'tmon-manifest-retry') {
					ev.preventDefault();
					ev.stopPropagation();
					// Replace notice with spinner notice
					showAdminNotice('Retrying manifest fetch... please wait.');
					fetchManifest(repoParam);
					document.removeEventListener('click', onClick);
				}
				if (el.id === 'tmon-manifest-validate') {
					ev.preventDefault();
					ev.stopPropagation();
					const validator = window.open ? window.open(window.location.origin + '/wp-admin/tools.php?page=tmon-validate','_blank') : null;
					if (!validator) alert('Open the WP endpoint validator in a new tab: ' + (window.location.origin + '/wp-admin/tools.php?page=tmon-validate'));
					document.removeEventListener('click', onClick);
				}
			}
			document.addEventListener('click', onClick);
			return null;
		}

		function displayManifest(obj) {
			let container = document.getElementById('tmon-manifest-output');
			if (!container) {
				container = document.createElement('pre');
				container.id = 'tmon-manifest-output';
				container.style.maxWidth = '720px';
				container.style.overflowX = 'auto';
				container.style.padding = '8px';
				container.style.border = '1px solid #ddd';
				container.style.background = '#fff';
				// Insert near provisioning controls if present, else append to body
				const provNode = document.querySelector('#tmon-admin-provisioning') || document.querySelector('#tmon-admin-provisioning-wrap') || document.body;
				provNode.appendChild(container);
			}
			try {
				container.textContent = JSON.stringify(obj, null, 2);
			} catch(e) {
				container.textContent = String(obj);
			}
		}

		// Auto-run in admin pages where provisioning UI exists
		document.addEventListener('DOMContentLoaded', function() {
			const repo = 'https://github.com/kevinnutt83/TMON/tree/main/micropython';
			fetchManifest(repo);
		});

		// Defensive shim: if DataTables is not available, provide a no-op to avoid hard JS errors
		try {
			if (window.jQuery && typeof jQuery.fn !== 'undefined' && typeof jQuery.fn.DataTable === 'undefined') {
				console.warn('DataTables not loaded; provisioning page will use a basic fallback.');
				jQuery.fn.DataTable = function () { return this; }; // minimal no-op to avoid errors
			}
		} catch (e) {
			try { console.warn('DataTable shim failed', e); } catch (err) {}
		}
	})();
})();
