import hmac
import json
import mimetypes
import os
import re
import secrets
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from .security import APIError, require, fields
from .service import Service, public_user, session_user

ROOT=Path(__file__).resolve().parent.parent

def make_handler(store):
    service=Service(store)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # Avoid logging query strings, credentials, or personal data.
            pass

        def respond(self,status,data,headers=None,content_type='application/json; charset=utf-8'):
            body=json.dumps(data,ensure_ascii=False).encode() if content_type.startswith('application/json') else data
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','same-origin')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if os.getenv('COOKIE_SECURE')=='1': self.send_header('Strict-Transport-Security','max-age=31536000')
            for k,v in (headers or {}).items(): self.send_header(k,v)
            self.end_headers()
            self.wfile.write(body)

        def cookie(self,token,age=28800):
            secure='; Secure' if os.getenv('COOKIE_SECURE')=='1' else ''
            return f'eventia_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={age}{secure}'

        def body(self):
            require(self.headers.get_content_type()=='application/json',415,'Usa Content-Type application/json.')
            try: size=int(self.headers.get('Content-Length','0'))
            except ValueError: raise APIError(400,'Longitud inválida.')
            require(0<size<=16384,413,'El cuerpo debe ocupar entre 1 y 16384 bytes.')
            try: data=json.loads(self.rfile.read(size))
            except (ValueError,UnicodeDecodeError): raise APIError(400,'JSON inválido.')
            require(isinstance(data,dict),400,'Se esperaba un objeto JSON.')
            return data

        def run_request(self):
            try:
                parsed=urlsplit(self.path)
                path=parsed.path
                method=self.command
                if method=='GET' and not path.startswith('/api/'):
                    known={'/':'index.html','/app.js':'app.js','/styles.css':'styles.css'}
                    if path=='/healthz':
                        return self.respond(200,{'status':'ok'})
                    if path=='/openapi.json':
                        return self.respond(200,(ROOT/'docs/openapi.json').read_bytes(),content_type='application/octet-stream')
                    require(path in known,404,'Página no encontrada.')
                    file=ROOT/'public'/known[path]
                    return self.respond(200,file.read_bytes(),content_type=mimetypes.guess_type(file.name)[0]+'; charset=utf-8')
                cookie=SimpleCookie()
                try: cookie.load(self.headers.get('Cookie',''))
                except Exception: raise APIError(400,'Cookie inválida.')
                token=cookie['eventia_session'].value if 'eventia_session' in cookie else None
                user=service.authenticate(token)
                if method in ('POST','PUT','PATCH','DELETE'):
                    expected=os.getenv('EVENTIA_ORIGIN',f'http://127.0.0.1:{self.server.server_port}')
                    origin=self.headers.get('Origin')
                    require(origin is None or origin==expected,403,'Origen no permitido.')
                    require(self.headers.get('Sec-Fetch-Site')!='cross-site',403,'Solicitud entre sitios rechazada.')
                    # Login is the only state-changing endpoint that may be called
                    # with an existing session, so protect it against login-CSRF too.
                    if user:
                        require(hmac.compare_digest(self.headers.get('X-CSRF-Token',''),user['csrf']),403,'Token CSRF inválido.')
                ip=self.client_address[0]  # Never trust client-controlled X-Forwarded-For.
                if method=='POST' and path=='/api/usuarios':
                    return self.respond(201,service.register(self.body(),ip))
                if method=='POST' and path=='/api/auth/login':
                    fresh,csrf,info=service.login(self.body(),ip)
                    if token:
                        with store.connect(write=True) as c: c.execute('DELETE FROM sesiones WHERE token=?',(token,))
                    return self.respond(200,{'usuario':info,'csrf':csrf},{'Set-Cookie':self.cookie(fresh)})
                if method=='GET' and path=='/api/auth/me':
                    return self.respond(200,{'usuario':session_user(user) if user else None,'csrf':user['csrf'] if user else None})
                if method=='GET' and path=='/api/eventos':
                    return self.respond(200,service.events(parse_qs(parsed.query)))
                match=re.fullmatch(r'/api/eventos/(\d+)',path)
                if method=='GET' and match: return self.respond(200,service.event(int(match[1])))
                require(user is not None,401,'Inicia sesión para continuar.')
                if method=='POST' and path=='/api/auth/logout':
                    with store.connect(write=True) as c: c.execute('DELETE FROM sesiones WHERE token=?',(token,))
                    return self.respond(200,{'mensaje':'Sesión cerrada.'},{'Set-Cookie':self.cookie('',0)})
                if method=='GET' and path=='/api/inscripciones': return self.respond(200,service.mine(user))
                if method=='GET' and path=='/api/mis-eventos': return self.respond(200,service.managed(user))
                if method=='POST' and path=='/api/eventos': return self.respond(201,service.save_event(user,self.body()))
                if method=='PUT' and match: return self.respond(200,service.save_event(user,self.body(),int(match[1])))
                match=re.fullmatch(r'/api/eventos/(\d+)/inscripciones',path)
                if match and method=='POST': return self.respond(201,service.enroll(user,int(match[1]),self.body()))
                if match and method=='GET': return self.respond(200,service.attendees(user,int(match[1])))
                match=re.fullmatch(r'/api/inscripciones/(\d+)',path)
                if match and method=='GET': return self.respond(200,service.registration(user,int(match[1])))
                match=re.fullmatch(r'/api/usuarios/(\d+)',path)
                if match and method=='GET':
                    require(user['id']==int(match[1]) or user['rol']=='administrador',403,'Acceso restringido.')
                    with store.connect() as c: row=c.execute('SELECT id,nombre,correo FROM usuarios WHERE id=?',(int(match[1]),)).fetchone()
                    require(row is not None,404,'Usuario no encontrado.')
                    return self.respond(200,public_user(row))
                if method=='GET' and path=='/api/admin/usuarios':
                    require(user['rol']=='administrador',403,'Acceso restringido.')
                    with store.connect() as c: rows=c.execute('SELECT id,nombre,correo,rol FROM usuarios ORDER BY id LIMIT 100').fetchall()
                    return self.respond(200,[dict(r) for r in rows])
                match=re.fullmatch(r'/api/admin/usuarios/(\d+)/rol',path)
                if method=='PATCH' and match:
                    require(user['rol']=='administrador',403,'Acceso restringido.')
                    d=self.body(); fields(d,('rol',),('rol',))
                    require(isinstance(d['rol'],str) and d['rol'] in ('usuario','organizador','administrador'),400,'Rol inválido.')
                    require(user['id']!=int(match[1]),409,'No puedes cambiar tu propio rol.')
                    with store.connect(write=True) as c:
                        row=c.execute('UPDATE usuarios SET rol=? WHERE id=? RETURNING id,nombre,correo,rol',(d['rol'],int(match[1]))).fetchone()
                        require(row is not None,404,'Usuario no encontrado.')
                        c.execute('DELETE FROM sesiones WHERE usuario_id=?',(int(match[1]),))
                    return self.respond(200,dict(row))
                raise APIError(404,'Ruta no encontrada.')
            except APIError as e:
                headers={'Retry-After':'900'} if e.status==429 else None
                self.respond(e.status,{'error':e.message},headers)
            except Exception:
                incident=secrets.token_hex(6)
                print(f'Error interno. Referencia {incident}',flush=True)
                self.respond(500,{'error':'Error interno. Intenta nuevamente.','referencia':incident})

        do_GET=run_request
        do_POST=run_request
        do_PUT=run_request
        do_PATCH=run_request
        do_DELETE=run_request
    return Handler

def serve(store,host='127.0.0.1',port=8000):
    server=ThreadingHTTPServer((host,port),make_handler(store))
    print(f'Eventia: http://{host}:{port}',flush=True)
    server.serve_forever()
