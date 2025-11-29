<?php
/**
 * PHPUnit tests for TMON Admin provisioning queue.
 *
 * Usage:
 *   vendor/bin/phpunit --filter TMON_Admin_Enqueue_Test
 */

class TMON_Admin_Enqueue_Test extends WP_UnitTestCase {
	public function test_enqueue_provision_creates_option_entry_with_user_and_wpapiurl() {
		$key = 'test-key-'.uniqid();
		$payload = ['site_url' => 'https://example.com', 'note'=>'phpunit-test'];
		// Ensure option cleared
		delete_option('tmon_admin_pending_provision');

		// Make sure a user exists and set current user
		$uid = $this->factory->user->create(['role' => 'administrator', 'user_login' => 'testadmin']);
		wp_set_current_user($uid);

		$result = tmon_admin_enqueue_provision($key, $payload);
		$this->assertTrue($result, 'tmon_admin_enqueue_provision returned true');

		$queue = get_option('tmon_admin_pending_provision', []);
		$this->assertIsArray($queue, 'pending_provision option is array');
		$this->assertArrayHasKey($key, $queue, 'Enqueued key present in option');
		$this->assertEquals('https://example.com', $queue[$key]['site_url']);
		$this->assertEquals('https://example.com', $queue[$key]['wordpress_api_url'], 'wordpress_api_url should default to site_url');
		$this->assertEquals('testadmin', $queue[$key]['requested_by_user']);
	}
}

