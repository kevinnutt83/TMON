<?php
// REST API for hierarchy CRUD and map data
add_action('rest_api_init', function() {
    register_rest_route('tmon/v1', '/hierarchy', [
        'methods' => 'GET',
        'callback' => 'tmon_uc_api_get_hierarchy',
        'permission_callback' => function() { return current_user_can('manage_options'); }
    ]);
    register_rest_route('tmon/v1', '/hierarchy', [
        'methods' => 'POST',
        'callback' => 'tmon_uc_api_save_hierarchy',
        'permission_callback' => function() { return current_user_can('manage_options'); }
    ]);
    register_rest_route('tmon/v1', '/hierarchy/(?P<level>company|site|zone|cluster|unit)/(?P<id>\d+)?', [
        'methods' => ['GET', 'POST', 'PUT', 'DELETE'],
        'callback' => 'tmon_uc_api_hierarchy_crud',
        'permission_callback' => function() { return current_user_can('edit_tmon_hierarchy'); }
    ]);
    // ...add endpoints for notes, map overlays, etc.
});

function tmon_uc_api_get_hierarchy($request) {
    global $wpdb;
    $companies = $wpdb->get_results("SELECT * FROM {$wpdb->prefix}tmon_company", ARRAY_A);
    foreach ($companies as &$company) {
        $company['sites'] = $wpdb->get_results($wpdb->prepare("SELECT * FROM {$wpdb->prefix}tmon_site WHERE company_id=%d", $company['id']), ARRAY_A);
        foreach ($company['sites'] as &$site) {
            $site['zones'] = $wpdb->get_results($wpdb->prepare("SELECT * FROM {$wpdb->prefix}tmon_zone WHERE site_id=%d", $site['id']), ARRAY_A);
            foreach ($site['zones'] as &$zone) {
                $zone['clusters'] = $wpdb->get_results($wpdb->prepare("SELECT * FROM {$wpdb->prefix}tmon_cluster WHERE zone_id=%d", $zone['id']), ARRAY_A);
                foreach ($zone['clusters'] as &$cluster) {
                    $cluster['units'] = $wpdb->get_results($wpdb->prepare("SELECT * FROM {$wpdb->prefix}tmon_unit WHERE cluster_id=%d", $cluster['id']), ARRAY_A);
                }
            }
        }
    }
    return ['success'=>true, 'data'=>$companies];
}

function tmon_uc_api_save_hierarchy($request) {
    global $wpdb;
    $params = $request->get_json_params();
    $level = $params['level'] ?? null;
    $data = $params['data'] ?? null;
    if (!$level || !$data) return ['success'=>false, 'error'=>'Missing data'];
    $table_map = [
        'company' => $wpdb->prefix.'tmon_company',
        'site' => $wpdb->prefix.'tmon_site',
        'zone' => $wpdb->prefix.'tmon_zone',
        'cluster' => $wpdb->prefix.'tmon_cluster',
        'unit' => $wpdb->prefix.'tmon_unit',
    ];
    if (!isset($table_map[$level])) return ['success'=>false, 'error'=>'Invalid level'];
    $table = $table_map[$level];
    foreach ($data as $row) {
        if (isset($row['id'])) {
            $wpdb->update($table, $row, ['id'=>$row['id']]);
        } else {
            $wpdb->insert($table, $row);
        }
    }
    return ['success'=>true];
}

// CSV export for hierarchy
add_action('admin_post_tmon_export_hierarchy', function() {
    global $wpdb;
    $level = $_GET['level'] ?? 'unit';
    $table = $wpdb->prefix.'tmon_'.$level;
    $rows = $wpdb->get_results("SELECT * FROM $table", ARRAY_A);
    header('Content-Type: text/csv');
    header('Content-Disposition: attachment; filename="tmon_".$level.".csv"');
    $out = fopen('php://output', 'w');
    if (!empty($rows)) {
        fputcsv($out, array_keys($rows[0]));
        foreach ($rows as $row) fputcsv($out, $row);
    }
    fclose($out);
    exit;
});

function tmon_uc_api_hierarchy_crud($request) {
    global $wpdb;
    $level = $request['level'];
    $id = $request['id'] ?? null;
    $method = $request->get_method();
    $table_map = [
        'company' => $wpdb->prefix.'tmon_company',
        'site' => $wpdb->prefix.'tmon_site',
        'zone' => $wpdb->prefix.'tmon_zone',
        'cluster' => $wpdb->prefix.'tmon_cluster',
        'unit' => $wpdb->prefix.'tmon_unit',
    ];
    if (!isset($table_map[$level])) return ['success'=>false, 'error'=>'Invalid level'];
    $table = $table_map[$level];
    if ($method === 'GET') {
        if ($id) {
            $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM $table WHERE id=%d", $id), ARRAY_A);
            return ['success'=>true, 'data'=>$row];
        } else {
            $rows = $wpdb->get_results("SELECT * FROM $table", ARRAY_A);
            return ['success'=>true, 'data'=>$rows];
        }
    } elseif ($method === 'POST' || $method === 'PUT') {
        $data = $request->get_json_params();
        if ($id) {
            $wpdb->update($table, $data, ['id'=>$id]);
            $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM $table WHERE id=%d", $id), ARRAY_A);
            return ['success'=>true, 'data'=>$row];
        } else {
            $wpdb->insert($table, $data);
            $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM $table WHERE id=%d", $wpdb->insert_id), ARRAY_A);
            return ['success'=>true, 'data'=>$row];
        }
    } elseif ($method === 'DELETE' && $id) {
        $wpdb->delete($table, ['id'=>$id]);
        return ['success'=>true];
    }
    return ['success'=>false, 'error'=>'Invalid request'];
}
