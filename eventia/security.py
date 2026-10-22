import hashlib
import hmac
import secrets
import time

ROUNDS = 600_000

def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), ROUNDS).hex()
    return f'{ROUNDS}${salt}${digest}'

def verify_password(password, encoded):
    rounds, salt, digest = encoded.split('$')
    actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), int(rounds)).hex()
    return hmac.compare_digest(actual, digest)

DUMMY_HASH = hash_password('timing-placeholder-never-a-user')

class APIError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message

def require(condition, status, message):
    if not condition: raise APIError(status, message)

def fields(data, allowed, required=()):
    require(isinstance(data, dict), 400, 'Se esperaba un objeto JSON.')
    require(not set(data)-set(allowed), 400, 'La solicitud contiene propiedades no permitidas.')
    require(set(required)<=set(data), 400, 'Faltan campos obligatorios.')

def text(value, name, low=1, high=200):
    require(isinstance(value,str) and low<=len(value.strip())<=high, 400,
            f'{name}: longitud permitida de {low} a {high} caracteres.')
    return value.strip()

def rate_limit(store, key, maximum, seconds):
    now = time.time()
    # Atomic increment; shared by processes using the same database.
    with store.connect(write=True) as c:
        row = c.execute('''INSERT INTO limites(clave,intentos,inicio) VALUES(?,1,?)
          ON CONFLICT(clave) DO UPDATE SET
          intentos=CASE WHEN limites.inicio<? THEN 1 ELSE limites.intentos+1 END,
          inicio=CASE WHEN limites.inicio<? THEN ? ELSE limites.inicio END
          RETURNING intentos''', (key,now,now-seconds,now-seconds,now)).fetchone()
        count = row['intentos']
        c.execute('DELETE FROM limites WHERE inicio<?', (now-86400,))
    require(count<=maximum, 429, 'Demasiados intentos. Intenta más tarde.')
