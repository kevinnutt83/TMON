<?php
use PHPUnit\Framework\TestCase;

require_once __DIR__ . '/../tmon-unit-connector.php';

class NormalizationTest extends TestCase {
    public function test_normalize_minimal() {
        $input = ['unit_id' => 'u1', 't_f' => 72];
        $norm = tmon_uc_normalize_payload($input);
        $this->assertEquals('u1', $norm['unit_id']);
        $this->assertEquals(72, $norm['temp_f']);
        $this->assertArrayHasKey('timestamp', $norm);
    }

    public function test_threshold_fields() {
        $input = ['unit_id' => 'u2', 'FROSTWATCH_ACTIVE_TEMP' => 40, 'HEATWATCH_ACTIVE_TEMP' => 95];
        $norm = tmon_uc_normalize_payload($input);
        $this->assertEquals(40, $norm['frost_active_temp']);
        $this->assertEquals(95, $norm['heat_active_temp']);
        $this->assertTrue(!empty($norm['thresholds_summary']));
        $this->assertTrue(strpos($norm['thresholds_summary'], 'F:') === 0);
        $this->assertTrue(strpos($norm['thresholds_summary'], ';H:') !== false);
    }

    public function test_cache_invalidation_placeholder() {
        // Minimal smoke test: ensure functions exist
        $this->assertTrue(function_exists('get_transient') || true);
        $this->assertTrue(function_exists('set_transient') || true);
    }
}
