import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = '''
CREATE TABLE IF NOT EXISTS usuarios (
 id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, correo TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL, rol TEXT NOT NULL DEFAULT 'usuario'
 CHECK(rol IN ('usuario','organizador','administrador')));
CREATE TABLE IF NOT EXISTS eventos (
 id INTEGER PRIMARY KEY, titulo TEXT NOT NULL, descripcion TEXT NOT NULL,
 fecha TEXT NOT NULL, ubicacion TEXT NOT NULL, categoria TEXT NOT NULL,
 cupo INTEGER NOT NULL CHECK(cupo>0), disponibles INTEGER NOT NULL CHECK(disponibles>=0 AND disponibles<=cupo),
 precio INTEGER NOT NULL DEFAULT 0 CHECK(precio=0), organizador_id INTEGER NOT NULL REFERENCES usuarios(id),
 estado TEXT NOT NULL DEFAULT 'activo' CHECK(estado IN ('activo','cancelado')));
CREATE TABLE IF NOT EXISTS inscripciones (
 id INTEGER PRIMARY KEY, evento_id INTEGER NOT NULL REFERENCES eventos(id),
 usuario_id INTEGER NOT NULL REFERENCES usuarios(id), fecha TEXT NOT NULL,
 UNIQUE(evento_id,usuario_id));
CREATE TABLE IF NOT EXISTS sesiones (
 token TEXT PRIMARY KEY, usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
 csrf TEXT NOT NULL, expira REAL NOT NULL);
CREATE TABLE IF NOT EXISTS limites (clave TEXT PRIMARY KEY, intentos INTEGER NOT NULL, inicio REAL NOT NULL);
CREATE TABLE IF NOT EXISTS notificaciones (
 id INTEGER PRIMARY KEY, inscripcion_id INTEGER NOT NULL UNIQUE REFERENCES inscripciones(id),
 destino TEXT NOT NULL, asunto TEXT NOT NULL, mensaje TEXT NOT NULL,
 estado TEXT NOT NULL DEFAULT 'pendiente', intentos INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_eventos_fecha ON eventos(estado,fecha);
CREATE INDEX IF NOT EXISTS idx_inscripciones_usuario ON inscripciones(usuario_id);
'''

class Store:
    def __init__(self, path=None, url=None):
        self.url = url or os.getenv('DATABASE_URL')
        self.path = path or os.getenv('EVENTIA_DB', 'data/eventia.db')
        if not self.url:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            schema = SCHEMA
            if self.url:
                schema = schema.replace('id INTEGER PRIMARY KEY', 'id SERIAL PRIMARY KEY')
                for statement in schema.split(';'):
                    if statement.strip(): c.execute(statement)
            else:
                c.executescript(schema)

    @contextmanager
    def connect(self, write=False):
        if self.url:
            import psycopg
            from psycopg.rows import dict_row
            c = psycopg.connect(self.url, row_factory=dict_row)
            wrapper = Postgres(c)
        else:
            c = sqlite3.connect(self.path, timeout=20)
            c.row_factory = sqlite3.Row
            c.execute('PRAGMA foreign_keys=ON')
            c.execute('PRAGMA journal_mode=WAL')
            if write: c.execute('BEGIN IMMEDIATE')
            wrapper = c
        try:
            yield wrapper
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def lock_event(self, c, event_id):
        sql = 'SELECT * FROM eventos WHERE id=?'
        if self.url: sql += ' FOR UPDATE'
        return c.execute(sql, (event_id,)).fetchone()

class Postgres:
    def __init__(self, connection): self.connection = connection
    def execute(self, sql, params=()):
        return self.connection.execute(sql.replace('?', '%s'), params)
