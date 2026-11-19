"""Minimal WebAuthn (passkey) relying party for the UZ801 dashboard.

Registration uses attestation "none" (we trust the authenticator the owner chooses);
assertions are verified with the stored COSE public key (ES256, EdDSA or RS256) using
the `cryptography` package. Store: /etc/uz/passkeys.json (0600).
"""
import base64, hashlib, json, os, secrets, struct, threading, time

STORE = '/etc/uz/passkeys.json'
CHALLENGE_TTL = 120
SESSION_TTL = 24 * 3600
_lock = threading.Lock()
_challenges = {}      # challenge(b64url) -> (kind, rp_id, expires)
_sessions = {}        # token -> expires


def b64u(b): return base64.urlsafe_b64encode(b).rstrip(b'=').decode()
def ub64u(s): s = str(s); return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


# ---------- minimal CBOR decoder (enough for attestationObject / COSE keys) ----------
def _cbor(b, i=0):
    ib = b[i]; mt, ai = ib >> 5, ib & 31; i += 1
    if ai < 24: val = ai
    elif ai == 24: val = b[i]; i += 1
    elif ai == 25: val = struct.unpack('>H', b[i:i + 2])[0]; i += 2
    elif ai == 26: val = struct.unpack('>I', b[i:i + 4])[0]; i += 4
    elif ai == 27: val = struct.unpack('>Q', b[i:i + 8])[0]; i += 8
    else: raise ValueError('indefinite CBOR not supported')
    if mt == 0: return val, i
    if mt == 1: return -1 - val, i
    if mt == 2: return bytes(b[i:i + val]), i + val
    if mt == 3: return b[i:i + val].decode(), i + val
    if mt == 4:
        out = []
        for _ in range(val): v, i = _cbor(b, i); out.append(v)
        return out, i
    if mt == 5:
        out = {}
        for _ in range(val):
            k, i = _cbor(b, i); v, i = _cbor(b, i); out[k] = v
        return out, i
    if mt == 7: return {20: False, 21: True, 22: None}.get(val), i
    raise ValueError('unsupported CBOR type')


def cbor_loads(b): return _cbor(b, 0)[0]


def _parse_auth_data(ad):
    rp_hash, flags, count = ad[:32], ad[32], struct.unpack('>I', ad[33:37])[0]
    out = {'rp_hash': rp_hash, 'up': bool(flags & 1), 'uv': bool(flags & 4), 'count': count}
    if flags & 0x40:  # attested credential data
        cl = struct.unpack('>H', ad[53:55])[0]
        out['cred_id'] = ad[55:55 + cl]
        key, _ = _cbor(ad, 55 + cl)
        out['cose'] = key
    return out


def _public_key(cose):
    from cryptography.hazmat.primitives.asymmetric import ec, rsa, ed25519
    kty, alg = cose.get(1), cose.get(3)
    if kty == 2 and alg == -7:   # EC2 P-256 / ES256
        x, y = int.from_bytes(cose[-2], 'big'), int.from_bytes(cose[-3], 'big')
        return 'es256', ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()
    if kty == 1 and alg == -8:   # OKP Ed25519
        return 'eddsa', ed25519.Ed25519PublicKey.from_public_bytes(cose[-2])
    if kty == 3 and alg == -257:  # RSA PKCS1v15 SHA-256
        n, e = int.from_bytes(cose[-1], 'big'), int.from_bytes(cose[-2], 'big')
        return 'rs256', rsa.RSAPublicNumbers(e, n).public_key()
    raise ValueError(f'unsupported key type kty={kty} alg={alg}')


def _verify(kind, key, sig, data):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, padding
    if kind == 'es256': key.verify(sig, data, ec.ECDSA(hashes.SHA256()))
    elif kind == 'eddsa': key.verify(sig, data)
    else: key.verify(sig, data, padding.PKCS1v15(), hashes.SHA256())


# ---------- store ----------
def load():
    try: return json.load(open(STORE))
    except Exception: return []


def save(creds):
    tmp = STORE + '.tmp'
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f: json.dump(creds, f)
    os.replace(tmp, STORE)


def enabled(): return bool(load())


def public_list():
    return [{'id': c['id'], 'name': c.get('name', ''), 'rp': c['rp'], 'created': c.get('created'), 'last_used': c.get('last_used')}
            for c in load()]


# ---------- challenges / sessions ----------
def _new_challenge(kind, rp_id):
    ch = b64u(secrets.token_bytes(32))
    with _lock:
        now = time.time()
        for k in [k for k, v in _challenges.items() if v[2] < now]: _challenges.pop(k, None)
        _challenges[ch] = (kind, rp_id, now + CHALLENGE_TTL)
    return ch


def _take_challenge(ch, kind, rp_id):
    with _lock: v = _challenges.pop(ch, None)
    if not v or v[0] != kind or v[1] != rp_id or v[2] < time.time(): raise ValueError('challenge expired or invalid')


def new_session():
    tok = secrets.token_urlsafe(32)
    with _lock:
        now = time.time()
        for k in [k for k, e in _sessions.items() if e < now]: _sessions.pop(k, None)
        _sessions[tok] = now + SESSION_TTL
    return tok


def session_ok(tok):
    with _lock: e = _sessions.get(tok or '')
    return bool(e and e > time.time())


def end_session(tok):
    with _lock: _sessions.pop(tok or '', None)


def end_all_sessions():
    with _lock: _sessions.clear()


# ---------- ceremonies ----------
def _client_data(cdj_b64, kind, rp_id):
    raw = ub64u(cdj_b64); cd = json.loads(raw)
    if cd.get('type') != kind: raise ValueError('wrong ceremony type')
    if cd.get('origin') != f'https://{rp_id}': raise ValueError('origin mismatch')
    _take_challenge(cd.get('challenge'), kind, rp_id)
    return raw


def register_begin(rp_id, user_name):
    creds = load()
    return {'challenge': _new_challenge('webauthn.create', rp_id),
            'rp': {'id': rp_id, 'name': 'UZ801'},
            'user': {'id': b64u(hashlib.sha256(('uz801:' + rp_id).encode()).digest()[:16]), 'name': user_name or 'owner', 'displayName': user_name or 'UZ801 owner'},
            'pubKeyCredParams': [{'type': 'public-key', 'alg': -7}, {'type': 'public-key', 'alg': -8}, {'type': 'public-key', 'alg': -257}],
            'excludeCredentials': [{'type': 'public-key', 'id': c['id']} for c in creds if c['rp'] == rp_id],
            'authenticatorSelection': {'residentKey': 'required', 'userVerification': 'required'},
            'attestation': 'none', 'timeout': CHALLENGE_TTL * 1000}


def register_finish(rp_id, body):
    raw_cd = _client_data(body['clientDataJSON'], 'webauthn.create', rp_id)
    att = cbor_loads(ub64u(body['attestationObject']))
    ad = _parse_auth_data(att['authData'])
    if ad['rp_hash'] != hashlib.sha256(rp_id.encode()).digest(): raise ValueError('rpId hash mismatch')
    if not (ad['up'] and ad['uv']): raise ValueError('user verification required')
    if 'cose' not in ad: raise ValueError('no credential data')
    _public_key(ad['cose'])  # validates the key type
    entry = {'id': b64u(ad['cred_id']), 'rp': rp_id, 'name': (str(body.get('name') or 'Passkey'))[:40],
             'cose': {str(k): (b64u(v) if isinstance(v, bytes) else v) for k, v in ad['cose'].items()},
             'count': ad['count'], 'created': int(time.time()), 'last_used': None}
    with _lock:
        creds = load()
        if any(c['id'] == entry['id'] for c in creds): raise ValueError('passkey already registered')
        creds.append(entry); save(creds)
    return entry['id']


def login_begin(rp_id):
    ids = [c['id'] for c in load() if c['rp'] == rp_id]
    if not ids: raise ValueError('no passkey registered for this address')
    return {'challenge': _new_challenge('webauthn.get', rp_id), 'rpId': rp_id,
            'allowCredentials': [{'type': 'public-key', 'id': i} for i in ids],
            'userVerification': 'required', 'timeout': CHALLENGE_TTL * 1000}


def login_finish(rp_id, body):
    raw_cd = _client_data(body['clientDataJSON'], 'webauthn.get', rp_id)
    ad_raw = ub64u(body['authenticatorData'])
    ad = _parse_auth_data(ad_raw)
    if ad['rp_hash'] != hashlib.sha256(rp_id.encode()).digest(): raise ValueError('rpId hash mismatch')
    if not (ad['up'] and ad['uv']): raise ValueError('user verification required')
    with _lock:
        creds = load()
        c = next((c for c in creds if c['id'] == body.get('id') and c['rp'] == rp_id), None)
        if not c: raise ValueError('unknown passkey')
        cose = {int(k): (ub64u(v) if isinstance(v, str) else v) for k, v in c['cose'].items()}
        kind, key = _public_key(cose)
        _verify(kind, key, ub64u(body['signature']), ad_raw + hashlib.sha256(raw_cd).digest())
        if ad['count'] and c.get('count') and ad['count'] <= c['count']: raise ValueError('signature counter regressed (cloned key?)')
        c['count'] = ad['count']; c['last_used'] = int(time.time()); save(creds)
    return new_session()


def delete(cred_id):
    with _lock:
        creds = load(); keep = [c for c in creds if c['id'] != cred_id]
        if len(keep) == len(creds): raise ValueError('no such passkey')
        save(keep)
    if not keep: end_all_sessions()
    return len(keep)


def reset():
    with _lock: save([])
    end_all_sessions()
