#@title Abrir ATLAS PROPS multideporte
%pip -q install pandas numpy scipy requests tzdata "ipywidgets>=8,<9" pillow pytesseract rapidocr_onnxruntime
!apt-get -qq update
!apt-get -qq install -y tesseract-ocr
from google.colab import output
output.enable_custom_widget_manager()
"""ATLAS PROPS — motor multideporte de investigación, sin claves."""
import io,json,math,hashlib,time,html,zipfile,re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import requests,numpy as np,pandas as pd
from scipy.stats import poisson,nbinom,norm,beta
import ipywidgets as W
from IPython.display import display,clear_output
VERSION='PROPS 1.0'
CSS='<style>.props{font:15px/1.65 Arial;background:#101c2e;color:#edf4ff;padding:25px;border-radius:15px;margin:12px 0}.props h1,.props h2,.props h3{color:#fff}.props a{color:#5de0d2}.props .box{padding:16px;border:1px solid #3d526c;border-radius:10px;margin:12px 0}.props table{border-collapse:collapse;width:100%}.props td,.props th{padding:9px;border-bottom:1px solid #3d526c}.props table.dataframe tr,.props table.dataframe th,.props table.dataframe td{background:#17283f!important;color:#edf4ff!important}.props .scroll{overflow:auto}.props pre{white-space:pre-wrap}</style>'
SPORTS={'NFL':('football','nfl'),'NCAA fútbol americano':('football','college-football'),'NBA':('basketball','nba'),'WNBA':('basketball','wnba'),'NCAA baloncesto':('basketball','mens-college-basketball'),'MLB':('baseball','mlb'),'NHL':('hockey','nhl'),'Soccer':('soccer','eng.1'),'Tenis':None,'UFC':None}
# Claves explícitas y unidades: no se infiere un cero si la estadística no aparece.
DEFS={
 'passingYards':('Yardas de pase','yardas','normal','passing'),'passingAttempts':('Intentos de pase','intentos','count','passing'),'completions':('Pases completos','pases','count','passing'),'passingTouchdowns':('TD de pase','TD','count','passing'),'passingInterceptions':('Intercepciones lanzadas','INT','count','passing'),
 'rushingYards':('Yardas terrestres','yardas','normal','rushing'),'rushingAttempts':('Acarreos','acarreos','count','rushing'),'rushingTouchdowns':('TD terrestres','TD','count','rushing'),
 'receivingYards':('Yardas recibidas','yardas','normal','receiving'),'receptions':('Recepciones','recepciones','count','receiving'),'receivingTargets':('Targets','targets','count','receiving'),'receivingTouchdowns':('TD recibidos','TD','count','receiving'),
 'points':('Puntos','puntos','count',None),'rebounds':('Rebotes','rebotes','count',None),'assists':('Asistencias','asistencias','count',None),'steals':('Robos','robos','count',None),'blocks':('Tapones','tapones','count',None),'threePointFieldGoalsMade':('Triples anotados','triples','count',None),'PRA':('Puntos + rebotes + asistencias','PRA','count',None),
 'batterHits':('Hits del bateador','hits','count','batting'),'batterHomeRuns':('Home runs','HR','count','batting'),'batterStrikeouts':('Ponches del bateador','K','count','batting'),'RBIs':('Carreras impulsadas','RBI','count','batting'),'pitcherStrikeouts':('Ponches del lanzador','K','count','pitching'),'pitcherOuts':('Outs lanzados','outs','count','pitching'),
 'shotsTotal':('Tiros según definición de la fuente','tiros','count',None),'shotsOnTarget':('Tiros a puerta','tiros','count',None),'goals':('Goles','goles','count',None),'totalSaves':('Paradas','paradas','count',None),
 'aces':('Aces','aces','count',None),'doubleFaults':('Dobles faltas','faltas','count',None),'gamesWon':('Juegos ganados','juegos','count',None),
 'significantStrikesLanded':('Golpes significativos conectados','golpes','count',None),'takedownsLanded':('Derribos logrados','derribos','count',None),'fightSeconds':('Duración del combate','segundos','continuous',None)}
def esc(x):return html.escape(str(x),quote=True)
def now():return pd.Timestamp.now(tz='UTC')
def american(x):return f'{x:+.0f}'
def odds(x):
 x=float(x)
 if not math.isfinite(x) or abs(x)<100:raise ValueError('Cuota americana inválida: usa +100 o más, o -100 o menos.')
 return x
def dec(x):return 1+(x/100 if x>0 else 100/abs(x))
def items(v):return list(v.values()) if isinstance(v,dict) else list(v)
def number(x):
 try:
  v=float(x);return v if math.isfinite(v) else np.nan
 except (ValueError,TypeError):return np.nan
class Store:
 def __init__(self):self.root=Path('atlas_props_cache');self.root.mkdir(exist_ok=True);self.blocked=set();self.log=[]
 def get(self,url,ttl=3600):
  from urllib.parse import urlparse
  host=urlparse(url).netloc;p=self.root/(hashlib.sha256(url.encode()).hexdigest()+'.json')
  if p.exists():
   try:
    obj=json.loads(p.read_text(encoding='utf-8'))
    if time.time()-obj['saved']<ttl:
     self.last_stamp=pd.Timestamp(obj['saved'],unit='s',tz='UTC').isoformat();return obj['data']
   except (ValueError,KeyError):pass
  if host in self.blocked:raise ValueError('Fuente bloqueada; no se elude el bloqueo.')
  r=requests.get(url,timeout=(8,30))
  if r.status_code in [401,403,429]:self.blocked.add(host)
  r.raise_for_status();self.last_stamp=now().isoformat();d=r.json();p.write_text(json.dumps({'saved':time.time(),'data':d}),encoding='utf-8');self.log.append({'url':url,'fetched_at':now().isoformat()});return d

def event_row(e,sport,code):
 cs=e.get('competitions',[])
 if not cs:return None
 c=cs[0];sides={x.get('homeAway'):x for x in c.get('competitors',[]) if x.get('team')}
 if 'home' not in sides or 'away' not in sides:return None
 st=c.get('status',e.get('status',{})).get('type',{});dt=pd.to_datetime(e.get('date',c.get('date')),utc=True,errors='coerce')
 if pd.isna(dt):return None
 return {'id':str(e['id']),'date':dt,'sport':sport,'code':code,'home_id':str(sides['home']['team']['id']),'away_id':str(sides['away']['team']['id']),'home':sides['home']['team']['displayName'],'away':sides['away']['team']['displayName'],'state':st.get('state'),'status':st.get('name'),'completed':bool(st.get('completed')),'season':int(e.get('season',{}).get('year',dt.year)),'season_type':str(e.get('season',{}).get('type','')),'period':c.get('status',e.get('status',{})).get('period',0)}
def endpoint(sport,code):return f'https://site.api.espn.com/apis/site/v2/sports/{sport}/{code}/'

def box_rows(payload,event,url,fetched):
 rows=[]
 for team in payload.get('boxscore',{}).get('players',[]):
  tid=str(team.get('team',{}).get('id',''));opponent=event['away'] if tid==event['home_id'] else event['home']
  for table in team.get('statistics',[]):
   keys=table.get('keys',[]);category=table.get('name')
   if event['sport']=='baseball':category='pitching' if 'fullInnings.partInnings' in keys else 'batting'
   for entry in table.get('athletes',[]):
    athlete=entry.get('athlete',{});raw=entry.get('stats',[])
    if not athlete.get('id') or len(raw)!=len(keys):continue
    if entry.get('didNotPlay'):continue
    vals=dict(zip(keys,raw));expanded=dict(vals)
    for k,v in vals.items():
     if k in ['completions/passingAttempts','threePointFieldGoalsMade-threePointFieldGoalsAttempted']:
      sep='/' if '/' in k else '-';parts=str(v).split(sep)
      if len(parts)==2:expanded.update(dict(zip(k.split(sep),parts)))
    if category=='passing' and 'interceptions' in expanded:expanded['passingInterceptions']=expanded['interceptions']
    if category=='batting':
     for a,b in [('hits','batterHits'),('homeRuns','batterHomeRuns'),('strikeouts','batterStrikeouts')]:
      if a in expanded:expanded[b]=expanded[a]
    if category=='pitching':
     if 'strikeouts' in expanded:expanded['pitcherStrikeouts']=expanded['strikeouts']
     ip=str(expanded.get('fullInnings.partInnings',''));mt=re.fullmatch(r'(\d+)(?:\.([012]))?',ip)
     if mt:expanded['pitcherOuts']=3*int(mt[1])+int(mt[2] or 0)
    if all(k in expanded and pd.notna(number(expanded[k])) for k in ['points','rebounds','assists']):expanded['PRA']=sum(number(expanded[k]) for k in ['points','rebounds','assists'])
    minutes=expanded.get('minutes',expanded.get('timeOnIce',''))
    if ':' in str(minutes):
     try:mm,ss=str(minutes).split(':');minutes=float(mm)+float(ss)/60
     except ValueError:minutes=np.nan
    else:minutes=number(minutes)
    if pd.notna(minutes) and minutes==0:continue
    for metric,definition in DEFS.items():
     if definition[3] and category!=definition[3]:continue
     value=number(expanded.get(metric))
     if pd.isna(value):continue
     if definition[2]=='count' and (value<0 or value%1):continue
     rows.append({'event_id':event['id'],'date':event['date'],'sport':event['code'],'athlete_id':str(athlete['id']),'athlete':athlete.get('displayName','Jugador'),'team_id':tid,'opponent':opponent,'metric':metric,'value':value,'source_url':url,'fetched_at':fetched,'minutes':minutes,'participated':True,'role':category or 'estadística publicada','starter':entry.get('starter',None)})
 if event['sport']=='soccer' and event.get('period',2)<=2:
  alias={'totalGoals':'goals','totalShots':'shotsTotal','goalAssists':'assists','saves':'totalSaves','shotsOnTarget':'shotsOnTarget'}
  for team in payload.get('rosters',[]):
   tid=str(team.get('team',{}).get('id',''))
   for entry in team.get('roster',[]):
    vals={x.get('name'):x.get('value',x.get('displayValue')) for x in entry.get('stats',[])}
    if number(vals.get('appearances'))!=1:continue
    athlete=entry.get('athlete',{})
    for key,metric in alias.items():
     value=number(vals.get(key))
     if pd.isna(value):continue
     rows.append({'event_id':event['id'],'date':event['date'],'sport':event['code'],'athlete_id':str(athlete.get('id')),'athlete':athlete.get('displayName','Jugador'),'team_id':tid,'opponent':event['away'] if tid==event['home_id'] else event['home'],'metric':metric,'value':value,'source_url':url,'fetched_at':fetched,'minutes':np.nan,'participated':True,'role':'soccer, tiempo reglamentario','starter':entry.get('starter')})
 return rows

REQUIRED=['event_id','date','sport','athlete_id','athlete','metric','value','source_url']
def normalize(df):
 if any(c not in df for c in REQUIRED):raise ValueError('El CSV requiere: '+', '.join(REQUIRED))
 d=df.copy();d['date']=pd.to_datetime(d.date,utc=True,errors='coerce');d['value']=pd.to_numeric(d.value,errors='coerce')
 for c in ['event_id','sport','athlete_id','athlete','metric']:d[c]=d[c].astype(str)
 if 'participated' not in d:d['participated']=True
 else:d['participated']=d.participated.map(lambda x:str(x).lower() in ['true','1','yes','sí'])
 d=d[~d[['event_id','sport','athlete_id','athlete']].apply(lambda c:c.str.strip().str.lower().isin(['','nan','none','<na>'])).any(axis=1)]
 d=d.dropna(subset=['date','value','source_url']);d=d[np.isfinite(d.value)&d.metric.isin(DEFS)]
 d=d[d.source_url.astype(str).str.match(r'^https?://')]
 d=d[~d.metric.map(lambda k:DEFS[k][2]=='continuous') | (d.value>=0)]
 count=d.metric.map(lambda k:DEFS[k][2]=='count');d=d[~count|((d.value>=0)&(d.value%1==0))]
 # Ambiguous duplicates are excluded, never silently counted twice.
 return d.drop_duplicates(['sport','athlete_id','event_id','metric'],keep=False).sort_values('date').reset_index(drop=True)

MODELS={'poisson':'Poisson','nb':'Binomial negativa','normal':'Normal discretizada','continuous':'Normal continua'}
def fit(values,kind):
 x=np.asarray(values,float);mu=float(x.mean());var=float(x.var(ddof=1)) if len(x)>1 else 0.
 if kind=='poisson':return poisson(max(mu,.01))
 if kind=='nb':
  if var<=mu+.001:return poisson(max(mu,.01))
  size=max(.05,mu*mu/max(var-mu,.001));return nbinom(size,size/(size+max(mu,.01)))
 return norm(mu,max(np.sqrt(var),1.))
def probability(x,kind,line):
 law=fit(x,kind)
 if kind=='continuous':under=float(law.cdf(line));push=0.;over=1-under
 elif kind in ['poisson','nb']:
  under=float(law.cdf(math.ceil(line)-1));over=float(law.sf(math.floor(line)));push=max(0.,1-under-over)
  if not float(line).is_integer():over=1-under;push=0.
 else:
  # Yardage is an integer statistic and may legitimately be negative.
  if float(line).is_integer():under=float(law.cdf(line-.5));over=float(law.sf(line+.5));push=max(0.,1-under-over)
  else:under=float(law.cdf(math.floor(line)+.5));over=1-under;push=0.
 return np.array([over,under,push])
def predictive_logloss(x,kind,value):
 law=fit(x,kind)
 if kind in ['poisson','nb']:p=law.pmf(value)
 elif kind=='continuous':return -float(law.logpdf(value))
 else:p=law.cdf(value+.5)-law.cdf(value-.5)
 return -math.log(max(float(p),1e-12))
def candidates(metric):return ['poisson','nb'] if DEFS[metric][2]=='count' else ['continuous'] if DEFS[metric][2]=='continuous' else ['normal']
def choose(values,metric,dates=None):
 kinds=candidates(metric)
 if len(values)<12:return kinds[0],{}
 scores={}
 for k in kinds:
  losses=[]
  for i in range(max(8,len(values)-8),len(values)):
   train=values[:i] if dates is None else np.asarray(values[:i])[np.asarray(dates[:i])<dates[i]]
   if len(train)>=8:losses.append(predictive_logloss(train,k,values[i]))
  if losses:scores[k]=float(np.mean(losses))
 if not scores:return kinds[0],{}
 return min(scores,key=scores.get),scores

def analyze_sample(sample,metric,line,over_odds,under_odds,bankroll,context_confirmed,cutoff,coverage=None):
 d=sample[(sample.date<min(cutoff,now()))&sample.participated].sort_values('date').tail(40)
 x=d.value.to_numpy(float)
 if len(x)<8:raise ValueError(f'Solo hay {len(x)} observaciones válidas; mínimo 8 para un análisis exploratorio.')
 if not math.isfinite(line):raise ValueError('Línea no finita.')
 if DEFS[metric][2]!='continuous' and abs(line*2-round(line*2))>1e-8:raise ValueError('Usa una línea entera o de medio punto.')
 kind,scores=choose(x,metric,d.date.to_numpy());pr=probability(x,kind,line);age=(cutoff-d.date.max()).total_seconds()/86400
 # Outer predictions choose the family solely on each earlier training window.
 back=[]
 for i in range(12,len(x)):
  mask=d.date.to_numpy()[:i]<d.iloc[i].date;train=x[:i][mask]
  if len(train)<12:continue
  family,_=choose(train,metric,d.date.to_numpy()[:i][mask]);p=probability(train,family,line);y=0 if x[i]>line else 1 if x[i]<line else 2
  back.append({'date':str(d.iloc[i].date),'value':x[i],'model':family,'p_over':p[0],'p_under':p[1],'p_push':p[2],'logloss':-math.log(max(float(p[y]),1e-12)),'brier':float(np.sum((p-np.eye(3)[y])**2))})
 warnings=[]
 if len(x)<20:warnings.append('Menos de 20 observaciones; no se habilita stake.')
 if age>90:warnings.append(f'Última observación hace {age:.0f} días: historial antiguo.')
 if not context_confirmed:warnings.append('Participación y reglas del mercado pendientes de confirmar por el usuario.')
 if coverage is not None and coverage<.9:warnings.append(f'Solo {coverage:.0%} de los partidos consultados tiene esta estadística explícita. Las ausencias no son ceros.')
 if len(back)<8:warnings.append('Menos de ocho pronósticos retrospectivos externos; evaluación insuficiente.')
 results=[]
 for label,pwin,ploss,odd in [('MÁS DE',pr[0],pr[1],odds(over_odds)),('MENOS DE',pr[1],pr[0],odds(under_odds))]:
  p=float(pwin/(pwin+ploss)) if pwin+ploss else 0.;b=dec(odd)-1;ev=b*pwin-ploss;edge=p-1/dec(odd);kelly=max(0.,(b*pwin-ploss)/(b*(pwin+ploss))) if pwin+ploss else 0.
  hits=int((x>line).sum()) if label=='MÁS DE' else int((x<line).sum());miss=int((x<line).sum()) if label=='MÁS DE' else int((x>line).sum())
  low=float(beta.ppf(.05,hits+.5,miss+.5));high=float(beta.ppf(.95,hits+.5,miss+.5))
  passes=bool(edge>.03 and ev>0);eligible=passes and not warnings and low>1/dec(odd)
  results.append({'Selección':label,'Cuota':odd,'Gana':float(pwin),'Pierde':float(ploss),'Devuelve':float(pr[2]),'Prob efectiva':p,'Ventaja':edge,'EV':float(ev),'Pasa valor':passes,'Elegible prudente':eligible,'Kelly completo':kelly,'Stake USD':bankroll*.25*kelly if eligible else 0.,'Frecuencia limite inferior':low,'Frecuencia limite superior':high})
 return {'data':d,'kind':kind,'scores':scores,'prob':pr,'rows':results,'backtest':back,'warnings':warnings,'age':age,'metric':metric,'line':line}

def make_report(result,bankroll,context,target):
 d=result['data'];x=d.value;last=d.iloc[-1];metric=result['metric'];line=result['line'];title,unit,_,_=DEFS[metric];out=[CSS,'<article class="props">',f'<h1>{esc(last.athlete)} · {esc(title)}</h1><p>{esc(target)} · línea {line:g} {esc(unit)} · ATLAS PROPS 1.0</p><h2>Previa del jugador</h2>']
 recent=x.tail(5);out.append(f'<p>En las últimas {len(recent)} observaciones disponibles, {esc(last.athlete)} promedió {recent.mean():.2f} {esc(unit)}, frente a {x.mean():.2f} en los {len(x)} registros utilizados. La mediana es {x.median():.2f}; el mínimo observado {x.min():g} y el máximo {x.max():g}. Esta comparación describe su producción, pero no confirma minutos, titularidad ni el rival del próximo encuentro.</p>')
 out.append(f'<h3>01 · Qué aporta el historial</h3><p>Superó la línea actual {int((x>line).sum())}/{len(x)} veces, quedó por debajo {int((x<line).sum())} y la igualó {int((x==line).sum())}. El conteo usa exclusivamente valores publicados o importados: no se rellena con cero un partido sin registro. Si solo aparecen partidos con acciones, el historial puede estar sesgado; comprueba esa cobertura.</p>')
 if 'minutes' in d and pd.to_numeric(d.minutes,errors='coerce').notna().any():
  mins=pd.to_numeric(d.minutes,errors='coerce').dropna();out.append(f'<p>Minutos publicados: media {mins.mean():.1f}, últimos disponibles {mins.tail(5).mean():.1f}. Se muestran como contexto; no se convierte esa media en una confirmación de minutos futuros.</p>')
 out.append(f'<h3>02 · Modelo y comparación</h3><p>Familia seleccionada: <b>{esc(MODELS[result["kind"]])}</b>. Para conteos se compara Poisson con binomial negativa mediante predicciones temporales anteriores. Para yardas se usa una normal discretizada, que permite valores negativos; para duración, una normal continua exploratoria. La selección no implica que sean los mejores modelos posibles ni que estén calibrados.</p>')
 if result['scores']:out.append('<p>Error predictivo usado para elegir familia (menor es mejor): '+', '.join(f'{MODELS[k]} {v:.3f}' for k,v in result['scores'].items())+'.</p>')
 out.append('<h3>03 · Valor, liquidación e importe</h3>')
 for r in result['rows']:
  status='Candidato prudente' if r['Elegible prudente'] else 'Valor teórico, sin stake' if r['Pasa valor'] else 'No supera el filtro'
  out.append(f'<section class="box"><h3>{r["Selección"]} {line:g} · {american(r["Cuota"])} — {status}</h3><p>Gana {r["Gana"]:.2%}; pierde {r["Pierde"]:.2%}; devuelve {r["Devuelve"]:.2%}. Probabilidad efectiva {r["Prob efectiva"]:.2%}, frente a {1/dec(r["Cuota"]):.2%} exigido por la cuota. Ventaja {100*r["Ventaja"]:+.2f} puntos; EV teórico por USD 100: USD {100*r["EV"]:+.2f}.</p><p>Intervalo bayesiano central del 90% para la frecuencia histórica, excluyendo empates de línea: {r["Frecuencia limite inferior"]:.1%}–{r["Frecuencia limite superior"]:.1%}. No es un intervalo garantizado para el próximo partido ni incorpora cambios de rol. Se exige que su extremo inferior supere el equilibrio para habilitar importe.</p><p>Banca USD {bankroll:,.2f}; ¼ Kelly, sujeto a los controles: <b>USD {r["Stake USD"]:.2f}</b>. Si no pasa los controles, se propone USD 0 aunque el EV puntual sea positivo.</p></section>')
 out.append('<h3>04 · Prueba retrospectiva</h3>')
 bt=pd.DataFrame(result['backtest'])
 if len(bt):out.append(f'<p>{len(bt)} predicciones temporales: log loss {bt.logloss.mean():.3f}, Brier {bt.brier.mean():.3f}. En cada paso se eligió el modelo usando solo observaciones anteriores. Se aplica la línea actual a todo el historial; no había cuotas históricas verificadas, por lo que NO se calcula ROI ni se afirma rentabilidad.</p><details><summary>Ver evaluación</summary>'+bt.to_html(index=False,escape=True,float_format=lambda v:f'{v:.3f}')+'</details>')
 else:out.append('<p>No hay suficientes observaciones para la evaluación temporal.</p>')
 out.append('<h3>05 · Riesgos que pueden invalidar la lectura</h3><p>Lesiones, suplencia, cambios de equipo o rol, restricciones de minutos, rival, superficie en tenis y duración pactada en UFC no se ajustan automáticamente. Retiradas, DNP, prórrogas, titularidad de pitchers y reglas de touchdowns dependen de la casa. El sistema no interpreta un TD de pase como touchdown anotado del jugador. No combina apuestas correlacionadas.</p>')
 for w in result['warnings']:out.append('<p><b>Control:</b> '+esc(w)+'</p>')
 if context:out.append('<p><b>Contexto declarado por el usuario, sin verificación automática:</b> '+esc(context)+'</p>')
 out.append('<h3>06 · Veredicto</h3><p>'+('Hay candidatos que superan el filtro de valor y los controles configurados. Siguen siendo estimaciones experimentales; no un acierto demostrado.' if any(r['Elegible prudente'] for r in result['rows']) else 'No hay selección habilitada para stake con estos controles. El sistema conserva el análisis, pero no fuerza un pick.')+'</p>')
 out.append(f'<h2>Datos y procedencia</h2><p>Primera observación: {d.date.min()}; última: {d.date.max()}. Hay enlaces por registro para contrastar con la fuente. Un enlace declarado en un CSV no equivale a una verificación automática de sus valores.</p><div class="scroll">')
 shown=d[['date','athlete','value','source_url']].copy();out.append(shown.to_html(index=False,escape=True));out.append('</div></article>');return ''.join(out)

class PropsDesk:
 def __init__(self):
  self.store=Store();self.games=pd.DataFrame();self.data=pd.DataFrame();self.events=[];self.last_report='';self.origin='';self.target_key=None
  self.sport=W.Dropdown(description='Deporte',options=list(SPORTS));self.code=W.Text(description='Liga soccer',value='eng.1');self.date=W.DatePicker(description='Fecha',value=datetime.now(ZoneInfo('America/New_York')).date());self.zone=W.Dropdown(description='Zona',options=['America/New_York','America/Chicago','America/Los_Angeles','America/Bogota','Europe/Madrid'])
  self.search=W.Button(description='Buscar encuentros',button_style='info');self.search.on_click(self.load_games);self.game=W.Dropdown(description='Encuentro',options=[],layout=W.Layout(width='98%'));self.team=W.Dropdown(description='Equipo',options=[],layout=W.Layout(width='98%'))
  self.limit=W.BoundedIntText(description='Historial',value=30,min=12,max=50);self.collect=W.Button(description='Cargar jugadores e historial',button_style='info');self.collect.on_click(self.load_players)
  self.player=W.Dropdown(description='Jugador',options=[],layout=W.Layout(width='98%'));self.metric=W.Dropdown(description='Prop',options=[],layout=W.Layout(width='98%'));self.only_starts=W.Checkbox(description='Solo titularidades confirmadas por la fuente',value=False,indent=False,layout=W.Layout(width='98%'))
  self.line=W.FloatText(description='Línea',value=0.5);self.over=W.Text(description='Cuota más de',placeholder='-110');self.under=W.Text(description='Cuota menos',placeholder='-110');self.bank=W.BoundedFloatText(description='Banca USD',value=1000,min=1,max=10000000)
  self.target=W.Text(description='Próximo rival',placeholder='Solo para datos importados; descripción del encuentro',layout=W.Layout(width='98%'));self.target_date=W.DatePicker(description='Fecha objetivo',value=datetime.now(ZoneInfo('America/New_York')).date())
  self.context=W.Textarea(description='Contexto',placeholder='Participación, rol, minutos previstos, rival, fuente y fecha. No ajusta automáticamente la probabilidad.',layout=W.Layout(width='98%',height='110px'))
  self.confirm=W.Checkbox(description='Comprobé participación y reglas de esta apuesta; los datos corresponden a este jugador.',indent=False,layout=W.Layout(width='98%'))
  self.go=W.Button(description='Generar análisis del prop',button_style='success');self.go.on_click(self.calculate);self.export=W.Button(description='Descargar informe y datos',disabled=True);self.export.on_click(self.download)
  self.msg=W.HTML('<p>Selecciona deporte. Tenis y UFC utilizan importación documentada; no tienen conector automático activo.</p>');self.out=W.HTML()
  self.analysis=W.VBox([self.sport,self.code,self.date,self.zone,self.search,self.game,self.team,self.limit,self.collect,self.player,self.metric,self.only_starts,W.HTML('<p>Props de partido completo según la fuente; verifica prórrogas, retiradas y condiciones de participación. MLB: no confundas ponches del bateador con los del lanzador.</p>'),self.line,self.over,self.under,self.bank,self.target,self.target_date,self.context,self.confirm,self.go,self.export,self.msg,self.out])
  self.upload=W.FileUpload(accept='.csv',description='Subir CSV');self.upload.observe(self.upload_csv,names='value');self.native=W.Button(description='Importar CSV con Colab');self.native.on_click(self.native_csv);self.upload_log=W.Output();self.csvmsg=W.HTML()
  self.library=W.VBox([W.HTML('<h2>Biblioteca y cobertura</h2><p>Conectores ESPN: NFL, NCAA fútbol americano, NBA, WNBA, NCAA baloncesto, MLB, NHL y soccer por código de liga. La cobertura depende de las tablas publicadas. Tenis y UFC: CSV con datos reales y enlace por registro; no se simula una descarga que no existe.</p><p>Columnas: event_id,date,sport,athlete_id,athlete,metric,value,source_url. Opcionales: minutes,participated,starter,opponent,role,fetched_at. Se excluyen duplicados ambiguos y datos no numéricos. Un CSV puede contener varios jugadores y deportes: se separan por identidad y métrica.</p><p><a href="https://baseballsavant.mlb.com/csv-docs">MLB Statcast: documentación</a> · <a href="https://github.com/nflverse/nflverse-data">nflverse</a> · <a href="http://ufcstats.com/statistics/events/completed?page=all">UFCStats</a> · <a href="https://www.tennis-data.co.uk/">Tennis-Data</a></p><p>Los archivos de estas fuentes no son intercambiables sin adaptar columnas. Los resultados de tenis por partido no contienen necesariamente aces; UFC puede requerir datos por asalto y contexto de duración. No se consideran esos conectores implementados.</p>'),self.native,self.upload_log,self.upload,self.csvmsg])
  self.images=W.FileUpload(accept='.png,.jpg,.jpeg',multiple=True,description='Subir capturas');self.ocr_btn=W.Button(description='Leer capturas');self.ocr_btn.on_click(self.ocr);self.ocr_text=W.Textarea(layout=W.Layout(width='98%',height='260px'));self.ocr_msg=W.HTML();self.use_text=W.Button(description='Usar texto revisado como contexto');self.use_text.on_click(self.attach_context)
  self.captures=W.VBox([W.HTML('<h2>Capturas del jugador</h2><p>OCR gratuito local. Revisa la transcripción antes de adjuntarla; no se convierte automáticamente en historial ni modifica números. El informe cuantitativo usa las filas de la biblioteca.</p>'),self.images,self.ocr_btn,self.ocr_msg,self.ocr_text,self.use_text])
  self.validation=W.HTML('<h2>Validación y controles</h2><p>El informe realiza evaluación temporal: en cada partido de prueba el modelo se elige con los datos anteriores. Se evalúa la línea actual, no cuotas históricas. No se calcula rentabilidad retrospectiva sin precios verificables. Conteos: Poisson frente a binomial negativa; yardas: normal discretizada; duraciones: normal continua exploratoria.</p><p>Para habilitar stake se exigen más de 3 puntos de ventaja, EV positivo, al menos 20 datos y ocho pruebas temporales, dato reciente, confirmación de reglas y un límite inferior de frecuencia histórica superior al equilibrio. Son filtros de prudencia, no validación de eficacia.</p><p>Los datos faltantes, lesiones, rivales y cambios de rol pueden invalidar las estimaciones. No se promete el mejor modelo ni ganancias.</p>')
  self.sections=[self.analysis,self.library,self.captures,self.validation];self.body=W.VBox([self.analysis]);buttons=[]
  for i,name in enumerate(['Análisis','Datos','Capturas','Metodología']):
   b=W.Button(description=name);b.on_click(lambda _,index=i:setattr(self.body,'children',[self.sections[index]]));buttons.append(b)
  self.root=W.VBox([W.HTML(CSS+'<div class="props"><h1>ATLAS PROPS</h1><p>Jugadores · Datos trazables · Modelos contrastables</p></div>'),W.HBox(buttons),self.body]);display(self.root)
  self.sport.observe(self.reset,names='value')
  for field in [self.date,self.code,self.zone]:field.observe(self.reset,names='value')
  self.game.observe(self.change_game,names='value');self.team.observe(self.change_team,names='value');self.player.observe(self.change_player,names='value')
  for w in [self.metric,self.line,self.over,self.under,self.bank,self.context,self.confirm,self.only_starts,self.target,self.target_date]:w.observe(self.invalidate,names='value')
 def invalidate(self,*_):self.last_report='';self.out.value='';self.export.disabled=True
 def reset(self,*_):
  self.games=pd.DataFrame();self.game.options=[];self.team.options=[];self.clear_data();self.msg.value='<p>Busca encuentros o importa un CSV documentado.</p>'
 def clear_data(self):
  self.data=pd.DataFrame();self.player.options=[];self.metric.options=[];self.events=[];self.origin='';self.confirm.value=False;self.invalidate()
 def change_game(self,*_):
  self.clear_data()
  if self.game.value is not None and not self.games.empty:
   g=self.games.loc[self.game.value];self.team.options=[(g.home,g.home_id),(g.away,g.away_id)];self.team.value=g.home_id
 def change_team(self,*_):self.clear_data()
 def change_player(self,*_):
  self.confirm.value=False;self.invalidate();self.metric.options=[]
  if self.player.value is not None and not self.data.empty:
   sport,aid=self.player.value;d=self.data[(self.data.sport==sport)&(self.data.athlete_id==aid)]
   self.metric.options=[(DEFS[k][0],k) for k in sorted(d.metric.unique())];self.metric.value=self.metric.options[0][1] if self.metric.options else None
 def load_games(self,_):
  self.search.disabled=True;self.reset()
  try:
   config=SPORTS[self.sport.value]
   if config is None:raise ValueError('Este deporte utiliza Datos → importar CSV. No hay un conector reciente automático activo.')
   sport,code=config
   if sport=='soccer':code=self.code.value.strip()
   if not re.fullmatch(r'[a-z0-9.-]+',code):raise ValueError('Código de competición inválido.')
   if not self.date.value:raise ValueError('Selecciona fecha.')
   start=pd.Timestamp(self.date.value).tz_localize(self.zone.value).tz_convert('UTC');end=start+pd.Timedelta(days=1);rows={}
   for dt in pd.date_range(start.normalize(),end.normalize()):
    suffix='&groups=80' if code=='college-football' else ''
    d=self.store.get(endpoint(sport,code)+f'scoreboard?dates={dt:%Y%m%d}&limit=1000'+suffix,120)
    for e in d.get('events',[]):
     row=event_row(e,sport,code)
     if row and row['state']=='pre' and row['status']=='STATUS_SCHEDULED' and max(start,now())<row['date']<end and row['season_type']!='1':rows[row['id']]=row
   self.games=pd.DataFrame(rows.values());self.game.options=[(f'{g.date.tz_convert(self.zone.value):%H:%M} · {g.away} @ {g.home}',i) for i,g in self.games.iterrows()];self.game.value=0 if len(self.games) else None
   self.msg.value=f'<p>{len(self.games)} encuentros pendientes no de pretemporada. Selecciona equipo y carga el historial.</p>'
  except Exception as e:self.msg.value='<p>'+esc(e)+'</p>'
  finally:self.search.disabled=False
 def load_players(self,_):
  self.collect.disabled=True;self.clear_data()
  try:
   if self.game.value is None:raise ValueError('Selecciona encuentro y equipo.')
   g=self.games.loc[self.game.value];team=str(self.team.value);events={};warnings=[]
   self.msg.value='<p>Consultando calendarios históricos…</p>'
   for year in [g.season-1,g.season]:
    for st in [2,3]:
     try:
      d=self.store.get(endpoint(g.sport,g.code)+f'teams/{team}/schedule?season={year}&seasontype={st}',21600)
      for e in d.get('events',[]):
       row=event_row(e,g.sport,g.code)
       if row and row['completed'] and row['date']<min(g.date,now()) and row['date']>=g.date-pd.Timedelta(days=730) and row['season_type']!='1':events[row['id']]=row
     except Exception as e:warnings.append(str(e))
   ordered=sorted(events.values(),key=lambda x:x['date'])[-self.limit.value:];rows=[];loaded=[]
   for i,event in enumerate(ordered,1):
    self.msg.value=f'<p>Leyendo estadísticas individuales {i}/{len(ordered)}…</p>'
    try:
     url=endpoint(g.sport,g.code)+f'summary?event={event["id"]}';payload=self.store.get(url,86400*7)
     extracted=box_rows(payload,event,url,self.store.last_stamp);rows.extend(r for r in extracted if r['team_id']==team);loaded.append(event)
    except Exception as e:warnings.append(f'{event["id"]}: {e}')
   if not rows:raise ValueError('No se obtuvieron estadísticas individuales compatibles. Usa importación con fuente; no se rellena con ceros.')
   self.data=normalize(pd.DataFrame(rows));self.events=ordered;self.origin='ESPN';self.set_players()
   self.msg.value=f'<p>{len(self.data)} estadísticas explícitas en {len(loaded)}/{len(ordered)} boxscores. Última observación: {self.data.date.max()}. Jugadores históricos, no convocatoria actual; confirma equipo y rol.</p>'+''.join('<p>'+esc(x)+'</p>' for x in warnings)
  except Exception as e:self.msg.value='<p>'+esc(e)+'</p>'
  finally:self.collect.disabled=False
 def set_players(self):
  d=self.data[['sport','athlete_id','athlete']].drop_duplicates(['sport','athlete_id']);self.player.options=[(f'{x.athlete} · {x.sport}',(x.sport,x.athlete_id)) for _,x in d.sort_values('athlete').iterrows()];self.player.value=self.player.options[0][1] if self.player.options else None
 def import_bytes(self,content):
  df=normalize(pd.read_csv(io.BytesIO(content),dtype={'athlete_id':str,'event_id':str}))
  if df.empty:raise ValueError('No quedaron filas válidas. Revisa columnas, métricas y URLs.')
  self.clear_data();self.data=df;self.origin='CSV aportado por usuario';self.set_players();self.csvmsg.value=f'<p>{len(df)} filas importadas; fecha más reciente {df.date.max()}. En Análisis elige jugador, prop y fecha objetivo. Los valores del CSV no se verificaron automáticamente.</p>'
 def upload_csv(self,*_):
  try:
   values=items(self.upload.value)
   if values:self.import_bytes(bytes(values[0]['content']))
  except Exception as e:self.csvmsg.value='<p>'+esc(e)+'</p>'
 def native_csv(self,_):
  try:
   from google.colab import files
   with self.upload_log:uploaded=files.upload()
   if len(uploaded)!=1:raise ValueError('Selecciona un CSV.')
   self.import_bytes(next(iter(uploaded.values())))
  except Exception as e:self.csvmsg.value='<p>'+esc(e)+'</p>'
 def calculate(self,_):
  self.go.disabled=True;self.invalidate()
  try:
   if self.player.value is None or self.metric.value is None:raise ValueError('Carga datos y selecciona jugador y prop.')
   sport,aid=self.player.value;d=self.data[(self.data.sport==sport)&(self.data.athlete_id==aid)&(self.data.metric==self.metric.value)].copy()
   coverage=None
   if self.origin=='ESPN':
    g=self.games.loc[self.game.value];payload=self.store.get(endpoint(g.sport,g.code)+f'summary?event={g.id}',0);head=payload.get('header',{});cs=head.get('competitions',[])
    if not cs:raise ValueError('No se pudo confirmar el encuentro.')
    head=dict(head);head['date']=cs[0].get('date',head.get('date'));fresh=event_row(head,g.sport,g.code)
    if not fresh or fresh['state']!='pre' or fresh['status']!='STATUS_SCHEDULED' or fresh['date']<=now():raise ValueError('El encuentro no sigue pendiente. Actualiza el calendario.')
    cutoff=fresh['date'];target=g.away+' @ '+g.home+' · '+str(cutoff)
    coverage=len(set(d.event_id))/max(len(self.events),1)
   else:
    if not self.target_date.value:raise ValueError('Indica fecha objetivo.')
    cutoff=pd.Timestamp(self.target_date.value).tz_localize(self.zone.value).tz_convert('UTC')
    if self.target_date.value<datetime.now(ZoneInfo(self.zone.value)).date():raise ValueError('Fecha objetivo anterior a hoy.')
    target=self.target.value.strip() or 'Encuentro declarado por usuario, sin verificación automática'
   if self.only_starts.value:
    if 'starter' not in d:raise ValueError('La fuente no identifica titularidades.')
    d=d[d.starter.map(lambda v:str(v).lower() in ['true','1'])]
   result=analyze_sample(d,self.metric.value,self.line.value,self.over.value,self.under.value,self.bank.value,self.confirm.value,cutoff,coverage)
   # Imported data are not verified; always retain an explicit provenance limitation.
   if self.origin!='ESPN':
    result['warnings'].append('CSV no verificado automáticamente: los importes quedan deshabilitados hasta cotejar y validar el conjunto.')
    for r in result['rows']:r['Stake USD']=0.;r['Elegible prudente']=False
   document=make_report(result,self.bank.value,self.context.value,target);self.out.value=document;self.last_report=document
   folder=Path('atlas_props_salida');folder.mkdir(exist_ok=True);(folder/'Informe.html').write_text('<!doctype html><html lang="es"><meta charset="utf-8">'+document+'</html>',encoding='utf-8');result['data'].to_csv(folder/'Historial.csv',index=False);pd.DataFrame(result['rows']).to_csv(folder/'Selecciones.csv',index=False);pd.DataFrame(result['backtest']).to_csv(folder/'Validacion.csv',index=False)
   audit={'version':VERSION,'origen':self.origin,'jugador':aid,'deporte':sport,'metrica':self.metric.value,'linea':self.line.value,'cuotas':[self.over.value,self.under.value],'cutoff':str(cutoff),'contexto':self.context.value,'modelo':result['kind'],'avisos':result['warnings'],'consultas':self.store.log,'banca':self.bank.value}
   (folder/'Auditoria.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
   with zipfile.ZipFile('ATLAS_PROPS_informe.zip','w',zipfile.ZIP_DEFLATED) as z:
    for file in folder.iterdir():z.write(file,file.name)
   self.export.disabled=False;self.msg.value='<p>Informe listo. Revisa primero cobertura y controles; no todas las estimaciones habilitan una apuesta.</p>'
  except Exception as e:self.msg.value='<p>No se completó: '+esc(e)+'</p>'
  finally:self.go.disabled=False
 def download(self,_):
  from google.colab import files
  files.download('ATLAS_PROPS_informe.zip')
 def ocr(self,_):
  self.ocr_btn.disabled=True
  try:
   from PIL import Image,ImageOps
   import pytesseract
   values=items(self.images.value)
   if not 1<=len(values)<=3:raise ValueError('Selecciona entre una y tres imágenes.')
   texts=[]
   for value in values:
    raw=bytes(value['content'])
    if len(raw)>15_000_000:raise ValueError('Imagen mayor a 15 MB.')
    im=Image.open(io.BytesIO(raw));im.load()
    if im.width*im.height>25_000_000:raise ValueError('Recorta la imagen: es demasiado grande.')
    im=ImageOps.grayscale(im);im=im.resize((im.width*2,im.height*2));texts.append(str(value['name'])+'\n'+pytesseract.image_to_string(im,config='--psm 6'))
   self.ocr_text.value='\n\n'.join(texts);self.ocr_msg.value='<p>Revisa decimales, columnas, identidad y fecha. La lectura puede contener errores.</p>'
  except Exception as e:self.ocr_msg.value='<p>'+esc(e)+'</p>'
  finally:self.ocr_btn.disabled=False
 def attach_context(self,_):
  self.context.value=self.ocr_text.value;self.ocr_msg.value='<p>Texto incorporado al contexto del siguiente informe. No altera estadísticas.</p>'


# Capturas: lectura local, revisión e investigación trazable.
DEFS['punts']=('Despejes de punt','punts','count','punting')
ALIASES={'PRA':'PRA','Punts':'punts','Points':'points','Rebounds':'rebounds','Assists':'assists','Pass Yards':'passingYards','Passing Yards':'passingYards','Rush Yards':'rushingYards','Receiving Yards':'receivingYards','Receptions':'receptions','Pitcher Strikeouts':'pitcherStrikeouts','Shots on Target':'shotsOnTarget'}
def parse_ticket(text):
 lines=[s.strip() for s in text.splitlines() if s.strip()];found=[];sport=''
 for i,s in enumerate(lines):
  for league in ['WNBA','NFL','NBA','MLB','NHL']:
   if re.search(r'\b'+league+r'\b',s):sport=league
  m=re.search(r'(\d+(?:[.,]\d+)?)\s+('+'|'.join(sorted(map(re.escape,ALIASES),key=len,reverse=True))+r')\b',s,re.I)
  if not m:continue
  key=next(k for k in ALIASES if k.lower()==m[2].lower());name=s[:m.start()].strip(' :-')
  if not name:
   for prior in reversed(lines[max(0,i-3):i]):
    if re.fullmatch(r"[A-Za-zÀ-ÿ .’'-]{4,60}",prior) and not re.search(r'Less|More|PLAYERS|PRIZEPICKS',prior,re.I):name=prior;break
  found.append({'jugador':name,'deporte':sport,'metrica':ALIASES[key],'linea':float(m[1].replace(',','.')),'lado':'SIN CONFIRMAR'})
 return found

def screenshot_text(raw):
 from PIL import Image,ImageOps
 if len(raw)>15_000_000:raise ValueError('Máximo 15 MB por imagen.')
 im=Image.open(io.BytesIO(raw));im.load()
 if im.width*im.height>20_000_000:raise ValueError('Imagen demasiado grande; recorta el boleto.')
 im=ImageOps.grayscale(ImageOps.exif_transpose(im));im=ImageOps.autocontrast(im)
 from rapidocr_onnxruntime import RapidOCR
 result,_=RapidOCR()(np.array(im.convert('RGB')))
 return '\n'.join(r[1] for r in (result or []))


def discover_news(player):
 from urllib.parse import urlencode,urlparse
 import xml.etree.ElementTree as ET
 query=urlencode({'q':'"'+player+'" when:14d','hl':'en-US','gl':'US','ceid':'US:en'})
 url='https://news.google.com/rss/search?'+query
 r=requests.get(url,timeout=(8,20));r.raise_for_status()
 root=ET.fromstring(r.content);rows=[]
 for item in root.findall('./channel/item')[:8]:
  link=item.findtext('link','');stamp=pd.to_datetime(item.findtext('pubDate'),utc=True,errors='coerce')
  if urlparse(link).scheme not in ['https','http'] or pd.isna(stamp) or stamp>now() or stamp<now()-pd.Timedelta(days=15):continue
  rows.append({'titulo':item.findtext('title',''),'medio':item.findtext('source',''),'fecha':str(stamp),'url':link})
 return rows,{'url':url,'consultado':str(now()),'tipo':'Índice RSS; artículos no leídos'}

class CaptureDesk(PropsDesk):
 def __init__(self):
  super().__init__();self.pending=None
  self.ticket_upload=W.FileUpload(accept='.png,.jpg,.jpeg',description='Subir boleto');self.read_ticket=W.Button(description='Leer captura',button_style='info');self.read_ticket.on_click(self.read_capture)
  self.ticket_native=W.Button(description='Subir desde Colab');self.ticket_native.on_click(self.native_ticket);self.ticket_log=W.Output()
  self.ticket_text=W.Textarea(description='OCR',layout=W.Layout(width='98%',height='130px'))
  self.ticket_json=W.Textarea(description='Selecciones',value='[]',layout=W.Layout(width='98%',height='220px'))
  self.ticket_parse=W.Button(description='Interpretar texto revisado');self.ticket_parse.on_click(lambda _:self.interpret())
  self.pick_index=W.BoundedIntText(description='Selección nº',value=1,min=1,max=20)
  self.detected_name=W.Text(description='Jugador',layout=W.Layout(width='95%'))
  self.detected_sport=W.Dropdown(description='Deporte',options=list(SPORTS))
  self.detected_metric=W.Dropdown(description='Mercado',options=[(v[0],k) for k,v in DEFS.items()],layout=W.Layout(width='95%'))
  self.detected_line=W.FloatText(description='Línea',value=.5)
  self.pick_index.observe(self.show_detected,names='value')
  self.ticket_json.layout.display='none'

  self.ticket_side=W.Dropdown(description='Elegiste',options=['SIN CONFIRMAR','Más de','Menos de'])
  self.ticket_check=W.Checkbox(description='Revisé jugador, deporte, mercado, línea y fecha completa.',indent=False)
  self.ticket_start=W.Button(description='Buscar partido de esta selección',button_style='info');self.ticket_start.on_click(self.start_pick)
  self.ticket_msg=W.HTML();self.research_btn=W.Button(description='Investigar y explicar selección',button_style='success');self.research_btn.on_click(self.research_pick)
  self.research_out=W.HTML();self.research_download=W.Button(description='Descargar investigación',disabled=True);self.research_download.on_click(self.download_research)
  self.capture_panel=W.VBox([W.HTML('<h2>Del boleto a la evidencia</h2><p>1. Sube una captura. 2. Revisa los campos detectados. 3. Indica fecha, busca el partido y carga el equipo en Análisis. 4. Vuelve aquí para investigar. El color de Más/Menos requiere tu confirmación. La imagen no proporciona fecha completa.</p>'),self.ticket_native,self.ticket_log,self.ticket_upload,self.read_ticket,self.ticket_text,self.ticket_parse,self.ticket_json,self.pick_index,self.detected_name,self.detected_sport,self.detected_metric,self.detected_line,self.ticket_side,self.date,self.ticket_check,self.ticket_start,self.ticket_msg,self.research_btn,self.research_download,self.research_out])
  self.sections.insert(0,self.capture_panel);self.body.children=[self.capture_panel];buttons=[]
  for i,name in enumerate(['Boleto','Análisis / historial','Datos','Capturas de apoyo','Metodología']):
   b=W.Button(description=name);b.on_click(lambda _,j=i:setattr(self.body,'children',[self.sections[j]]));buttons.append(b)
  self.root.children=[W.HTML(CSS+'<div class="props"><h1>ATLAS LENS</h1><p>Una captura. Una investigación documentada. Sin APIs de pago.</p></div>'),W.HBox(buttons),self.body]
  for field in [self.detected_name,self.detected_sport,self.detected_metric,self.detected_line,self.ticket_json,self.ticket_side,self.ticket_check,self.date,self.game,self.team,self.player,self.metric,self.line]:field.observe(self.clear_research,names='value')
 def clear_research(self,*_):
  self.research_out.value='';self.research_download.disabled=True
 def interpret(self):
  self.ticket_json.value=json.dumps(parse_ticket(self.ticket_text.value),ensure_ascii=False,indent=2);self.ticket_check.value=False
  self.show_detected()
  self.ticket_msg.value='<p>Revisa los campos detectados. Si el OCR omitió un jugador, escribe su nombre, mercado y línea en los campos. No se adivinan líneas ni selecciones.</p>'
 def show_detected(self,*_):
  rows=json.loads(self.ticket_json.value)
  if not rows:return
  p=rows[min(self.pick_index.value-1,len(rows)-1)]
  self.detected_name.value=p['jugador']
  if p['deporte'] in SPORTS:self.detected_sport.value=p['deporte']
  self.detected_metric.value=p['metrica'];self.detected_line.value=p['linea'];self.ticket_side.value='SIN CONFIRMAR';self.ticket_check.value=False
 def consume_capture(self,raw):
  self.ticket_text.value=screenshot_text(raw);self.interpret()
 def read_capture(self,_):
  try:
   values=items(self.ticket_upload.value)
   if len(values)!=1:raise ValueError('Sube exactamente una captura.')
   self.consume_capture(bytes(values[0]['content']))
  except Exception as e:self.ticket_msg.value='<p>'+esc(e)+'</p>'
 def native_ticket(self,_):
  try:
   from google.colab import files
   with self.ticket_log:uploaded=files.upload()
   if len(uploaded)!=1:raise ValueError('Selecciona una imagen.')
   self.consume_capture(next(iter(uploaded.values())))
  except Exception as e:self.ticket_msg.value='<p>'+esc(e)+'</p>'
 def start_pick(self,_):
  try:
   if not self.ticket_check.value or self.ticket_side.value=='SIN CONFIRMAR':raise ValueError('Revisa los datos y confirma el lado elegido.')
   pick={'jugador':self.detected_name.value.strip(),'deporte':self.detected_sport.value,'metrica':self.detected_metric.value,'linea':self.detected_line.value}
   if pick['deporte'] not in SPORTS or pick['metrica'] not in DEFS:raise ValueError('Deporte o métrica no compatible. Usa los nombres de la biblioteca.')
   if not pick['jugador'].strip() or not math.isfinite(float(pick['linea'])):raise ValueError('Jugador o línea inválida.')
   self.pending=dict(pick,lado=self.ticket_side.value);self.sport.value=pick['deporte'];self.load_games(None);self.body.children=[self.analysis]
   self.ticket_msg.value='<p>Selecciona el encuentro y equipo correctos en Análisis / historial. Carga sus jugadores y regresa a Boleto. No se presupone que un jugador histórico siga en ese equipo.</p>'
  except Exception as e:self.ticket_msg.value='<p>'+esc(e)+'</p>'
 def research_pick(self,_):
  self.research_btn.disabled=True;self.clear_research()
  try:
   if self.pending is None or self.data.empty:raise ValueError('Primero revisa la selección y carga el historial del equipo en Análisis.')
   p=self.pending
   current={'jugador':self.detected_name.value.strip(),'deporte':self.detected_sport.value,'metrica':self.detected_metric.value,'linea':self.detected_line.value}
   if any(current.get(k)!=p.get(k) for k in ['jugador','deporte','metrica','linea']) or self.ticket_side.value!=p['lado']:raise ValueError('Cambiaste la selección: pulsa Buscar partido de esta selección otra vez.')
   if self.sport.value!=p['deporte']:raise ValueError('El deporte actual no coincide con la selección.')
   def canonical(s):
    import unicodedata
    return re.sub(r'[^a-z]','',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower())
   d=self.data[(self.data.athlete.map(canonical)==canonical(p['jugador']))&(self.data.metric==p['metrica'])].copy()
   if d.empty:raise ValueError('No hay coincidencia exacta de jugador y métrica. Revisa el OCR y equipo; no se sustituye por otro jugador.')
   if d.athlete_id.nunique()!=1:raise ValueError('Identidad ambigua. Selecciona un único jugador en el historial.')
   if self.origin!='ESPN' or self.game.value is None:raise ValueError('Esta investigación automática requiere un encuentro ESPN confirmado. Para CSV usa Análisis / historial.')
   g=self.games.loc[self.game.value];url=endpoint(g.sport,g.code)+f'summary?event={g.id}';payload=self.store.get(url,0)
   head=dict(payload.get('header',{}));cs=head.get('competitions',[])
   if not cs:raise ValueError('No se pudo verificar el partido actual.')
   head['date']=cs[0].get('date');fresh=event_row(head,g.sport,g.code)
   if not fresh or fresh['state']!='pre' or fresh['status']!='STATUS_SCHEDULED' or fresh['date']<=now():raise ValueError('El partido ya empezó o no figura programado. Actualiza el calendario.')
   d=d[(d.date<min(fresh['date'],now()))&d.participated].sort_values('date').tail(40)
   if len(d)<8:raise ValueError(f'Solo {len(d)} datos válidos. No se emite una probabilidad con esta muestra.')
   x=d.value.to_numpy(float);line=float(p['linea']);kind,scores=choose(x,p['metrica'],d.date.to_numpy());pr=probability(x,kind,line);side=0 if p['lado']=='Más de' else 1
   hit=x>line if side==0 else x<line;recent=x[-5:];age=(fresh['date']-d.date.max()).days
   from urllib.parse import quote_plus
   queries=[('Noticias y disponibilidad',f'{p["jugador"]} injury status {fresh["date"]:%Y-%m-%d}'),('Rol y rival',f'{p["jugador"]} {g.away} {g.home} preview')]
   news=[];news_audit={}
   try:
    news,news_audit=discover_news(p['jugador']);news_status=f'{len(news)} titulares recientes encontrados. Se consultó el índice, no el texto de los artículos; no confirman por sí solos lesiones ni participación.'
   except Exception as e:news_status='No se pudo consultar el índice de noticias: '+str(e)
   news_html='<p>'+esc(news_status)+'</p><ul>'+''.join('<li><a href="'+esc(n['url'])+'">'+esc(n['titulo'])+'</a> · '+esc(n['medio'])+' · '+esc(n['fecha'])+'</li>' for n in news)+'</ul>'
   links=''.join(f'<li><a href="https://www.google.com/search?q={quote_plus(q)}">{esc(label)}</a> — búsqueda externa pendiente, no evidencia consultada.</li>' for label,q in queries)
   delta=float(recent.mean()-x.mean());direction='por encima' if delta>0 else 'por debajo' if delta<0 else 'al mismo nivel'
   sources=''.join(f'<li><a href="{esc(u)}">Boxscore utilizado</a></li>' for u in d.source_url.unique())
   text=f"""{CSS}<div class="props"><h1>{esc(p['jugador'])}: {esc(p['lado'])} {line:g} {esc(DEFS[p['metrica']][0])}</h1>
   <p>{esc(g.away)} @ {esc(g.home)} · {esc(fresh['date'])}. Informe generado {esc(now())}.</p>
   <h2>La lectura del encuentro</h2><p>La selección exige que {esc(p['jugador'])} termine {esc(p['lado'].lower())} {line:g}. Su historial disponible ofrece una media de {x.mean():.2f} y una mediana de {np.median(x):.2f}. En las últimas cinco actuaciones promedia {recent.mean():.2f}, {direction} de la muestra completa por {abs(delta):.2f} unidades. Esa diferencia describe una tendencia observada; por sí sola no demuestra un cambio sostenible de nivel.</p>
   <h2>Qué respalda y qué cuestiona la selección</h2><p>La selección se cumplió en {hit.sum()} de {len(x)} actuaciones ({hit.mean():.1%}); en las cinco últimas, {int(hit[-5:].sum())} de 5. La línea está {abs(line-x.mean()):.2f} unidades {'por encima' if line>x.mean() else 'por debajo'} de la media. El rango observado fue {x.min():g}–{x.max():g}. Una media favorable no elimina las actuaciones que quedaron al otro lado de la línea.</p>
   <p>La última observación tiene {age} días respecto al encuentro. Se encontraron {len(d)} registros para esta métrica entre {len(self.events)} encuentros del equipo consultados; ausencias, cambios de equipo y boxscores incompletos pueden reducir esa cobertura. No se rellenaron ausencias con ceros.</p>
   <h2>Probabilidad exploratoria</h2><p>Familia seleccionada: {esc(kind)}. Más de: {pr[0]:.1%}; menos de: {pr[1]:.1%}; igualdad: {pr[2]:.1%}. Para tu lado: {pr[side]:.1%}. La selección de familia compara pérdidas predictivas con datos anteriores; no equivale a validar ganancias ni a conocer la probabilidad verdadera del próximo partido.</p>
   <p>Resultados de comparación temporal de familias: {esc(scores)}. No se ajustaron lesiones, minutos futuros, fuerza del rival ni cambios tácticos. Esos factores pueden desplazar la distribución: el modelo constituye una referencia histórica, no una recomendación definitiva.</p>
   <h2>Información comprobada y pendientes</h2><p>Consultado: calendario actualizado y boxscores individuales de ESPN. El encuentro sigue programado al consultar. La identidad coincide exactamente con la del historial. No se confirmó convocatoria actual, lesión, titularidad ni reglas especiales del boleto. No se presenta una búsqueda de noticias como información ya verificada.</p><h3>Noticias localizadas automáticamente</h3>{news_html}<p>Consultas complementarias:</p><ul>{links}</ul>
   <h2>Precio y decisión</h2><p>Sin cuota individual verificable no hay EV individual calculable. El multiplicador de PrizePicks corresponde al boleto completo. No se transforma en una cuota para este jugador. Las reglas de Power/Flex, empates, Demons, promociones y Early Payout deben conocerse antes de calcular el retorno conjunto. No se suman probabilidades ni se presupone independencia entre selecciones.</p><p><b>Estado: investigación exploratoria; stake recomendado USD 0.</b> No hay aún evidencia suficiente para declarar una ventaja comprobada. Conserva este informe como base para revisar disponibilidad, contexto y precio.</p>
   <h2>Datos auditables</h2><p><a href="{esc(url)}">Registro del encuentro</a>. Los enlaces siguientes respaldan el historial, no noticias de lesiones.</p><details><summary>Ver registros y fuentes</summary>{d[['date','athlete','opponent','metric','value','source_url']].to_html(index=False,escape=True)}<ul>{sources}</ul></details></div>"""
   self.research_out.value=text;self.research_document=text;self.research_data=d;self.research_audit={'seleccion':p,'evento':g.id,'generado':str(now()),'modelo':kind,'probabilidades':pr.tolist(),'consultas':self.store.log,'noticias_indice':news,'consulta_noticias':news_audit};self.research_download.disabled=False
   self.ticket_msg.value='<p>Investigación lista. Las noticias externas figuran como pendientes, no como hechos comprobados.</p>'
  except Exception as e:self.ticket_msg.value='<p>No se pudo completar: '+esc(e)+'</p>'
  finally:self.research_btn.disabled=False
 def download_research(self,_):
  with zipfile.ZipFile('ATLAS_LENS_investigacion.zip','w',zipfile.ZIP_DEFLATED) as z:
   z.writestr('Informe.html','<!doctype html><html lang="es"><meta charset="utf-8">'+self.research_document+'</html>');z.writestr('Datos.csv',self.research_data.to_csv(index=False));z.writestr('Auditoria.json',json.dumps(self.research_audit,ensure_ascii=False,indent=2))
  from google.colab import files
  files.download('ATLAS_LENS_investigacion.zip')

if __name__=='__main__':
 lens=CaptureDesk()
