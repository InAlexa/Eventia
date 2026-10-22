"""Regression: enable an existing account without replacing it or keeping stale sessions."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from eventia.db import Store

class ExistingAccountRoleTests(unittest.TestCase):
    def setUp(self):
        scratch=Path('data/test-runs');scratch.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=scratch)
        self.path=str((Path(self.tmp.name)/'roles.db').resolve())
        self.store=Store(path=self.path)
        with self.store.connect(write=True) as c:
            self.user=c.execute('INSERT INTO usuarios(nombre,correo,password_hash) VALUES(?,?,?) RETURNING id',
                ('Cuenta existente','existente@test.local','hash-conservado')).fetchone()['id']
            c.execute('INSERT INTO sesiones VALUES(?,?,?,?)',('sesion-anterior',self.user,'csrf',9999999999))

    def tearDown(self): self.tmp.cleanup()

    def command(self,email):
        env={**os.environ,'EVENTIA_DB':self.path};env.pop('DATABASE_URL',None)
        return subprocess.run([sys.executable,'manage.py','set-role','--correo',email,'--rol','organizador'],
            capture_output=True,text=True,env=env)

    def test_existing_account_preserved_and_sessions_revoked(self):
        result=self.command(' EXISTENTE@test.local ')
        self.assertEqual(result.returncode,0,result.stderr)
        with self.store.connect() as c:
            rows=c.execute('SELECT * FROM usuarios').fetchall()
            sessions=c.execute('SELECT * FROM sesiones').fetchall()
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['id'],self.user)
        self.assertEqual(rows[0]['password_hash'],'hash-conservado')
        self.assertEqual(rows[0]['rol'],'organizador');self.assertEqual(len(sessions),0)

    def test_unknown_email_does_not_create_account(self):
        result=self.command('desconocido@test.local')
        self.assertEqual(result.returncode,2)
        with self.store.connect() as c:
            rows=c.execute('SELECT * FROM usuarios').fetchall()
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['rol'],'usuario')
