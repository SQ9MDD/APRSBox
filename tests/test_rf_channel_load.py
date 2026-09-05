import contextlib
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.db import execute, fetch_one, get_connection, init_db, set_app_setting
from app.services.content import _normalize_modem_payload, create_section_row, update_section_row
from app.services.outbound import build_tnc2_kiss_frame
from app.services.radio_activity import (
    _collect_bucket_source_rows,
    _dashboard_rf_channel_load,
    _logged_rf_ax25_length,
    estimate_rf_airtime_seconds,
    get_dashboard_radio_activity,
    rf_channel_occupancy_pct,
    rf_channel_state,
    run_radio_activity_aggregation,
)

START = datetime(2026, 8, 1, 12, tzinfo=timezone.utc)
LINE = 'SP5ABC>APRS,WIDE1-1:>RF diagnostic test'


@contextlib.contextmanager
def temporary_database():
    with tempfile.TemporaryDirectory() as directory:
        with patch.dict(os.environ, APRSBOX_DB_PATH=str(Path(directory) / 'test.db')):
            init_db()
            set_app_setting('rf_load_available_since', (START - timedelta(hours=1)).isoformat())
            yield


def insert_modem(name='RF', bitrate=1200, uart=115200):
    execute('''INSERT INTO modems(name, modem_type, rf_bitrate, baud_rate, created_at, updated_at)
               VALUES (?, 'SERIALL', ?, ?, ?, ?)''',
            (name, bitrate, uart, (START - timedelta(days=1)).isoformat(), START.isoformat()))
    return int(fetch_one('SELECT id FROM modems WHERE name = ?', (name,))['id'])


def insert_frame(interface_id, direction='rx', source_kind='rf', command=None, length=100, hex_value=None):
    command = command if command is not None else ('0x0' if direction == 'rx' else 'TX')
    if hex_value is None:
        hex_value = build_tnc2_kiss_frame(LINE).hex() if direction == 'tx' else ''
    execute('''INSERT INTO traffic_frames(source, source_kind, interface_id, direction, format, line,
               port, command, length, hex, created_at) VALUES (?, ?, ?, ?, ?, ?, '0', ?, ?, ?, ?)''',
            (f'RF-{interface_id}', source_kind, interface_id, direction,
             'TNC2' if direction == 'rx' else 'TNC2-TX', LINE, command, length, hex_value, START.isoformat()))


def collect():
    return _collect_bucket_source_rows(bucket_start_utc=START, bucket_end_utc=START + timedelta(minutes=5),
                                       collect_band_condition=False)[0]


def aggregate():
    result = run_radio_activity_aggregation(now_utc=START + timedelta(minutes=16))
    assert 'error' not in result, result
    return result


def load(bucket_minutes=5, count=3, start=START):
    starts = [(start + timedelta(minutes=bucket_minutes * i)).isoformat() for i in range(count)]
    return _dashboard_rf_channel_load(bucket_starts=starts, bucket_minutes=bucket_minutes,
                                     window_start_utc=start,
                                     window_end_utc=start + timedelta(minutes=bucket_minutes * count))


class RfAirtimeTests(unittest.TestCase):
    def test_ax25_airtime_at_1200_and_9600(self):
        # 100 existing AX.25 bytes + 2 FCS, expected stuffing + two flags.
        self.assertAlmostEqual(estimate_rf_airtime_seconds(100, 1200), 0.7043010752688172)
        self.assertAlmostEqual(estimate_rf_airtime_seconds(100, 9600), 0.08803763440860215)
        self.assertAlmostEqual(estimate_rf_airtime_seconds(100, 300), 2.817204301075269)

    def test_occupancy_empty_and_over_100(self):
        self.assertEqual(rf_channel_occupancy_pct(60, 300), 20)
        self.assertEqual(rf_channel_occupancy_pct(0, 300), 0)
        self.assertAlmostEqual(rf_channel_occupancy_pct(330, 300), 110)

    def test_classification_boundaries(self):
        for value, expected in ((19.9, 'normal'), (20.0, 'busy'), (39.9, 'busy'), (40.0, 'congested'), (110, 'congested')):
            with self.subTest(value=value):
                self.assertEqual(rf_channel_state(value), expected)

    def test_kiss_tx_excludes_command_delimiters_and_escape_expansion(self):
        # Same AX.25 length despite longer KISS transport encoding; no FCS in KISS.
        ax25 = bytes([0x55]) * 98 + bytes([0xC0, 0xDB])
        kiss = b'\xc0\x00' + ax25.replace(b'\xdb', b'\xdb\xdd').replace(b'\xc0', b'\xdb\xdc') + b'\xc0'
        self.assertEqual(_logged_rf_ax25_length({'direction': 'tx', 'command': 'TX', 'hex': kiss.hex(), 'length': 9999}), 100)
        self.assertEqual(_logged_rf_ax25_length({'direction': 'rx', 'command': '0x0', 'length': 100}), 100)

    def test_missing_or_malformed_metadata_never_uses_text_length(self):
        for command, value in (('TX', ''), ('TX', 'not hex'), ('TX', 'c0 00 db dc c0'), ('TX-PROXY', 'c0 00' + '55' * 100 + 'c0')):
            self.assertIsNone(_logged_rf_ax25_length({'direction': 'tx', 'command': command, 'hex': value, 'length': 100}))
        self.assertIsNone(_logged_rf_ax25_length({'direction': 'rx', 'command': 'MQTT', 'length': 4096}))

    def test_uart_is_independent_of_rf_bitrate(self):
        with temporary_database():
            first = insert_modem(bitrate=1200, uart=9600)
            insert_frame(first)
            second = insert_modem(name='RF9600', bitrate=9600, uart=1200)
            insert_frame(second)
            third = insert_modem(name='Unknown RF', bitrate=None, uart=1200)
            insert_frame(third)
            buckets = {row['interface_id']: row for row in collect()}
            self.assertAlmostEqual(buckets[first]['rf_rx_airtime_seconds'], estimate_rf_airtime_seconds(100, 1200))
            self.assertAlmostEqual(buckets[second]['rf_rx_airtime_seconds'], estimate_rf_airtime_seconds(100, 9600))
            self.assertEqual(buckets[third]['rf_frames_total'], 0)
            self.assertEqual(buckets[third]['rf_unestimated_frames_total'], 1)

    def test_rx_and_repeat_are_two_transmissions_aprsis_and_skips_are_not(self):
        with temporary_database():
            modem = insert_modem()
            insert_frame(modem)
            insert_frame(modem, direction='tx', length=9999)
            insert_frame(modem, source_kind='aprsis')
            insert_frame(modem, direction='tx', command='TX-SKIP')
            row = collect()[0]
            self.assertEqual(row['rf_frames_total'], 2)
            self.assertEqual(row['rf_unestimated_frames_total'], 0)
            tx_length = _logged_rf_ax25_length({'direction': 'tx', 'command': 'TX', 'hex': build_tnc2_kiss_frame(LINE).hex()})
            self.assertAlmostEqual(row['rf_rx_airtime_seconds'], estimate_rf_airtime_seconds(100, 1200))
            self.assertAlmostEqual(row['rf_tx_airtime_seconds'], estimate_rf_airtime_seconds(tx_length, 1200))
            self.assertEqual((row['rx_total'], row['tx_total'], row['digipeated_total']), (1, 1, 1))

    def test_aprsis_to_rf_consumes_airtime_without_changing_existing_activity(self):
        with temporary_database():
            modem = insert_modem()
            insert_frame(modem, direction='tx', source_kind='aprsis_to_rf')
            aggregate()  # Also finds an oldest bucket when this is the only traffic.
            row = fetch_one('SELECT * FROM radio_activity_5m')
            self.assertEqual(row['rf_frames_total'], 1)
            self.assertGreater(row['rf_tx_airtime_seconds'], 0)
            self.assertEqual((row['rx_total'], row['tx_total'], row['digipeated_total']), (0, 0, 0))

    def test_empty_buckets_missing_data_interfaces_and_downsampling(self):
        with temporary_database():
            first = insert_modem()
            second = insert_modem(name='Second RF')
            insert_frame(first)
            insert_frame(second)
            aggregate()
            result = load()
            self.assertEqual(result['measurement'], 'estimated_aprs_rf_channel_load')
            self.assertEqual(len(result['interfaces']), 2)
            for interface in result['interfaces']:
                series = interface['series']
                expected = estimate_rf_airtime_seconds(100, 1200)
                self.assertAlmostEqual(series['rf_airtime_seconds'][0], expected)
                self.assertEqual(series['rf_airtime_seconds'][1:], [0, 0])
                self.assertEqual(series['rf_channel_state'][1:], ['normal', 'normal'])
            downsampled = load(bucket_minutes=15, count=1)['interfaces'][0]['series']
            self.assertAlmostEqual(downsampled['rf_channel_occupancy_pct'][0], expected / 900 * 100)
            self.assertIsNone(load(count=4)['interfaces'][0]['series']['rf_channel_occupancy_pct'][-1])
            self.assertIsNone(load(bucket_minutes=30, count=1)['interfaces'][0]['series']['rf_channel_occupancy_pct'][0])

    def test_empty_database_reports_zero_after_successful_aggregation(self):
        with temporary_database():
            insert_modem()
            aggregate()
            self.assertEqual(load()['interfaces'][0]['series']['rf_channel_occupancy_pct'], [0, 0, 0])

    def test_unknown_bitrate_and_unverified_proxy_are_gaps(self):
        with temporary_database():
            modem = insert_modem(bitrate=None)
            insert_frame(modem)
            proxy = insert_modem(name='Proxy')
            insert_frame(proxy, direction='tx', command='TX-PROXY')
            aggregate()
            for interface in load()['interfaces']:
                self.assertIsNone(interface['series']['rf_channel_state'][0])
                self.assertIsNone(interface['series']['rf_channel_occupancy_pct'][0])
                self.assertEqual(interface['series']['rf_unestimated_frames_total'][0], 1)

    def test_legacy_history_is_not_backfilled_and_null_is_not_zero(self):
        with temporary_database():
            modem = insert_modem()
            execute('''INSERT INTO radio_activity_5m(bucket_start_utc, bucket_end_utc, interface_id, source_name,
                       rx_total, created_at_utc, updated_at_utc) VALUES (?, ?, ?, 'Legacy', 100, ?, ?)''',
                    (START.isoformat(), (START + timedelta(minutes=5)).isoformat(), modem, START.isoformat(), START.isoformat()))
            init_db()
            self.assertIsNone(fetch_one('SELECT rf_frames_total FROM radio_activity_5m')['rf_frames_total'])
            aggregate()
            self.assertIsNone(load()['interfaces'][0]['series']['rf_channel_occupancy_pct'][0])
            self.assertIsNone(load(start=START - timedelta(hours=2), count=1)['interfaces'][0]['series']['rf_channel_occupancy_pct'][0])

    def test_aggregation_is_idempotent_and_saved_airtime_survives_bitrate_change(self):
        with temporary_database():
            modem = insert_modem()
            insert_frame(modem)
            aggregate()
            before = load()['interfaces'][0]['series']['rf_airtime_seconds'][0]
            execute('UPDATE modems SET rf_bitrate = 9600 WHERE id = ?', (modem,))
            self.assertEqual(aggregate()['processed_buckets'], 0)
            self.assertEqual(load()['interfaces'][0]['series']['rf_airtime_seconds'][0], before)

    def test_interface_edit_during_bucket_does_not_reinterpret_old_frames(self):
        with temporary_database():
            modem = insert_modem()
            insert_frame(modem)
            execute('UPDATE modems SET rf_bitrate = 9600, updated_at = ? WHERE id = ?',
                    ((START + timedelta(minutes=1)).isoformat(), modem))
            aggregate()
            series = load()['interfaces'][0]['series']
            self.assertIsNone(series['rf_channel_occupancy_pct'][0])
            self.assertEqual(series['rf_unestimated_frames_total'][0], 1)

    def test_api_endpoint_exposes_estimated_metric_with_existing_series(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest('fastapi is not installed in this environment')
        from app.dependencies import get_current_user
        from app.main import app
        from app.models import UserIdentity
        with temporary_database():
            insert_modem()
            aggregate()
            app.dependency_overrides[get_current_user] = lambda: UserIdentity(
                id=1, username='tester', role='admin', is_active=True,
            )
            try:
                response = TestClient(app).get('/api/dashboard/radio-activity?range=1h')
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                metric = payload['rf_channel_load']
                self.assertEqual(metric['measurement'], 'estimated_aprs_rf_channel_load')
                self.assertEqual(metric['thresholds_pct'], {'busy': 20, 'congested': 40})
                self.assertIn('rx_total', payload['series'])
                self.assertIn('tx_total', payload['series'])
                self.assertEqual(len(metric['interfaces'][0]['series']['rf_channel_state']), len(payload['labels']))
            finally:
                app.dependency_overrides.clear()

    def test_api_retains_grid_and_does_not_clamp_above_100(self):
        with temporary_database():
            modem = insert_modem()
            insert_frame(modem)
            aggregate()
            execute('UPDATE radio_activity_5m SET rf_rx_airtime_seconds = 330, rf_tx_airtime_seconds = 0')
            with patch('app.services.radio_activity.datetime') as clock:
                clock.now.return_value = START + timedelta(minutes=16)
                clock.fromtimestamp.side_effect = datetime.fromtimestamp
                clock.fromisoformat.side_effect = datetime.fromisoformat
                payload = get_dashboard_radio_activity(range_value='1h')
            rf = payload['rf_channel_load']['interfaces'][0]['series']
            self.assertEqual(len(rf['rf_channel_occupancy_pct']), len(payload['labels']))
            self.assertAlmostEqual(max(value for value in rf['rf_channel_occupancy_pct'] if value is not None), 110)
            self.assertEqual(payload['series']['rx_total'].count(1), 1)

    def test_schema_upgrade_adds_nullable_columns_without_traffic_update(self):
        with temporary_database():
            modem = insert_modem()
            insert_frame(modem)
            with get_connection() as connection:
                for column in ('rf_rx_airtime_seconds', 'rf_tx_airtime_seconds', 'rf_frames_total', 'rf_unestimated_frames_total'):
                    connection.execute(f'ALTER TABLE radio_activity_5m DROP COLUMN {column}')
                connection.execute('ALTER TABLE modems DROP COLUMN rf_bitrate')
            before = dict(fetch_one('SELECT * FROM traffic_frames'))
            init_db()
            self.assertEqual(dict(fetch_one('SELECT * FROM traffic_frames')), before)
            self.assertIsNone(fetch_one('SELECT rf_bitrate FROM modems')['rf_bitrate'])


class RfBitrateConfigurationTests(unittest.TestCase):
    def test_optional_rf_bitrate_roundtrips_through_existing_configuration(self):
        with temporary_database():
            payload = {'name': 'KISS', 'modem_type': 'TCP', 'device_path': '127.0.0.1:8001', 'rf_bitrate': '9600'}
            create_section_row('modems', payload)
            row = fetch_one("SELECT * FROM modems WHERE name = 'KISS'")
            self.assertEqual(row['rf_bitrate'], 9600)
            self.assertIsNone(row['baud_rate'])
            update_section_row('modems', row['id'], dict(payload, rf_bitrate='1200'))
            self.assertEqual(fetch_one('SELECT rf_bitrate FROM modems')['rf_bitrate'], 1200)
            self.assertIsNone(_normalize_modem_payload(dict(payload, rf_bitrate=''))['rf_bitrate'])

    def test_rf_bitrate_validation(self):
        for value in ('-1', '0', '1.5', 'nan', '10000001'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _normalize_modem_payload({'modem_type': 'TCP', 'rf_bitrate': value})


if __name__ == '__main__':
    unittest.main()
