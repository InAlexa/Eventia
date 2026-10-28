// Regression tests for session/role decisions, using the real app.js and a minimal DOM stub.
// Run: node tests/test_organize.cjs (no packages required).
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
function app(user,fail=false){
 const nodes=new Map();
 function element(key){if(!nodes.has(key))nodes.set(key,{innerHTML:'',hidden:false,open:false,classList:{toggle(){}},addEventListener(){},querySelectorAll(){return []},showModal(){this.open=true},close(){this.open=false}});return nodes.get(key)}
 const calls=[];
 const location={_hash:'',get hash(){return this._hash},set hash(value){this._hash=value?(value.startsWith('#')?value:'#'+value):''}};
 const context=vm.createContext({document:{querySelector:element,querySelectorAll(){return []}},window:{addEventListener(){}},location,
  Intl,Date,URLSearchParams,console,setTimeout(){return 1},clearTimeout(){},
  fetch:async(url)=>{calls.push(url);if(fail)throw Error('Sin conexión');return {ok:true,json:async()=>url==='/api/auth/me'?{usuario:user,csrf:user?'fresh-csrf':null}:[]}}});
 const code=fs.readFileSync(path.join(__dirname,'../public/app.js'),'utf8').replace(/init\(\);\s*$/,'');
 vm.runInContext(code,context);return {context,element,calls,run:()=>vm.runInContext('organize()',context)};
}
test('visitor is offered login to an existing account',async()=>{
 const a=app(null);await a.run();const html=a.element('#modal-content').innerHTML;
 assert.match(html,/Iniciar sesión/);assert.doesNotMatch(html,/name="nombre"/);
 assert.ok(a.element('#auth-switch').onclick);
});
test('registration offers creating events or only attending, never an admin choice',async()=>{
 const a=app(null);vm.runInContext('auth(true)',a.context);const html=a.element('#modal-content').innerHTML;
 assert.match(html,/crear eventos y también asistir/i);assert.match(html,/solo quiero asistir/i);
 assert.doesNotMatch(html,/administrador/);
});
test('signed-in assistant is not asked to register again',async()=>{
 const a=app({id:1,nombre:'Ana',rol:'usuario'});await a.run();const html=a.element('#modal-content').innerHTML;
 assert.match(html,/Tu cuenta ya está creada/);assert.match(html,/tipo de cuenta que tienes/);
 assert.doesNotMatch(html,/rol de asistente|rol de organizador/);
 assert.doesNotMatch(html,/Crear mi cuenta/);assert.equal(a.context.location.hash,'');
});
test('organizer proceeds to event management after a fresh session check',async()=>{
 const a=app({id:2,nombre:'Organizadora',rol:'organizador'});await a.run();
 assert.equal(a.context.location.hash,'#organizar');assert.ok(a.calls.includes('/api/mis-eventos'));
 assert.equal(a.element('#modal').open,false);
});
test('stale organizer state cannot bypass the current server role',async()=>{
 const a=app({id:1,nombre:'Ana',rol:'usuario'});
 vm.runInContext("state.user={id:1,nombre:'Ana',rol:'organizador'}",a.context);
 await a.run();assert.match(a.element('#modal-content').innerHTML,/tipo de cuenta que tienes/);
 assert.equal(a.context.location.hash,'');
});
test('a failed session check does not redirect to registration',async()=>{
 const a=app(null,true);await a.run();assert.equal(a.element('#modal').open,false);
 assert.match(a.element('#toast').textContent,/No pudimos comprobar tu sesión/);
});
