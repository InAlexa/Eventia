import re
import secrets
import time
from datetime import datetime, timezone
from .security import APIError, require, fields, text, hash_password, verify_password, DUMMY_HASH, rate_limit

def now_iso(): return datetime.now(timezone.utc).isoformat()

def public_user(row):
    return {k:row[k] for k in ('id','nombre','correo')}

def session_user(row): return {**public_user(row), 'rol':row['rol']}

class Service:
    def __init__(self, store): self.store=store

    def register(self, data, ip):
        rate_limit(self.store, 'registro:'+ip, 20, 3600)
        fields(data, ('nombre','correo','password'), ('nombre','correo','password'))
        name=text(data['nombre'],'Nombre',2,80)
        email=text(data['correo'],'Correo',3,254).lower()
        require(bool(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email)),400,'Correo inválido.')
        password=data['password']
        require(isinstance(password,str) and 12<=len(password)<=128,400,'La contraseña debe tener entre 12 y 128 caracteres.')
        encoded=hash_password(password)
        with self.store.connect(write=True) as c:
            row=c.execute('''INSERT INTO usuarios(nombre,correo,password_hash) VALUES(?,?,?)
                ON CONFLICT(correo) DO NOTHING RETURNING id,nombre,correo''',(name,email,encoded)).fetchone()
            require(row is not None,409,'No se pudo crear la cuenta con estos datos.')
            return dict(row)

    def login(self,data,ip):
        fields(data,('correo','password'),('correo','password'))
        email=text(data['correo'],'Correo',3,254).lower()
        password=data['password']
        require(isinstance(password,str) and len(password)<=128,400,'Solicitud inválida.')
        rate_limit(self.store,'login-ip:'+ip,30,900)
        rate_limit(self.store,'login-cuenta:'+email,8,900)
        with self.store.connect() as c:
            user=c.execute('SELECT * FROM usuarios WHERE correo=?',(email,)).fetchone()
        valid=verify_password(password,user['password_hash'] if user else DUMMY_HASH)
        require(user is not None and valid,401,'Correo o contraseña incorrectos.')
        token,csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
        with self.store.connect(write=True) as c:
            c.execute('DELETE FROM sesiones WHERE expira<?',(time.time(),))
            c.execute('INSERT INTO sesiones VALUES(?,?,?,?)',(token,user['id'],csrf,time.time()+28800))
        return token,csrf,session_user(user)

    def authenticate(self,token):
        if not token: return None
        with self.store.connect() as c:
            row=c.execute('''SELECT u.*,s.csrf FROM sesiones s JOIN usuarios u ON u.id=s.usuario_id
                WHERE s.token=? AND s.expira>?''',(token,time.time())).fetchone()
        return dict(row) if row else None

    def events(self,query):
        search=query.get('q',[''])[0][:100]
        category=query.get('categoria',[''])[0][:50]
        with self.store.connect() as c:
            rows=c.execute('''SELECT * FROM eventos WHERE estado='activo' AND fecha>?
                AND (LOWER(titulo) LIKE LOWER(?) ESCAPE '\\' OR LOWER(descripcion) LIKE LOWER(?) ESCAPE '\\')
                AND (?='' OR categoria=?) ORDER BY fecha LIMIT 100''',
                (now_iso(),'%'+search.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%',
                 '%'+search.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%',category,category)).fetchall()
        return [dict(r) for r in rows]

    def event(self,id):
        with self.store.connect() as c: row=c.execute('SELECT * FROM eventos WHERE id=?',(id,)).fetchone()
        require(row is not None,404,'Evento no encontrado.')
        return dict(row)

    def validate_event(self,data):
        keys=('titulo','descripcion','fecha','ubicacion','categoria','cupo','precio')
        fields(data,keys,keys)
        result={k:text(data[k],k,1,3000 if k=='descripcion' else 160) for k in keys[:5]}
        try:
            dt=datetime.fromisoformat(result['fecha'].replace('Z','+00:00'))
            require(dt.tzinfo is not None and dt>datetime.now(timezone.utc),400,'La fecha debe ser futura e incluir zona horaria.')
            result['fecha']=dt.astimezone(timezone.utc).isoformat()
        except ValueError: raise APIError(400,'Fecha inválida.')
        require(type(data['cupo']) is int and 1<=data['cupo']<=100000,400,'El cupo debe ser un entero entre 1 y 100000.')
        require(type(data['precio']) is int and data['precio']==0,400,'El MVP admite solamente eventos gratuitos (precio 0).')
        result.update(cupo=data['cupo'],precio=0)
        return result

    def save_event(self,user,data,id=None):
        require(user['rol'] in ('organizador','administrador'),403,'Se requiere rol de organizador.')
        d=self.validate_event(data)
        with self.store.connect(write=True) as c:
            if id is None:
                row=c.execute('''INSERT INTO eventos(titulo,descripcion,fecha,ubicacion,categoria,cupo,disponibles,precio,organizador_id)
                    VALUES(?,?,?,?,?,?,?,?,?) RETURNING *''',tuple(d[k] for k in ('titulo','descripcion','fecha','ubicacion','categoria','cupo'))+(d['cupo'],0,user['id'])).fetchone()
            else:
                event=self.store.lock_event(c,id)
                require(event is not None,404,'Evento no encontrado.')
                require(event['organizador_id']==user['id'] or user['rol']=='administrador',403,'No puedes modificar eventos ajenos.')
                occupied=event['cupo']-event['disponibles']
                require(d['cupo']>=occupied,409,'El cupo no puede ser menor que las inscripciones existentes.')
                row=c.execute('''UPDATE eventos SET titulo=?,descripcion=?,fecha=?,ubicacion=?,categoria=?,cupo=?,disponibles=?,precio=?
                    WHERE id=? RETURNING *''',tuple(d[k] for k in ('titulo','descripcion','fecha','ubicacion','categoria','cupo'))+(d['cupo']-occupied,0,id)).fetchone()
            return dict(row)

    def enroll(self,user,id,data):
        fields(data,('cantidad',),('cantidad',))
        require(type(data['cantidad']) is int and data['cantidad']==1,400,'Se permite un cupo por usuario y evento.')
        rate_limit(self.store,'inscribir:'+str(user['id']),20,60)
        with self.store.connect(write=True) as c:
            event=self.store.lock_event(c,id)
            require(event is not None,404,'Evento no encontrado.')
            require(event['estado']=='activo' and event['fecha']>now_iso(),409,'El evento no está disponible para inscripción.')
            require(not c.execute('SELECT id FROM inscripciones WHERE evento_id=? AND usuario_id=?',(id,user['id'])).fetchone(),409,'Ya estás inscrito en este evento.')
            require(event['disponibles']>0,409,'Los cupos están agotados.')
            c.execute('UPDATE eventos SET disponibles=disponibles-1 WHERE id=? AND disponibles>0',(id,))
            row=c.execute('INSERT INTO inscripciones(evento_id,usuario_id,fecha) VALUES(?,?,?) RETURNING *',(id,user['id'],now_iso())).fetchone()
            c.execute('''INSERT INTO notificaciones(inscripcion_id,destino,asunto,mensaje) VALUES(?,?,?,?)''',
                (row['id'],user['correo'],'Tu inscripción en Eventia',f"Inscripción #{row['id']} confirmada: {event['titulo']}. Fecha: {event['fecha']}. Lugar: {event['ubicacion']}."))
            return {**dict(row),'disponibles':event['disponibles']-1,'notificacion':'pendiente'}

    def registration(self,user,id):
        with self.store.connect() as c:
            row=c.execute('''SELECT i.*,e.organizador_id FROM inscripciones i JOIN eventos e ON e.id=i.evento_id WHERE i.id=?''',(id,)).fetchone()
        require(row is not None,404,'Inscripción no encontrada.')
        require(row['usuario_id']==user['id'] or user['rol']=='administrador' or
                (user['rol']=='organizador' and row['organizador_id']==user['id']),403,'No tienes acceso a esta inscripción.')
        return {k:row[k] for k in ('id','evento_id','usuario_id','fecha')}

    def mine(self,user):
        with self.store.connect() as c:
            rows=c.execute('''SELECT i.id,i.fecha,e.titulo,e.fecha AS fecha_evento,e.ubicacion,e.categoria,e.estado
                FROM inscripciones i JOIN eventos e ON e.id=i.evento_id WHERE i.usuario_id=? ORDER BY e.fecha''',(user['id'],)).fetchall()
        return [dict(r) for r in rows]

    def managed(self,user):
        require(user['rol'] in ('organizador','administrador'),403,'Acceso restringido.')
        with self.store.connect() as c:
            rows=c.execute('SELECT * FROM eventos WHERE organizador_id=? ORDER BY fecha',(user['id'],)).fetchall()
        return [dict(r) for r in rows]

    def attendees(self,user,id):
        e=self.event(id)
        require(user['rol']=='administrador' or (user['rol']=='organizador' and e['organizador_id']==user['id']),403,'No tienes acceso a los asistentes de este evento.')
        with self.store.connect() as c:
            rows=c.execute('''SELECT i.id,i.fecha,u.nombre,u.correo FROM inscripciones i JOIN usuarios u ON u.id=i.usuario_id
                WHERE i.evento_id=? ORDER BY i.id''',(id,)).fetchall()
        return [dict(r) for r in rows]
