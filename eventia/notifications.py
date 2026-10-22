"""Outbox durable: ejecutar un solo worker. Entrega SMTP al menos una vez."""
import os
import smtplib
import time
from email.message import EmailMessage

def deliver(store, once=False):
    while True:
        if os.getenv('SMTP_HOST'):
            with store.connect() as c:
                rows=c.execute("SELECT * FROM notificaciones WHERE estado='pendiente' AND intentos<5 ORDER BY id LIMIT 20").fetchall()
            for row in rows:
                try:
                    message=EmailMessage()
                    message['From']=os.environ['SMTP_FROM']
                    message['To']=row['destino']
                    message['Subject']=row['asunto']
                    message['Message-ID']=f"<eventia-{row['id']}@{os.environ.get('SMTP_MESSAGE_DOMAIN','eventia.local')}>"
                    message.set_content(row['mensaje'])
                    with smtplib.SMTP(os.environ['SMTP_HOST'],int(os.getenv('SMTP_PORT','587')),timeout=15) as smtp:
                        smtp.starttls()
                        if os.getenv('SMTP_USER'): smtp.login(os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD'])
                        smtp.send_message(message)
                    state='enviada'
                except Exception:
                    state='pendiente'
                with store.connect(write=True) as c:
                    c.execute('UPDATE notificaciones SET estado=?,intentos=intentos+1 WHERE id=?',(state,row['id']))
        if once: return
        time.sleep(30)
