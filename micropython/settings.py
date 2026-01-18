# Core settings defaults (override per-device)
LOG_DIR = '/logs'

# Identity
UNIT_ID = 'UNPROVISIONED'
UNIT_Name = 'TMON'
NODE_TYPE = 'base'  # 'base' | 'wifi' | 'remote'
PLAN = ''

# Firmware
FIRMWARE_VERSION = 'v2.06.1'
try:
    with open(LOG_DIR + '/version.txt', 'r') as f:
        _v = (f.read() or '').strip()
        if _v:
            FIRMWARE_VERSION = _v
except Exception:
    pass

# Feature flags
DEBUG = True
ENABLE_OLED = False
OLED_DEBUG_BANNER = False

ENABLE_WIFI = True
WIFI_SSID = ''
WIFI_PASS = ''
WIFI_CONN_RETRIES = 20
WIFI_BACKOFF_S = 1
WIFI_SIGNAL_SAMPLE_INTERVAL_S = 10
WIFI_ALWAYS_ON_WHEN_UNPROVISIONED = True
ALLOW_REMOTE_WIFI_CREDENTIALS = False

ENABLE_LORA = True
LORA_MAX_PAYLOAD = 240
OLED_LORA_STALE_S = 120
LORA_FIELD_LOG_MAX_BYTES = 4096

# WP / Unit Connector
WORDPRESS_API_URL = ''
WORDPRESS_APP_USER = ''
WORDPRESS_APP_PASS = ''
HTTP_TIMEOUT_S = 12

# Logs
LOG_FILE = LOG_DIR + '/tmon.log'
ERROR_LOG_FILE = LOG_DIR + '/tmon_errors.log'
FIELD_DATA_LOG = LOG_DIR + '/field_data.log'
FIELD_DATA_DELIVERED_LOG = LOG_DIR + '/field_data_delivered.log'
DATA_HISTORY_LOG = LOG_DIR + '/data_history.log'
LORA_LOG_FILE = LOG_DIR + '/lora.log'

FIELD_DATA_SEND_INTERVAL = 300
FIELD_DATA_MAX_BATCH = 50
FIELD_DATA_REWRITE_MAX_LINES = 2000

# Staged settings paths
REMOTE_SETTINGS_STAGED_FILE = LOG_DIR + '/remote_settings.staged.json'
REMOTE_SETTINGS_APPLIED_FILE = LOG_DIR + '/remote_settings.applied.json'

# Provisioning
UNIT_PROVISIONED = False
PROVISION_CHECK_INTERVAL_S = 60
PROVISIONED_FLAG_FILE = LOG_DIR + '/provisioned.flag'
PROVISION_REBOOT_GUARD_FILE = LOG_DIR + '/provision_reboot.flag'
TMON_ADMIN_API_URL = ''
TMON_ADMIN_CONFIRM_TOKEN = ''

# OLED layout defaults
OLED_HEADER_HEIGHT = 16
OLED_FOOTER_HEIGHT = 12
OLED_HEADER_FLIP_S = 4
OLED_UPDATE_INTERVAL_S = 10
OLED_PAGE_ROTATE_INTERVAL_S = 30
OLED_SCROLL_ENABLED = False
DISPLAY_NET_BARS = True

# ADC defaults (if used)
VBAT_ADC_PIN = 26
ADC_VREF = 3.3
VBAT_DIVIDER = 2.0

# Pins (set per board)
STATUS_LED_PIN = 25
I2C_B_SCL_PIN = 9
I2C_B_SDA_PIN = 8

# LoRa radio pins/bus (set per board)
SPI_BUS = 1
CLK_PIN = 10
MOSI_PIN = 11
MISO_PIN = 12
CS_PIN = 13
IRQ_PIN = 14
RST_PIN = 15
BUSY_PIN = 16

# LoRa radio config
FREQ = 915.0
BW = 125.0
SF = 9
CR = 5
SYNC_WORD = 0x12
POWER = 14
CURRENT_LIMIT = 140.0
PREAMBLE_LEN = 8
CRC_ON = True
TCXO_VOLTAGE = 1.7
USE_LDO = False

# Sensors
SAMPLE_TEMP = True
ENABLE_sensorBME280 = False

# Frost/Heat watch
ENABLE_FROSTWATCH = False
ENABLE_HEATWATCH = False

# Relay safety defaults
RELAY_SAFETY_MAX_RUNTIME_MIN = 1440
RELAY_RUNTIME_LIMITS = {}

# RS485 engine
ENGINE_FORCE_DISABLED = True
USE_RS485 = False
ENGINE_ENABLED = False
ENGINE_DEV_ADDR = 1
ENGINE_DEV_COUNT = 1
ENGINE_POLL_INTERVAL_S = 5
COMM_BAUD = 9600
COMM_PARITY = None
COMM_STOP_BITS = 1
CH1_TX_PIN = 4
CH1_RX_PIN = 5
CH2_TX_PIN = 6
CH2_RX_PIN = 7
ENGINE_PUMP1_COIL = 0
ENGINE_PUMP2_COIL = 1

# GPS
GPS_ENABLED = False
GPS_SOURCE = 'static'
GPS_LAT = 0.0
GPS_LNG = 0.0
GPS_ACCEPT_FROM_BASE = True
GPS_OVERRIDE_ALLOWED = True
GPS_BROADCAST_TO_REMOTES = False

# Device control
DEVICE_SUSPENDED = False

# GC maintenance
GC_INTERVAL_S = 60

# Internet test
INTERNET_TEST_URL = 'https://example.com'

# --- BME280 (required by /lib/BME280.py) ---
# Some BME280 drivers in this repo expect these exact names on settings.*
i2cAddr_BME280 = 0x76  # common BME280 address (alternate is 0x77)
i2cFreq_BME280 = 100000

# If your board uses different pins/bus, override these in your device config.
# Keep these present so imports don't fail even when ENABLE_sensorBME280=False.
try:
    I2C_B_SCL_PIN
except Exception:
    I2C_B_SCL_PIN = 9
try:
    I2C_B_SDA_PIN
except Exception:
    I2C_B_SDA_PIN = 8