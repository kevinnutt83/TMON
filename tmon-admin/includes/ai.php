
<?php
// Archive, review, and generate instructions for received AI data from unit-connector
add_action('tmon_ai_send_to_admin', function($payload) {
    // Archive data for review
    $archive = get_option('tmon_admin_ai_archive', []);
    $archive[] = [
        'timestamp' => current_time('mysql'),
        'payload' => $payload,
    ];
    update_option('tmon_admin_ai_archive', $archive);

    // Review and generate instructions (simple example)
    $instructions = [];
    if ($payload['category'] === 'agriculture' && $payload['subcat'] === 'weather_adaptation') {
        $temps = array_column($payload['data'], 'value');
        $avg = $temps ? array_sum($temps)/count($temps) : null;
        if ($avg && $avg > 28) {
            $instructions[] = 'Increase irrigation or cooling.';
        } elseif ($avg && $avg < 10) {
            $instructions[] = 'Prepare for frost.';
        } else {
            $instructions[] = 'Maintain current settings.';
        }
    }
    // ...add more logic for other categories/subcategories...

    // Send instructions back to unit-connector AI
    do_action('tmon_admin_ai_send_instructions', [
        'device_id' => $payload['device_id'],
        'instructions' => $instructions,
    ]);
});

// Example: unit-connector AI listens for instructions
add_action('tmon_admin_ai_send_instructions', function($data) {
    if (class_exists('TMON_AI_Advanced')) {
        TMON_AI_Advanced::receive_instructions($data['instructions']);
    }
});

/**
 * TMON Admin AI System Management
 * Hooks into TMON AI for admin-level error and health monitoring.
 */
if (file_exists(dirname(__DIR__).'/unit-connector/includes/ai.php')) {
    require_once dirname(__DIR__).'/unit-connector/includes/ai.php';
}
add_action('tmon_admin_error', function($msg, $context = null) {
    if (class_exists('TMON_AI')) {
        TMON_AI::observe_error($msg, $context);
    }
});
