#!/usr/bin/env node

import process from 'node:process';

let chromium;
try {
  ({ chromium } = await import('playwright'));
} catch (err) {
  console.error('Playwright is not installed. Install with: npm i -D playwright');
  process.exit(2);
}

const adminUrlInput = process.env.TMON_UC_ADMIN_URL || process.env.WP_ADMIN_URL || '';
const adminUser = process.env.TMON_UC_ADMIN_USER || process.env.WP_ADMIN_USER || '';
const adminPass = process.env.TMON_UC_ADMIN_PASS || process.env.WP_ADMIN_PASS || '';
const headless = (process.env.TMON_UC_SMOKE_HEADLESS || '1') !== '0';

if (!adminUrlInput || !adminUser || !adminPass) {
  console.error('Missing required environment variables: TMON_UC_ADMIN_URL, TMON_UC_ADMIN_USER, TMON_UC_ADMIN_PASS');
  process.exit(2);
}

function normalizeBase(url) {
  const u = new URL(url);
  return `${u.protocol}//${u.host}`;
}

function toAdminPath(url) {
  const u = new URL(url);
  if (u.pathname.includes('/wp-admin')) return u.toString();
  return `${normalizeBase(url)}/wp-admin/`;
}

function toLoginUrl(adminUrl) {
  return `${normalizeBase(adminUrl)}/wp-login.php`;
}

const adminUrl = toAdminPath(adminUrlInput);
const loginUrl = toLoginUrl(adminUrlInput);
const deviceDataUrl = `${normalizeBase(adminUrlInput)}/wp-admin/admin.php?page=tmon-device-data`;

const report = {
  login: false,
  navigation: false,
  pickerPresent: false,
  pickerHasUnits: false,
  settingsHydrated: false,
  unitNameControlsPresent: false,
  validStageTriggered: false,
  invalidJsonBlocked: false,
  shortcodeSwitchesPresent: false,
  details: []
};

const browser = await chromium.launch({ headless });
const context = await browser.newContext();
const page = await context.newPage();

try {
  await page.goto(loginUrl, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.fill('#user_login', adminUser);
  await page.fill('#user_pass', adminPass);
  await page.click('#wp-submit');
  await page.waitForLoadState('domcontentloaded', { timeout: 45000 });

  const atLogin = page.url().includes('wp-login.php');
  if (atLogin) {
    throw new Error('Login failed; still on wp-login.php');
  }
  report.login = true;

  await page.goto(deviceDataUrl, { waitUntil: 'domcontentloaded', timeout: 45000 });
  report.navigation = page.url().includes('tmon-device-data');

  await page.waitForSelector('#tmon-unit-picker', { timeout: 15000 });
  report.pickerPresent = true;

  const unitCount = await page.$eval('#tmon-unit-picker', (el) => {
    const opts = Array.from(el.options || []);
    return opts.filter((o) => o.value && o.value.trim() !== '').length;
  });
  report.pickerHasUnits = unitCount > 0;

  if (unitCount > 0) {
    await page.$eval('#tmon-unit-picker', (el) => {
      const opts = Array.from(el.options || []).filter((o) => o.value && o.value.trim() !== '');
      if (opts.length > 0) {
        el.value = opts[0].value;
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });

    await page.waitForFunction(() => {
      const a = document.querySelector('#tmon-settings-applied');
      const s = document.querySelector('#tmon-settings-staged');
      if (!a || !s) return false;
      const ta = (a.textContent || '').trim();
      const ts = (s.textContent || '').trim();
      return ta !== '' && ts !== '' && ta !== 'Loading...' && ts !== 'Loading...';
    }, { timeout: 20000 });
    report.settingsHydrated = true;
  } else {
    report.details.push('No non-empty unit options were available.');
  }

  report.unitNameControlsPresent = await page.$('#tmon_unit_name_input') !== null && await page.$('#tmon_update_unit_name_btn') !== null;

  const editor = await page.$('#tmon-settings-editor');
  const pushBtn = await page.$('#tmon-settings-push');
  const statusSel = '#tmon-settings-status';
  if (editor && pushBtn && unitCount > 0) {
    await page.fill('#tmon-settings-editor', JSON.stringify({ SAMPLE_TEMP: true }));
    await page.click('#tmon-settings-push');
    await page.waitForTimeout(1500);
    const statusText = (await page.textContent(statusSel))?.trim() || '';
    if (statusText.length > 0 && statusText !== 'Invalid JSON') {
      report.validStageTriggered = true;
    } else {
      report.details.push(`Valid stage status text was unexpected: "${statusText}"`);
    }

    await page.fill('#tmon-settings-editor', '{invalid-json');
    await page.click('#tmon-settings-push');
    await page.waitForFunction(() => {
      const st = document.querySelector('#tmon-settings-status');
      return st && (st.textContent || '').includes('Invalid JSON');
    }, { timeout: 8000 });
    report.invalidJsonBlocked = true;
  } else {
    report.details.push('Staging controls not available for automation.');
  }

  const loadBtn = await page.$('#tmon_ds_load');
  if (loadBtn && unitCount > 0) {
    await page.click('#tmon_ds_load');
    await page.waitForTimeout(1200);
    const switchCount = await page.$$eval('.tmon-switch', (els) => els.length);
    report.shortcodeSwitchesPresent = switchCount > 0;
    if (!report.shortcodeSwitchesPresent) {
      report.details.push('No animated bool switches found in tmon_device_settings editor.');
    }
  }

  const required = [
    'login',
    'navigation',
    'pickerPresent',
    'pickerHasUnits',
    'settingsHydrated',
    'unitNameControlsPresent',
    'invalidJsonBlocked'
  ];
  const failed = required.filter((k) => !report[k]);

  console.log(JSON.stringify(report, null, 2));
  if (failed.length > 0) {
    console.error('Smoke test failed checks:', failed.join(', '));
    process.exitCode = 1;
  }
} catch (err) {
  console.error('Smoke test execution error:', err?.message || err);
  console.log(JSON.stringify(report, null, 2));
  process.exitCode = 1;
} finally {
  await context.close();
  await browser.close();
}
