'use strict';
const $ = s => document.querySelector(s);
const state = {user:null,csrf:null,events:[],category:'',query:'',sort:'date'};
const categories = ['Todos','Tecnología','Arte y cultura','Talleres','Bienestar','Comunidad'];
const artClass = c => ({'Tecnología':'art-tech','Arte y cultura':'art-culture','Talleres':'art-workshop','Bienestar':'art-wellness','Comunidad':'art-community'}[c] || 'art-tech');
// All content from the API is escaped before interpolation; no user HTML is rendered.
const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date = (value,options={dateStyle:'long',timeStyle:'short'}) => new Intl.DateTimeFormat('es-GT',{...options,timeZone:'America/Guatemala'}).format(new Date(value));
let toastTimer;
function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,5000)}
async function api(path,method='GET',data){
  const headers={};if(data!==undefined)headers['Content-Type']='application/json';if(state.csrf)headers['X-CSRF-Token']=state.csrf;
  const response=await fetch(path,{method,headers,credentials:'same-origin',body:data!==undefined?JSON.stringify(data):undefined});
  const result=await response.json();if(!response.ok)throw new Error(result.error||'No se pudo completar la solicitud.');return result;
}
function modal(html){$('#modal-content').innerHTML=html;if(!$('#modal').open)$('#modal').showModal()}
$('#modal-close').onclick=()=>$('#modal').close();
$('#modal').addEventListener('click',e=>{if(e.target===$('#modal')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close()}});
function empty(title,message){return `<div class="empty"><h3>${esc(title)}</h3><p>${esc(message)}</p></div>`}
function account(){
  const u=state.user;
  $('#account').innerHTML=u?`<div class="account-name"><span>Hola, ${esc(u.nombre.split(' ')[0])}</span><button class="text-button" id="logout">Salir ↗</button></div>`:'<button class="button small outline" id="login-open">Iniciar sesión <span>↗</span></button>';
  $('#nav-manage').hidden=!u||!['organizador','administrador'].includes(u.rol);
  $('#nav-admin').hidden=!u||u.rol!=='administrador';
  if(u)$('#logout').onclick=async()=>{try{await api('/api/auth/logout','POST',{});state.user=null;state.csrf=null;account();location.hash='explorar';route();toast('Sesión cerrada.')}catch(e){toast(e.message)}};
  else $('#login-open').onclick=()=>auth();
}
function auth(register=false,onSuccess=null){
  modal(`<p class="eyebrow">TU PRÓXIMA HISTORIA EMPIEZA AQUÍ</p><h2>${register?'Hagamos conexión.':'Qué bueno verte de nuevo.'}</h2><p class="form-note">${register?'Crea tu cuenta y encuentra tu próximo encuentro.':'Entra para reservar tu lugar y consultar tus inscripciones.'}</p><form id="auth-form" class="form">${register?'<label>Tu nombre<input name="nombre" autocomplete="name" minlength="2" maxlength="80" required></label>':''}<label>Correo electrónico<input name="correo" type="email" autocomplete="email" maxlength="254" required></label><label>Contraseña<input name="password" type="password" autocomplete="${register?'new-password':'current-password'}" ${register?'minlength="12"':''} maxlength="128" required></label>${register?'<span class="form-note">Usa una contraseña de al menos 12 caracteres. Tu cuenta se creará como asistente.</span>':''}<p class="form-error" id="auth-error" role="alert" hidden></p><button class="button dark" type="submit">${register?'Crear mi cuenta':'Iniciar sesión'} <span>↗</span></button></form><p class="form-note">${register?'¿Ya tienes cuenta?':'¿Es tu primera vez?'} <button class="text-button" id="auth-switch">${register?'Inicia sesión':'Crea tu cuenta'}</button></p>`);
  $('#auth-switch').onclick=()=>auth(!register,onSuccess);
  $('#auth-form').onsubmit=async e=>{
    e.preventDefault();const form=e.currentTarget,button=form.querySelector('[type=submit]');button.disabled=true;
    const data=Object.fromEntries(new FormData(form));
    try{
      if(register)await api('/api/usuarios','POST',data);
      const result=await api('/api/auth/login','POST',{correo:data.correo,password:data.password});
      state.user=result.usuario;state.csrf=result.csrf;account();$('#modal').close();toast(register?'Tu cuenta está lista. ¡Bienvenido a Eventia!':'Ya estás dentro.');route();if(onSuccess)await onSuccess();
    }catch(error){$('#auth-error').textContent=error.message;$('#auth-error').hidden=false}
    finally{button.disabled=false}
  };
}
function renderCategories(){
  $('#categories').innerHTML=categories.map((c,i)=>`<button class="category ${(state.category===''&&i===0)||state.category===c?'active':''}" data-category="${esc(i===0?'':c)}" aria-pressed="${(state.category===''&&i===0)||state.category===c}">${esc(c)}</button>`).join('');
  $('#categories').querySelectorAll('button').forEach(b=>b.onclick=()=>{state.category=b.dataset.category;renderCategories();loadEvents()});
}
let requestSequence=0;
async function loadEvents(){
  const seq=++requestSequence;
  try{
    const events=await api('/api/eventos?'+new URLSearchParams({q:state.query,categoria:state.category}));
    if(seq!==requestSequence)return;state.events=events;renderEvents();
  }catch(e){if(seq!==requestSequence)return;$('#result-count').textContent='No se pudieron cargar los eventos';$('#event-grid').innerHTML=empty('No pudimos conectar',e.message)+'<button class="button outline" id="retry">Volver a intentar</button>';$('#retry').onclick=loadEvents}
}
function renderEvents(){
  const list=[...state.events];if(state.sort==='title')list.sort((a,b)=>a.titulo.localeCompare(b.titulo));if(state.sort==='spaces')list.sort((a,b)=>b.disponibles-a.disponibles);
  $('#result-count').textContent=`${list.length} ${list.length===1?'encuentro por descubrir':'encuentros por descubrir'}`;
  $('#event-grid').innerHTML=list.length?list.map(event=>{
    const day=date(event.fecha,{day:'2-digit'}),month=date(event.fecha,{month:'short'}).replace('.','');
    return `<article class="event-card"><div class="event-art ${artClass(event.categoria)}" aria-hidden="true"><span class="art-tag">${esc(event.categoria)}</span><span class="art-word">NOS VEMOS AQUÍ ↗</span><div class="date-badge"><strong>${day}</strong><span>${month}</span></div></div><div class="card-body"><p class="event-meta">${esc(date(event.fecha,{weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}))}</p><h3>${esc(event.titulo)}</h3><p class="event-place">↗ ${esc(event.ubicacion)}</p><div class="card-bottom"><div><span class="free">Entrada gratuita</span><div class="spots">${event.disponibles?`${event.disponibles} lugares disponibles`:'Cupos agotados'}</div></div><button class="card-link" data-event="${event.id}" aria-label="Ver ${esc(event.titulo)}">Ver evento ↗</button></div></div></article>`;
  }).join(''):empty('Otra buena historia está por llegar.','Prueba otra búsqueda o elige una categoría diferente.');
  $('#event-grid').querySelectorAll('[data-event]').forEach(b=>b.onclick=()=>detail(Number(b.dataset.event)));
}
async function detail(id){
  try{
    const event=await api('/api/eventos/'+id);
    modal(`<div class="event-art detail-art ${artClass(event.categoria)}" aria-hidden="true"></div><p class="eyebrow">${esc(event.categoria)}</p><h2>${esc(event.titulo)}</h2><p class="detail-description">${esc(event.descripcion)}</p><div class="detail-meta"><p>◷ ${esc(date(event.fecha))} · Guatemala</p><p>↗ ${esc(event.ubicacion)}</p><p>◎ ${event.disponibles} de ${event.cupo} lugares disponibles</p><p>Entrada gratuita · Un lugar por persona</p></div><p class="form-error" id="enroll-error" role="alert" hidden></p><button class="button dark" id="enroll" ${event.disponibles===0||event.estado!=='activo'?'disabled':''}>${event.disponibles===0?'Cupos agotados':state.user?'Reservar mi lugar':'Inicia sesión para inscribirte'} <span>↗</span></button><p class="form-note">Tu lugar se confirma al completar la inscripción.</p>`);
    $('#enroll').onclick=async()=>{
      if(!state.user){auth();return}
      const button=$('#enroll');button.disabled=true;
      try{
        const result=await api(`/api/eventos/${id}/inscripciones`,'POST',{cantidad:1});
        modal(`<p class="eyebrow">YA ERES PARTE DEL ENCUENTRO</p><h2>Nos vemos ahí.</h2><p class="detail-description">Tu lugar en <strong>${esc(event.titulo)}</strong> está confirmado.</p><div class="detail-meta"><p>Confirmación #${result.id}</p><p>${esc(date(event.fecha))}</p><p>${esc(event.ubicacion)}</p></div><p class="form-note">El comprobante ya está en Mis inscripciones. El correo queda pendiente de envío.</p><button class="button dark" id="go-mine">Ver mis inscripciones ↗</button>`);
        $('#go-mine').onclick=()=>{$('#modal').close();location.hash='inscripciones'};loadEvents();
      }catch(e){$('#enroll-error').textContent=e.message;$('#enroll-error').hidden=false;button.disabled=false}
    };
  }catch(e){toast(e.message)}
}
let searchTimer;$('#search').oninput=e=>{state.query=e.target.value;clearTimeout(searchTimer);searchTimer=setTimeout(loadEvents,250)};
$('#sort').onchange=e=>{state.sort=e.target.value;renderEvents()};
async function organize(){
  try{
    // Refresh before deciding: another tab or the administrator may have changed the session.
    const current=await api('/api/auth/me');state.user=current.usuario;state.csrf=current.csrf;account();
  }catch(e){toast('No pudimos comprobar tu sesión. '+e.message);return}
  if(!state.user){auth(false,organize);return}
  if(['organizador','administrador'].includes(state.user.rol)){location.hash='organizar';await route();return}
  modal('<p class="eyebrow">PERMISO PARA PUBLICAR</p><h2>Tu cuenta ya está creada.</h2><p class="detail-description">Has iniciado sesión como <strong>'+esc(state.user.nombre)+'</strong>. Tu cuenta tiene el rol de asistente; para crear eventos necesita el permiso de organizador.</p><p class="form-note">No necesitas registrarte otra vez. Pide al administrador que habilite el rol de organizador para tu cuenta actual. Después, inicia sesión de nuevo.</p><button class="button dark" id="organizer-account">Entendido</button>');
  $('#organizer-account').onclick=()=>$('#modal').close();
}
$('#organize-cta').onclick=organize;
async function route(){
  const routeName=location.hash.slice(1)||'explorar';
  if(routeName==='catalogo')return;
  const mine=routeName==='inscripciones',manage=routeName==='organizar',admin=routeName==='usuarios';
  $('#explore-view').hidden=mine||manage||admin;$('#mine-view').hidden=!mine;$('#manage-view').hidden=!manage;$('#admin-view').hidden=!admin;
  document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('active',a.hash==='#'+routeName));
  if(!mine&&!manage&&!admin)return;
  const target=mine?$('#my-registrations'):manage?$('#managed-events'):$('#admin-users');
  if(!state.user){target.innerHTML=empty('Tu próximo encuentro empieza aquí.','Inicia sesión para acceder a esta sección.')+'<button class="button dark" id="view-login">Iniciar sesión ↗</button>';$('#view-login').onclick=()=>auth();return}
  target.innerHTML=empty('Un momento…','Estamos preparando tus datos.');
  try{
    if(mine){
      const rows=await api('/api/inscripciones');
      target.innerHTML=rows.length?rows.map(r=>`<article class="registration-row"><div><span class="eyebrow">INSCRIPCIÓN #${r.id}</span><h3>${esc(r.titulo)}</h3><p>${esc(date(r.fecha_evento))}</p><p>${esc(r.ubicacion)}</p></div><span class="confirmed">${r.estado==='cancelado'?'Evento cancelado':'Inscripción confirmada'}</span></article>`).join(''):empty('Tu agenda tiene espacio para algo bueno.','Explora los eventos y reserva tu primer encuentro.');
    }else if(manage){
      const rows=await api('/api/mis-eventos');
      target.innerHTML=rows.length?rows.map(r=>`<article class="registration-row"><div><h3>${esc(r.titulo)}</h3><p>${esc(date(r.fecha))} · ${r.cupo-r.disponibles} personas inscritas</p><p>${esc(r.ubicacion)}</p></div><div><button class="card-link" data-edit="${r.id}">Editar ↗</button> <button class="card-link" data-attendees="${r.id}">Ver asistentes</button></div></article>`).join(''):empty('Todo empieza con una idea.','Crea tu primer evento y reúne a tu comunidad.');
      target.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>eventForm(rows.find(r=>r.id===Number(b.dataset.edit))));
      target.querySelectorAll('[data-attendees]').forEach(b=>b.onclick=()=>attendees(Number(b.dataset.attendees)));
    }else{
      const rows=await api('/api/admin/usuarios');
      target.innerHTML=rows.map(r=>`<article class="registration-row"><div><h3>${esc(r.nombre)}</h3><p>${esc(r.correo)} · ${esc(r.rol)}</p></div>${r.id===state.user.id?'<span class="confirmed">Tu cuenta</span>':`<label>Rol <select data-role="${r.id}" aria-label="Rol de ${esc(r.nombre)}">${['usuario','organizador','administrador'].map(role=>`<option ${role===r.rol?'selected':''}>${role}</option>`).join('')}</select></label>`}</article>`).join('');
      target.querySelectorAll('[data-role]').forEach(s=>s.onchange=async()=>{try{await api(`/api/admin/usuarios/${s.dataset.role}/rol`,'PATCH',{rol:s.value});toast('Rol actualizado. Se cerraron sus sesiones.');route()}catch(e){toast(e.message);route()}});
    }
  }catch(e){target.innerHTML=empty('No pudimos abrir esta sección.',e.message)}
}
$('#create-event').onclick=()=>eventForm();
function localDate(iso){const d=new Date(iso);return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16)}
function eventForm(event){
  modal(`<p class="eyebrow">HECHO PARA CONECTAR</p><h2>${event?'Dale forma al encuentro.':'Tu idea merece un encuentro.'}</h2><form class="form" id="event-form"><label>Título<input name="titulo" maxlength="160" value="${esc(event?.titulo||'')}" required></label><label>Descripción<textarea name="descripcion" maxlength="3000" required>${esc(event?.descripcion||'')}</textarea></label><div class="row"><label>Fecha y hora (zona de tu dispositivo)<input name="fecha" type="datetime-local" value="${event?localDate(event.fecha):''}" required></label><label>Cupo total<input name="cupo" type="number" min="1" max="100000" step="1" value="${event?.cupo||30}" required></label></div><label>Ubicación<input name="ubicacion" maxlength="160" value="${esc(event?.ubicacion||'')}" required></label><label>Categoría<select name="categoria">${categories.slice(1).map(c=>`<option ${event?.categoria===c?'selected':''}>${esc(c)}</option>`).join('')}</select></label><p class="form-note">Todos los eventos de esta versión son gratuitos. El cupo incluye las inscripciones ya confirmadas.</p><p class="form-error" id="event-error" role="alert" hidden></p><button class="button dark" type="submit">${event?'Guardar cambios':'Publicar evento'} ↗</button></form>`);
  $('#event-form').onsubmit=async e=>{
    e.preventDefault();const button=e.currentTarget.querySelector('[type=submit]');button.disabled=true;
    const d=Object.fromEntries(new FormData(e.currentTarget));
    try{d.cupo=Number(d.cupo);d.precio=0;d.fecha=new Date(d.fecha).toISOString();await api(event?'/api/eventos/'+event.id:'/api/eventos',event?'PUT':'POST',d);$('#modal').close();toast(event?'Cambios guardados.':'Tu evento ya está publicado.');route();loadEvents()}
    catch(error){$('#event-error').textContent=error.message;$('#event-error').hidden=false}finally{button.disabled=false}
  };
}
async function attendees(id){try{const rows=await api(`/api/eventos/${id}/inscripciones`);modal('<p class="eyebrow">TU COMUNIDAD</p><h2>Personas inscritas.</h2><div class="registration-list">'+(rows.length?rows.map(r=>`<article><p><strong>${esc(r.nombre)}</strong><br>${esc(r.correo)}<br><span class="form-note">Inscripción #${r.id}</span></p></article>`).join(''):empty('Aún no hay inscripciones.','Comparte tu evento con tu comunidad.'))+'</div>')}catch(e){toast(e.message)}}
window.addEventListener('hashchange',route);
async function init(){renderCategories();try{const r=await api('/api/auth/me');state.user=r.usuario;state.csrf=r.csrf}catch(e){toast('No se pudo recuperar la sesión. '+e.message)}account();await Promise.all([loadEvents(),route()])}
init();
