"""WSGI de pareamento pessoal. Um processo, sessões efêmeras, sem log de URLs/tokens."""
import os,json,time,secrets,hashlib,base64,hmac,threading
from urllib.parse import urlencode,urlsplit,parse_qs
import requests
BASE=(os.environ.get('PUBLIC_BASE_URL') or os.environ.get('RENDER_EXTERNAL_URL','')).rstrip('/')
CLIENT=os.environ.get('SPOTIFY_CLIENT_ID','')
KEY=os.environ.get('DEVICE_ENROLLMENT_KEY','')
SCOPES='user-read-playback-state user-modify-playback-state user-read-currently-playing playlist-read-private playlist-read-collaborative'
SESSIONS={};LOCK=threading.RLock();MAX_SESSIONS=16

def valid_config():
 u=urlsplit(BASE)
 return u.scheme=='https' and u.hostname and not u.username and not u.password and not u.query and not u.fragment and u.path=='' and len(KEY)>=32 and len(CLIENT)==32 and all(c in '0123456789abcdefABCDEF' for c in CLIENT)
def response(start,status,data,kind='json',extra=()):
 if kind=='json':data=json.dumps(data,separators=(',',':')).encode();ctype='application/json'
 else:data=data.encode();ctype='text/html; charset=utf-8'
 start(status,[('Content-Type',ctype),('Content-Length',str(len(data))),('Cache-Control','no-store'),('Referrer-Policy','no-referrer'),('X-Content-Type-Options','nosniff'),('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"),*extra]);return [data]
def page(message,form=''):
 return '<!doctype html><html lang="pt-BR"><meta name="viewport" content="width=device-width, initial-scale=1"><title>PH Pocket</title><style>body{background:#000;color:#fff;font:18px system-ui;padding:24px;max-width:500px;margin:auto}button{background:#1DB954;border:0;border-radius:14px;padding:16px;font:inherit}input{font:inherit;padding:12px;width:160px}small{color:#aaa}</style><h1>PH Pocket</h1><p>'+message+'</p>'+form+'<p><small>by PH · Spotify via Wi-Fi</small></p></html>'
def prune():
 now=time.monotonic()
 for sid in list(SESSIONS):
  if now>=SESSIONS[sid]['expires']:del SESSIONS[sid]
def authorized(env,key):return hmac.compare_digest(env.get('HTTP_AUTHORIZATION',''),'Bearer '+key)
def body(env):
 n=int(env.get('CONTENT_LENGTH','0') or 0)
 if n<0 or n>2048:raise ValueError()
 raw=env['wsgi.input'].read(n)
 if env.get('CONTENT_TYPE','').startswith('application/json'):return json.loads(raw)
 return {k:v[0] for k,v in parse_qs(raw.decode(),keep_blank_values=True).items() if len(v)==1}
def application(env,start):
 try:return dispatch(env,start)
 except (ValueError,KeyError,TypeError,UnicodeError):return response(start,'400 Bad Request',{'error':'invalid_request'})
 except Exception:return response(start,'503 Service Unavailable',{'error':'service_unavailable'})
def dispatch(env,start):
 path=env.get('PATH_INFO','');method=env.get('REQUEST_METHOD','GET')
 if path=='/health':return response(start,'200 OK' if valid_config() else '503 Service Unavailable',{'ready':bool(valid_config())})
 if not valid_config():return response(start,'503 Service Unavailable',{'error':'configure_service'})
 with LOCK:
  prune()
  if path=='/api/session' and method=='POST':
   if not authorized(env,KEY):return response(start,'401 Unauthorized',{'error':'unauthorized'})
   d=body(env);secret=d.get('device_secret','');pin=d.get('pin','')
   if not isinstance(secret,str) or len(secret)!=64 or any(c not in '0123456789abcdef' for c in secret) or not isinstance(pin,str) or len(pin)!=6 or not pin.isdecimal():raise ValueError()
   if len(SESSIONS)>=MAX_SESSIONS:return response(start,'429 Too Many Requests',{'error':'busy'},extra=[('Retry-After','30')])
   sid=secrets.token_urlsafe(18);verifier=secrets.token_urlsafe(64)
   SESSIONS[sid]={'expires':time.monotonic()+300,'secret':hashlib.sha256(secret.encode()).digest(),'pin':pin,'attempts':0,'verifier':verifier,'state':secrets.token_urlsafe(32),'status':'pending','token':'','used':False}
   return response(start,'201 Created',{'id':sid,'url':BASE+'/p/'+sid,'expires_in':300})
  if path.startswith('/api/poll/') or path.startswith('/api/ack/'):
   if method!='POST':return response(start,'405 Method Not Allowed',{'error':'method'})
   sid=path.rsplit('/',1)[-1];s=SESSIONS.get(sid)
   raw=env.get('HTTP_AUTHORIZATION','').removeprefix('Bearer ')
   if not s or not hmac.compare_digest(s['secret'],hashlib.sha256(raw.encode()).digest()):return response(start,'404 Not Found',{'error':'expired'})
   if path.startswith('/api/ack/'):
    del SESSIONS[sid];return response(start,'200 OK',{'status':'deleted'})
   out={'status':s['status']}
   if s['status']=='ready':out.update(client_id=CLIENT,refresh_token=s['token'])
   return response(start,'200 OK',out)
  if path.startswith('/p/'):
   sid=path.rsplit('/',1)[-1];s=SESSIONS.get(sid)
   if not s:return response(start,'410 Gone',page('Sessão expirada. Gere outro QR na placa.'),'html')
   if s['used']:return response(start,'409 Conflict',page('Autorização já iniciada. Volte à placa.'),'html')
   if method=='GET':return response(start,'200 OK',page('Confira que foi você quem iniciou na placa. Digite o código de seis dígitos exibido no PH Pocket. Válido por até 5 minutos.', '<form method="post"><input name="pin" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" required autocomplete="off"><p><button>Conectar Spotify</button></p></form>'),'html')
   if method!='POST':return response(start,'405 Method Not Allowed',{'error':'method'})
   if env.get('HTTP_ORIGIN') and env['HTTP_ORIGIN']!=BASE:return response(start,'403 Forbidden',{'error':'origin'})
   pin=body(env).get('pin','');s['attempts']+=1
   if s['attempts']>5:del SESSIONS[sid];return response(start,'410 Gone',page('Sessão cancelada por tentativas incorretas.'),'html')
   if not hmac.compare_digest(str(pin),s['pin']):return response(start,'403 Forbidden',page('Código incorreto. Volte e confira na placa.'),'html')
   s['used']=True
   challenge=base64.urlsafe_b64encode(hashlib.sha256(s['verifier'].encode()).digest()).rstrip(b'=').decode()
   url='https://accounts.spotify.com/authorize?'+urlencode({'client_id':CLIENT,'redirect_uri':BASE+'/callback','response_type':'code','scope':SCOPES,'state':s['state'],'code_challenge_method':'S256','code_challenge':challenge})
   return response(start,'303 See Other',page('Abrindo Spotify...'),'html',[('Location',url)])
  if path=='/callback' and method=='GET':
   q=parse_qs(env.get('QUERY_STRING',''));state=q.get('state',[])
   if len(state)!=1:return response(start,'400 Bad Request',page('State inválido.'),'html')
   found=next(((sid,s) for sid,s in SESSIONS.items() if s['used'] and hmac.compare_digest(s['state'],state[0])),None)
   if not found:return response(start,'400 Bad Request',page('Sessão expirada ou callback já utilizado.'),'html')
   sid,s=found;s['state']='';s['status']='exchanging'
   if 'error' in q:s['status']='denied';return response(start,'403 Forbidden',page('Permissão negada. Gere outro QR para tentar novamente.'),'html')
   code=q.get('code',[])
   if len(code)!=1 or not code[0]:s['status']='failed';return response(start,'400 Bad Request',page('Callback sem código. Gere outro QR.'),'html')
   try:
    result=requests.post('https://accounts.spotify.com/api/token',data={'grant_type':'authorization_code','code':code[0],'redirect_uri':BASE+'/callback','client_id':CLIENT,'code_verifier':s['verifier']},timeout=15,allow_redirects=False,stream=True)
    # Stream bounded manually rather than trusting an unlimited JSON body.
    if result.status_code!=200:result.close();s['status']='failed';return response(start,'502 Bad Gateway',page('Spotify recusou a sessão. Confira o Client ID, callback e usuários autorizados.'),'html')
    raw=bytearray()
    try:
     for chunk in result.iter_content(1024):
      if len(raw)+len(chunk)>8192:raise ValueError()
      raw.extend(chunk)
    finally:result.close()
    parsed=json.loads(raw)
    if not isinstance(parsed,dict):raise ValueError()
    token=parsed.get('refresh_token','')
    if not isinstance(token,str) or not 21<=len(token)<=1024:raise ValueError()
    if time.monotonic()>=s['expires']:s['status']='failed';return response(start,'410 Gone',page('Sessão expirada. Gere outro QR.'),'html')
    s['token']=token;s['status']='ready';s['verifier']='';s['pin']=''
    return response(start,'200 OK',page('Autorizado! Aguarde a confirmação na tela do PH Pocket. Pode fechar esta página.'),'html')
   except (requests.RequestException,ValueError,TypeError):s['status']='failed';return response(start,'502 Bad Gateway',page('Falha na autorização. Gere outro QR para tentar novamente.'),'html')
  return response(start,'404 Not Found',page('PH Pocket: abra o QR gerado pela placa.'),'html')
