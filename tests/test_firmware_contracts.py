import ast
import hashlib
import hmac
import importlib.util
import os
import sys
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

    return {
        'ujson': ujson,
        'uasyncio': uasyncio,
        'utime': utime,
        'machine': machine,
        'gc': gc,
        'settings': settings,
        'config_persist': config_persist,
        'diagnostics': diagnostics,
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

        manifest = manifest_module.build_manifest(version=expected_version)
        self.assertEqual(manifest['version'], expected_version)
        self.assertTrue(manifest['files'])
        self.assertIn('settings.py', manifest['files'])

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
        self.assertEqual(compact['t_f'], 72.1)
        self.assertEqual(compact['hum'], 45)
        self.assertNotIn('sys_voltage', compact)
        self.assertEqual(compact['note'], 'keep')

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
        self.assertIn('REMOTE_DISABLE_CONNECTLORA_LOOP', main_text)
        self.assertIn('use_deep_sleep = is_remote and bool(getattr(settings, \'REMOTE_DISABLE_CONNECTLORA_LOOP\', True))', main_text)

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


if __name__ == '__main__':
    unittest.main()
