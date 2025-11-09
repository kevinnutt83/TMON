
<?php
echo '<div class="wrap">';
echo '<h1>TMON Admin Settings</h1>';
echo '<form method="post" action="options.php">';
settings_fields('tmon_admin_settings_group');
do_settings_sections('tmon-admin-settings');
submit_button();
echo '</form>';
echo '</div>';
