<?php
/**
 * Advanced AI Categories and Subcategories
 */
const TMON_AI_CATEGORIES = [
    'industrial' => [
        'energy_management',
        'predictive_maintenance',
        'environmental_monitoring',
        'asset_tracking',
        'safety_compliance',
        'process_optimization',
        'equipment_utilization',
        'quality_control',
        'supply_chain',
        'facility_security',
    ],
    'agriculture' => [
        'irrigation_control',
        'soil_health',
        'crop_monitoring',
        'livestock_management',
        'weather_adaptation',
        'pest_disease_detection',
        'yield_prediction',
        'resource_optimization',
        'greenhouse_management',
        'harvest_timing',
    ]
];

class TMON_AI_Advanced extends TMON_AI {
    // Gather historical and forecast data for all subcategories
    public static function gather_data($category, $subcat, $device_id = null) {
        global $wpdb;
        $table = $wpdb->prefix.'tmon_device_data';
        $where = $device_id ? $wpdb->prepare('WHERE device_id=%s', $device_id) : '';
        $rows = $wpdb->get_results("SELECT * FROM $table $where ORDER BY created_at DESC LIMIT 1000", ARRAY_A);
        // Filter and tabulate by subcategory
        $tabulated = [];
        foreach ($rows as $row) {
            $data = maybe_unserialize($row['data']);
            if (isset($data[$subcat])) {
                $tabulated[] = [
                    'timestamp' => $row['created_at'],
                    'value' => $data[$subcat],
                ];
            }
        }
        return $tabulated;
    }

    // Analyze temperature and forecast, generate suggestions
    public static function analyze_temperature($device_id) {
        $history = self::gather_data('agriculture', 'weather_adaptation', $device_id);
        $temps = array_column($history, 'value');
        $avg = $temps ? array_sum($temps)/count($temps) : null;
        $forecast = self::get_forecast($device_id);
        $suggestion = null;
        if ($avg && $forecast) {
            if ($forecast['high'] > $avg + 5) {
                $suggestion = 'Increase cooling or irrigation. Forecasted high exceeds average.';
            } elseif ($forecast['low'] < $avg - 5) {
                $suggestion = 'Prepare for cold. Forecasted low below average.';
            } else {
                $suggestion = 'Conditions normal. Maintain current settings.';
            }
        }
        return [
            'avg_temp' => $avg,
            'forecast' => $forecast,
            'suggestion' => $suggestion,
        ];
    }

    // Dummy forecast fetcher (replace with real API integration)
    public static function get_forecast($device_id) {
        // In production, fetch from weather API using device location
        return [ 'high' => 30, 'low' => 15 ];
    }

    // Tabulate and send data to tmon-admin AI for archiving/review
    public static function send_to_admin($category, $subcat, $device_id = null) {
        $data = self::gather_data($category, $subcat, $device_id);
        $payload = [
            'category' => $category,
            'subcat' => $subcat,
            'device_id' => $device_id,
            'data' => $data,
        ];
        // Send via REST or WP hook
        do_action('tmon_ai_send_to_admin', $payload);
    }

    // Receive instructions from tmon-admin AI and relay to device AI
    public static function receive_instructions($instructions) {
        // Store or relay instructions to device AI (e.g., via DB, MQTT, etc.)
        // Example: update device settings or thresholds
        // ...
    }
}
/**
 * TMON AI System Management
 * Provides AI-driven health monitoring, error response, and suggestions for the entire TMON platform.
 */
class TMON_AI {
    public static $error_count = 0;
    public static $last_error = null;
    public static $recovery_actions = [];

    public static function observe_error($error_msg, $context = null) {
        self::$error_count++;
        self::$last_error = [$error_msg, $context];
        if (self::$error_count > 5) {
            self::log('AI: Too many errors, attempting system recovery', $context);
            self::recover_system();
        }
    }

    public static function recover_system() {
        // Example: restart services, clear caches, notify admin
        self::log('AI: Performing system recovery', 'recovery');
        // Add actual recovery logic here
    }

    public static function suggest_action($context) {
        if (stripos($context, 'wifi') !== false) return 'Check WiFi credentials or signal.';
        if (stripos($context, 'ota') !== false) return 'Retry OTA or check file integrity.';
        return 'Check logs and restart the service if needed.';
    }

    public static function log($msg, $context = null) {
        error_log('[TMON_AI] ' . $msg . ($context ? " | Context: $context" : ''));
        // Optionally, store in DB or notify admin
    }
}
// Hook into error logging and system events
add_action('tmon_uc_error', function($msg, $context = null) {
    TMON_AI::observe_error($msg, $context);
});
add_action('tmon_admin_error', function($msg, $context = null) {
    TMON_AI::observe_error($msg, $context);
});
