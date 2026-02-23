# Firmware Version: v2.06.4

# Bootstrap critical variables before any reference
try:
    FIELD_DATA_APP_PASS
except NameError:
    FIELD_DATA_APP_PASS = ""  # default; overridden by persisted config later
# Ensure claim-flow toggles exist before use
try:
    ENABLE_FIRST_CHECKIN_CLAIM
except NameError:
    ENABLE_FIRST_CHECKIN_CLAIM = False
try:
    CLAIM_CONFIRM_DELAY_S
except NameError:
    CLAIM_CONFIRM_DELAY_S = 0

# Move LOG_DIR and essential file paths near the top so other constants can reference them.
LOG_DIR = '/logs'

# Files used for persistence (UNIT_ID, staged/applied settings, provision flag)
UNIT_ID_FILE = LOG_DIR + '/unit_id.txt'
MACHINE_ID_FILE = LOG_DIR + '/machine_id.txt'
WORDPRESS_API_URL_FILE = LOG_DIR + '/wordpress_api_url.txt'
PROVISIONED_FLAG_FILE = LOG_DIR + '/provisioned.flag'
REMOTE_SETTINGS_STAGED_FILE = LOG_DIR + '/remote_settings.staged.json'
REMOTE_SETTINGS_APPLIED_FILE = LOG_DIR + '/remote_settings.applied.json'
REMOTE_SETTINGS_PREV_FILE = LOG_DIR + '/remote_settings.prev.json'
UNIT_NAME_FILE = '/logs/unit_name.txt'   # Persisted human-friendly unit name (applied after provisioning)

# Generic logs
LOG_FILE = LOG_DIR + '/lora.log'
ERROR_LOG_FILE = LOG_DIR + '/lora_errors.log'
FIELD_DATA_LOG = LOG_DIR + '/field_data.log'
DATA_HISTORY_LOG = LOG_DIR + '/data_history.log'

# --- Field Data Logging and controls ---
FIELD_DATA_DELIVERED_LOG = LOG_DIR + '/field_data.delivered.log'  # archive of delivered entries
FIELD_DATA_MAX_BYTES = 256 * 1024  # rotate/trim when exceeding this size
FIELD_DATA_MAX_BATCH = 50          # max records per POST batch
FIELD_DATA_SEND_INTERVAL = 30      # seconds, adjustable remotely
FIELD_DATA_BACKOFF_S = 10          # retry backoff on HTTP failures
FIELD_DATA_GZIP = True             # allow gzip payload when supported

# Then other vars
UNIT_ID = "None"              # 6-digit assigned by Admin after first check-in (persisted locally)
UNIT_Name = "No Device Name"    # Human-friendly name (provisioned)
NODE_TYPE = 'base'             # 'base','wifi', or 'remote'; base can host LoRa network & WiFi; remote uses LoRa primarily
#NODE_TYPE = 'remote'          # Uncomment for remote role during flashing

FIRMWARE_VERSION = "v2.00.1a"   # Firmware version string

 # WordPress Unit Connector API integration
WORDPRESS_API_URL = ""   # Customer Unit Connector site for provisioned devices
WORDPRESS_USERNAME = "agadmin"              # (Optional) Basic auth / future removal for token-based access
WORDPRESS_PASSWORD = "Pepper-1"             # (Optional) Replace with secure secret storage in production

 # WordPress TMON Admin API integration
# --- Provisioning & Identity ---
# MACHINE_ID is detected from chipset on first boot (populated by firmware); persisted to disk and echoed here
MACHINE_ID = None                       # Chipset UID hex string
UNIT_PROVISIONED = False                # True after provisioning applied & reboot
TMON_ADMIN_API_URL = "https://tmonsystems.com"  # Admin hub base URL for registration / provisioning
PROVISION_CHECK_INTERVAL_S = 30         # Seconds between registration attempts
PROVISION_MAX_RETRIES = 60              # Max immediate retries before backoff escalation
WIFI_ALWAYS_ON_WHEN_UNPROVISIONED = True  # Keep WiFi on until provisioning completes (remote needs Internet initially)
WIFI_DISABLE_AFTER_PROVISION = True       # Remote nodes disable WiFi after provisioning (LoRa only thereafter)
PROVISIONED_FLAG_FILE = '/logs/provisioned.flag'  # Presence indicates initial hub registration completed
REMOTE_SETTINGS_STAGED_FILE = '/logs/remote_settings.staged.json'  # Admin or UC pushed settings awaiting apply
REMOTE_SETTINGS_APPLIED_FILE = '/logs/remote_settings.applied.json' # Snapshot of last applied settings
REMOTE_SETTINGS_PREV_FILE = '/logs/remote_settings.prev.json'       # Snapshot of previous settings before last apply
UNIT_ID_FILE = '/logs/unit_id.txt'       # Persisted UNIT_ID mapping
MACHINE_ID_FILE = '/logs/machine_id.txt' # Persisted MACHINE_ID after detection
LAST_FIRMWARE_CHECK_FILE = '/logs/fw_last_check.txt'
OTA_PENDING_FILE = '/logs/ota_pending.flag'

#Feature/device enables 
ENABLE_WIFI = True
ENABLE_LORA = True
ENABLE_OLED = True
GPS_ENABLED = True                      # Global GPS enable
ENGINE_ENABLED = False 

# Waveshare Environmental / Sensor settings
ENABLE_sensorBME280 = True              # BME280 Sensor Enable
i2cAddr_BME280 = 0x76
ENABLE_sensorDHT11 = False              # BME280 Sensor Enable
i2cAddr_DHT11 = 0x76
ENABLE_sensorLTR390 = False 
light_i2c_address = 0x53
ENABLE_MPU925x = False
motion_i2c_address = 0x68
ENABLE_sensorSGP40 = False
voc_i2c_address = 0x59
ENABLE_sensorTSL2591 = False
lux_i2c_address = 0x29

# Pin definitions
SYS_VOLTAGE_PIN = 3                # ADC pin used for voltage divider (adjust as needed)
# LED Light control pin
LED_PIN = 21
# Relay control pins
RELAY_PIN1 = 17
RELAY_PIN2 = 18
RELAY_PIN3 = None
RELAY_PIN4 = None
RELAY_PIN5 = None
RELAY_PIN6 = None
RELAY_PIN7 = None
RELAY_PIN8 = None
# I2C pins
I2C_A_SCL_PIN = 33
I2C_A_SDA_PIN = 34
I2C_B_SCL_PIN = 38
I2C_B_SDA_PIN = 39
# LoRa Radio pins
SPI_BUS = 1
CLK_PIN = 35
MOSI_PIN = 36
MISO_PIN = 37
CS_PIN = 14
IRQ_PIN = 4
RST_PIN = 40
BUSY_PIN = 13
# RS485 / Engine controller pins
CH1_TX_PIN = 4
CH1_RX_PIN = 5
CH2_TX_PIN = 6
CH2_RX_PIN = 7

#Debug toggles flags
DEBUG = False
DEBUG_SAMPLING = False
DEBUG_BME280 = False
DEBUG_DHT11 = False
DEBUG_TEMP = False
DEBUG_BAR = False
DEBUG_HUMID = False
DEBUG_LORA = True
DEBUG_WIFI_CONNECT = False
DEBUG_OTA = True
DEBUG_PROVISION = True
DEBUG_DISPLAY = False
DEBUG_BASE_NODE = True
DEBUG_REMOTE_NODE = True
DEBUG_WIFI_NODE = False
DEBUG_WPREST = False
DEBUG_FIELD_DATA = True
DEBUG_RS485 = False

# Backwards-compatible aliases for older/alternate flag names used by debug_print/callsites
DEBUG_WIFI = DEBUG_WIFI_CONNECT
DEBUG_OLED = DEBUG_DISPLAY
DEBUG_WP_REST = DEBUG_WPREST
DEBUG_PROV = DEBUG_PROVISION

# RS485 / Engine controller
ENGINE_FORCE_DISABLED = True          # Temporary kill switch to disable engine control
ENABLE_RS485 = False                  # Enable RS485 engine controller
ENABLE_ENGINE_CONTROLLER = False      # Enable engine polling/controls
ENGINE_POLL_INTERVAL_S = 30           # Seconds between polls
ENGINE_DEV_ADDR = 1                   # Base Modbus address
ENGINE_DEV_COUNT = 1                  # Number of engines chained
ENGINE_SAMPLE_RATE = 30               # Heartbeat/sample cadence seconds
ENGINE_KEEPALIVE = 5                  # Extra keep-alive loops between polls
ENGINE_PUMP1_COIL = 0                 # Coil address for Pump1
ENGINE_PUMP2_COIL = 1                 # Coil address for Pump2
COMM_BAUD = 9600
COMM_PARITY = None
COMM_STOP_BITS = 1


# Relay Settings
ENABLE_RELAY1 = True
ENABLE_RELAY2 = True
ENABLE_RELAY3 = False
ENABLE_RELAY4 = False
ENABLE_RELAY5 = False
ENABLE_RELAY6 = False
ENABLE_RELAY7 = False
ENABLE_RELAY8 = False
RELAY_RUNTIME_LIMITS = {               # Per relay runtime cap (minutes) override; fallback to RELAY_SAFETY_MAX_RUNTIME_MIN
    1: 720,
    2: 720
}

# wifi settings
WIFI_SSID = "house of nonsense"          # Provisioned or manually set SSID
WIFI_PASS = "bluebread219"               # Provisioned or manually set password
WIFI_CONN_RETRIES = 5                     # Immediate retries before longer backoff
WIFI_BACKOFF_S = 15                       # Base backoff between retry bursts
WIFI_SIGNAL_SAMPLE_INTERVAL_S = 30        # Interval to refresh RSSI for OLED

# --- LoRa sync & recovery ---
nextLoraSync = 100                      # Remote next absolute sync epoch (assigned by base)
LORA_SYNC_WINDOW = 2                    # seconds of minimum spacing between remote sync slots
LORA_SLOT_SPACING_S = LORA_SYNC_WINDOW  # alias for clarity
LORA_CHECK_IN_MINUTES = 5               # Default check-in cadence in minutes used when no explicit nextLoraSync is set
LORA_INIT_RETRY_BACKOFF_S = 1      # small delay between init retries
LORA_HARD_REBOOT_ERR_CODES = [-2]  # error codes that trigger hard reboot (e.g., ERR_CHIP_NOT_FOUND)
LORA_ERR_PERSIST_REBOOTS = 2       # if persists this many times across reboots, stop rebooting and log
ERROR_STATE_FILE = LOG_DIR + '/last_error.state'  # persist last error and reboot counters
LORA_REMOTE_INFO_LOG = LOG_DIR + '/remote_info.log'  # base records remote identities here
LORA_HMAC_ENABLED = True            # When True, firmware includes a signature with LoRa frames
LORA_HMAC_SECRET = ''               # Per-device secret used to sign LoRa frames (provisioned)
LORA_HMAC_COUNTER_FILE = LOG_DIR + '/lora_ctr.json'  # Persist local counter (remote)
LORA_REMOTE_COUNTERS_FILE = LOG_DIR + '/remote_ctr.json'  # Base: last seen counters per remote
LORA_HMAC_REJECT_UNSIGNED = True     # When enabled + HMAC active, reject frames lacking valid signature
LORA_HMAC_REPLAY_PROTECT = True      # Enforce strictly increasing counter (ctr) to prevent replay
LORA_ENCRYPT_ENABLED = True         # Optional payload encryption (ChaCha20 stream cipher)
LORA_ENCRYPT_SECRET = ''  
#LoRa Radio Settings
FREQ = 915.0                               # Regional frequency (EU example); change per deployment
BW = 125.0
SF = 12
CR = 7                                    # stronger coding rate (4/7)
SYNC_WORD = 0xF4
POWER = 14                                # default transmit power reduced for regulatory safety
CURRENT_LIMIT = 140.0
PREAMBLE_LEN = 12
CRC_ON = True
TCXO_VOLTAGE = 1.8  # Confirmed for Waveshare SX1262
USE_LDO = True
CAD_SYMBOLS = 8  # Symbols for CAD detection before TX
# NEW: CAD backoff when channel busy (seconds)
LORA_CAD_BACKOFF_S = 2       # Base backoff when CAD indicates busy
LORA_CAD_BACKOFF_MAX_S = 30  # Maximum randomized backoff applied

# --- Last error telemetry (include in sdata payloads) ---
LAST_ERROR_CODE = 0
LAST_ERROR_NAME = ''
LAST_ERROR_TS = None                    # epoch seconds
TELEMETRY_INCLUDE_LAST_ERROR = True     # Include last error telemetry in field data
ERROR_COUNT_RESET_INTERVAL_S = 3600     # Period to reset soft error counters

# --- GPS / Sensors / Feature flags ---
# Enable GPS location features. If False, GPS fields are ignored.
# Source of GPS coordinates: 'manual' (static in this file), 'module' (hardware GNSS), 'network' (WiFi/IP geolocation via service)
GPS_SOURCE = 'manual'
# Current coordinates (degrees). For 'manual', set these; for 'module'/'network', they will be updated at runtime.
GPS_LAT = None      # float or None
GPS_LNG = None      # float or None
GPS_ALT_M = None    # altitude in meters (optional)
GPS_ACCURACY_M = None  # estimated accuracy in meters (optional)
GPS_LAST_FIX_TS = None  # epoch seconds of last known fix
# Allow settings fetched from WordPress (or commands) to override GPS_*
GPS_OVERRIDE_ALLOWED = True
# For base stations: include base GPS in LoRa ACK packets to inform remotes
GPS_BROADCAST_TO_REMOTES = True
# For remotes: accept GPS coordinates from base ACK and persist as fixed position
GPS_ACCEPT_FROM_BASE = True

#oLED Options 
OLED_UPDATE_INTERVAL_S = 10               # Refresh interval for status page
OLED_SCROLL_ENABLED = False               # Future multi-page support
OLED_PAGE_ROTATE_INTERVAL_S = 30          # Interval for automatic page rotation

# NEW: layout heights for header/footer so message area does not overlap
OLED_HEADER_HEIGHT = 16                   # pixels reserved at top for header (voltage/bars)
OLED_FOOTER_HEIGHT = 12                   # pixels reserved at bottom for footer (temp/unit)

# NEW: control whether the compact network bars and labels are shown in header
DISPLAY_NET_BARS = True                   # When True, show concise "W"/"L" bars in OLED header

# NEW: seconds to flip between voltage and r_temp_f in header (smooth flip)
OLED_HEADER_FLIP_S = 4

#Sampling Toggles
SAMPLE_TEMP = True
COMPARE_TEMP = True                     # Compare against thresholds for frost/heat watch triggers
SAMPLE_BAR = True
COMPARE_BAR = True
SAMPLE_HUMID = True
COMPARE_HUMID = True
SAMPLE_LIGHT = False                    # Future light sensor enable
SAMPLE_VOC = False                      # VOC sensor enable
SAMPLE_LUX = False                      # Lux sensor enable

#Frost & Heat Monitoring
ENABLE_FROSTWATCH = False
FROSTWATCH_ACTIVE_TEMP = 70
FROSTWATCH_ALERT_TEMP = 42
FROSTWATCH_ACTION_TEMP = 38
FROSTWATCH_STANDDOWN_TEMP = 40

ENABLE_HEATWATCH = False
HEATWATCH_ACTIVE_TEMP = 90
HEATWATCH_ALERT_TEMP = 100
HEATWATCH_ACTION_TEMP = 110
HEATWATCH_STANDDOWN_TEMP = 105

# System voltage measurement settings
SYS_VOLTAGE_MAX = 5.0                      # Maximum measurable voltage (adjust for your divider)
SYS_VOLTAGE_SAMPLE_INTERVAL_S = 60         # Voltage telemetry refresh cadence

# --- OTA & Command/Relay Safety ---
OTA_ENABLED = True                       # Re-enable OTA updates
OTA_BACKUP_ENABLED = True                 # Keep backup of current firmware/settings
OTA_BACKUP_DIR = '/ota/backup'
OTA_MAX_RETRIES = 3
ALLOW_REMOTE_COMMANDS = True              # Accept OTA commands/relay toggles
RELAY_SAFETY_MAX_RUNTIME_MIN = 1440       # Safety cap for relay runtime
OTA_VERSION_ENDPOINT = 'https://raw.githubusercontent.com/kevinnutt83/TMON/main/micropython/version.txt'
OTA_FIRMWARE_BASE_URL = 'https://raw.githubusercontent.com/kevinnutt83/TMON/main/micropython/'
OTA_MANIFEST_URL = OTA_FIRMWARE_BASE_URL + 'manifest.json'
OTA_MIN_VERSION = FIRMWARE_VERSION         # block any update older than running firmware
OTA_REQUIRE_NEWER_VERSION = True           # skip when remote version <= current
OTA_HASH_VERIFY = True                   # keep integrity checks enabled
OTA_APPLY_INTERVAL_S = 5                  # Check/apply pending update every few seconds (was 600)
OTA_RESTORE_ON_FAIL = True                # Restore backups if any file verification/apply fails
OTA_MAX_FILE_BYTES = 256*1024             # Safety cap per file download size
OTA_FILES_ALLOWLIST = [                   # Limit which files can be updated via OTA
    'main.py','lora.py','utils.py','sampling.py','settings.py','relay.py','oled.py','ota.py','wprest.py'
]
OTA_MANIFEST_SIG_URL = OTA_MANIFEST_URL + '.sig'  # Optional detached HMAC signature (hex)
OTA_MANIFEST_HMAC_SECRET = ''             # If set, verify manifest with HMAC(secret, manifest_bytes)
# Added OTA safety toggles
OTA_ALLOW_DOWNGRADE = False              # block downgrades to avoid stale hashes
OTA_SKIP_OLDER_VERSION = True            # skip applies when repo version < current
OTA_ABORT_ON_HASH_MISMATCH = False       # keep main loop running; do not abort on mismatch
OTA_RETRY_ON_HASH_MISMATCH = True        # retry download when hash fails
OTA_MAX_HASH_FAILURES = 3                # bounded retries before giving up
OTA_HASH_RETRY_INTERVAL_S = 2            # short delay (seconds) before retrying after a hash failure

# OTA fallback mirrors to reduce GitHub 400s during fetch
OTA_VERSION_URLS = [
    'https://raw.githubusercontent.com/kevinnutt83/TMON/main/micropython/version.txt',
]
OTA_MANIFEST_URLS = [
    'https://raw.githubusercontent.com/kevinnutt83/TMON/main/micropython/manifest.json',
]
OTA_HTTP_HEADERS = {
    'User-Agent': 'TMON-Device/v2.06.0',
    'Accept': '*/*',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
}

# --- Connectivity ---
HTTP_TIMEOUT_S = 20
TLS_VERIFY = True

DEVICE_SUSPENDED = False                  # Suspension flag set by Admin/UC commands; halts tasks but allows check-ins
DEVICE_SUSPENDED_FILE = '/logs/suspended.flag'
LORA_NETWORK_NAME = 'tmon'                # Secure network name (provisioned for base & remotes)
LORA_NETWORK_PASSWORD = '12345'           # Simple password handshake (strengthen later)
REMOTE_CHECKIN_INTERVAL_S = 300           # Default remote -> base sync period
REMOTE_CHECKIN_JITTER_S = 5               # Jitter to avoid collisions

# Unit Connector periodic check-in interval for provisioned devices
UC_CHECKIN_INTERVAL_S = 300  # seconds

BASE_REMOTE_TABLE_FILE = '/logs/remotes.table.json'  # Base-maintained remote registry

# --- Field Data HMAC (optional) ---
FIELD_DATA_HMAC_ENABLED = False           # When True, sign each field-data payload
FIELD_DATA_HMAC_SECRET = ''               # Secret for field data HMAC (provisioned)
FIELD_DATA_HMAC_INCLUDE_KEYS = ['unit_id','firmware_version','node_type']  # Keys guaranteed present (order stable)
FIELD_DATA_HMAC_TRUNCATE = 32             # Hex chars of hash to include as signature

TMON_ADMIN_CONFIRM_TOKEN = ''  # Optional small secret to confirm applied settings when device posts; set on Admin & device for security

PLAN = ""  # NEW: subscription plan (standard/pro/enterprise) applied via provisioning

PROVISION_REBOOT_GUARD_FILE = LOG_DIR + '/provision_reboot.flag'  # Prevent repeated soft resets after provisioning

# --- UC Commands & Staged Settings Controls ---
# Devices poll UC for staged commands; confirm after execution
COMMANDS_POLL_INTERVAL_S = 20                # seconds between command polls
COMMANDS_MAX_PER_POLL = 10                   # max commands to fetch in one poll
COMMAND_CONFIRM_DELAY_S = 0.2                # small delay before confirming back

# Staged settings application behavior
APPLY_STAGED_SETTINGS_ON_BOOT = True         # if staged file exists, apply on boot
APPLY_STAGED_SETTINGS_ON_SYNC = True         # re-check staged settings on each UC/Admin sync
STAGED_SETTINGS_KEYS_ALLOW = [
    'WORDPRESS_API_URL','TMON_ADMIN_API_URL','NODE_TYPE','UNIT_Name','PLAN',
    'ENABLE_WIFI','ENABLE_LORA','ENABLE_OLED','DEVICE_SUSPENDED',
    'WIFI_SSID','WIFI_PASS','WIFI_CONN_RETRIES','WIFI_BACKOFF_S',
    'OTA_ENABLED','OTA_CHECK_INTERVAL_S','OTA_APPLY_INTERVAL_S',
    'OTA_VERSION_ENDPOINT','OTA_MANIFEST_URL',
    'SAMPLE_TEMP','SAMPLE_BAR','SAMPLE_HUMID','SYS_VOLTAGE_SAMPLE_INTERVAL_S',
    'GPS_ENABLED','GPS_SOURCE','GPS_LAT','GPS_LNG','GPS_ALT_M','GPS_ACCURACY_M',
    'FIELD_DATA_HMAC_ENABLED','FIELD_DATA_HMAC_SECRET',
    'DEBUG','DEBUG_PROVISION','DEBUG_LORA','DEBUG_WIFI','DEBUG_OTA',
    # Added keys to support device feature toggles and engine/pin control
    'ENGINE_ENABLED','ENGINE_FORCE_DISABLED','ENABLE_SENSORBME280',
    'RELAY_PIN1','RELAY_PIN2','RELAY_RUNTIME_LIMITS',
    'ENABLE_OLED','UNIT_Name'  # ensure these are accepted when staged
]
# Optional denylist to prevent accidental overrides
STAGED_SETTINGS_KEYS_DENY = [
    'FIRMWARE_VERSION','MACHINE_ID'  # never override these from UC
]

# Command names expected from UC/Admin and their runtime aliases
COMMAND_ALIASES = {
    'relay_ctrl': 'relay_ctrl',      # {'relay':1,'state':'on'|'off'}
    'set_var': 'set_var',            # {'key':'DEBUG','value':true}
    'run_func': 'run_func',          # {'name':'reboot'|'ota_check'...,'args':[]}
    'firmware_update': 'firmware_update'
}

# --- OTA/Repository integration aliases (used by ota.py and utils.py) ---
OTA_VERSION_ENDPOINT = OTA_VERSION_ENDPOINT     # alias retained for clarity
OTA_MANIFEST_URL = OTA_MANIFEST_URL             # alias retained for clarity
OTA_FIRMWARE_BASE_URL = OTA_FIRMWARE_BASE_URL   # ensure consistency

# --- Admin/UC integration defaults (device-side) ---
# If WORDPRESS_API_URL is empty at first boot, device will read persisted file and defer until provisioned.
# The device firmware prefers persisted WORDPRESS_API_URL loaded via utils.load_persisted_wordpress_api_url().

# NOTE:
# - sdata.py should include LAST_ERROR_* when TELEMETRY_INCLUDE_LAST_ERROR is True.
# - Sender must append delivered entries to FIELD_DATA_DELIVERED_LOG and truncate FIELD_DATA_LOG post-send.
# - Base must log remote identities to LORA_REMOTE_INFO_LOG on join/sync.

# --- Admin/UC REST endpoint paths (align with v2.00m and current TMON) ---
ADMIN_REGISTER_PATH = '/wp-json/tmon-admin/v1/device/register'       # POST: device registers/checks in
ADMIN_STATUS_PATH   = '/wp-json/tmon-admin/v1/device/status'         # GET: device status by machine_id
ADMIN_SETTINGS_PATH = '/wp-json/tmon-admin/v1/device/settings'       # GET: settings by machine_id
ADMIN_CONFIRM_PATH  = '/wp-json/tmon-admin/v1/device/confirm'        # POST: device confirms provisioning (legacy)
ADMIN_CONFIRM_APPLIED_PATH = '/wp-json/tmon-admin/v1/device/confirm-applied'  # POST: confirm applied (new)

# Admin v2 (versioned provisioning)
ADMIN_V2_CHECKIN_PATH = '/wp-json/tmon-admin/v2/device/checkin'      # POST: device check-in (versioned)
ADMIN_V2_ACK_PATH     = '/wp-json/tmon-admin/v2/device/ack'          # POST: ACK applied settings version

# UC endpoints (device-side)
UC_DEVICE_COMMANDS_PATH        = '/wp-json/tmon/v1/device/commands'         # GET: {unit_id}
UC_DEVICE_COMMAND_CONFIRM_PATH = '/wp-json/tmon/v1/device/command/confirm'  # POST: {unit_id,id,ok}
UC_SETTINGS_STAGED_PATH        = '/wp-json/tmon/v1/admin/device/settings-staged'    # GET: {unit_id|machine_id}
UC_SETTINGS_APPLIED_PATH       = '/wp-json/tmon/v1/admin/device/settings-applied'   # POST: confirm applied

# --- REST headers / auth knobs (device-side HTTP calls) ---
REST_HEADER_ADMIN_KEY = 'X-TMON-ADMIN'     # Admin API key header (UC/Admin integrations)
REST_HEADER_HUB_KEY   = 'X-TMON-HUB'       # Hub shared key header (Admin↔UC trusted channel)
REST_HEADER_READ_KEY  = 'X-TMON-READ'      # Read-only token header (listing endpoints)
REST_HEADER_CONFIRM   = 'X-TMON-CONFIRM'   # Device confirm-applied token header (optional)
REST_HEADER_API_KEY   = 'X-TMON-API-Key'   # Generic API key header (legacy v2.00m sync)
REST_DEFAULT_HEADERS  = {
    'User-Agent': 'TMON-Device/' + FIRMWARE_VERSION,
    'Accept': 'application/json'
}

# Native WordPress REST auth (Application Passwords) — replaces JWT plugin usage
REST_BASIC_AUTH_ENABLED = True
REST_BASIC_AUTH_USERNAME = WORDPRESS_USERNAME
REST_BASIC_AUTH_PASSWORD = FIELD_DATA_APP_PASS  # Application Password (set per UC site)

# Helper: endpoints requiring auth will send Authorization: Basic base64(f"{REST_BASIC_AUTH_USERNAME}:{REST_BASIC_AUTH_PASSWORD}")
# Note: keep FIELD_DATA_USE_JWT = False and FIELD_DATA_USE_APP_PASSWORD = True (already set above).

# Optional device-side confirm token (pairs with Admin expected token)
DEVICE_CONFIRM_TOKEN = TMON_ADMIN_CONFIRM_TOKEN

# --- WPREST canonical endpoints (used by field data; no JWT) ---
# Removed JWT token path; use native Application Passwords for auth
# WPREST_FIELD_DATA_PATH remains unchanged; device uses Basic Authorization header
WPREST_FIELD_DATA_PATH = '/wp-json/tmon/v1/device/field-data'
WPREST_COMMANDS_PATH   = UC_DEVICE_COMMANDS_PATH

# --- Field data uploader behaviour toggles (native WP auth via Application Passwords) ---
FIELD_DATA_USE_JWT = False                         # disable JWT plugin usage
FIELD_DATA_USE_APP_PASSWORD = True                 # enable native Application Passwords (Basic Auth)
FIELD_DATA_APP_USER = WORDPRESS_USERNAME           # WP user for Application Password
FIELD_DATA_APP_PASS = ''                           # Application Password for the user (set per site)
FIELD_DATA_HTTP_TIMEOUT_S = HTTP_TIMEOUT_S
FIELD_DATA_MAX_ATTEMPTS = 5                      # attempts per batch
FIELD_DATA_RETRY_BASE_S = FIELD_DATA_BACKOFF_S   # base backoff in seconds

# Note: When FIELD_DATA_USE_APP_PASSWORD is True, firmware must send:
# Authorization: Basic base64("{FIELD_DATA_APP_USER}:{FIELD_DATA_APP_PASS}")
# with requests to WPREST_FIELD_DATA_PATH and other authenticated endpoints.

# --- Admin device identity and claim flow (firmware-side) ---
ADMIN_CLAIM_ON_FIRST_CHECKIN = ENABLE_FIRST_CHECKIN_CLAIM
ADMIN_CLAIM_DELAY_S = CLAIM_CONFIRM_DELAY_S
ADMIN_CLAIM_ENDPOINT_PATH = ADMIN_CONFIRM_APPLIED_PATH       # prefer newer confirm-applied
ADMIN_LEGACY_CONFIRM_PATH  = ADMIN_CONFIRM_PATH              # legacy confirm endpoint fallback

# --- Safety toggles for WiFi/LoRa command pathways (firmware-side) ---
ALLOW_WIFI_COMMANDS = True
ALLOW_LORA_COMMANDS = True

# --- Admin modal-driven provisioning integration (canonical action names) ---
ADMIN_MODAL_SAVE_QUEUE_ACTION = 'tmon_save_queue_item'       # Admin AJAX: save provisioning/queue item
ADMIN_MODAL_GET_DEVICES_ACTION = 'tmon_get_devices'          # Admin AJAX: merged device listing
ADMIN_MODAL_SEND_COMMAND_ACTION = 'tmon_send_device_command' # Admin AJAX: stage device command

# Modal UX hints (firmware-side logs can reference these to keep consistency)
MODAL_DEFAULT_ROLE_OPTIONS = ['base', 'remote', 'gateway']
MODAL_DEFAULT_PLAN_OPTIONS = ['standard', 'pro']
MODAL_DEFAULT_STATUS_OPTIONS = ['pending', 'active', 'provisioned']

# --- Command names used by modal buttons → firmware mapping ---
COMMAND_NAME_REBOOT = 'reboot'
COMMAND_NAME_FACTORY_RESET = 'factory_reset'

# --- Utility grouping helpers (read-only views of related settings) ---
def get_network_settings():
    """Return a dict of network-related settings for easier inspection."""
    return {
        'WIFI_SSID': WIFI_SSID,
        'WIFI_PASS': WIFI_PASS,
        'WIFI_CONN_RETRIES': WIFI_CONN_RETRIES,
        'WIFI_BACKOFF_S': WIFI_BACKOFF_S,
        'WIFI_SIGNAL_SAMPLE_INTERVAL_S': WIFI_SIGNAL_SAMPLE_INTERVAL_S,
        'ENABLE_WIFI': ENABLE_WIFI,
        'WIFI_DISABLE_AFTER_PROVISION': WIFI_DISABLE_AFTER_PROVISION,
    }

def get_lora_settings():
    """Return a dict of LoRa-related settings for easier inspection."""
    return {
        'ENABLE_LORA': ENABLE_LORA,
        'FREQ': FREQ, 'BW': BW, 'SF': SF, 'CR': CR,
        'SYNC_WORD': SYNC_WORD, 'POWER': POWER,
        'LORA_HMAC_ENABLED': LORA_HMAC_ENABLED,
        'LORA_ENCRYPT_ENABLED': LORA_ENCRYPT_ENABLED,
    }

def get_ota_settings():
    """Return a dict of OTA-related settings for easier inspection."""
    return {
        'OTA_ENABLED': OTA_ENABLED,
        'OTA_VERSION_ENDPOINT': OTA_VERSION_ENDPOINT,
        'OTA_MANIFEST_URL': OTA_MANIFEST_URL,
        'OTA_FIRMWARE_BASE_URL': OTA_FIRMWARE_BASE_URL,
        'OTA_FILES_ALLOWLIST': OTA_FILES_ALLOWLIST,
        'OTA_BACKUP_ENABLED': OTA_BACKUP_ENABLED,
    }

def get_display_settings():
    """Return a dict of display-related settings."""
    return {
        'ENABLE_OLED': ENABLE_OLED,
        'OLED_UPDATE_INTERVAL_S': OLED_UPDATE_INTERVAL_S,
        'OLED_SCROLL_ENABLED': OLED_SCROLL_ENABLED,
        'DISPLAY_NET_BARS': DISPLAY_NET_BARS,
        'OLED_HEADER_FLIP_S': OLED_HEADER_FLIP_S,
    }

# LoRa chunked transfer parameters (remote -> base)
LORA_CHUNK_RAW_BYTES = 150        # raw bytes per chunk before base64 & JSON overhead (tune so final msg <= 250)
LORA_CHUNK_MAX_RETRIES = 3       # attempts per chunk before deferring
LORA_CHUNK_ACK_WAIT_MS = 1500    # ms to wait for per-chunk ACK before retry
# LoRa payload safety: keep below SX126x limits and leave headroom for driver overhead.
# Reasonable default chosen to avoid packet-too-long (-4) errors in the field.
LORA_MAX_PAYLOAD = 255

# NEW: control retries for single-frame sends before re-init (helps transient -1 cases)
LORA_SINGLE_FRAME_RETRIES = 2

# NEW: explicit lists for handling chunk send errors
LORA_CHUNK_SHRINK_CODES = [-4]            # codes that indicate "packet too long" and should trigger chunk size shrink
LORA_CHUNK_TRANSIENT_CODES = [86, 87, 89] # codes considered transient — retry the chunk rather than shrink