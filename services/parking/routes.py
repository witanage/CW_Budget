"""
Parking QR notifier routes (Blueprint mounted at /park).

Public:
  GET  /park/s/<token>            scan landing page
  POST /park/s/<token>/notify     reCAPTCHA-gated notification
  POST /park/s/<token>/call       reCAPTCHA-gated in-app call (if the owner enabled calls)
  /park/call/<caller>/...         caller side of a call (status poll, hang up)
  /park/c/<owner>[/...]           owner side of a call (link sent via ntfy)
Auth:
  GET/POST /park/login, POST /park/logout (no self-registration; admins create accounts)
Back office (park_login_required):
  /park/, /park/api/vehicles..., /park/api/scans, /park/api/account/...
Admin (park_admin_required):
  /park/api/admin/users...
"""

import io
import logging
import os
import time
from datetime import datetime

import qrcode
from flask import (Blueprint, jsonify, make_response, redirect, render_template, request,
                   send_file, session, url_for, abort)
from werkzeug.security import check_password_hash, generate_password_hash

from . import notifier, repository, security, totp, validators
from .repository import DatabaseUnavailable, DuplicateError
from .validators import ValidationError

logger = logging.getLogger(__name__)

# A real hash so failed logins for unknown numbers take the same time as wrong passwords.
_DUMMY_HASH = generate_password_hash('timing-equaliser-not-a-password')


def _cooldown_seconds() -> int:
    try:
        return max(0, int(os.environ.get('PARK_NOTIFY_COOLDOWN_SECONDS', '60')))
    except ValueError:
        return 60


def _iso(value):
    if isinstance(value, datetime):
        return value.isoformat() + 'Z'
    return value


def _serialize(row, drop=()):
    out = {}
    for k, v in row.items():
        if k in drop:
            continue
        if isinstance(v, datetime):
            v = _iso(v)
        elif hasattr(v, 'is_finite'):  # Decimal
            v = float(v)
        out[k] = v
    return out


def _vehicle_json(v):
    data = _serialize(v, drop=('qr_nonce',))
    data['scan_url'] = security.public_scan_url(security.derive_qr_token(v['id'], v['qr_nonce']))
    data['qr_png'] = url_for('parking.vehicle_qr_png', vehicle_id=v['id'])
    data['print_url'] = url_for('parking.vehicle_print', vehicle_id=v['id'])
    return data


def _payload():
    return request.get_json(silent=True) or request.form


MAX_SDP_BYTES = 20000

PENDING_2FA_SECONDS = 300
MAX_2FA_TRIES = 5


def _check_second_factor(uid, code) -> bool:
    """Accept a current TOTP code (once per time step) or an unused recovery code."""
    info = repository.get_totp(uid)
    if not info or not info.get('totp_enabled'):
        return False
    if totp.is_totp_code(code):
        step = totp.verify(info['totp_secret'], code, info['totp_last_step'])
        return step is not None and repository.claim_totp_step(uid, step)
    remaining = totp.use_recovery_code(info.get('totp_recovery'), code)
    return remaining is not None and repository.replace_recovery(uid, info['totp_recovery'], remaining)


def create_blueprint(limiter):
    bp = Blueprint('parking', __name__, url_prefix='/park')

    rl_notify = os.environ.get('RATE_LIMIT_PARK_NOTIFY', '5 per 10 minutes')
    rl_call = os.environ.get('RATE_LIMIT_PARK_CALL', '3 per 10 minutes')
    rl_call_poll = os.environ.get('RATE_LIMIT_PARK_CALL_POLL', '240 per minute')
    rl_scan_page = os.environ.get('RATE_LIMIT_PARK_SCAN_PAGE', '30 per minute')
    rl_login = os.environ.get('RATE_LIMIT_LOGIN', '5 per 15 minutes')
    rl_password = os.environ.get('RATE_LIMIT_CHANGE_PASSWORD', '3 per hour')
    rl_api = os.environ.get('RATE_LIMIT_API', '100 per minute')
    rl_admin = os.environ.get('RATE_LIMIT_ADMIN', '30 per minute')

    @bp.after_request
    def security_headers(resp):
        resp.headers['X-Frame-Options'] = 'DENY'
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        # Only the origin (never the /park/s/<token> path) leaves in Referer headers.
        resp.headers['Referrer-Policy'] = 'strict-origin'
        return resp

    @bp.errorhandler(DatabaseUnavailable)
    def db_unavailable(_e):
        if '/api/' in request.path or request.method == 'POST':
            return jsonify({'error': 'Service temporarily unavailable'}), 503
        return render_template('park/scan_invalid.html',
                               message='Service temporarily unavailable. Please try again shortly.'), 503

    @bp.errorhandler(404)
    def not_found(_e):
        if '/api/' in request.path:
            return jsonify({'error': 'Not found'}), 404
        return render_template('park/scan_invalid.html', message='Page not found.'), 404

    @bp.errorhandler(403)
    def forbidden(_e):
        return render_template('park/scan_invalid.html', message='Access denied.'), 403

    @bp.context_processor
    def inject():
        return {
            'csrf_token': security.csrf_token,
            'recaptcha_site_key': security.recaptcha_site_key(),
        }

    # ------------------------------------------------------------------
    # Public scan
    # ------------------------------------------------------------------

    def _lookup(token):
        if not security.is_well_formed_token(token):
            return None
        return repository.find_vehicle_by_token(token)

    @bp.route('/s/<token>', methods=['GET'])
    @limiter.limit(rl_scan_page)
    def scan_page(token):
        vehicle = _lookup(token)
        if not vehicle:
            return render_template('park/scan_invalid.html'), 404
        window = vehicle['scan_window_minutes']
        return render_template('park/scan.html', token=token, reasons=notifier.REASONS,
                               scan_proof=security.issue_scan_window(token),
                               window_seconds=window * 60,
                               calls_enabled=bool(vehicle.get('calls_enabled')),
                               ice_servers=security.ice_servers(),
                               mobile_hint=validators.get_country(vehicle['country_code']).mobile_hint)

    @bp.route('/s/<token>/notify', methods=['POST'])
    @limiter.limit(rl_notify)
    def scan_notify(token):
        if not security.csrf_valid():
            return jsonify({'error': 'Session expired. Please reload the page.'}), 403
        data = _payload()
        if not security.verify_recaptcha(data.get('g-recaptcha-response', ''), security.client_ip()):
            return jsonify({'error': 'Please complete the "I\'m not a robot" check.'}), 400

        vehicle = _lookup(token)
        if not vehicle:
            return jsonify({'error': 'This QR code is no longer valid.'}), 404
        if not security.scan_window_remaining(token, data.get('scan_proof', ''), vehicle['scan_window_minutes']):
            return jsonify({'error': 'Time expired. Please scan the QR code again.', 'expired': True}), 410

        reason = data.get('reason', 'other')
        if reason not in notifier.REASONS:
            reason = 'other'
        message = validators.clean_text(data.get('message'), 200)
        mobile = None
        raw_mobile = validators.clean_text(data.get('mobile'), 25)
        if raw_mobile:
            try:
                mobile = validators.normalize_any_mobile(raw_mobile, vehicle['country_code'])
            except ValidationError as e:
                return jsonify({'error': str(e)}), 400
        lat, lng, acc = validators.parse_coordinates(data.get('lat'), data.get('lng'), data.get('accuracy'))

        ago = repository.seconds_since_last_sent(vehicle['id'])
        if ago is not None and ago < _cooldown_seconds():
            status = 'throttled'
        else:
            payload = notifier.build_message(vehicle['plate_display'], reason, message, mobile, lat, lng)
            status = 'sent' if notifier.send(vehicle['ntfy_topic'], payload) else 'failed'

        repository.record_scan(vehicle['id'], security.client_ip(), request.headers.get('User-Agent'),
                               mobile, lat, lng, acc, reason, message, status)

        if status == 'failed':
            return jsonify({'error': 'Could not reach the owner right now. Please try again.'}), 502
        return jsonify({
            'status': status,
            'message': ('The owner was already notified moments ago.' if status == 'throttled'
                        else 'The owner has been notified.'),
        }), 200

    # ------------------------------------------------------------------
    # In-app calls (WebRTC audio; park_calls is the signalling channel)
    #
    # Scanner: POST /s/<qr>/call (offer) -> poll /call/<caller>/status -> /call/<caller>/end
    # Owner:   GET /c/<owner> (link in ntfy) -> /c/<owner>/status (offer) -> /answer -> /end
    # ------------------------------------------------------------------

    def _no_store(resp):
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    def _clean_sdp(raw):
        if not isinstance(raw, str) or not raw.startswith('v=0') or len(raw) > MAX_SDP_BYTES:
            return None
        return raw

    @bp.route('/s/<token>/call', methods=['POST'])
    @limiter.limit(rl_call)
    def call_start(token):
        if not security.csrf_valid():
            return jsonify({'error': 'Session expired. Please reload the page.'}), 403
        data = _payload()
        if not security.verify_recaptcha(data.get('g-recaptcha-response', ''), security.client_ip()):
            return jsonify({'error': 'Please complete the "I\'m not a robot" check.'}), 400
        vehicle = _lookup(token)
        if not vehicle:
            return jsonify({'error': 'This QR code is no longer valid.'}), 404
        if not vehicle.get('calls_enabled'):
            return jsonify({'error': 'The owner does not accept calls.'}), 403
        if not security.scan_window_remaining(token, data.get('scan_proof', ''), vehicle['scan_window_minutes']):
            return jsonify({'error': 'Time expired. Please scan the QR code again.', 'expired': True}), 410
        offer = _clean_sdp(data.get('sdp'))
        if not offer:
            return jsonify({'error': 'Could not start the call on this device.'}), 400
        if repository.has_ringing_call(vehicle['id']):
            return jsonify({'error': 'Someone is already calling the owner. Please try again in a minute.'}), 409

        caller_token, owner_token = security.new_call_token(), security.new_call_token()
        repository.create_call(vehicle['id'], security.hash_token(caller_token),
                               security.hash_token(owner_token), offer, security.client_ip())
        join_url = security.public_url('parking.call_owner_page', token=owner_token)
        sent = notifier.send(vehicle['ntfy_topic'], notifier.build_call_message(vehicle['plate_display'], join_url))
        repository.record_scan(vehicle['id'], security.client_ip(), request.headers.get('User-Agent'),
                               None, None, None, None, 'call', None, 'sent' if sent else 'failed')
        if not sent:
            repository.end_call('caller', security.hash_token(caller_token), 'failed')
            return jsonify({'error': 'Could not reach the owner right now. Please try again.'}), 502
        return _no_store(jsonify({
            'status': 'ringing',
            'ring_seconds': repository.CALL_RING_SECONDS,
            'status_url': url_for('parking.call_caller_status', token=caller_token),
            'end_url': url_for('parking.call_caller_end', token=caller_token),
        })), 201

    def _call_or_404(role, token):
        if not security.is_well_formed_token(token):
            abort(404)
        call = repository.get_call(role, security.hash_token(token))
        if not call:
            abort(404)
        return call

    @bp.route('/call/<token>/status', methods=['GET'])
    @limiter.limit(rl_call_poll)
    def call_caller_status(token):
        call = _call_or_404('caller', token)
        out = {'status': call['status']}
        if call['status'] == 'connected':
            out['answer'] = call['answer_sdp']
        return _no_store(jsonify(out))

    @bp.route('/call/<token>/end', methods=['POST'])
    @limiter.limit(rl_call_poll)
    def call_caller_end(token):
        if not security.csrf_valid():
            return jsonify({'error': 'Session expired. Please reload the page.'}), 403
        _call_or_404('caller', token)
        reason = 'failed' if _payload().get('reason') == 'failed' else 'cancelled'
        repository.end_call('caller', security.hash_token(token), reason)
        return jsonify({'status': 'ended'})

    @bp.route('/c/<token>', methods=['GET'])
    @limiter.limit(rl_scan_page)
    def call_owner_page(token):
        call = _call_or_404('owner', token)
        return _no_store(make_response(render_template(
            'park/call.html', token=token, status=call['status'], plate=call['plate_display'],
            ice_servers=security.ice_servers())))

    @bp.route('/c/<token>/status', methods=['GET'])
    @limiter.limit(rl_call_poll)
    def call_owner_status(token):
        call = _call_or_404('owner', token)
        out = {'status': call['status']}
        if call['status'] == 'ringing':
            out['offer'] = call['offer_sdp']
        return _no_store(jsonify(out))

    @bp.route('/c/<token>/answer', methods=['POST'])
    @limiter.limit(rl_call_poll)
    def call_owner_answer(token):
        if not security.csrf_valid():
            return jsonify({'error': 'Session expired. Please reload the page.'}), 403
        _call_or_404('owner', token)
        answer = _clean_sdp(_payload().get('sdp'))
        if not answer:
            return jsonify({'error': 'Could not answer the call on this device.'}), 400
        if not repository.answer_call(security.hash_token(token), answer):
            return jsonify({'error': 'This call has already ended.'}), 409
        return jsonify({'status': 'connected'})

    @bp.route('/c/<token>/end', methods=['POST'])
    @limiter.limit(rl_call_poll)
    def call_owner_end(token):
        if not security.csrf_valid():
            return jsonify({'error': 'Session expired. Please reload the page.'}), 403
        _call_or_404('owner', token)
        reason = 'failed' if _payload().get('reason') == 'failed' else 'declined'
        repository.end_call('owner', security.hash_token(token), reason)
        return jsonify({'status': 'ended'})

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    @bp.route('/login', methods=['GET', 'POST'])
    @limiter.limit(rl_login, methods=['POST'])
    def login():
        if request.method == 'GET':
            if security.current_park_user_id():
                return redirect(url_for('parking.dashboard'))
            return render_template('park/login.html')

        if not security.csrf_valid():
            return jsonify({'error': 'Session expired. Please reload the page.'}), 403
        data = _payload()
        password = data.get('password') or ''
        try:
            mobile = validators.normalize_mobile(data.get('mobile', ''), data.get('country'))
        except ValidationError:
            mobile = None
        user = repository.get_user_for_login(mobile) if mobile else None
        ok = check_password_hash(user['password_hash'] if user else _DUMMY_HASH, password)
        if not user or not ok:
            logger.info('Park login failed from %s', security.client_ip())
            return jsonify({'error': 'Invalid mobile number or password.'}), 401
        if not user['is_active']:
            return jsonify({'error': 'Your account is disabled. Contact an administrator.'}), 403

        if user.get('totp_enabled'):
            # Password is right but the session is not logged in until the second factor passes.
            session[security.SESSION_PENDING] = user['id']
            session[security.SESSION_PENDING_AT] = int(time.time())
            session[security.SESSION_PENDING_TRIES] = 0
            return jsonify({'totp_required': True}), 200

        security.start_park_session(user)
        repository.record_login(user['id'])
        return jsonify({'redirect': url_for('parking.dashboard')}), 200

    @bp.route('/login/2fa', methods=['POST'])
    @limiter.limit(rl_login)
    def login_2fa():
        if not security.csrf_valid():
            return jsonify({'error': 'Session expired. Please reload the page.'}), 403
        uid = session.get(security.SESSION_PENDING)
        started = session.get(security.SESSION_PENDING_AT, 0)
        tries = session.get(security.SESSION_PENDING_TRIES, 0)
        if not uid or time.time() - started > PENDING_2FA_SECONDS:
            security.clear_pending_2fa()
            return jsonify({'error': 'Verification expired. Please sign in again.', 'restart': True}), 401
        if tries >= MAX_2FA_TRIES:
            security.clear_pending_2fa()
            return jsonify({'error': 'Too many incorrect codes. Please sign in again.', 'restart': True}), 401
        user = repository.get_user(uid)
        if not user or not user['is_active']:
            security.clear_pending_2fa()
            return jsonify({'error': 'Your account is disabled. Contact an administrator.'}), 403
        if not _check_second_factor(uid, _payload().get('code')):
            session[security.SESSION_PENDING_TRIES] = tries + 1
            logger.info('Park 2FA failed for user %s from %s', uid, security.client_ip())
            return jsonify({'error': 'Invalid verification code.'}), 401
        security.clear_pending_2fa()
        security.start_park_session(user)
        repository.record_login(uid)
        return jsonify({'redirect': url_for('parking.dashboard')}), 200

    @bp.route('/logout', methods=['POST'])
    def logout():
        if security.csrf_valid():
            security.end_park_session()
        return redirect(url_for('parking.login'))

    # ------------------------------------------------------------------
    # Back office
    # ------------------------------------------------------------------

    @bp.route('/', methods=['GET'])
    @security.park_login_required
    def dashboard():
        user = repository.get_user(security.current_park_user_id())
        country = validators.get_country(user['country_code'])
        return render_template('park/dashboard.html', user=user, is_admin=bool(user['is_admin']),
                               ntfy_server=notifier.ntfy_server(),
                               plate_hint=country.plate_hint, mobile_hint=country.mobile_hint)

    @bp.route('/api/vehicles', methods=['GET'])
    @security.park_login_required
    @limiter.limit(rl_api)
    def vehicles_list():
        uid = security.current_park_user_id()
        return jsonify([_vehicle_json(v) for v in repository.list_vehicles(uid)])

    @bp.route('/api/vehicles', methods=['POST'])
    @security.park_login_required
    @limiter.limit(rl_api)
    def vehicles_add():
        uid = security.current_park_user_id()
        user = repository.get_user(uid)
        data = _payload()
        try:
            plate = validators.normalize_plate(data.get('plate', ''), user['country_code'])
        except ValidationError as e:
            return jsonify({'error': str(e)}), 400
        nickname = validators.clean_text(data.get('nickname'), 50)
        try:
            vid = repository.add_vehicle(uid, user['country_code'], plate, nickname)
        except DuplicateError:
            return jsonify({'error': 'You have already registered this vehicle.'}), 409
        return jsonify(_vehicle_json(repository.get_vehicle(uid, vid))), 201

    @bp.route('/api/vehicles/<int:vehicle_id>/rotate-qr', methods=['POST'])
    @security.park_login_required
    @limiter.limit(rl_api)
    def vehicles_rotate(vehicle_id):
        uid = security.current_park_user_id()
        if not repository.rotate_vehicle_qr(uid, vehicle_id):
            return jsonify({'error': 'Vehicle not found'}), 404
        logger.info('Park user %s rotated QR for vehicle %s', uid, vehicle_id)
        return jsonify(_vehicle_json(repository.get_vehicle(uid, vehicle_id)))

    @bp.route('/api/vehicles/<int:vehicle_id>/active', methods=['POST'])
    @security.park_login_required
    @limiter.limit(rl_api)
    def vehicles_active(vehicle_id):
        uid = security.current_park_user_id()
        if not repository.set_vehicle_active(uid, vehicle_id, bool(_payload().get('is_active'))):
            return jsonify({'error': 'Vehicle not found'}), 404
        return jsonify(_vehicle_json(repository.get_vehicle(uid, vehicle_id)))

    @bp.route('/api/vehicles/<int:vehicle_id>', methods=['DELETE'])
    @security.park_login_required
    @limiter.limit(rl_api)
    def vehicles_delete(vehicle_id):
        uid = security.current_park_user_id()
        if not repository.delete_vehicle(uid, vehicle_id):
            return jsonify({'error': 'Vehicle not found'}), 404
        return jsonify({'message': 'Vehicle removed'})

    def _owned_vehicle_or_404(vehicle_id):
        v = repository.get_vehicle(security.current_park_user_id(), vehicle_id)
        if not v:
            abort(404)
        return v

    @bp.route('/vehicles/<int:vehicle_id>/qr.png', methods=['GET'])
    @security.park_login_required
    def vehicle_qr_png(vehicle_id):
        v = _owned_vehicle_or_404(vehicle_id)
        url = security.public_scan_url(security.derive_qr_token(v['id'], v['qr_nonce']))
        img = qrcode.make(url, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        resp = make_response(send_file(buf, mimetype='image/png', download_name=f'park-qr-{v["id"]}.png'))
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    @bp.route('/vehicles/<int:vehicle_id>/print', methods=['GET'])
    @security.park_login_required
    def vehicle_print(vehicle_id):
        v = _owned_vehicle_or_404(vehicle_id)
        return render_template('park/print_qr.html', vehicle=v,
                               qr_png=url_for('parking.vehicle_qr_png', vehicle_id=v['id']))

    @bp.route('/api/scans', methods=['GET'])
    @security.park_login_required
    @limiter.limit(rl_api)
    def scans_list():
        uid = security.current_park_user_id()
        vehicle_id = request.args.get('vehicle_id', type=int)
        limit = min(max(request.args.get('limit', 100, type=int), 1), 500)
        offset = max(request.args.get('offset', 0, type=int), 0)
        rows = repository.list_scans(uid, vehicle_id, limit, offset)
        return jsonify([_serialize(r) for r in rows])

    @bp.route('/api/account/password', methods=['POST'])
    @security.park_login_required
    @limiter.limit(rl_password)
    def change_password():
        uid = security.current_park_user_id()
        data = _payload()
        current = data.get('current_password') or ''
        new = data.get('new_password') or ''
        if not check_password_hash(repository.get_password_hash(uid) or _DUMMY_HASH, current):
            return jsonify({'error': 'Current password is incorrect.'}), 400
        try:
            validators.validate_password(new)
        except ValidationError as e:
            return jsonify({'error': str(e)}), 400
        if new != (data.get('confirm_password') or ''):
            return jsonify({'error': 'New passwords do not match.'}), 400
        if new == current:
            return jsonify({'error': 'New password must differ from the current one.'}), 400
        repository.update_password(uid, generate_password_hash(new))
        logger.info('Park user %s changed password', uid)
        return jsonify({'message': 'Password changed.'})

    # ------------------------------------------------------------------
    # Two-factor authentication (account)
    # ------------------------------------------------------------------

    @bp.route('/api/account/2fa/setup', methods=['POST'])
    @security.park_login_required
    @limiter.limit(rl_password)
    def totp_setup():
        uid = security.current_park_user_id()
        user = repository.get_user(uid)
        if user.get('totp_enabled'):
            return jsonify({'error': 'Two-factor authentication is already enabled.'}), 409
        secret = totp.new_secret()
        session[security.SESSION_TOTP_SETUP] = secret
        uri = totp.provisioning_uri(secret, user['mobile_e164'])
        resp = jsonify({'secret': secret, 'uri': uri, 'qr': totp.qr_data_uri(uri)})
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    @bp.route('/api/account/2fa/enable', methods=['POST'])
    @security.park_login_required
    @limiter.limit(rl_password)
    def totp_enable():
        uid = security.current_park_user_id()
        secret = session.get(security.SESSION_TOTP_SETUP)
        if not secret:
            return jsonify({'error': 'Start the setup again.'}), 400
        step = totp.verify(secret, _payload().get('code'))
        if step is None:
            return jsonify({'error': 'Invalid verification code.'}), 400
        plain, stored = totp.new_recovery_codes()
        repository.enable_totp(uid, secret, stored, step)
        session.pop(security.SESSION_TOTP_SETUP, None)
        logger.info('Park user %s enabled 2FA', uid)
        resp = jsonify({'message': 'Two-factor authentication enabled.', 'recovery_codes': plain})
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    @bp.route('/api/account/2fa/disable', methods=['POST'])
    @security.park_login_required
    @limiter.limit(rl_password)
    def totp_disable():
        uid = security.current_park_user_id()
        data = _payload()
        if not check_password_hash(repository.get_password_hash(uid) or _DUMMY_HASH, data.get('password') or ''):
            return jsonify({'error': 'Current password is incorrect.'}), 400
        if not _check_second_factor(uid, data.get('code')):
            return jsonify({'error': 'Invalid verification code.'}), 400
        repository.disable_totp(uid)
        logger.info('Park user %s disabled 2FA', uid)
        return jsonify({'message': 'Two-factor authentication disabled.'})

    @bp.route('/api/account/scan-window', methods=['POST'])
    @security.park_login_required
    @limiter.limit(rl_api)
    def set_scan_window():
        raw = _payload().get('minutes')
        try:
            minutes = int(raw)
        except (TypeError, ValueError):
            minutes = 0
        lo, hi = security.MIN_SCAN_WINDOW_MINUTES, security.MAX_SCAN_WINDOW_MINUTES
        if not lo <= minutes <= hi:
            return jsonify({'error': f'Enter a whole number of minutes between {lo} and {hi}.'}), 400
        repository.set_scan_window(security.current_park_user_id(), minutes)
        return jsonify({'minutes': minutes, 'message': 'Scan time limit saved.'})

    @bp.route('/api/account/calls', methods=['POST'])
    @security.park_login_required
    @limiter.limit(rl_api)
    def set_calls():
        enabled = _payload().get('enabled') in (True, 'true', 'on', '1', 1)
        repository.set_calls_enabled(security.current_park_user_id(), enabled)
        return jsonify({'enabled': enabled,
                        'message': 'In-app calls enabled.' if enabled else 'In-app calls disabled.'})

    @bp.route('/api/account/ntfy-topic', methods=['POST'])
    @security.park_login_required
    @limiter.limit(rl_api)
    def rotate_topic():
        topic = repository.rotate_ntfy_topic(security.current_park_user_id())
        return jsonify({'ntfy_topic': topic})

    @bp.route('/api/account/test-notification', methods=['POST'])
    @security.park_login_required
    @limiter.limit('3 per minute')
    def test_notification():
        user = repository.get_user(security.current_park_user_id())
        ok = notifier.send(user['ntfy_topic'], {
            'title': '✅ Parking alerts are working',
            'message': 'This is a test notification from your parking QR back office.',
            'priority': 3, 'tags': ['white_check_mark'],
        })
        return (jsonify({'message': 'Test notification sent.'}) if ok
                else (jsonify({'error': 'Could not reach the ntfy server.'}), 502))

    # ------------------------------------------------------------------
    # Admin
    # ------------------------------------------------------------------

    @bp.route('/api/admin/users', methods=['GET'])
    @security.park_admin_required
    @limiter.limit(rl_admin)
    def admin_users():
        return jsonify([_serialize(u, drop=('ntfy_topic',)) for u in repository.list_users()])

    @bp.route('/api/admin/users', methods=['POST'])
    @security.park_admin_required
    @limiter.limit(rl_admin)
    def admin_create_user():
        data = _payload()
        try:
            country = validators.get_country(data.get('country'))
            mobile = country.normalize_mobile(data.get('mobile', ''))
            password = data.get('password') or ''
            validators.validate_password(password)
            plate = country.normalize_plate(data['plate']) if data.get('plate') else None
        except ValidationError as e:
            return jsonify({'error': str(e)}), 400
        name = validators.clean_text(data.get('full_name'), 100)
        is_admin = data.get('is_admin') in (True, 'true', 'on', '1')
        try:
            if plate:
                uid = repository.create_user_with_vehicle(name, country.code, mobile,
                                                          generate_password_hash(password), plate, is_admin)
            else:
                uid = repository.create_user(name, country.code, mobile, generate_password_hash(password),
                                             is_admin=is_admin)
        except DuplicateError:
            return jsonify({'error': 'A user with this mobile number already exists.'}), 409
        logger.info('Park admin %s created user %s', security.current_park_user_id(), uid)
        return jsonify({'message': 'User created.', 'id': uid}), 201

    @bp.route('/api/admin/vehicles', methods=['GET'])
    @security.park_admin_required
    @limiter.limit(rl_admin)
    def admin_vehicles():
        return jsonify([_serialize(v) for v in repository.list_all_vehicles()])

    @bp.route('/api/admin/users/<int:user_id>/vehicles', methods=['POST'])
    @security.park_admin_required
    @limiter.limit(rl_admin)
    def admin_add_vehicle(user_id):
        user = repository.get_user(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        data = _payload()
        try:
            plate = validators.normalize_plate(data.get('plate', ''), user['country_code'])
        except ValidationError as e:
            return jsonify({'error': str(e)}), 400
        nickname = validators.clean_text(data.get('nickname'), 50)
        try:
            vid = repository.add_vehicle(user_id, user['country_code'], plate, nickname)
        except DuplicateError:
            return jsonify({'error': 'This vehicle is already registered for that user.'}), 409
        logger.info('Park admin %s added vehicle %s for user %s', security.current_park_user_id(), vid, user_id)
        return jsonify({'message': 'Vehicle added.', 'id': vid}), 201

    @bp.route('/api/admin/users/<int:user_id>/active', methods=['POST'])
    @security.park_admin_required
    @limiter.limit(rl_admin)
    def admin_user_active(user_id):
        if user_id == security.current_park_user_id():
            return jsonify({'error': 'You cannot disable your own account.'}), 400
        if not repository.set_user_active(user_id, bool(_payload().get('is_active'))):
            return jsonify({'error': 'User not found'}), 404
        return jsonify({'message': 'Updated.'})

    @bp.route('/api/admin/users/<int:user_id>/reset-2fa', methods=['POST'])
    @security.park_admin_required
    @limiter.limit(rl_admin)
    def admin_reset_2fa(user_id):
        if not repository.get_user(user_id):
            return jsonify({'error': 'User not found'}), 404
        repository.disable_totp(user_id)
        logger.info('Park admin %s reset 2FA for user %s', security.current_park_user_id(), user_id)
        return jsonify({'message': 'Two-factor authentication reset.'})

    return bp
