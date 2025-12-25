<?php
// TMON Admin Data Export (CSV/JSON)
// Usage: echo tmon_admin_export_data('audit', 'csv');
function tmon_admin_export_data($type, $format = 'csv') {
    $data = [];
    switch ($type) {
        case 'audit':
            $data = get_option('tmon_admin_audit_logs', []);
            break;
        case 'notifications':
            $data = get_option('tmon_admin_notifications', []);
            break;
        case 'ota':
            $data = get_option('tmon_admin_ota_jobs', []);
            break;
        case 'files':
            $data = get_option('tmon_admin_files', []);
            break;
        case 'groups':
            $data = get_option('tmon_admin_groups', []);
            break;
        case 'custom_code':
            $data = get_option('tmon_admin_custom_code', []);
            break;
        default:
            return '';
    }
    if ($format === 'json') {
        return json_encode($data);
    }
    if (empty($data) || !is_array($data)) return '';
    $rows = [];
    foreach ($data as $row) {
        if (is_object($row)) $row = (array)$row;
        if (!is_array($row)) $row = ['value' => (string)$row];
        $rows[] = $row;
    }
    $headers = [];
    foreach ($rows as $r) { foreach (array_keys($r) as $k) $headers[$k] = true; }
    $headers = array_keys($headers);
    $out = fopen('php://temp', 'r+');
    fputcsv($out, $headers);
    foreach ($rows as $r) {
        $line = [];
        foreach ($headers as $h) $line[] = isset($r[$h]) ? (is_scalar($r[$h]) ? $r[$h] : json_encode($r[$h])) : '';
        fputcsv($out, $line);
    }
    rewind($out);
    $csv = stream_get_contents($out);
    fclose($out);
    return $csv;
}
