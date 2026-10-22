import argparse
import getpass
from datetime import datetime, timedelta, timezone
from eventia.db import Store
from eventia.service import Service
from eventia.security import hash_password

def main():
    parser=argparse.ArgumentParser(description='Eventia')
    sub=parser.add_subparsers(dest='command',required=True)
    run=sub.add_parser('run'); run.add_argument('--host',default='127.0.0.1'); run.add_argument('--port',type=int,default=8000)
    sub.add_parser('seed')
    sub.add_parser('worker')
    account=sub.add_parser('create-user')
    account.add_argument('--correo',required=True); account.add_argument('--nombre',required=True)
    account.add_argument('--rol',choices=['usuario','organizador','administrador'],default='usuario')
    role=sub.add_parser('set-role',help='Cambiar el rol de una cuenta existente (administración local).')
    role.add_argument('--correo',required=True)
    role.add_argument('--rol',required=True,choices=['usuario','organizador','administrador'])
    args=parser.parse_args(); store=Store()
    if args.command=='run':
        from eventia.server import serve
        serve(store,args.host,args.port)
    elif args.command=='worker':
        from eventia.notifications import deliver
        deliver(store)
    elif args.command=='create-user':
        password=getpass.getpass('Contraseña (12-128 caracteres): ')
        if not 12<=len(password)<=128: parser.error('Longitud inválida.')
        with store.connect(write=True) as c:
            c.execute('INSERT INTO usuarios(nombre,correo,password_hash,rol) VALUES(?,?,?,?)',
                (args.nombre,args.correo.lower(),hash_password(password),args.rol))
        print('Usuario creado.')
    elif args.command=='set-role':
        # Administrative CLI requires access to the installation/database; never exposed as self-service.
        with store.connect(write=True) as c:
            row=c.execute('UPDATE usuarios SET rol=? WHERE correo=? RETURNING id',
                (args.rol,args.correo.strip().lower())).fetchone()
            if row is None: parser.error('No existe una cuenta con ese correo. No se creó otra cuenta.')
            c.execute('DELETE FROM sesiones WHERE usuario_id=?',(row['id'],))
        print('Rol actualizado en la cuenta existente. Inicia sesión de nuevo para aplicar el permiso.')
    elif args.command=='seed':
        # No usable default passwords or automatic privileged demo login.
        with store.connect(write=True) as c:
            user=c.execute("SELECT * FROM usuarios WHERE correo='organizacion@eventia.invalid'").fetchone()
            if user is None:
                import secrets
                user=c.execute('INSERT INTO usuarios(nombre,correo,password_hash,rol) VALUES(?,?,?,?) RETURNING *',
                    ('Comunidad Eventia','organizacion@eventia.invalid',hash_password(secrets.token_urlsafe(40)),'organizador')).fetchone()
            exists=c.execute('SELECT id FROM eventos LIMIT 1').fetchone()
        if exists: print('El catálogo ya tiene eventos.'); return
        entries=[
            ('Ideas que conectan','Una tarde para compartir proyectos, conocer a la comunidad creativa y transformar una buena conversación en tu próxima gran idea.','Tecnología','Centro Cultural de Quetzaltenango',120,4),
            ('Código & café','Trae tu laptop y tus preguntas. Un encuentro práctico sobre desarrollo web, buenas prácticas y proyectos que merecen salir al mundo.','Tecnología','Hub de innovación · Zona 3',35,7),
            ('El arte de mirar distinto','Explora la ciudad con una caminata fotográfica y descubre las historias que se esconden en los detalles cotidianos.','Arte y cultura','Parque Central · Quetzaltenango',25,10),
            ('Diseña tu próxima idea','Un taller para pasar del boceto al prototipo. Experimenta con herramientas de diseño en una sesión abierta para todos los niveles.','Talleres','Casa de la Cultura',40,13),
            ('Rutas para reconectar','Una mañana al aire libre para bajar el ritmo, caminar en comunidad y disfrutar de los paisajes del altiplano.','Bienestar','Punto de encuentro · El Baúl',30,17),
            ('Conversaciones que inspiran','Historias reales de personas que están construyendo nuevas posibilidades para su comunidad. Ven a escuchar, preguntar y conectar.','Comunidad','Auditorio universitario · Xela',80,21)]
        service=Service(store)
        for title,desc,category,location,capacity,days in entries:
            date=(datetime.now(timezone.utc)+timedelta(days=days)).replace(hour=21,minute=0,second=0,microsecond=0)
            service.save_event(dict(user),dict(titulo=title,descripcion=desc,categoria=category,ubicacion=location,cupo=capacity,precio=0,fecha=date.isoformat()))
        print('Se crearon seis eventos de ejemplo. No se crearon cuentas con contraseñas públicas.')

if __name__=='__main__': main()
