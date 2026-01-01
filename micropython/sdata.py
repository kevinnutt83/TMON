# Firmware Version: 2.0.0h
# Performance/health metrics for reporting
loop_runtime = 0
script_runtime = 0
sys_voltage = 0
free_mem = 0
cpu_temp = 0
error_count = 0
last_error = ''
# Device Information and Data
loop_runtime = 0
script_runtime = 0
sys_voltage = 0

# Lora Information
lora_SigStr = 0
# Added SNR for better signal info
lora_snr = 0

# Engine controller metrics
engine1_speed_rpm = 0
engine2_speed_rpm = 0
engine1_batt_v = 0
engine2_batt_v = 0
engine_last_poll_ts = 0

# Remote Node Data Variables
cur_temp_c = 0
cur_temp_f = 0
cur_bar_pres = 0
cur_humid = 0
# NEW: indicate sampling in progress so OLED can render sampling-only content
sampling_active = False

# Base Station Data Variables
lowest_temp_f = 0
highest_temp_f = 0
lowest_bar = 0
highest_bar = 0
lowest_humid = 0
highest_humid = 0

# Relay States
relay1_on = False
relay2_on = False
relay3_on = False
relay4_on = False
relay5_on = False
relay6_on = False
relay7_on = False
relay8_on = False

# Relay runtime counters (seconds)
relay1_runtime_s = 0
relay2_runtime_s = 0
relay3_runtime_s = 0
relay4_runtime_s = 0
relay5_runtime_s = 0
relay6_runtime_s = 0
relay7_runtime_s = 0
relay8_runtime_s = 0

# Frost and Heat Monitoring Data Variables
frostwatch_active = False
heatwatch_active = False
frost = False
heat = False
frost_act = False
heat_act = False

# WiFi/Network State
WIFI_CONNECTED = False
WAN_CONNECTED = False
# Added RSSI for WiFi strength display
wifi_rssi = 0

# Messages
# Store last short message for UI overlay
last_message = ''

# GPS state (populated if settings.GPS_ENABLED)
gps_lat = None
gps_lng = None
gps_alt_m = None
gps_accuracy_m = None
gps_last_fix_ts = None