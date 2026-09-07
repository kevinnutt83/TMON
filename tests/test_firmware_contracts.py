import ast
import hashlib
import hmac
import importlib.util
import os
import sys
import tempfile
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
VERSION_PATH = os.path.join(ROOT, 'micropython', 'version.txt')
SETTINGS_PATH = os.path.join(ROOT, 'micropython', 'settings.py')
MANIFEST_SCRIPT_PATH = os.path.join(ROOT, 'scripts', 'generate_manifest.py')
UTILS_PATH = os.path.join(ROOT, 'micropython', 'utils.py')
WPREST_PATH = os.path.join(ROOT, 'micropython', 'wprest.py')


def load_module_from_path(module_name, file_path, extra_modules=None):
    if extra_modules:
        for key, module in extra_modules.items():
            sys.modules[key] = module
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def stub_micro_python_modules():
    ujson = types.ModuleType('ujson')
    ujson.loads = __import__('json').loads
    ujson.dumps = __import__('json').dumps

    uasyncio = types.ModuleType('uasyncio')

    class Lock:
        def __init__(self):
            self._locked = False

        def locked(self):
            return self._locked

        async def __aenter__(self):
            self._locked = True
            return self

        async def __aexit__(self, exc_type, exc, tb):
            self._locked = False
            return False

    uasyncio.sleep_ms = lambda *args, **kwargs: None
    uasyncio.sleep = lambda *args, **kwargs: None
    uasyncio.create_task = lambda *args, **kwargs: None
    uasyncio.Lock = Lock

    utime = types.ModuleType('utime')
    utime.time = lambda: 0
    utime.ticks_ms = lambda: 0
    utime.ticks_diff = lambda a, b: 0

    machine = types.ModuleType('machine')
    class Pin:
        IN = 0
        OUT = 1
        def __init__(self, *args, **kwargs):
            pass
    machine.Pin = Pin
    machine.ADC = object
    machine.soft_reset = lambda: None

    gc = types.ModuleType('gc')
    gc.collect = lambda: 0
    gc.mem_alloc = lambda: 0
    gc.mem_free = lambda: 0
    gc.enable = lambda: None

    settings = types.ModuleType('settings')
    settings.LOG_DIR = '/logs'
    settings.FIELD_DATA_COMPACT_KEYS = True
    settings.FIELD_DATA_SKIP_DEFAULTS = True
    settings.FIELD_DATA_LOG = '/logs/field_data.log'
    settings.DATA_HISTORY_LOG = '/logs/data_history.log'
    settings.UNIT_ID = '123456'
    settings.UNIT_Name = 'Test'
    settings.NODE_TYPE = 'base'
    settings.WORDPRESS_USERNAME = 'user'
    settings.WORDPRESS_PASSWORD = 'pass'
    settings.FIELD_DATA_APP_USER = 'user'
    settings.FIELD_DATA_APP_PASS = 'pass'
    settings.TMON_HUB_SHARED_KEY = 'hub-secret'
    settings.TMON_HUB_READ_TOKEN = 'read-token'
    settings.TMON_ADMIN_CONFIRM_TOKEN = 'admin-token'
    settings.WORDPRESS_API_URL = 'https://example.test'
    settings.FIRMWARE_VERSION = 'v2.00.4g'
    settings.SAMPLE_DEVICE_TEMP = True
    settings.SAMPLE_DEVICE_HUMID = True
    settings.SAMPLE_DEVICE_BAR = True
    settings.SAMPLE_PROBE_TEMP = False
    settings.SAMPLE_PROBE_HUMID = False
    settings.SAMPLE_PROBE_BAR = False
    settings.SAMPLE_TEMP = False
    settings.SAMPLE_HUMID = False
    settings.SAMPLE_BAR = False
    settings.SYS_VOLTAGE_PIN = 0
    settings.LED_PIN = 0
    settings.RELAY_PIN1 = 0
    settings.RELAY_PIN2 = 0
    settings.DEVICE_TEMP_SCL_PIN = 0
    settings.DEVICE_TEMP_SDA_PIN = 0
    settings.BME280_PROBE_SCL_PIN = 0
    settings.BME280_PROBE_SDA_PIN = 0
    settings.OLED_SCL_PIN = 0
    settings.OLED_SDA_PIN = 0
    settings.CLK_PIN = 0
    settings.MOSI_PIN = 0
    settings.MISO_PIN = 0
    settings.CS_PIN = 0
    settings.IRQ_PIN = 0
    settings.RST_PIN = 0
    settings.BUSY_PIN = 0
    settings.CH1_TX_PIN = 0
    settings.CH1_RX_PIN = 0
    settings.CH2_TX_PIN = 0
    settings.CH2_RX_PIN = 0
    settings.SOIL_PROBE_PIN = 0

    config_persist = types.ModuleType('config_persist')
    config_persist.write_text = lambda *args, **kwargs: True
    config_persist.read_json = lambda *args, **kwargs: {}
    config_persist.set_flag = lambda *args, **kwargs: True
    config_persist.is_flag_set = lambda *args, **kwargs: False
    config_persist.write_json = lambda *args, **kwargs: True
    config_persist.write_json_atomic = lambda *args, **kwargs: True
    config_persist.read_text = lambda *args, **kwargs: None
    config_persist.ensure_dir = lambda *args, **kwargs: True
    config_persist.read_json_safe = lambda *args, **kwargs: {}

    diagnostics = types.ModuleType('diagnostics')
    diagnostics.get_diagnostics_snapshot = lambda: {}

    sdata = types.ModuleType('sdata')
    sdata.free_mem = 0

    return {
        'ujson': ujson,
        'uasyncio': uasyncio,
        'utime': utime,
        'machine': machine,
        'gc': gc,
        'settings': settings,
        'config_persist': config_persist,
        'diagnostics': diagnostics,
        'sdata': sdata,
    }


class FirmwareContractTests(unittest.TestCase):
    def test_version_txt_is_source_of_truth(self):
        with open(VERSION_PATH, 'r', encoding='utf-8') as handle:
            version = handle.read().strip()

        self.assertTrue(version, 'micropython/version.txt is empty')
        self.assertTrue(version.startswith('v'), 'version.txt should use v-prefixed firmware version strings')

        with open(SETTINGS_PATH, 'r', encoding='utf-8') as handle:
            settings_text = handle.read()

        self.assertIn('FIRMWARE_VERSION = _read_firmware_version()', settings_text)
        self.assertIn('def _read_firmware_version()', settings_text)

    def test_manifest_generator_reads_version_file(self):
        manifest_module = load_module_from_path('generate_manifest', MANIFEST_SCRIPT_PATH)

        with open(VERSION_PATH, 'r', encoding='utf-8') as handle:
            expected_version = handle.read().strip()

        self.assertEqual(manifest_module.read_version(), expected_version)
        self.assertEqual(manifest_module.find_mp_dir(), os.path.join(ROOT, 'micropython'))

        manifest = manifest_module.build_manifest(version=expected_version)
        self.assertEqual(manifest['version'], expected_version)
        self.assertTrue(manifest['files'])
        self.assertIn('settings.py', manifest['files'])
        self.assertIn('version.txt', manifest['files'])
        self.assertIn('def emit_version(mp_dir, version):', open(MANIFEST_SCRIPT_PATH, 'r', encoding='utf-8').read())
        self.assertIn('def emit_firmware_manifest_py(mp_dir, version):', open(MANIFEST_SCRIPT_PATH, 'r', encoding='utf-8').read())

    def test_manifest_metadata_and_hashes_are_consistent(self):
        manifest_module = load_module_from_path('generate_manifest', MANIFEST_SCRIPT_PATH)

        version = manifest_module.read_version()
        manifest = manifest_module.build_manifest(version=version)

        self.assertEqual(manifest['name'], 'tmon-micropython')
        self.assertEqual(manifest['description'], 'TMON MicroPython firmware manifest')
        self.assertIn('version', manifest)
        self.assertTrue(manifest['files'])

        for rel_path, digest in manifest['files'].items():
            self.assertTrue(isinstance(rel_path, str) and rel_path.strip())
            self.assertTrue(rel_path.strip() == rel_path)
            self.assertTrue(digest.startswith('sha256:'))
            self.assertEqual(len(digest), 71)

    def test_wprest_auth_headers_and_field_data_compaction(self):
        extra_modules = stub_micro_python_modules()
        utils_module = load_module_from_path('utils_real', UTILS_PATH, extra_modules)
        sys.modules['utils'] = utils_module
        wprest_module = load_module_from_path('wprest_real', WPREST_PATH, extra_modules)

        hub_headers = wprest_module._auth_headers('hub')
        self.assertEqual(hub_headers['X-TMON-HUB'], 'hub-secret')

        admin_headers = wprest_module._auth_headers('admin')
        self.assertEqual(admin_headers['X-TMON-ADMIN'], 'admin-token')
        self.assertEqual(admin_headers['X-TMON-CONFIRM'], 'admin-token')
        self.assertTrue(admin_headers['Authorization'].startswith('Bearer '))

        record = {
            'cur_temp_f': 72.1,
            'cur_humid': 45,
            'sys_voltage': 0,
            'free_mem': 120000,
            'note': 'keep'
        }
        compact = utils_module._compact_field_record(record)
        self.assertEqual(compact['cur_temp_f'], 72.1)
        self.assertEqual(compact['cur_humid'], 45)
        self.assertNotIn('sys_voltage', compact)
        self.assertEqual(compact['note'], 'keep')

        utils_module.utc_epoch = lambda: 1788755564
        canonical = utils_module.build_field_data_record(
            'unit-l7riag', 'remote', {'u': 'unit-l7riag', 't': 77.2, 'ts': 842070764}
        )
        self.assertEqual(list(canonical)[:5], ['unit_id', 'node_type', 'ts', 'ts_iso', 'fw'])
        self.assertEqual(canonical['unit_id'], 'unit-l7riag')
        self.assertEqual(canonical['temp_f'], 77.2)
        self.assertGreaterEqual(canonical['ts'], 1600000000)
        self.assertIn('ts_iso', canonical)
        self.assertNotIn('u', canonical)
        self.assertNotIn('t', canonical)

        remote_record = {
            'unit_id': 'remote-1',
            'remote_unit_id': 'remote-1',
            'base_unit_id': 'base-1',
            'node_type': 'remote',
            'ingested_via': 'lora_base',
            'ts': 1000000000,
            'ts_iso': '2001-09-08T20:46:40Z',
            'fw': 'v2.00.4g',
        }
        compact_remote = utils_module._compact_field_record(remote_record)
        self.assertEqual(compact_remote['unit_id'], 'remote-1')
        self.assertEqual(compact_remote['remote_unit_id'], 'remote-1')
        self.assertEqual(compact_remote['base_unit_id'], 'base-1')
        self.assertEqual(compact_remote['ts'], 1000000000)
        self.assertIn('fw', compact_remote)
        self.assertIn('ts_iso', compact_remote)

        with tempfile.TemporaryDirectory() as temp_dir:
            backlog_path = os.path.join(temp_dir, 'field_data_backlog.log')
            with open(backlog_path, 'w', encoding='utf-8') as handle:
                handle.write('{"data":[1]}\n')
                handle.write('{"truncated"\n')
            utils_module.FIELD_DATA_BACKLOG = backlog_path
            utils_module.checkLogDirectory = lambda: None
            self.assertEqual(utils_module.read_backlog(), [{'data': [1]}])

    def test_lora_ack_and_wp_retry_contracts(self):
        with open(os.path.join(ROOT, 'micropython', 'lora.py'), 'r', encoding='utf-8') as handle:
            lora_source = handle.read()
        checker_start = lora_source.index('async def check_incomplete_bursts():')
        checker_end = lora_source.index('\n\ndef _simple_session_parse_chunk', checker_start)
        checker = lora_source[checker_start:checker_end]
        self.assertIn("if st.get('ack_sent'):", checker)
        self.assertIn("await asyncio.sleep(5)", checker)
        self.assertIn('>= 60000', checker)
        self.assertIn("st['ack_sent'] = True", lora_source)
        self.assertIn("st['chunks'] = []", lora_source)

        with open(WPREST_PATH, 'r', encoding='utf-8') as handle:
            wprest_source = handle.read()
        settings_start = wprest_source.index('async def send_settings_to_wp():')
        settings_end = wprest_source.index('\n# Addition for OTA polling', settings_start)
        settings_sender = wprest_source[settings_start:settings_end]
        self.assertIn("candidate_paths = ['/wp-json/tmon/v1/device/settings-applied']", settings_sender)
        self.assertIn('route missing; not backlogging', settings_sender)
        self.assertIn('if last_response is None:', settings_sender)
        self.assertIn("candidate_paths = ['/wp-json/tmon/v1/device/diagnostics']", wprest_source)

    def test_oled_grid_and_simple_session_ota_contracts(self):
        with open(os.path.join(ROOT, 'micropython', 'oled.py'), 'r', encoding='utf-8') as handle:
            oled_source = handle.read()
        self.assertIn('BODY_LINE_H = 8', oled_source)
        self.assertNotIn('BODY_LINE_H = 7', oled_source)
        self.assertIn('BODY_TOP + i * BODY_LINE_H', oled_source)
        self.assertNotIn('y + 9 - h', oled_source)
        self.assertIn('def _header_radio_line():', oled_source)
        self.assertIn('y % 8 == 0', oled_source)
        self.assertIn('time.ticks_ms()', oled_source)
        self.assertIn('time.ticks_diff(', oled_source)

        with open(os.path.join(ROOT, 'micropython', 'lora.py'), 'r', encoding='utf-8') as handle:
            lora_source = handle.read()
        handler_start = lora_source.index('async def handle_simple_session_hub(clear):')
        handler_end = lora_source.index('\nasync def handle_incoming_packet(msg):', handler_start)
        handler = lora_source[handler_start:handler_end]
        self.assertIn('_stage_remote_lora_ota_job(remote_uid, remote_fw)', handler)
        self.assertIn('await _send_lora_ota_job(remote_uid)', handler)
        self.assertIn("remote_fw = ''", lora_source)
        self.assertNotIn('Chunk {i}/{total} repeated', lora_source)
        self.assertIn('last_chunk_ticks', lora_source)
        self.assertIn('Silence ACK withheld for partial session', lora_source)
        self.assertIn('jitter_ms = sum(ord(char) for char in uid) % 801', lora_source)

        with open(os.path.join(ROOT, 'micropython', 'ota.py'), 'r', encoding='utf-8') as handle:
            ota_source = handle.read()
        self.assertIn('def _dest_path(name):', ota_source)
        self.assertIn("return '/' + base if base else ''", ota_source)
        self.assertIn('def _write_version(version):', ota_source)
        self.assertIn("('/version.txt', 'version.txt')", ota_source)
        self.assertIn('def _frozen_allowlist_files(allow):', ota_source)
        self.assertIn('OTA: cannot override frozen', ota_source)
        self.assertIn('live_hash = _sha256_file(final_path)', ota_source)
        self.assertIn('OTA: apply completed ver=%s', ota_source)

        ota_tree = ast.parse(ota_source)
        ota_namespace = {}
        for node in ota_tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == '_dest_path':
                exec(compile(ast.Module(body=[node], type_ignores=[]), 'ota.py', 'exec'), ota_namespace)
        self.assertEqual(ota_namespace['_dest_path']('settings.py'), '/settings.py')

    def test_scheduler_and_routines_contracts(self):
        with open(os.path.join(ROOT, 'micropython', 'main.py'), 'r', encoding='utf-8') as handle:
            source = handle.read()
        self.assertIn('run_once=False', source)
        self.assertIn("'run_once': bool(run_once)", source)
        self.assertIn("from provision import first_boot_provision", source)
        field_start = source.index('async def periodic_field_data_task():')
        field_end = source.index('\n# Periodic command poll task', field_start)
        self.assertNotIn('while True', source[field_start:field_end])

        with open(os.path.join(ROOT, 'micropython', 'routines.py'), 'r', encoding='utf-8') as handle:
            routines_source = handle.read()
        self.assertIn("'DEBUG_ROUTINES'", open(SETTINGS_PATH, 'r', encoding='utf-8').read())
        self.assertIn('def validate_routine(routine):', routines_source)
        self.assertIn("ALLOWED_ACTIONS = {'relay', 'log', 'flag', 'record', 'sleep_skip'}", routines_source)
        self.assertNotIn('exec(', routines_source)
        self.assertNotIn('eval(', routines_source)

    def test_lora_hmac_parity_helpers_are_stable(self):
        lora_path = os.path.join(ROOT, 'micropython', 'lora.py')
        with open(lora_path, 'r', encoding='utf-8') as handle:
            source = handle.read()

        namespace = {'uhashlib': hashlib}
        tree = ast.parse(source)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in {'hmac_sha256', 'lora_hmac_material', 'lora_hmac_digest'}:
                exec(compile(ast.Module(body=[node], type_ignores=[]), lora_path, 'exec'), namespace)

        secret = '7383daf15e2f078f7d4316f4aa0d0e9746355b461da5932e4d62352b4e728197'
        message = 'HELLO:unit-test'
        counter = 7

        material = namespace['lora_hmac_material'](message, counter)
        expected = hmac.new(secret.encode('utf-8'), material, hashlib.sha256).digest()

        self.assertEqual(namespace['hmac_sha256'](secret.encode('utf-8'), material), expected)
        self.assertEqual(namespace['lora_hmac_digest'](secret, message, counter), expected)

    def test_manifest_version_matches_runtime_config(self):
        manifest_module = load_module_from_path('generate_manifest', MANIFEST_SCRIPT_PATH)

        with open(VERSION_PATH, 'r', encoding='utf-8') as handle:
            version = handle.read().strip()

        with open(SETTINGS_PATH, 'r', encoding='utf-8') as handle:
            settings_text = handle.read()

        self.assertIn('FIRMWARE_VERSION = _read_firmware_version()', settings_text)
        self.assertEqual(manifest_module.read_version(), version)

    def test_remote_loop_gate_and_lora_diagnostics_contract(self):
        with open(os.path.join(ROOT, 'micropython', 'main.py'), 'r', encoding='utf-8') as handle:
            main_text = handle.read()
        with open(os.path.join(ROOT, 'micropython', 'lora.py'), 'r', encoding='utf-8') as handle:
            lora_text = handle.read()
        self.assertIn('REMOTE_DISABLE_CONNECTLORA_LOOP', main_text)
        self.assertIn('runtime_remote = str(getattr(settings, \'NODE_TYPE\', \'\') or \'\').strip().lower() == \'remote\'', main_text)
        self.assertIn('persisted_remote = str(load_persisted_node_type() or \'\').strip().lower() == \'remote\'', main_text)
        self.assertIn("'rx listen lora=%s busy=%s'", lora_text)
        self.assertIn("'init failed; retry in 5s (no abort)'", lora_text)
        self.assertIn('READY not received; sending one-chunk payload best-effort', lora_text)
        self.assertIn("'irq=0x%04x status=0x%02x mode=%d'", lora_text)
        self.assertIn('IRQ_RX_DONE = 0x0002', lora_text)
        self.assertIn("await debug_print('startReceive armed', 'LORA')", lora_text)
        self.assertIn('last_irq_log_ticks', lora_text)
        self.assertIn('def arm_rx():', lora_text)
        self.assertIn('lora.setDioIrqParams(IRQ_ALL, IRQ_RX, 0, 0)', lora_text)
        arm_end = lora_text.index('def _chip_status():')
        self.assertNotIn('PREAMBLE_DETECTED', lora_text[lora_text.index('def arm_rx():'):arm_end])
        self.assertNotIn('getPacketLength', lora_text[lora_text.index('def arm_rx():'):arm_end])
        ready_start = lora_text.index('def _lora_rx_ready():')
        ready_end = lora_text.index('\n\nasync def _record_lora_session_failure', ready_start)
        self.assertNotIn('getPacketLength', lora_text[ready_start:ready_end])
        self.assertIn('status=0x%02x mode=%d', lora_text)
        self.assertIn("'not in RX — re-arm'", lora_text)
        self.assertIn("'BEACON:%s' % _usable_unit_id()", lora_text)
        self.assertIn('LORA_BASE_BEACON_PAUSE_DURING_SESSION', lora_text)
        self.assertIn("raw.startswith('BEACON:')", lora_text)
        hello_start = lora_text.index('async def send_hello_and_wait_ready')
        hello_end = lora_text.index('\ndef _lora_data_budget()', hello_start)
        self.assertIn('window_end = min(deadline', lora_text[hello_start:hello_end])
        self.assertIn('and \'BASE\' in parts', lora_text[hello_start:hello_end])
        self.assertIn('_last_rx_digest', lora_text)
        self.assertIn("raw.decode('utf-8')", lora_text)
        self.assertIn("clear.startswith(('READY:', 'ACK:', 'BEACON:'))", lora_text)
        self.assertIn('LoRa session busy watchdog cleared', lora_text)
        self.assertIn('def _looks_collided(message):', lora_text)
        self.assertIn("text.split(',DATA:', 1)[0].count('TYPE:') > 1", lora_text)
        self.assertIn('def _canonicalize_remote_record(uid, payload, rssi=None):', lora_text)
        self.assertIn('build_field_data_record(', lora_text)
        self.assertIn('ENABLE_LORA_OTA', lora_text)
        self.assertIn('IRQ_PREAMBLE', lora_text)
        self.assertIn('lora.clearIrqStatus(non_rx_done)', lora_text)
        self.assertIn('lora.recv(length)', lora_text)
        self.assertIn("getattr(settings, 'LORA_CRC_ENABLED', False)", lora_text)
        self.assertIn("b.startswith('TYPE:')", lora_text)
        self.assertIn('assemble failed; no ACK uid=%s', lora_text)
        self.assertIn("skipped=lora_startup", main_text)
        self.assertIn("skipped=lora_busy", main_text)
        self.assertIn("result = run_remote_deep_sleep()", main_text)
        self.assertIn("settings._REMOTE_DEEPSLEEP_ACTIVE = False", main_text)

        with open(os.path.join(ROOT, 'unit-connector', 'includes', 'field-data-api.php'), 'r', encoding='utf-8') as handle:
            field_api = handle.read()
        self.assertIn("$is_bridged = ($rec_unit !== ''", field_api)
        self.assertIn("if (isset($record_unit_ids[$remote_unit])) continue;", field_api)
        self.assertIn("$rec['humid']", field_api)
        self.assertIn("$rec['volt']", field_api)
        self.assertIn("if (!$is_bridged && !empty($t['machine_id']))", field_api)
        self.assertIn("$t['machine_id'] = '';", field_api)
        self.assertNotIn("|| !empty($data['bridge'])", field_api)
        self.assertIn("if (!$is_bridged && !$rec_unit && $rec_machine)", field_api)
        self.assertIn("if (!$is_bridged && $rec_unit && $rec_machine)", field_api)

        settings_mod = types.ModuleType('settings')
        settings_mod.LOG_DIR = '/logs'
        settings_mod.NODE_TYPE = 'remote'
        settings_mod.REMOTE_DISABLE_CONNECTLORA_LOOP = True
        settings_mod.LORA_SIMPLE_SESSION_ONLY = True
        settings_mod.PAIRED_BASE_UID = 'BASE123'
        settings_mod.LORA_CHUNK_SIZE = 96
        settings_mod.REMOTE_NODE_INFO = {
            'R1': {'missed_syncs': 2, 'last_heartbeat_ts': 123456},
            'R2': {'missed_syncs': 0, 'last_heartbeat_ts': 123457},
        }
        sys.modules['settings'] = settings_mod

        sdata_mod = types.ModuleType('sdata')
        sdata_mod.lora_SigStr = -82
        sdata_mod.lora_snr = 8
        sdata_mod.LORA_CONNECTED = True
        sdata_mod.lora_last_rx_ts = 222
        sdata_mod.lora_last_tx_ts = 333
        sys.modules['sdata'] = sdata_mod

        diagnostics_module = load_module_from_path('diagnostics_real', os.path.join(ROOT, 'micropython', 'diagnostics.py'))

        diag = diagnostics_module.get_lora_health()
        self.assertEqual(diag['loop_mode'], 'deep_sleep')
        self.assertEqual(diag['session_mode'], 'simple')
        self.assertEqual(diag['paired_base_uid'], 'BASE123')
        self.assertEqual(diag['chunk_size'], 96)
        self.assertEqual(diag['remote_nodes'], 2)

    def test_lora_session_receive_and_uid_contracts(self):
        lora_path = os.path.join(ROOT, 'micropython', 'lora.py')
        with open(lora_path, 'r', encoding='utf-8') as handle:
            source = handle.read()

        listener_start = source.index('async def ensure_lora_listening():')
        listener_end = source.index('\nasync def init_lora():', listener_start)
        listener = source[listener_start:listener_end]
        self.assertNotIn('lora.recv(', listener)
        self.assertIn('startReceive', listener)
        self.assertIn('setBlockingCallback(False, callback=_lora_irq_callback)', source)
        self.assertIn('def _usable_unit_id():', source)
        self.assertIn("uid.lower() in ('none', 'null', 'unknown', 'n/a')", source)
        self.assertIn("parts[0] == 'READY' and parts[1] == uid", source)
        self.assertIn("parts[0] == 'ACK'", source)
        self.assertIn("if len(parts) < 4 or parts[1] != uid or parts[2] != 'NEXT':", source)
        self.assertIn("await _record_lora_session_failure('READY timeout')", source)
        self.assertIn("await _record_lora_session_failure('Final ACK timeout')", source)
        self.assertIn('def _assemble_simple_session_field_data(', source)
        self.assertIn('def _simple_session_parse_chunk(', source)
        self.assertIn('def _clean_b64(value):', source)
        self.assertIn('def _valid_unit_uid(uid):', source)
        self.assertIn('def _chunk_data_ok(data, uid=None):', source)
        self.assertIn("st.get('simple_chunks')", source)
        self.assertIn('candidate = _clean_b64(data_b64)', source)
        self.assertIn('ch[idx] = candidate', source)
        self.assertIn("st.get('assemble_fail_count')", source)
        self.assertIn("Dropped invalid HELLO uid=", source)
        self.assertIn("Dropped invalid CHUNK uid=", source)
        self.assertIn("Dropped invalid END uid=", source)
        self.assertIn("assemble failed; no ACK uid=%s", source)
        self.assertIn("candidate_ok = _chunk_data_ok(candidate, uid=uid)", source)
        self.assertIn('def _is_truncated_rx(raw):', source)
        self.assertIn('lora.recv(length)', source)
        self.assertIn("Dropped truncated RX len=%d", source)
        self.assertIn("text = raw.decode('utf-8').strip().rstrip('\\x00')", source)
        namespace = {}
        tree = ast.parse(source)
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(getattr(target, 'id', '') == '_B64_KEEP' for target in node.targets):
                exec(compile(ast.Module(body=[node], type_ignores=[]), lora_path, 'exec'), namespace)
            if isinstance(node, ast.FunctionDef) and node.name in {'_clean_b64', '_valid_unit_uid', '_chunk_data_ok', '_is_truncated_rx'}:
                exec(compile(ast.Module(body=[node], type_ignores=[]), lora_path, 'exec'), namespace)
            if isinstance(node, ast.Assign) and any(getattr(target, 'id', '') in ('_SHORT_OK', '_TRUNC_HEADS') for target in node.targets):
                exec(compile(ast.Module(body=[node], type_ignores=[]), lora_path, 'exec'), namespace)
        self.assertEqual(namespace['_clean_b64']('eyJ1IjoieCJ9|CRC:21CE\x00TYPE:X'), 'eyJ1IjoieCJ9')
        self.assertIn("for marker in ('\\x00', '|HMAC:', '|CRC:', '|CNT:')", source)
        self.assertTrue(namespace['_valid_unit_uid']('unit-l7riag'))
        self.assertFalse(namespace['_valid_unit_uid']('unit-5HELLO'))
        self.assertFalse(namespace['_is_truncated_rx'](b'HELLO:unit-5axfdv'))
        self.assertFalse(namespace['_is_truncated_rx'](b'END:unit-e9wjst:1'))
        self.assertTrue(namespace['_is_truncated_rx'](b'TYPE:FIELD_DATA_C'))
        self.assertTrue(namespace['_is_truncated_rx'](b'HEHELLO:unit-5axfdv'))
        self.assertTrue("st['data']['FIELD_DATA']" in source or 'st["data"]["FIELD_DATA"]' in source)
        self.assertIn('send_ack=False', source)
        self.assertNotIn('ch[idx] = clear', source)
        self.assertIn("ack += ':CMD:%s' % encoded_cmd", source)
        self.assertIn("'t': getattr(sdata, 'cur_device_temp_f', None)", source)
        self.assertIn("CHUNK:0/1", source)
        self.assertIn("chunks=1 idx=0 ok=", source)
        self.assertIn("'v': getattr(sdata, 'sys_voltage', None)", source)
        self.assertIn("return {key: value for key, value in payload.items() if value is not None and value != ''}", source)
        payload_start = source.index('def _minimal_remote_payload():')
        payload_end = source.index('\n\nasync def send_field_data_controlled', payload_start)
        payload_source = source[payload_start:payload_end]
        self.assertIn("'h': getattr(sdata, 'cur_device_humid', None)", payload_source)
        self.assertIn("'b': getattr(sdata, 'cur_device_bar_pres', None)", payload_source)
        self.assertIn("'v': getattr(sdata, 'sys_voltage', None)", payload_source)
        self.assertIn("'fw': getattr(settings, 'FIRMWARE_VERSION', '') or ''", payload_source)
        controlled_start = source.index('async def send_field_data_controlled(payload):')
        controlled_end = source.index('\nasync def _send_remote_command_result', controlled_start)
        controlled = source[controlled_start:controlled_end]
        self.assertIn('batch_id = None', controlled)
        self.assertIn("if len(parts) < 4 or parts[1] != uid or parts[2] != 'NEXT':", controlled)
        self.assertIn("decode('ascii')", controlled)
        self.assertNotIn('Chunk {i}/{total} repeated', controlled)
        self.assertIn("Dropped invalid CHUNK data uid=", source)
        self.assertIn('async def _wait_tx_done(timeout=None):', source)
        wait_start = source.index('async def _wait_tx_done(timeout=None):')
        wait_end = source.index('\ndef calculate_next_delay', wait_start)
        self.assertNotIn('return lora is not None', source[wait_start:wait_end])
        self.assertNotIn('hard_reset_lora', source[wait_start:])
        self.assertIn('_session_field_chunks(st)', source)
        send_start = source.index('async def _send_with_retry(')
        wait_start = source.index('async def _wait_tx_done(', send_start)
        self.assertNotIn('ensure_lora_listening()', source[send_start:source.index('lora.send(tx_view)')])
        self.assertNotIn('hard_reset_lora', source[wait_start:])

        remote_path = os.path.join(ROOT, 'micropython', 'remote_node.py')
        with open(remote_path, 'r', encoding='utf-8') as handle:
            remote_source = handle.read()
        self.assertIn('_usable_unit_id()', remote_source)
        self.assertIn('load_persisted_node_type', remote_source)
        self.assertIn("expected remote role but persisted/runtime role is", remote_source)


if __name__ == '__main__':
    unittest.main()
