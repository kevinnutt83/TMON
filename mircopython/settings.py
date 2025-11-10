# Firmware Version: v2.00j
UNIT_ID = "None"              # 6-digit assigned by Admin after first check-in (persisted locally)
UNIT_Name = "Unnamed Unit"    # Human-friendly name (provisioned)
NODE_TYPE = 'base'             # 'base' or 'remote'; base can host LoRa network & WiFi; remote uses LoRa primarily
#NODE_TYPE = 'remote'          # Uncomment for remote role during flashing

FIRMWARE_VERSION = "v2.00j"    # Bumped automatically by OTA; compared during update check

 # WordPress API integration
WORDPRESS_API_URL = "https://movealong.us"   # Customer Unit Connector site for provisioned devices
WORDPRESS_USERNAME = "agadmin"              # (Optional) Basic auth / future removal for token-based access
WORDPRESS_PASSWORD = "Pepper-1"             # (Optional) Replace with secure secret storage in production


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

# wifi settings
WIFI_SSID = "house of nonsense"          # Provisioned or manually set SSID
WIFI_PASS = "bluebread219"               # Provisioned or manually set password
WIFI_CONN_RETRIES = 5                     # Immediate retries before longer backoff
WIFI_BACKOFF_S = 15                       # Base backoff between retry bursts
WIFI_SIGNAL_SAMPLE_INTERVAL_S = 30        # Interval to refresh RSSI for OLED

# --- Logging & Rotation Controls ---
LOG_DIR = '/logs'
LOG_FILE = LOG_DIR + '/lora.log'
ERROR_LOG_FILE = LOG_DIR + '/lora_errors.log'
FIELD_DATA_LOG = LOG_DIR + '/field_data.log'
DATA_HISTORY_LOG = LOG_DIR + '/data_history.log'
FIELD_DATA_DELIVERED_LOG = LOG_DIR + '/field_data.delivered.log'  # archive of delivered entries
FIELD_DATA_MAX_BYTES = 256 * 1024  # rotate/trim when exceeding this size
FIELD_DATA_MAX_BATCH = 50          # max records per POST batch
FIELD_DATA_SEND_INTERVAL = 30      # seconds, adjustable remotely
FIELD_DATA_BACKOFF_S = 10          # retry backoff on HTTP failures
FIELD_DATA_GZIP = True             # allow gzip payload when supported

# --- LoRa sync & recovery ---
nextLoraSync = 300                      # Remote next absolute sync epoch (assigned by base)
LORA_SYNC_WINDOW = 2 # seconds of minimum spacing between remote sync slots
LORA_SLOT_SPACING_S = LORA_SYNC_WINDOW  # alias for clarity
LORA_INIT_RETRY_BACKOFF_S = 1      # small delay between init retries
LORA_HARD_REBOOT_ERR_CODES = [-2]  # error codes that trigger hard reboot (e.g., ERR_CHIP_NOT_FOUND)
LORA_ERR_PERSIST_REBOOTS = 2       # if persists this many times across reboots, stop rebooting and log
ERROR_STATE_FILE = LOG_DIR + '/last_error.state'  # persist last error and reboot counters
LORA_REMOTE_INFO_LOG = LOG_DIR + '/remote_info.log'  # base records remote identities here
LORA_HMAC_ENABLED = False            # When True, firmware includes a signature with LoRa frames
LORA_HMAC_SECRET = ''                # Per-device secret used to sign LoRa frames (provisioned)
LORA_HMAC_COUNTER_FILE = LOG_DIR + '/lora_ctr.json'  # Persist local counter (remote)
LORA_REMOTE_COUNTERS_FILE = LOG_DIR + '/remote_ctr.json'  # Base: last seen counters per remote
LORA_HMAC_REJECT_UNSIGNED = True     # When enabled + HMAC active, reject frames lacking valid signature
LORA_HMAC_REPLAY_PROTECT = True      # Enforce strictly increasing counter (ctr) to prevent replay
LORA_ENCRYPT_ENABLED = False         # Optional payload encryption (ChaCha20 stream cipher)
LORA_ENCRYPT_SECRET = ''             # 32-byte key (hex or text) for encryption; provision per device

# --- Last error telemetry (include in sdata payloads) ---
LAST_ERROR_CODE = 0
LAST_ERROR_NAME = ''
LAST_ERROR_TS = None                    # epoch seconds
TELEMETRY_INCLUDE_LAST_ERROR = True     # Include last error telemetry in field data
ERROR_COUNT_RESET_INTERVAL_S = 3600     # Period to reset soft error counters

# --- GPS / Sensors / Feature flags ---
# Enable GPS location features. If False, GPS fields are ignored.
GPS_ENABLED = True                      # Global GPS enable
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

SAMPLE_TEMP = True
COMPARE_TEMP = True                     # Compare against thresholds for frost/heat watch triggers
SAMPLE_BAR = True
COMPARE_BAR = True
SAMPLE_HUMID = True
COMPARE_HUMID = True
SAMPLE_LIGHT = False                    # Future light sensor enable
SAMPLE_VOC = False                      # VOC sensor enable
SAMPLE_LUX = False                      # Lux sensor enable

DEBUG = True
DEBUG_TEMP = True
DEBUG_BAR = True
DEBUG_HUMID = True
DEBUG_LORA = True
DEBUG_WIFI = True
DEBUG_OTA = True
DEBUG_PROVISION = True
DEBUG_SAMPLING = True
DEBUG_DISPLAY = True
DEBUG_REMOTE = True

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

ENABLE_sensorBME280 = True              # Primary environmental sensor module
i2cAddr_BME280 = 0x76
light_i2c_address = 0x53
motion_i2c_address = 0x68
voc_i2c_address = 0x59
lux_i2c_address = 0x29

# System voltage measurement settings
SYS_VOLTAGE_PIN = 3                        # ADC pin used for voltage divider (adjust as needed)
SYS_VOLTAGE_MAX = 5.0                      # Maximum measurable voltage (adjust for your divider)
SYS_VOLTAGE_SAMPLE_INTERVAL_S = 60         # Voltage telemetry refresh cadence

LED_PIN = 21

RELAY_PIN1 = 17
RELAY_PIN2 = 18

I2C_A_SCL_PIN = 33
I2C_A_SDA_PIN = 34
I2C_B_SCL_PIN = 11
I2C_B_SDA_PIN = 12

SPI_BUS = 1
CLK_PIN = 35
MOSI_PIN = 36
MISO_PIN = 37
CS_PIN = 14
IRQ_PIN = 4
RST_PIN = 40
BUSY_PIN = 13

FREQ = 868.0                               # Regional frequency (EU example); change per deployment
BW = 125.0
SF = 12
CR = 5
SYNC_WORD = 0xF4
POWER = 20
CURRENT_LIMIT = 140.0
PREAMBLE_LEN = 12
CRC_ON = True
TCXO_VOLTAGE = 1.8  # Confirmed for Waveshare SX1262
USE_LDO = True


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

# --- OTA & Command/Relay Safety ---
OTA_ENABLED = True
OTA_BACKUP_ENABLED = True                 # Keep backup of current firmware/settings
OTA_BACKUP_DIR = '/ota/backup'
OTA_MAX_RETRIES = 3
ALLOW_REMOTE_COMMANDS = True              # Accept OTA commands/relay toggles
RELAY_SAFETY_MAX_RUNTIME_MIN = 1440       # Safety cap for relay runtime
OTA_VERSION_ENDPOINT = 'https://raw.githubusercontent.com/kevinnutt83/TMON/main/mircopython/version.txt'
OTA_FIRMWARE_BASE_URL = 'https://raw.githubusercontent.com/kevinnutt83/TMON/main/mircopython/'
OTA_CHECK_INTERVAL_S = 1800               # 30 min default update check cadence
OTA_MANIFEST_URL = OTA_FIRMWARE_BASE_URL + 'manifest.json'  # Manifest lists files + hashes
OTA_HASH_VERIFY = True                    # Verify sha256 of downloaded files against manifest
OTA_APPLY_INTERVAL_S = 600                # Check/apply pending update every 10 minutes
OTA_RESTORE_ON_FAIL = True                # Restore backups if any file verification/apply fails
OTA_MAX_FILE_BYTES = 256*1024             # Safety cap per file download size
OTA_FILES_ALLOWLIST = [                   # Limit which files can be updated via OTA
	'main.py','lora.py','utils.py','sampling.py','settings.py','relay.py','oled.py','ota.py','wprest.py'
]
OTA_MANIFEST_SIG_URL = OTA_MANIFEST_URL + '.sig'  # Optional detached HMAC signature (hex)
OTA_MANIFEST_HMAC_SECRET = ''             # If set, verify manifest with HMAC(secret, manifest_bytes)

# --- Connectivity ---
ENABLE_WIFI = True
ENABLE_LORA = True
ENABLE_OLED = True
HTTP_TIMEOUT_S = 20
TLS_VERIFY = True
OLED_UPDATE_INTERVAL_S = 10               # Refresh interval for status page
OLED_SCROLL_ENABLED = False               # Future multi-page support
OLED_PAGE_ROTATE_INTERVAL_S = 30          # Interval for automatic page rotation
DEVICE_SUSPENDED = False                  # Suspension flag set by Admin/UC commands; halts tasks but allows check-ins
DEVICE_SUSPENDED_FILE = '/logs/suspended.flag'
LORA_NETWORK_NAME = 'tmon'                # Secure network name (provisioned for base & remotes)
LORA_NETWORK_PASSWORD = '12345'           # Simple password handshake (strengthen later)
REMOTE_CHECKIN_INTERVAL_S = 300           # Default remote -> base sync period
REMOTE_CHECKIN_JITTER_S = 5               # Jitter to avoid collisions
BASE_REMOTE_TABLE_FILE = '/logs/remotes.table.json'  # Base-maintained remote registry

# --- Field Data HMAC (optional) ---
FIELD_DATA_HMAC_ENABLED = False           # When True, sign each field-data payload
FIELD_DATA_HMAC_SECRET = ''               # Secret for field data HMAC (provisioned)
FIELD_DATA_HMAC_INCLUDE_KEYS = ['unit_id','firmware_version','node_type']  # Keys guaranteed present (order stable)
FIELD_DATA_HMAC_TRUNCATE = 32             # Hex chars of hash to include as signature

# NOTE:
# - sdata.py should include LAST_ERROR_* when TELEMETRY_INCLUDE_LAST_ERROR is True.
# - Sender must append delivered entries to FIELD_DATA_DELIVERED_LOG and truncate FIELD_DATA_LOG post-send.
# - Base must log remote identities to LORA_REMOTE_INFO_LOG on join/sync.