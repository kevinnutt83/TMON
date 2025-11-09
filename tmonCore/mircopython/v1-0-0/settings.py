# Firmware Version: v2.00j
UNIT_ID = "None"
UNIT_Name = "Unnamed Unit"
NODE_TYPE = 'base'
#NODE_TYPE = 'remote'  # 'base' or 'remote'

FIRMWARE_VERSION = "v2.00j"

 # WordPress API integration
WORDPRESS_API_URL = ""  # Set to your WordPress site URL
WORDPRESS_USERNAME = "agadmin"  # Set to your WordPress username
WORDPRESS_PASSWORD = "Pepper-1"  # Set to your WordPress password


# --- Provisioning & Identity ---
# MACHINE_ID is detected from chipset on first boot (populated by firmware); persisted to disk and echoed here
MACHINE_ID = None                 # Populated by firmware from chipset UID on first boot
UNIT_PROVISIONED = False  # Set to True after initial setup is complete
TMON_ADMIN_API_URL = "https://tmonsystems.com"  # TMON Admin Hub API for first-boot check-in (optional)
PROVISION_CHECK_INTERVAL_S = 30   # Retry interval for hub check-in
PROVISION_MAX_RETRIES = 60        # Max retries before longer backoff
WIFI_ALWAYS_ON_WHEN_UNPROVISIONED = True  # keep WiFi enabled until provisioned
WIFI_DISABLE_AFTER_PROVISION = True  # for remote nodes

# wifi settings
WIFI_SSID = "house of nonsense"
WIFI_PASS = "bluebread219"

# --- Logging & Rotation Controls ---
LOG_DIR = '/logs'
LOG_FILE = LOG_DIR + '/lora.log'
ERROR_LOG_FILE = LOG_DIR + '/lora_errors.log'
FIELD_DATA_LOG = LOG_DIR + '/field_data.log'
DATA_HISTORY_LOG = LOG_DIR + '/data_history.log'
FIELD_DATA_DELIVERED_LOG = LOG_DIR + '/field_data.delivered.log'  # archive of delivered entries
FIELD_DATA_MAX_BYTES = 256 * 1024  # rotate/trim when exceeding this size
FIELD_DATA_MAX_BATCH = 50          # max records per POST batch
FIELD_DATA_SEND_INTERVAL = 30      # seconds, can be changed as needed
FIELD_DATA_BACKOFF_S = 10          # retry backoff on HTTP failures
FIELD_DATA_GZIP = True             # allow gzip payload when supported

# --- LoRa sync & recovery ---
nextLoraSync = 300   # see README; base cadence / remote next absolute epoch
LORA_SYNC_WINDOW = 2 # seconds of minimum spacing between remote sync slots
LORA_SLOT_SPACING_S = LORA_SYNC_WINDOW  # alias for clarity
LORA_INIT_RETRY_BACKOFF_S = 1      # small delay between init retries
LORA_HARD_REBOOT_ERR_CODES = [-2]  # error codes that trigger hard reboot (e.g., ERR_CHIP_NOT_FOUND)
LORA_ERR_PERSIST_REBOOTS = 2       # if persists this many times across reboots, stop rebooting and log
ERROR_STATE_FILE = LOG_DIR + '/last_error.state'  # persist last error and reboot counters
LORA_REMOTE_INFO_LOG = LOG_DIR + '/remote_info.log'  # base records remote identities here

# --- Last error telemetry (include in sdata payloads) ---
LAST_ERROR_CODE = 0
LAST_ERROR_NAME = ''
LAST_ERROR_TS = None  # epoch seconds
TELEMETRY_INCLUDE_LAST_ERROR = True  # sdata.py should include last error fields when True

# --- GPS / Sensors / Feature flags ---
# Enable GPS location features. If False, GPS fields are ignored.
GPS_ENABLED = True
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
COMPARE_TEMP = True
SAMPLE_BAR = True
COMPARE_BAR = True
SAMPLE_HUMID = True
COMPARE_HUMID = True

DEBUG = True
DEBUG_TEMP = True
DEBUG_BAR = True
DEBUG_HUMID = True
DEBUG_LORA = True

ENABLE_RELAY1 = True
ENABLE_RELAY2 = True 
ENABLE_RELAY3 = False
ENABLE_RELAY4 = False
ENABLE_RELAY5 = False
ENABLE_RELAY6 = False
ENABLE_RELAY7 = False
ENABLE_RELAY8 = False

ENABLE_sensorBME280 = True
i2cAddr_BME280 = 0x76
light_i2c_address = 0x53
motion_i2c_address = 0x68
voc_i2c_address = 0x59
lux_i2c_address = 0x29

# System voltage measurement settings
SYS_VOLTAGE_PIN = 3  # ADC pin used for voltage divider (adjust as needed)
SYS_VOLTAGE_MAX = 5.0  # Maximum measurable voltage (adjust for your divider)

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

FREQ = 868.0
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

# --- LoRa network admission (simple shared secret; not cryptographic) ---
# Remotes must present matching name/password to the base. Base will ignore packets that fail auth.
LORA_NETWORK_NAME = "tmon"
LORA_NETWORK_PASSWORD = "12345"


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
OTA_BACKUP_ENABLED = True                 # keep backup of current firmware/settings
OTA_BACKUP_DIR = '/ota/backup'
OTA_MAX_RETRIES = 3
ALLOW_REMOTE_COMMANDS = True              # accept OTA commands/relay toggles
RELAY_SAFETY_MAX_RUNTIME_MIN = 1440       # safety cap for relay runtime

# --- Connectivity ---
ENABLE_WIFI = True
ENABLE_LORA = True
ENABLE_OLED = True
HTTP_TIMEOUT_S = 20
TLS_VERIFY = True

# NOTE:
# - sdata.py should include LAST_ERROR_* when TELEMETRY_INCLUDE_LAST_ERROR is True.
# - Sender must append delivered entries to FIELD_DATA_DELIVERED_LOG and truncate FIELD_DATA_LOG post-send.
# - Base must log remote identities to LORA_REMOTE_INFO_LOG on join/sync.