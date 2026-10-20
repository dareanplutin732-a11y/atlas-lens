import io, json, math, hashlib, time, html, zipfile, re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import requests, numpy as np, pandas as pd
from scipy.stats import poisson, nbinom, norm, beta
import streamlit as st
from PIL import Image, ImageOps
import pytesseract

VERSION = 'PROPS 1.0 (Streamlit Native)'
CSS = """
<style>
.props {font: 15px/1.65 Arial; background: #101c2e; color: #edf4ff; padding: 20px; border-radius: 12px; margin: 10px 0;}
.props h1, .props h2, .props h3 {color: #fff;}
.props a {color: #5de0d2;}
.props .box {padding: 14px; border: 1px solid #3d526c; border-radius: 8px; margin: 10px 0;}
.props table {border-collapse: collapse; width: 100%;}
.props td, .props th {padding: 8px; border-bottom: 1px solid #3d526c;}
.props table.dataframe tr, .props table.dataframe th, .props table.dataframe td {background: #17283f !important; color: #edf4ff !important;}
.props .scroll {overflow: auto;}
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
}

DEFS = {
    'passingYards': ('Yardas de pase', 'yardas', 'normal', 'passing'),
    'points': ('Puntos', 'puntos', 'count', None),
    'rebounds': ('Rebotes', 'rebotes', 'count', None),
    'assists': ('Asistencias', 'asistencias', 'count', None),
    'shotsOnTarget': ('Tiros a puerta', 'tiros', 'count', None),
    'goals': ('Goles', 'goles', 'count', None),
}

MODELS = {'poisson': 'Poisson', 'nb': 'Binomial negativa', 'normal': 'Normal discretizada', 'continuous': 'Normal continua'}

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

def fit(values, kind):
    x = np.asarray(values, float)
    mu = float(x.mean())
    var = float(x.var(ddof=1)) if len(x) > 1 else 0.
    if kind == 'poisson': return poisson(max(mu, .01))
    if kind == 'nb':
        if var <= mu + .001: return poisson(max(mu, .01))
        size = max(.05, mu * mu / max(var - mu, .001))
        return nbinom(size, size / (size + max(mu, .01)))
    return norm(mu, max(np.sqrt(var), 1.))

def probability(x, kind, line):
    law = fit(x, kind)
    if kind == 'continuous':
        under = float(law.cdf(line)); over = 1 - under; push = 0.
    elif kind in ['poisson', 'nb']:
        under = float(law.cdf(math.ceil(line) - 1)); over = float(law.sf(math.floor(line))); push = max(0., 1 - under - over)
        if not float(line).is_integer(): over = 1 - under; push = 0.
    else:
        if float(line).is_integer(): under = float(law.cdf(line - .5)); over = float(law.sf(line + .5)); push = max(0., 1 - under - over)
        else: under = float(law.cdf(math.floor(line) + .5)); over = 1 - under; push = 0.
    return np.array([over, under, push])

st.set_page_config(page_title="ATLAS LENS PROPS", layout="centered", page_icon="🎯")
st.markdown(CSS, unsafe_allow_html=True)

st.markdown("""
<div class="props">
    <h1>ATLAS LENS · Motor Multideporte</h1>
    <p>Análisis cuantitativo avanzado optimizado para entorno web móvil.</p>
</div>
""", unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["📊 Análisis Cuantitativo", "🎫 Boleto OCR", "📁 Datos y CSV"])

with tab1:
    st.header("Configuración del Pronóstico")
    sport_choice = st.selectbox("Deporte", list(SPORTS.keys()))
    metric_choice = st.selectbox("Métrica / Prop", list(DEFS.keys()), format_func=lambda x: DEFS[x][0])
    line_val = st.number_input("Línea de apuesta", value=1.5, step=0.5)
    
    col1, col2 = st.columns(2)
    with col1:
        over_odds = st.text_input("Cuota Más de (Americana)", value="-110")
    with col2:
        under_odds = st.text_input("Cuota Menos de (Americana)", value="-110")
        
    bankroll = st.number_input("Banca total (USD)", value=1000.0)

    # Simulación de historial para pruebas inmediatas o carga propia
    st.subheader("Historial de observaciones recientes")
    sample_data_input = st.text_area("Valores históricos (separados por coma)", value="2, 1, 3, 0, 2, 1, 4, 1, 2, 3, 2, 1")

    if st.button("Ejecutar Análisis Estadístico (Poisson / Normal)", type="primary"):
        try:
            raw_vals = [number(v.strip()) for v in sample_data_input.split(",") if v.strip()]
            vals = [v for v in raw_vals if pd.notna(v)]
            
            if len(vals) < 5:
                st.error("Se requieren al menos 5 observaciones válidas.")
            else:
                kind = 'poisson' if DEFS[metric_choice][2] == 'count' else 'normal'
                pr = probability(vals, kind, line_val)
                
                o_odd = odds(float(over_odds))
                u_odd = odds(float(under_odds))
                
                p_over, p_under, p_push = pr[0], pr[1], pr[2]
                ev_over = (dec(o_odd) - 1) * p_over - p_under
                ev_under = (dec(u_odd) - 1) * p_under - p_over

                st.markdown(f"""
                <div class="props">
                    <h2>Resultados del Modelo ({MODELS[kind]})</h2>
                    <p><b>Media histórica:</b> {np.mean(vals):.2f} | <b>Muestra:</b> {len(vals)} partidos</p>
                    <div class="box">
                        <h3>📈 MÁS DE {line_val} ({american(o_odd)})</h3>
                        <p>Probabilidad: <b>{p_over:.2%}</b> | EV Teórico: <b>{ev_over:+.2f}</b></p>
                    </div>
                    <div class="box">
                        <h3>📉 MENOS DE {line_val} ({american(u_odd)})</h3>
                        <p>Probabilidad: <b>{p_under:.2%}</b> | EV Teórico: <b>{ev_under:+.2f}</b></p>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Error en el cálculo: {e}")

with tab2:
    st.header("Lector OCR de Boletos")
    uploaded_ticket = st.file_uploader("Sube la captura de tu boleto", type=["png", "jpg", "jpeg"])
    if uploaded_ticket is not None:
        image = Image.open(uploaded_ticket)
        st.image(image, caption="Imagen cargada", use_container_width=True)
        gray = ImageOps.grayscale(ImageOps.exif_transpose(image))
        extracted = pytesseract.image_to_string(gray, config='--psm 6')
        st.text_area("Texto detectado:", value=extracted, height=150)

with tab3:
    st.header("Gestión de Datos CSV")
    csv_file = st.file_uploader("Cargar archivo de datos históricos", type=["csv"])
    if csv_file is not None:
        df = pd.read_csv(csv_file)
        st.success(f"Archivo cargado con {len(df)} registros.")
        st.dataframe(df)
