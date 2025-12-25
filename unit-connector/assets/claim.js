(function(){
  function findParent(el, selector){
    while (el && el !== document && !el.matches(selector)) el = el.parentElement;
    return el && el.matches && el.matches(selector) ? el : null;
  }

  function validHex(str){
    return /^[A-Fa-f0-9]{6,64}$/.test(str);
  }

  function validUnit(str){
    return /^[A-Za-z0-9._-]{1,64}$/.test(str);
  }

  function onSubmit(e){
    const form = findParent(e.target, '.tmon-claim-form');
    if (!form) return;
    e.preventDefault();

    const result = form.querySelector('.tmon-claim-result');
    const unit = (form.querySelector('[name="unit_id"]').value || '').trim();
    const machine = (form.querySelector('[name="machine_id"]').value || '').trim();

    // Basic client-side validation
    // Clear field messages
    form.querySelectorAll('.tmon-field-msg').forEach(el=>{ el.textContent=''; });
    form.querySelectorAll('.tmon-invalid').forEach(el=>{ el.classList.remove('tmon-invalid'); });

    let invalid = false;
    if (!validUnit(unit)){
      const el = form.querySelector('[name="unit_id"]');
      const msg = form.querySelector('.tmon-field-msg[data-for="unit_id"]');
      el.classList.add('tmon-invalid');
      if (msg) msg.textContent = 'Letters, numbers, dot, underscore, or dash (max 64).';
      invalid = true;
    }
    if (!validHex(machine)){
      const el = form.querySelector('[name="machine_id"]');
      const msg = form.querySelector('.tmon-field-msg[data-for="machine_id"]');
      el.classList.add('tmon-invalid');
      if (msg) msg.textContent = '6–64 hex characters (0-9, A-F).';
      invalid = true;
    }
    if (invalid) return;

    result.textContent = 'Submitting…';
    const fd = new FormData();
    fd.append('unit_id', unit);
    fd.append('machine_id', machine);

    const url = (window.TMON_CLAIM && TMON_CLAIM.restUrl) || (window.location.origin + '/wp-json/tmon-admin/v1/claim');
    const nonce = (window.TMON_CLAIM && TMON_CLAIM.nonce) || '';

    fetch(url, {
      method: 'POST',
      headers: { 'X-WP-Nonce': nonce },
      body: fd
    }).then(async r => {
      let j = null;
      try{ j = await r.json(); } catch(e){}
      if (r.ok && j && j.status === 'ok'){
        result.textContent = 'Claim submitted. ID: ' + j.id;
        form.reset();
      } else {
        const msg = (j && (j.message || j.code)) || ('HTTP ' + r.status);
        result.textContent = 'Error: ' + msg;
      }
    }).catch(err => {
      result.textContent = 'Error: ' + err.toString();
    });
  }

  document.addEventListener('submit', onSubmit, true);
})();
