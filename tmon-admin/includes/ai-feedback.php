<?php
// TMON Admin AI Feedback & User Input
// Usage: do_action('tmon_admin_ai_feedback', $feedback);
add_action('tmon_admin_ai_feedback', function($feedback) {
    $fb = get_option('tmon_admin_ai_feedback', []);
    $feedback['timestamp'] = current_time('mysql');
    $fb[] = $feedback;
    update_option('tmon_admin_ai_feedback', $fb);
});

// Helper: Get AI feedback
function tmon_admin_get_ai_feedback() {
    $fb = get_option('tmon_admin_ai_feedback', []);
    return array_reverse($fb);
}
