import concurrent.futures
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from eventia.db import Store
from eventia.server import make_handler
from eventia.service import Service
from eventia.security import APIError, hash_password

class SecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch=Path('data/test-runs');scratch.mkdir(parents=True,exist_ok=True)
        cls.tmp=tempfile.TemporaryDirectory(dir=scratch)
        cls.store=Store(path=os.path.join(cls.tmp.name,'test.db'),url=os.getenv('TEST_DATABASE_URL'))
        cls.service=Service(cls.store)
        cls.password='Eventia-pruebas-2026!'
        encoded=hash_password(cls.password)
        with cls.store.connect(write=True) as c:
            for name,role in [('Ana','usuario'),('Luis','usuario'),('Org','organizador'),('Otra','organizador'),('Admin','administrador')]:
                c.execute('INSERT INTO usuarios(nombre,correo,password_hash,rol) VALUES(?,?,?,?)',
                    (name,name.lower()+'@test.local',encoded,role))
            cls.users={r['nombre']:dict(r) for r in c.execute('SELECT * FROM usuarios').fetchall()}
        # Run requests through the real HTTP handler without opening a socket.
        # This keeps the suite usable in locked-down Windows/sandbox environments.
        cls.handler=make_handler(cls.store)
        cls.server=SimpleNamespace(server_port=8000)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def event(self,**kw):
        d=dict(titulo='Encuentro de prueba',descripcion='Descripción de prueba',ubicacion='Xela',categoria='Comunidad',
               fecha=(datetime.now(timezone.utc)+timedelta(days=5)).isoformat(),cupo=10,precio=0)
        d.update(kw);return d

    def create(self,**kw): return self.service.save_event(self.users['Org'],self.event(**kw))

    def error(self,status,fn,*args):
        with self.assertRaises(APIError) as caught: fn(*args)
        self.assertEqual(caught.exception.status,status)

    def request(self,method,path,data=None,token=None,csrf=None,origin=None):
        headers={'Host':'127.0.0.1:8000'}
        if data is not None: headers['Content-Type']='application/json'
        if data is not None: headers['Content-Length']=str(len(json.dumps(data).encode()))
        if token: headers['Cookie']='eventia_session='+token
        if csrf: headers['X-CSRF-Token']=csrf
        if origin: headers['Origin']=origin
        body=json.dumps(data).encode() if data is not None else b''
        request=io.BytesIO((f'{method} {path} HTTP/1.1\r\n'+'\r\n'.join(f'{k}: {v}' for k,v in headers.items())+'\r\n\r\n').encode()+body)
        output=io.BytesIO()
        handler=self.handler.__new__(self.handler)
        handler.server=self.server;handler.client_address=('127.0.0.1',12345)
        handler.request_version='HTTP/1.1';handler.command=method;handler.path=path
        handler.rfile=request;handler.wfile=output
        # BaseHTTPRequestHandler parses its request line/headers in __init__, so
        # provide the in-memory streams before invoking it via a tiny socket shim.
        class MemorySocket:
            def makefile(self,mode,*args,**kwargs): return request if 'r' in mode else output
            def sendall(self,data): output.write(data)
            def close(self): pass
        try: self.handler(MemorySocket(),('127.0.0.1',12345),self.server)
        except Exception as exc:
            raise AssertionError(f'In-memory HTTP handler failed: {exc}') from exc
        response=output.getvalue().split(b'\r\n\r\n',1)
        status_line=response[0].split(b'\r\n',1)[0].decode()
        status=int(status_line.split()[1]);header_lines=response[0].decode().split('\r\n')[1:]
        response_headers={}
        for line in header_lines:
            if ':' in line:
                key,value=line.split(':',1);response_headers[key.strip()]=value.strip()
        payload=response[1] if len(response)>1 else b''
        parsed=json.loads(payload) if 'application/json' in response_headers.get('Content-Type','') else payload
        return status,parsed,response_headers

    def session(self,name='Ana'):
        return self.service.login(dict(correo=name.lower()+'@test.local',password=self.password),'test-'+name)

    def test_01_public_catalog_and_parameterized_search(self):
        self.create()
        self.assertEqual(self.request('GET','/api/eventos')[0],200)
        status,rows,_=self.request('GET','/api/eventos?q=%27%20OR%201%3D1--')
        self.assertEqual(status,200);self.assertEqual(rows,[])

    def test_02_register_rejects_role(self):
        d=dict(nombre='Intruso',correo='intruso@test.local',password=self.password,tipo_cuenta='administrador')
        self.assertEqual(self.request('POST','/api/usuarios',d)[0],400)

    def test_03_valid_registration_is_unprivileged_and_hashed(self):
        status,data,_=self.request('POST','/api/usuarios',dict(nombre='Nueva',correo='nueva@test.local',password=self.password,tipo_cuenta='asistente'))
        self.assertEqual(status,201);self.assertEqual(set(data),{'id','nombre','correo'})
        with self.store.connect() as c: row=c.execute('SELECT * FROM usuarios WHERE id=?',(data['id'],)).fetchone()
        self.assertEqual(row['rol'],'usuario');self.assertNotEqual(row['password_hash'],self.password)

    def test_32_registration_choice_grants_only_the_selected_non_admin_role(self):
        for kind,expected,email in [('organizador','organizador','creadora@test.local'),('asistente','usuario','asistente2@test.local')]:
            status,data,_=self.request('POST','/api/usuarios',dict(nombre='Nueva Cuenta',correo=email,password=self.password,tipo_cuenta=kind))
            self.assertEqual(status,201)
            with self.store.connect() as c: row=c.execute('SELECT rol FROM usuarios WHERE id=?',(data['id'],)).fetchone()
            self.assertEqual(row['rol'],expected)
            self.assertNotEqual(row['rol'],'administrador')

    def test_registration_requires_account_type(self):
        d=dict(nombre='Sin Tipo',correo='sintipo@test.local',password=self.password)
        self.assertEqual(self.request('POST','/api/usuarios',d)[0],400)

    def test_04_invalid_password(self):
        self.assertEqual(self.request('POST','/api/usuarios',dict(nombre='Ana',correo='x@test.local',password='123456'))[0],400)

    def test_05_login_generic_error(self):
        a=self.request('POST','/api/auth/login',dict(correo='ana@test.local',password='wrong-password'))
        b=self.request('POST','/api/auth/login',dict(correo='ausente@test.local',password='wrong-password'))
        self.assertEqual(a[:2],b[:2]);self.assertEqual(a[0],401)

    def test_06_login_rate_limit(self):
        codes=[self.request('POST','/api/auth/login',dict(correo='limit@test.local',password='invalid-password'))[0] for _ in range(9)]
        self.assertEqual(codes[:8],[401]*8);self.assertEqual(codes[8],429)

    def test_07_cookie_and_no_secret_leak(self):
        status,data,headers=self.request('POST','/api/auth/login',dict(correo='ana@test.local',password=self.password))
        self.assertEqual(status,200);self.assertIn('HttpOnly',headers['Set-Cookie']);self.assertIn('SameSite=Strict',headers['Set-Cookie'])
        self.assertNotIn('password_hash',json.dumps(data));self.assertIn('csrf',data)

    def test_08_auth_required(self):
        self.assertEqual(self.request('POST','/api/eventos',self.event())[0],401)

    def test_09_user_cannot_create_event(self):
        self.error(403,self.service.save_event,self.users['Ana'],self.event())

    def test_10_negative_and_noninteger_capacity(self):
        for value in [-50,0,1.5,True,'10']:
            self.error(400,self.service.save_event,self.users['Org'],self.event(cupo=value))

    def test_11_prices_rejected(self):
        for value in [-100,50,True]: self.error(400,self.service.save_event,self.users['Org'],self.event(precio=value))

    def test_12_organizer_creates_own_event(self):
        event=self.create();self.assertEqual(event['organizador_id'],self.users['Org']['id']);self.assertEqual(event['disponibles'],10)

    def test_13_other_organizer_cannot_edit(self):
        e=self.create();self.error(403,self.service.save_event,self.users['Otra'],self.event(titulo='Secuestrado'),e['id'])
        self.assertNotEqual(self.service.event(e['id'])['titulo'],'Secuestrado')

    def test_14_owner_can_edit(self):
        e=self.create();r=self.service.save_event(self.users['Org'],self.event(titulo='Actualizado'),e['id']);self.assertEqual(r['titulo'],'Actualizado')

    def test_15_successful_enrollment_and_outbox(self):
        e=self.create();r=self.service.enroll(self.users['Ana'],e['id'],{'cantidad':1});self.assertEqual(r['disponibles'],9)
        with self.store.connect() as c: n=c.execute('SELECT * FROM notificaciones WHERE inscripcion_id=?',(r['id'],)).fetchone()
        self.assertEqual(n['estado'],'pendiente')

    def test_16_duplicate_does_not_consume_capacity(self):
        e=self.create();self.service.enroll(self.users['Ana'],e['id'],{'cantidad':1})
        self.error(409,self.service.enroll,self.users['Ana'],e['id'],{'cantidad':1})
        self.assertEqual(self.service.event(e['id'])['disponibles'],9)

    def test_17_bulk_rejected(self):
        e=self.create();self.error(400,self.service.enroll,self.users['Ana'],e['id'],{'cantidad':500})

    def test_18_registration_object_authorization(self):
        e=self.create();r=self.service.enroll(self.users['Ana'],e['id'],{'cantidad':1})
        self.assertEqual(self.service.registration(self.users['Ana'],r['id'])['id'],r['id'])
        self.error(403,self.service.registration,self.users['Luis'],r['id'])
        self.error(403,self.service.registration,self.users['Otra'],r['id'])
        self.assertEqual(self.service.registration(self.users['Org'],r['id'])['id'],r['id'])

    def test_19_attendee_list_restricted(self):
        e=self.create();self.error(403,self.service.attendees,self.users['Otra'],e['id'])
        self.error(403,self.service.attendees,self.users['Ana'],e['id'])

    def test_20_profile_only_name_email_id(self):
        token,csrf,_=self.session()
        status,data,_=self.request('GET',f"/api/usuarios/{self.users['Ana']['id']}",token=token)
        self.assertEqual(status,200);self.assertEqual(set(data),{'id','nombre','correo'})
        self.assertEqual(self.request('GET',f"/api/usuarios/{self.users['Luis']['id']}",token=token)[0],403)

    def test_21_csrf_and_origin(self):
        token,csrf,_=self.session('Org')
        self.assertEqual(self.request('POST','/api/eventos',self.event(),token=token)[0],403)
        self.assertEqual(self.request('POST','/api/eventos',self.event(),token=token,csrf=csrf,origin='https://evil.example')[0],403)
        self.assertEqual(self.request('POST','/api/eventos',self.event(),token=token,csrf=csrf)[0],201)

    def test_22_concurrency_last_seat(self):
        e=self.create(cupo=1)
        def reserve(name):
            try: self.service.enroll(self.users[name],e['id'],{'cantidad':1});return 201
            except APIError as error: return error.status
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: codes=list(pool.map(reserve,['Ana','Luis']))
        self.assertEqual(sorted(codes),[201,409]);self.assertEqual(self.service.event(e['id'])['disponibles'],0)
        with self.store.connect() as c: count=c.execute('SELECT COUNT(*) AS n FROM inscripciones WHERE evento_id=?',(e['id'],)).fetchone()['n']
        self.assertEqual(count,1)

    def test_23_cannot_reduce_below_occupied(self):
        e=self.create();self.service.enroll(self.users['Ana'],e['id'],{'cantidad':1});self.service.enroll(self.users['Luis'],e['id'],{'cantidad':1})
        self.error(409,self.service.save_event,self.users['Org'],self.event(cupo=1),e['id'])

    def test_24_unknown_properties_and_dates(self):
        self.error(400,self.service.save_event,self.users['Org'],self.event(organizador_id=99))
        self.error(400,self.service.save_event,self.users['Org'],self.event(fecha='2020-01-01T12:00:00+00:00'))

    def test_25_logout_invalidates_session(self):
        token,csrf,_=self.session('Luis')
        self.assertEqual(self.request('POST','/api/auth/logout',{},token=token,csrf=csrf)[0],200)
        self.assertEqual(self.request('GET','/api/inscripciones',token=token)[0],401)

    def test_26_security_headers_and_static(self):
        status,body,headers=self.request('GET','/')
        self.assertEqual(status,200);self.assertIn(b'Eventia',body);self.assertIn("frame-ancestors 'none'",headers.get('Content-Security-Policy',''))

    def test_27_admin_only_role_change(self):
        token,csrf,_=self.session('Ana')
        path=f"/api/admin/usuarios/{self.users['Luis']['id']}/rol"
        self.assertEqual(self.request('PATCH',path,{'rol':'organizador'},token=token,csrf=csrf)[0],403)
        admin,csrf,_=self.session('Admin');victim,_,_=self.session('Luis')
        self.assertEqual(self.request('PATCH',path,{'rol':'organizador'},token=admin,csrf=csrf)[0],200)
        self.assertIsNone(self.service.authenticate(victim))

    def test_29_login_with_existing_session_requires_csrf(self):
        token,csrf,_=self.session('Ana')
        credentials=dict(correo='luis@test.local',password=self.password)
        self.assertEqual(self.request('POST','/api/auth/login',credentials,token=token)[0],403)
        status,_,headers=self.request('POST','/api/auth/login',credentials,token=token,csrf=csrf)
        self.assertEqual(status,200)
        self.assertIsNone(self.service.authenticate(token))
        self.assertIn('eventia_session=',headers['Set-Cookie'])

    def test_30_admin_cannot_change_own_role_or_assign_invalid_role(self):
        admin,csrf,_=self.session('Admin')
        path=f"/api/admin/usuarios/{self.users['Admin']['id']}/rol"
        self.assertEqual(self.request('PATCH',path,{'rol':'usuario'},token=admin,csrf=csrf)[0],409)
        path=f"/api/admin/usuarios/{self.users['Ana']['id']}/rol"
        self.assertEqual(self.request('PATCH',path,{'rol':'superadmin'},token=admin,csrf=csrf)[0],400)

    def test_31_role_change_revokes_old_sessions_and_updates_permissions(self):
        admin,csrf,_=self.session('Admin')
        user_token,_,_=self.session('Luis')
        path=f"/api/admin/usuarios/{self.users['Luis']['id']}/rol"
        self.assertEqual(self.request('PATCH',path,{'rol':'organizador'},token=admin,csrf=csrf)[0],200)
        self.assertEqual(self.request('POST','/api/eventos',self.event(),token=user_token,csrf='stale')[0],401)
        fresh,_,_=self.session('Luis')
        self.assertEqual(self.request('POST','/api/eventos',self.event(),token=fresh,csrf='invalid')[0],403)

    def test_28_hsts_and_secure_cookie_in_https_mode(self):
        before=os.environ.get('COOKIE_SECURE');os.environ['COOKIE_SECURE']='1'
        try:
            status,data,headers=self.request('POST','/api/auth/login',dict(correo='org@test.local',password=self.password))
            self.assertEqual(status,200);self.assertIn('; Secure',headers['Set-Cookie']);self.assertIn('Strict-Transport-Security',headers)
        finally:
            if before is None: os.environ.pop('COOKIE_SECURE',None)
            else: os.environ['COOKIE_SECURE']=before

if __name__=='__main__': unittest.main(verbosity=2)
