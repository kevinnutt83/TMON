(function(){
	'use strict';
	if (typeof window.tmonProvisionData === 'undefined') window.tmonProvisionData = {};
	var DATA = window.tmonProvisionData || {};

	function qs(selector, root){ return (root||document).querySelector(selector); }
	function qsa(selector, root){ return Array.prototype.slice.call((root||document).querySelectorAll(selector)); }

	// Toasts
	function ensureToasts(){ var c = qs('#tmon-toasts'); if(c) return c; c = document.createElement('div'); c.id='tmon-toasts'; c.style.position='fixed'; c.style.right='18px'; c.style.bottom='18px'; c.style.zIndex='100000'; document.body.appendChild(c); return c; }
	function showToast(msg, type){ var c = ensureToasts(); var el = document.createElement('div'); el.className = 'tmon-toast tmon-toast-'+(type||'info'); el.style.background = (type==='error')? '#d9534f' : (type==='warn' ? '#ffb900' : '#2e8b57'); el.style.color='#fff'; el.style.padding='8px 12px'; el.style.marginTop='8px'; el.style.borderRadius='6px'; el.textContent = msg; c.appendChild(el); setTimeout(function(){ el.style.opacity='0'; setTimeout(function(){ try{ c.removeChild(el); }catch(e){} }, 400); }, 4000); }

	// Confirm modal
	function ensureModal(){ var m = qs('#tmon-action-modal'); if(m) return m;
		m = document.createElement('div'); m.id='tmon-action-modal'; m.setAttribute('role','dialog'); m.setAttribute('aria-modal','true'); m.style.display='none'; m.style.position='fixed'; m.style.left='0'; m.style.top='0'; m.style.right='0'; m.style.bottom='0'; m.style.alignItems='center'; m.style.justifyContent='center'; m.style.background='rgba(0,0,0,0.4)'; m.style.zIndex='100001';
		var box = document.createElement('div'); box.className='tmon-modal-box'; box.style.background='#fff'; box.style.padding='18px'; box.style.borderRadius='6px'; box.style.minWidth='320px'; box.style.maxWidth='90%';
		var title = document.createElement('h3'); title.id='tmon-action-modal-title'; title.style.marginTop='0'; box.appendChild(title);
		var body = document.createElement('div'); body.id='tmon-action-modal-body'; body.style.marginTop='8px'; box.appendChild(body);
		var actions = document.createElement('div'); actions.style.textAlign='right'; actions.style.marginTop='12px';
		var cancel = document.createElement('button'); cancel.className='button'; cancel.id='tmon-action-modal-cancel'; cancel.textContent='Cancel';
		var confirm = document.createElement('button'); confirm.className='button button-primary'; confirm.id='tmon-action-modal-confirm'; confirm.textContent='Proceed'; confirm.style.marginLeft='8px';
		actions.appendChild(cancel); actions.appendChild(confirm); box.appendChild(actions);
		m.appendChild(box); document.body.appendChild(m);
		cancel.addEventListener('click', function(){ hideModal(); if(m._cb) m._cb(false); });
		confirm.addEventListener('click', function(){ hideModal(); if(m._cb) m._cb(true); });
		m.addEventListener('click', function(e){ if(e.target === m){ hideModal(); if(m._cb) m._cb(false); } });
		function hideModal(){ m.style.display='none'; m._cb = null; }
		return m;
	}
	function showModal(title, bodyHtml, cb){ var m = ensureModal(); qs('#tmon-action-modal-title').textContent = title; qs('#tmon-action-modal-body').innerHTML = bodyHtml; m.style.display='flex'; m._cb = cb; qs('#tmon-action-modal-confirm').focus(); }

	// AJAX helpers
	function ajaxFetch(action, payload){
		var params = new URLSearchParams(); params.append('action', action);
		for (var k in payload){ if(payload.hasOwnProperty(k)) params.append(k, payload[k]); }
		if (DATA.nonce) params.append('_wpnonce', DATA.nonce);
		return fetch(DATA.ajax_url || window.ajaxurl || '/wp-admin/admin-ajax.php', { method:'POST', credentials:'same-origin', body: params })
			.then(function(r){
				var ct = r.headers.get('content-type');
				if (ct && ct.indexOf('application/json') !== -1) return r.json();
				return r.text().then(function(txt){ if (txt === "0") return 0; try { return JSON.parse(txt); } catch(e) { return txt; } });
			});
	}

	// Modal builder + save handler
	function escapeHtml(str){ if (!str) return ''; return String(str).replace(/[&<>"']/g,function(s){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s];}); }
	function showDeviceSettingsModal(device) {
		var html =
			'<form id="tmon-device-settings-form">' +
			'<label>Unit ID:<br><input name="unit_id" value="' + escapeHtml(device.unit_id || '') + '" required></label><br>' +
			'<label>Unit Name:<br><input name="unit_name" value="' + escapeHtml(device.unit_name || '') + '"></label><br>' +
			'<label>Machine ID:<br><input name="machine_id" value="' + escapeHtml(device.machine_id || '') + '" required></label><br>' +
			'<label>Site URL:<br><input name="site_url" value="' + escapeHtml(device.site_url || '') + '" required></label><br>' +
			'<label>Role:<br><select name="role"><option value="base">base</option><option value="remote">remote</option><option value="gateway">gateway</option></select></label><br>' +
			'<label>Company ID:<br><input name="company_id" type="number" value="' + escapeHtml(device.company_id || '') + '"></label><br>' +
			'<label>Plan:<br><select name="plan"><option value="standard">standard</option><option value="pro">pro</option></select></label><br>' +
			'<label>Status:<br><select name="status"><option value="pending">pending</option><option value="active">active</option><option value="provisioned">provisioned</option></select></label><br>' +
			'<label>Notes:<br><textarea name="notes">' + escapeHtml(device.notes || '') + '</textarea></label><br>' +
			'<label>Check-in Time:<br><input name="checkin_time" value="' + escapeHtml(device.checkin_time || '') + '" readonly></label><br>' +
			(device.firmware ? '<label>Firmware:<br><input name="firmware" value="' + escapeHtml(device.firmware) + '"></label><br>' : '') +
			'<input type="hidden" name="id" value="' + (device.id || 0) + '">' +
			'</form>';

		showModal('Device Information & Settings', html, function(ok){
			if (!ok) return;
			var form = qs('#tmon-device-settings-form');
			var payload = {
				id: form.id.value,
				unit_id: form.unit_id.value.trim(),
				unit_name: form.unit_name.value.trim(),
				machine_id: form.machine_id.value.trim(),
				site_url: form.site_url.value.trim(),
				role: form.role.value,
				company_id: form.company_id.value,
				plan: form.plan.value,
				status: form.status.value,
				notes: form.notes.value,
				checkin_time: form.checkin_time.value,
				firmware: form.firmware ? form.firmware.value : ''
			};
			if (!payload.unit_id || !payload.site_url) { showToast('Unit ID and Site URL are required', 'error'); return; }
			ajaxFetch('tmon_save_queue_item', payload).then(function(json){
				if (json && json.success) {
					showToast('Device saved', 'success');
					if (json.data && json.data.uc && json.data.uc.http_code) showToast('UC HTTP ' + json.data.uc.http_code, 'info');
					location.reload();
				} else {
					var errMsg = (json && json.data && json.data.message) ? json.data.message : 'Save failed';
					showToast(errMsg, 'error');
				}
			}).catch(function(err){ console.error('Save error:', err); showToast('Save error: ' + (err.message || 'Unknown error'), 'error'); });
		});
	}

	// Commands
	function sendCommand(unit_id, command, site_url) {
		ajaxFetch('tmon_send_device_command', { unit_id: unit_id, command: command, site_url: site_url })
			.then(function(json){ if (json && json.success) showToast('Command sent: ' + command, 'success'); else { var msg = json && json.data ? (json.data.message || JSON.stringify(json.data)) : 'Command failed'; showToast(msg,'error'); } })
			.catch(function(e){ console.error(e); showToast('Command error','error'); });
	}
	window.sendCommand = sendCommand;

	// List rendering helpers
	function renderDevicesFromResponse(resp) {
		var data = resp && resp.data ? resp.data : resp;
		var un = [], prov = [];
		if (data && Array.isArray(data)) {
			data.forEach(function(d){ if (String(d.status || '').toLowerCase() === 'provisioned') prov.push(d); else un.push(d); });
		} else if (data && data.unprovisioned && data.provisioned) {
			un = data.unprovisioned; prov = data.provisioned;
		}
		renderDeviceColumns(un, prov);
	}
	function ensureDeviceColumnsContainer() {
		var container = qs('#tmon-device-columns'); if (!container) { container = document.createElement('div'); container.id = 'tmon-device-columns'; var wrap = qs('.tmon-provision-wrap') || document.body; wrap.appendChild(container); }
		container.style.display = 'flex'; container.style.gap = '12px'; return container;
	}
	function renderDeviceColumns(unprovisioned, provisioned) {
		var container = ensureDeviceColumnsContainer(); container.innerHTML = '';
		container.appendChild(buildColumn('Unprovisioned Devices', unprovisioned));
		container.appendChild(buildColumn('Provisioned Devices', provisioned));
	}
	function buildColumn(title, devices) {
		var col = document.createElement('div'); col.className = 'tmon-device-column'; col.style.flex='1';
		col.innerHTML = '<h2>'+title+'</h2>';
		var table = document.createElement('table'); table.className='wp-list-table widefat fixed striped';
		var thead = document.createElement('thead'); thead.innerHTML = '<tr><th>Unit ID</th><th>Name</th><th>Machine ID</th><th>Role</th><th>Company</th><th>Plan</th><th>Status</th><th>Check-in</th><th>Actions</th></tr>'; table.appendChild(thead);
		var tbody = document.createElement('tbody');
		(devices||[]).forEach(function(device){
			var tr = document.createElement('tr'); tr.className='tmon-device-row';
			tr.dataset.id = device.id || '';
			tr.dataset.unitId = device.unit_id || '';
			tr.dataset.unitName = device.unit_name || '';
			tr.dataset.machineId = device.machine_id || '';
			tr.dataset.role = device.role || '';
			tr.dataset.companyId = device.company_id || '';
			tr.dataset.plan = device.plan || '';
			tr.dataset.status = device.status || '';
			tr.dataset.checkinTime = device.checkin_time || device.created_at || '';
			tr.dataset.siteUrl = device.site_url || '';
			tr.dataset.firmware = device.firmware || '';
			function td(text){ var c=document.createElement('td'); c.textContent = text||''; return c; }
			tr.appendChild(td(tr.dataset.unitId));
			tr.appendChild(td(tr.dataset.unitName));
			tr.appendChild(td(tr.dataset.machineId));
			tr.appendChild(td(tr.dataset.role));
			tr.appendChild(td(tr.dataset.companyId));
			tr.appendChild(td(tr.dataset.plan));
			tr.appendChild(td(tr.dataset.status));
			tr.appendChild(td(tr.dataset.checkinTime));
			var actionsTd = document.createElement('td');
			if (tr.dataset.siteUrl) {
				var reboot = document.createElement('button'); reboot.className='button tmon-action-reboot'; reboot.textContent='Reboot';
				reboot.addEventListener('click', function(e){ e.stopPropagation(); sendCommand(tr.dataset.unitId, 'reboot', tr.dataset.siteUrl); });
				var reset = document.createElement('button'); reset.className='button tmon-action-reset'; reset.textContent='Factory Reset'; reset.style.marginLeft='6px';
				reset.addEventListener('click', function(e){ e.stopPropagation(); sendCommand(tr.dataset.unitId, 'factory_reset', tr.dataset.siteUrl); });
				actionsTd.appendChild(reboot); actionsTd.appendChild(reset);
			}
			tr.appendChild(actionsTd);
			tr.addEventListener('click', function(){
				var deviceObj = {
					id: tr.dataset.id,
					unit_id: tr.dataset.unitId,
					unit_name: tr.dataset.unitName,
					machine_id: tr.dataset.machineId,
					role: tr.dataset.role,
					company_id: tr.dataset.companyId,
					plan: tr.dataset.plan,
					status: tr.dataset.status,
					checkin_time: tr.dataset.checkinTime,
					site_url: tr.dataset.siteUrl,
					firmware: tr.dataset.firmware
				};
				showDeviceSettingsModal(deviceObj);
			});
			tbody.appendChild(tr);
		});
		table.appendChild(tbody);
		col.appendChild(table);
		return col;
	}
	function loadAndRenderDevices() {
		ajaxFetch('tmon_get_devices', {}).then(function(json){ renderDevicesFromResponse(json); }).catch(function(e){ console.error(e); showToast('Load error','error'); });
	}
	document.addEventListener('DOMContentLoaded', loadAndRenderDevices);
	setInterval(loadAndRenderDevices, 30000);
})();
