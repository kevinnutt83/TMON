<?php
if (!current_user_can('manage_options')) wp_die('Forbidden');
?>
<div class="wrap">
  <h1>Remote Shell</h1>
  <p>Send a safe shell command (ls/cat/tail) to a specific unit and monitor streamed output (polled).</p>
  <form id="tmon-remote-shell-form">
    <table class="form-table">
      <tr><th>Unit ID</th><td><input id="rs-unit" class="regular-text" /></td></tr>
      <tr><th>Command</th><td><input id="rs-cmd" class="regular-text" placeholder="tail /logs/field_data.log 20" /></td></tr>
    </table>
    <button id="rs-send" class="button button-primary">Send</button>
  </form>

  <h2>Output</h2>
  <pre id="rs-output" style="height:300px;overflow:auto;border:1px solid #ddd;padding:8px;background:#fff"></pre>
</div>

<script>
(function(){
  const send = document.getElementById('rs-send');
  const unitIn = document.getElementById('rs-unit');
  const cmdIn = document.getElementById('rs-cmd');
  const out = document.getElementById('rs-output');
  let jobId = null;
  let pollTimer = null;
  send.addEventListener('click', function(ev){
    ev.preventDefault();
    const unit = unitIn.value.trim();
    const cmd = cmdIn.value.trim();
    if(!unit || !cmd) return alert('unit & cmd required');
    fetch('<?php echo esc_url_raw(rest_url('tmon/v1/device/command')); ?>', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({unit_id: unit, command: 'remote_shell', params: {cmd: cmd}})
    }).then(r=>r.json()).then(j=>{
      if (j && j.id) {
        jobId = j.id;
        out.textContent = 'Command queued (id='+jobId+'). Polling for output...\\n';
        if (pollTimer) clearInterval(pollTimer);
        pollTimer = setInterval(()=>{ pollLogs(unit, jobId); }, 2000);
      } else {
        out.textContent = 'Enqueue failed: '+JSON.stringify(j)+'\\n';
      }
    }).catch(e=> out.textContent = 'Send error: '+e );
  });

  function pollLogs(unit, job) {
    fetch('<?php echo esc_url_raw(rest_url('tmon/v1/admin/shell-log')); ?>?unit_id='+encodeURIComponent(unit)+'&job_id='+encodeURIComponent(job))
      .then(r=>r.json()).then(j=>{
        if (j && j.chunks) {
          out.textContent = j.chunks.map(c=> (new Date(c.ts)).toLocaleString() + ' > ' + (typeof c.chunk === 'string' ? c.chunk : JSON.stringify(c.chunk)) ).join('\\n');
        }
      }).catch(e=>{ /* ignore */ });
  }
})();
</script>
