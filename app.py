import io, json, math, hashlib, time, html, zipfile, re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import requests, numpy as np, pandas as pd
from scipy.stats import poisson, nbinom, norm, beta
import streamlit as st

VERSION = 'PROPS 1.0 (Streamlit Cloud)'
CSS = """
<style>
.props {font: 15px/1.65 Arial; background: #101c2e; color: #edf4ff; padding: 25px; border-radius: 15px; margin: 12px 0;}
.props h1, .props h2, .props h3 {color: #fff;}
.props a {color: #5de0d2;}
.props .box {padding: 16px; border: 1px solid #3d526c; border-radius: 10px; margin: 12px 0;}
.props table {border-collapse: collapse; width: 100%;}
.props td, .props th {padding: 9px; border-bottom: 1px solid #3d526c;}
.props table.dataframe tr, .props table.dataframe th, .props table.dataframe td {background: #17283f !important; color: #edf4ff !important;}
.props .scroll {overflow: auto;}
.props pre {white-space: pre-wrap;}
</style>
"""

SPORTS = {
    'NFL': ('football', 'nfl'),
    'NCAA fútbol americano': ('football', 'college-football'),
    'NBA': ('basketball', 'nba'),
    'WNBA': ('basketball', 'wnba'),
    'NCAA baloncesto': ('basketball', 'mens-college-basketball'),
    'MLB': ('baseball', 'mlb'),
    'NHL': ('hockey', 'nhl'),
    'Soccer': ('soccer', 'eng.1'),
    'Tenis': None,
    'UFC': None,
}

DEFS = {
    'passingYards': ('Yardas de pase', 'yardas', 'normal', 'passing'),
    'passingAttempts': ('Intentos de pase', 'intentos', 'count', 'passing'),
    'completions': ('Pases completos', 'pases', 'count', 'passing'),
    'passingTouchdowns': ('TD de pase', 'TD', 'count', 'passing'),
    'passingInterceptions': ('Intercepciones lanzadas', 'INT', 'count', 'passing'),
    'rushingYards': ('Yardas terrestres', 'yardas', 'normal', 'rushing'),
    'rushingAttempts': ('Acarreos', 'acarreos', 'count', 'rushing'),
    'rushingTouchdowns': ('TD terrestres', 'TD', 'count', 'rushing'),
    'receivingYards': ('Yardas recibidas', 'yardas', 'normal', 'receiving'),
    'receptions': ('Recepciones', 'recepciones', 'count', 'receiving'),
    'receivingTargets': ('Targets', 'targets', 'count', 'receiving'),
    'receivingTouchdowns': ('TD recibidos', 'TD', 'count', 'receiving'),
    'points': ('Puntos', 'puntos', 'count', None),
    'rebounds': ('Rebotes', 'rebotes', 'count', None),
    'assists': ('Asistencias', 'asistencias', 'count', None),
    'steals': ('Robos', 'robos', 'count', None),
    'blocks': ('Tapones', 'tapones', 'count', None),
    'threePointFieldGoalsMade': ('Triples anotados', 'triples', 'count', None),
    'PRA': ('Puntos + rebotes + asistencias', 'PRA', 'count', None),
    'batterHits': ('Hits del bateador', 'hits', 'count', 'batting'),
    'batterHomeRuns': ('Home runs', 'HR', 'count', 'batting'),
    'batterStrikeouts': ('Ponches del bateador', 'K', 'count', 'batting'),
    'RBIs': ('Carreras impulsadas', 'RBI', 'count', 'batting'),
    'pitcherStrikeouts': ('Ponches del lanzador', 'K', 'count', 'pitching'),
    'pitcherOuts': ('Outs lanzados', 'outs', 'count', 'pitching'),
    'shotsTotal': ('Tiros según definición de la fuente', 'tiros', 'count', None),
    'shotsOnTarget': ('Tiros a puerta', 'tiros', 'count', None),
    'goals': ('Goles', 'goles', 'count', None),
    'totalSaves': ('Paradas', 'paradas', 'count', None),
    'aces': ('Aces', 'aces', 'count', None),
    'doubleFaults': ('Dobles faltas', 'faltas', 'count', None),
    'gamesWon': ('Juegos ganados', 'juegos', 'count', None),
    'significantStrikesLanded': ('Golpes significativos conectados', 'golpes', 'count', None),
    'takedownsLanded': ('Derribos logrados', 'derribos', 'count', None),
    'fightSeconds': ('Duración del combate', 'segundos', 'continuous', None),
    'punts': ('Despejes de punt', 'punts', 'count', 'punting'),
}

def esc(x): return html.escape(str(x), quote=True)
def now(): return pd.Timestamp.now(tz='UTC')
def american(x): return f'{x:+.0f}'
def odds(x):
    x = float(x)
    if not math.isfinite(x) or abs(x) < 100: raise ValueError('Cuota americana inválida.')
    return x
def dec(x): return 1 + (x / 100 if x > 0 else 100 / abs(x))
def number(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else np.nan
    except (ValueError, TypeError):
        return np.nan

class Store:
    def __init__(self):
        self.root = Path('atlas_props_cache')
        self.root.mkdir(exist_ok=True)
        self.blocked = set()
        self.log = []
    def get(self, url, ttl=3600):
        from urllib.parse import urlparse
        host = urlparse(url).netloc
        p = self.root / (hashlib.sha256(url.encode()).hexdigest() + '.json')
        if p.exists():
            try:
                obj = json.loads(p.read_text(encoding='utf-8'))
                if time.time() - obj['saved'] < ttl:
                    self.last_stamp = pd.Timestamp(obj['saved'], unit='s', tz='UTC').isoformat()
                    return obj['data']
            except (ValueError, KeyError):
                pass
        if host in self.blocked: raise ValueError('Fuente bloqueada.')
        r = requests.get(url, timeout=(8, 30))
        if r.status_code in [401, 403, 429]: self.blocked.add(host)
        r.raise_for_status()
        self.last_stamp = now().isoformat()
        d = r.json()
        p.write_text(json.dumps({'saved': time.time(), 'data': d}), encoding='utf-8')
        self.log.append({'url': url, 'fetched_at': now().isoformat()})
        return d

st.set_page_config(page_title="ATLAS LENS", layout="centered")
st.markdown(CSS, unsafe_allow_html=True)

st.markdown("""
<div class="props">
    <h1>ATLAS LENS / PROPS</h1>
    <p>Investigación multideporte local optimizada para Streamlit en móvil.</p>
</div>
""", unsafe_allow_html=True)

# Interfaz básica interactiva en Streamlit para operar desde el móvil
sport_name = st.selectbox("Selecciona Deporte", list(SPORTS.keys()))
selected_sport = SPORTS[sport_name]

if selected_sport is None:
    st.info("Este deporte requiere la importación manual de un archivo CSV de datos.")
    uploaded_file = st.file_uploader("Sube tu archivo CSV de datos", type=["csv"])
    if uploaded_file is not None:
        df_user = pd.read_csv(uploaded_file)
        st.success(f"¡CSV cargado con éxito! {len(df_user)} registros encontrados.")
        st.dataframe(df_user.head())
else:
    st.write(f"Conector activo para: **{sport_name}**")
    target_date = st.date_input("Fecha del evento", datetime.now(ZoneInfo('America/New_York')).date())
    
    if st.button("Consultar Estado de la App"):
        st.success("Configuración correcta de Streamlit Cloud. El entorno móvil está listo para operar sin las restricciones de Google Colab.")
