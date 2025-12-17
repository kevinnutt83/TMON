<?php
/**
 * PHPUnit integration tests for Unit Connector command staging pipeline.
 *
 * To run: vendor/bin/phpunit --filter UC_Commands_Test
 */

class UC_Commands_Test extends WP_UnitTestCase {
	// Ensure commands table exists
	public static function setUpBeforeClass(): void {
		parent::setUpBeforeClass();
		if ( function_exists( 'tmon_uc_ensure_commands_table' ) ) {
			tmon_uc_ensure_commands_table();
		}
	}

	public function test_staged_settings_and_command_flow() {
		global $wpdb;

		$unit = 'phpunit-test-unit-1';
		// 1) insert staged settings into UC option to simulate admin staging
		$store = get_option('tmon_uc_device_settings', []);
		$store[$unit] = ['unit_id'=>$unit, 'machine_id'=>'m-1234', 'settings'=>['TEST_FLAG'=>1], 'ts'=>current_time('mysql')];
		update_option('tmon_uc_device_settings', $store);

		// 2) Queue a device command via REST
		$req = new WP_REST_Request('POST', '/tmon/v1/device/command');
		$req->set_param('unit_id', $unit);
		$req->set_param('command', 'set_var');
		$req->set_param('params', ['key'=>'TEST_FLAG','value'=>0]);
		$res = rest_do_request($req);
		$this->assertEquals(200, $res->get_status());
		$body = rest_get_server()->response_to_data( $res, false );
		$this->assertArrayHasKey('id', $body);

		// 3) Retrieve staged-settings and ensure staged + commands are present
		$req2 = new WP_REST_Request('GET', '/tmon/v1/device/staged-settings');
		$req2->set_param('unit_id', $unit);
		$res2 = rest_do_request($req2);
		$this->assertEquals(200, $res2->get_status());
		$data = rest_get_server()->response_to_data($res2, false);
		$this->assertEquals('ok', $data['status']);
		$this->assertArrayHasKey('staged', $data);
		$this->assertArrayHasKey('commands', $data);

		// 4) Simulate device polling POST /device/commands (this should claim the queued command)
		$req3 = new WP_REST_Request('POST', '/tmon/v1/device/commands');
		$req3->set_param('unit_id', $unit);
		$res3 = rest_do_request($req3);
		$this->assertEquals(200, $res3->get_status());
		$polled = rest_get_server()->response_to_data($res3, false);
		$this->assertIsArray($polled);
		$this->assertNotEmpty($polled);

		$cmd = $polled[0];
		$this->assertArrayHasKey('id', $cmd);
		$this->assertArrayHasKey('command', $cmd);

		// 5) Mark command complete via /device/command-complete
		$req4 = new WP_REST_Request('POST', '/tmon/v1/device/command-complete');
		$req4->set_param('job_id', $cmd['id']);
		$req4->set_param('ok', true);
		$req4->set_param('result', 'ok');
		$res4 = rest_do_request($req4);
		$this->assertEquals(200, $res4->get_status());

		// Assert DB shows executed_at not null
		$row = $wpdb->get_row( $wpdb->prepare( "SELECT executed_at, status FROM {$wpdb->prefix}tmon_device_commands WHERE id = %d", intval($cmd['id']) ), ARRAY_A );
		$this->assertNotEmpty($row['executed_at']);
		$this->assertTrue( in_array( $row['status'], ['done','failed'], true ) );
	}
}
