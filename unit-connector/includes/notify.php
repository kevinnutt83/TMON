<?php
// Notification logic for device events, jobs, etc.
function tmon_uc_notify($user_id, $subject, $message) {
    $user = get_userdata($user_id);
    if ($user && $user->user_email) {
        wp_mail($user->user_email, $subject, $message);
    }
    // SMS/push support (Twilio/Pushover example)
    $phone = get_user_meta($user_id, 'tmon_phone', true);
    if ($phone) {
        // Use Twilio or similar API here
        // tmon_uc_send_sms($phone, $subject.': '.$message);
    }
    $pushover = get_user_meta($user_id, 'tmon_pushover_key', true);
    if ($pushover) {
        // Use Pushover API here
        // tmon_uc_send_push($pushover, $subject, $message);
    }
}
// Usage: tmon_uc_notify($user_id, 'Device Offline', 'Device X is offline.');
