"""
Tests for the parking QR module.

Run:  .venv/bin/python -m unittest tests.test_parking -v

Route tests use a minimal Flask app with the parking blueprint and a mocked
repository/notifier/reCAPTCHA, so no database or network is needed.
"""

import os
import re
import time
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from flask import Flask  # noqa: E402
from flask_limiter import Limiter  # noqa: E402
from flask_limiter.util import get_remote_address  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

from services.parking import security, validators  # noqa: E402
from services.parking.routes import create_blueprint  # noqa: E402
from services.parking.validators import ValidationError  # noqa: E402


class PlateTests(unittest.TestCase):
    def check(self, raw, normalized, display, region=None):
        p = validators.normalize_plate(raw, 'LK')
        self.assertEqual((p.normalized, p.display, p.region), (normalized, display, region), raw)

    def test_modern(self):
        self.check('CAB-1234', 'CAB1234', 'CAB-1234')
        self.check('cab 1234', 'CAB1234', 'CAB-1234')
        self.check('KA1234', 'KA1234', 'KA-1234')

    def test_province_prefix(self):
        self.check('WP CAB-1234', 'CAB1234', 'WP CAB-1234', 'WP')
        self.check('wp-ka-1234', 'KA1234', 'WP KA-1234', 'WP')
        # 3-letter series that happens to start with a province code
        self.check('SPA-1234', 'SPA1234', 'SPA-1234')
        self.check('NP-1234', 'NP1234', 'NP-1234')

    def test_numeric(self):
        self.check('250-1234', '250-1234', '250-1234')
        self.check('65 1234', '65-1234', '65-1234')

    def test_sri(self):
        sri = 'ශ්‍රී'
        self.check(f'19 {sri} 1234', '19SRI1234', f'19 {sri} 1234')
        self.check('19 SRI 1234', '19SRI1234', f'19 {sri} 1234')
        self.check('19ශ්රී1234', '19SRI1234', f'19 {sri} 1234')  # no ZWJ

    def test_invalid(self):
        for bad in ['', 'ABCD-1234', 'CAB-123', 'CAB-12345', 'XX CAB-1234', '1234-1234', '651234',
                    '<script>', 'C4B-1234']:
            with self.assertRaises(ValidationError, msg=bad):
                validators.normalize_plate(bad, 'LK')

    def test_unsupported_country(self):
        with self.assertRaises(ValidationError):
            validators.normalize_plate('CAB-1234', 'IN')


class MobileTests(unittest.TestCase):
    def test_lk_formats(self):
        for raw in ['0771234567', '077 123 4567', '+94771234567', '0094771234567', '94-77-1234567', '771234567']:
            self.assertEqual(validators.normalize_mobile(raw, 'LK'), '+94771234567', raw)

    def test_lk_invalid(self):
        for bad in ['0112345678', '07712345', '+9477123456789', 'abc', '']:
            with self.assertRaises(ValidationError, msg=bad):
                validators.normalize_mobile(bad, 'LK')

    def test_scanner_any_e164(self):
        self.assertEqual(validators.normalize_any_mobile('+44 7911 123456', 'LK'), '+447911123456')
        with self.assertRaises(ValidationError):
            validators.normalize_any_mobile('12345', 'LK')


class HelperTests(unittest.TestCase):
    def test_coordinates(self):
        self.assertEqual(validators.parse_coordinates('6.9271', '79.8612', '12.7'), (6.9271, 79.8612, 12))
        self.assertEqual(validators.parse_coordinates('95', '0'), (None, None, None))
        self.assertEqual(validators.parse_coordinates('x', '1'), (None, None, None))
        self.assertEqual(validators.parse_coordinates(None, None), (None, None, None))

    def test_clean_text(self):
        self.assertEqual(validators.clean_text('  hi\x00\x1b there ', 200), 'hi there')
        self.assertEqual(len(validators.clean_text('a' * 500, 200)), 200)


def make_app():
    app = Flask(__name__, template_folder=os.path.join(ROOT, 'templates'))
    app.config.update(SECRET_KEY='test-secret', TESTING=True)
    limiter = Limiter(app=app, key_func=get_remote_address, storage_uri='memory://', enabled=False)
    app.register_blueprint(create_blueprint(limiter))
    app.test_limiter = limiter  # Flask-Limiter holds only a weakref; keep it alive
    return app


class TokenTests(unittest.TestCase):
    def setUp(self):
        self.app = make_app()

    def test_token_properties(self):
        with self.app.test_request_context():
            t1 = security.derive_qr_token(1, 'a' * 32)
            self.assertTrue(security.is_well_formed_token(t1))
            self.assertEqual(t1, security.derive_qr_token(1, 'a' * 32))       # deterministic
            self.assertNotEqual(t1, security.derive_qr_token(1, 'b' * 32))    # rotation changes it
            self.assertNotEqual(t1, security.derive_qr_token(2, 'a' * 32))
            self.assertEqual(len(security.hash_token(t1)), 64)
            url = security.public_scan_url(t1)
            self.assertRegex(url, r'/park/s/[A-Za-z0-9_-]{32}$')

    def test_secret_env_changes_token(self):
        with self.app.test_request_context():
            base = security.derive_qr_token(1, 'n' * 32)
            with mock.patch.dict(os.environ, {'PARK_QR_SECRET': 'other'}):
                self.assertNotEqual(base, security.derive_qr_token(1, 'n' * 32))

    def test_public_base_url(self):
        with self.app.test_request_context(), \
                mock.patch.dict(os.environ, {'PARK_PUBLIC_BASE_URL': 'https://park.example.com/'}):
            self.assertTrue(security.public_scan_url('x' * 32).startswith('https://park.example.com/park/s/'))

    def test_recaptcha_fails_closed_without_secret(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(security.verify_recaptcha('token', '1.2.3.4'))


VEHICLE = {'id': 7, 'plate_display': 'WP CAB-1234', 'country_code': 'LK', 'ntfy_topic': 'park-topic',
           'scan_window_minutes': 10}
USER = {'id': 1, 'full_name': 'Owner', 'country_code': 'LK', 'mobile_e164': '+94771234567',
        'ntfy_topic': 'park-topic', 'is_admin': False, 'is_active': True,
        'scan_window_minutes': 10, 'created_at': None, 'last_login_at': None}


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.app = make_app()
        self.client = self.app.test_client()
        self.repo = mock.patch('services.parking.routes.repository').start()
        self.sec_repo = mock.patch('services.parking.repository.get_user').start()
        self.captcha = mock.patch('services.parking.security.verify_recaptcha', return_value=True).start()
        self.send = mock.patch('services.parking.notifier.send', return_value=True).start()
        mock.patch('services.parking.notifier.ntfy_server', return_value='https://ntfy.sh').start()
        self.repo.find_vehicle_by_token.return_value = VEHICLE
        self.repo.seconds_since_last_sent.return_value = None
        self.token = 'A' * 32

    def tearDown(self):
        mock.patch.stopall()

    def csrf(self):
        html = self.client.get(f'/park/s/{self.token}').get_data(as_text=True)
        return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)

    def proof(self):
        html = self.client.get(f'/park/s/{self.token}').get_data(as_text=True)
        return re.search(r'name="scan_proof" value="([^"]+)"', html).group(1)

    # ---- public scan ----

    def test_scan_page_renders_without_pii(self):
        res = self.client.get(f'/park/s/{self.token}')
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn('g-recaptcha', body)
        self.assertNotIn('CAB', body)          # plate not shown to scanner
        self.assertNotIn('park-topic', body)   # topic never leaked
        self.assertEqual(res.headers['X-Frame-Options'], 'DENY')

    def test_malformed_token_never_hits_db(self):
        res = self.client.get('/park/s/short')
        self.assertEqual(res.status_code, 404)
        self.repo.find_vehicle_by_token.assert_not_called()

    def test_unknown_token(self):
        self.repo.find_vehicle_by_token.return_value = None
        self.assertEqual(self.client.get(f'/park/s/{self.token}').status_code, 404)

    def test_notify_requires_csrf(self):
        res = self.client.post(f'/park/s/{self.token}/notify', json={'reason': 'blocking'})
        self.assertEqual(res.status_code, 403)
        self.send.assert_not_called()

    def test_notify_requires_captcha(self):
        self.captcha.return_value = False
        res = self.client.post(f'/park/s/{self.token}/notify', json={'reason': 'blocking'},
                               headers={'X-CSRF-Token': self.csrf()})
        self.assertEqual(res.status_code, 400)
        self.send.assert_not_called()
        self.repo.record_scan.assert_not_called()

    def test_notify_rejected_after_window(self):
        proof = self.proof()
        with mock.patch('services.parking.security.time.time', return_value=time.time() + 11 * 60):
            res = self.client.post(f'/park/s/{self.token}/notify', headers={'X-CSRF-Token': self.csrf()},
                                   json={'reason': 'blocking', 'scan_proof': proof, 'g-recaptcha-response': 'ok'})
        self.assertEqual(res.status_code, 410)
        self.send.assert_not_called()

    def test_notify_rejected_without_proof(self):
        res = self.client.post(f'/park/s/{self.token}/notify', headers={'X-CSRF-Token': self.csrf()},
                               json={'reason': 'blocking', 'g-recaptcha-response': 'ok'})
        self.assertEqual(res.status_code, 410)

    def test_notify_success_records_scan(self):
        res = self.client.post(f'/park/s/{self.token}/notify', headers={'X-CSRF-Token': self.csrf()}, json={
            'reason': 'blocking', 'message': 'white van', 'scan_proof': self.proof(), 'mobile': '0771234567',
            'lat': '6.9271', 'lng': '79.8612', 'accuracy': '10', 'g-recaptcha-response': 'ok'})
        self.assertEqual(res.status_code, 200, res.get_json())
        self.assertEqual(res.get_json()['status'], 'sent')
        topic, payload = self.send.call_args.args
        self.assertEqual(topic, 'park-topic')
        self.assertIn('+94771234567', payload['message'])
        self.assertIn('maps.google.com/?q=6.9271,79.8612', payload['message'])
        args = self.repo.record_scan.call_args.args
        self.assertEqual(args[0], 7)
        self.assertEqual(args[3:7], ('+94771234567', 6.9271, 79.8612, 10))
        self.assertEqual(args[-1], 'sent')

    def test_notify_cooldown_throttles(self):
        self.repo.seconds_since_last_sent.return_value = 5
        res = self.client.post(f'/park/s/{self.token}/notify', json={'reason': 'blocking', 'scan_proof': self.proof()},
                               headers={'X-CSRF-Token': self.csrf()})
        self.assertEqual(res.get_json()['status'], 'throttled')
        self.send.assert_not_called()
        self.assertEqual(self.repo.record_scan.call_args.args[-1], 'throttled')

    def test_notify_bad_mobile(self):
        res = self.client.post(f'/park/s/{self.token}/notify', json={'mobile': 'abc', 'scan_proof': self.proof()},
                               headers={'X-CSRF-Token': self.csrf()})
        self.assertEqual(res.status_code, 400)

    # ---- auth / isolation ----

    def test_backoffice_requires_park_login(self):
        self.assertEqual(self.client.get('/park/').status_code, 302)
        self.assertEqual(self.client.get('/park/api/vehicles').status_code, 401)

    def test_budget_session_does_not_grant_park_access(self):
        with self.client.session_transaction() as s:
            s['user_id'] = 1
            s['is_admin'] = True
        self.assertEqual(self.client.get('/park/api/vehicles').status_code, 401)

    def _login(self, user=USER):
        csrf = self.csrf()
        self.repo.get_user_for_login.return_value = dict(user, password_hash=generate_password_hash('correct-pass'))
        self.sec_repo.return_value = user
        res = self.client.post('/park/login', json={'mobile': '0771234567', 'password': 'correct-pass'},
                               headers={'X-CSRF-Token': csrf})
        self.assertEqual(res.status_code, 200)
        with self.client.session_transaction() as s:
            return s['park_csrf']

    def test_login_wrong_password(self):
        csrf = self.csrf()
        self.repo.get_user_for_login.return_value = dict(USER, password_hash=generate_password_hash('x' * 8))
        res = self.client.post('/park/login', json={'mobile': '0771234567', 'password': 'nope'},
                               headers={'X-CSRF-Token': csrf})
        self.assertEqual(res.status_code, 401)

    def test_login_rotates_csrf_and_scopes_queries(self):
        old = self.csrf()
        csrf = self._login()
        self.assertNotEqual(old, csrf)
        self.repo.list_vehicles.return_value = []
        self.assertEqual(self.client.get('/park/api/vehicles').status_code, 200)
        self.repo.list_vehicles.assert_called_with(1)

        # IDOR: rotating someone else's vehicle -> repository scoped by user returns False -> 404
        self.repo.rotate_vehicle_qr.return_value = False
        res = self.client.post('/park/api/vehicles/999/rotate-qr', headers={'X-CSRF-Token': csrf})
        self.assertEqual(res.status_code, 404)
        self.repo.rotate_vehicle_qr.assert_called_with(1, 999)

    def test_state_change_requires_csrf_when_logged_in(self):
        self._login()
        res = self.client.post('/park/api/vehicles/1/rotate-qr')
        self.assertEqual(res.status_code, 403)
        self.repo.rotate_vehicle_qr.assert_not_called()

    def test_deactivated_user_is_logged_out(self):
        self._login()
        self.sec_repo.return_value = dict(USER, is_active=False)
        self.assertEqual(self.client.get('/park/api/vehicles').status_code, 401)

    def test_admin_api_forbidden_for_normal_user(self):
        self._login()
        self.assertEqual(self.client.get('/park/api/admin/users').status_code, 403)

    def test_dashboard_renders(self):
        self._login()
        self.repo.get_user.return_value = USER
        res = self.client.get('/park/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('Change password', res.get_data(as_text=True))

    def test_qr_png_contains_no_pii(self):
        self._login()
        self.repo.get_vehicle.return_value = {'id': 7, 'qr_nonce': 'n' * 32, 'plate_display': 'CAB-1234'}
        with mock.patch('services.parking.routes.qrcode.make', wraps=__import__('qrcode').make) as make:
            res = self.client.get('/park/vehicles/7/qr.png')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, 'image/png')
        encoded = make.call_args.args[0]
        self.assertRegex(encoded, r'/park/s/[A-Za-z0-9_-]{32}$')
        self.assertNotIn('CAB', encoded)
        self.assertNotIn('7712', encoded)

    def test_change_password(self):
        csrf = self._login()
        self.repo.get_password_hash.return_value = generate_password_hash('correct-pass')
        res = self.client.post('/park/api/account/password', headers={'X-CSRF-Token': csrf}, json={
            'current_password': 'correct-pass', 'new_password': 'brand-new-pass',
            'confirm_password': 'brand-new-pass'})
        self.assertEqual(res.status_code, 200, res.get_json())
        self.repo.update_password.assert_called_once()

    def test_register(self):
        csrf = self.csrf()
        res = self.client.post('/park/register', headers={'X-CSRF-Token': csrf}, json={
            'mobile': '077 123 4567', 'plate': 'wp cab 1234', 'password': 'longenough',
            'confirm_password': 'longenough', 'g-recaptcha-response': 'ok'})
        self.assertEqual(res.status_code, 201, res.get_json())
        args = self.repo.create_user_with_vehicle.call_args.args
        self.assertEqual(args[2], '+94771234567')
        self.assertEqual(args[4].normalized, 'CAB1234')

    def test_register_requires_captcha(self):
        self.captcha.return_value = False
        res = self.client.post('/park/register', headers={'X-CSRF-Token': self.csrf()}, json={
            'mobile': '0771234567', 'plate': 'CAB-1234', 'password': 'longenough', 'confirm_password': 'longenough'})
        self.assertEqual(res.status_code, 400)
        self.repo.create_user_with_vehicle.assert_not_called()


if __name__ == '__main__':
    unittest.main()
