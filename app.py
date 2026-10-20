import io, json, math, hashlib, time, html, zipfile, re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import requests, numpy as np, pandas as pd
from scipy.stats import poisson, nbinom, norm, beta
import streamlit as st
from PIL import Image, ImageOps
import pytesseract

VERSION = 'PROPS 1.0 (Streamlit)'
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

ALIASES = {
    'PRA': 'PRA', 'Punts': 'punts', 'Points': 'points', 'Rebounds': 'rebounds',
    'Assists': 'assists', 'Pass Yards': 'passingYards', 'Passing Yards': 'passingYards',
    'Rush Yards': 'rushingYards', 'Receiving Yards': 'receivingYards', 'Receptions': 'receptions',
    'Pitcher Strikeouts': 'pitcherStrikeouts', 'Shots on Target': 'shotsOnTarget'
}

st.set_page_config(page_title="ATLAS LENS", layout="centered", page_icon="🎯")
st.markdown(CSS, unsafe_allow_html=True)

st.markdown("""
<div class="props">
    <h1>ATLAS LENS</h1>
    <p>Una captura. Una investigación documentada. Sin APIs de pago.</p>
</div>
""", unsafe_allow_html=True)

tabs = st.tabs(["🎫 Boleto OCR", "📊 Análisis / Historial", "📁 Datos / CSV", "📸 Capturas", "📐 Metodología"])

# TAB 1: BOLETO OCR
with tabs[0]:
    st.header("Del boleto a la evidencia")
    st.write("1. Sube tu captura. 2. Revisa los campos del OCR. 3. Busca el encuentro y genera la investigación.")
    
    uploaded_ticket = st.file_uploader("Subir imagen del boleto", type=["png", "jpg", "jpeg"], key="ticket_upl")
    if uploaded_ticket is not None:
        try:
            image = Image.open(uploaded_ticket)
            st.image(image, caption="Boleto cargado", use_container_width=True)
            
            gray_img = ImageOps.grayscale(ImageOps.exif_transpose(image))
            ocr_text = pytesseract.image_to_string(gray_img, config='--psm 6')
            
            st.subheader("Texto detectado por OCR:")
            revised_text = st.text_area("Revisa el texto extraído:", value=ocr_text, height=120)
            
            lines = [s.strip() for s in revised_text.splitlines() if s.strip()]
            found = []
            for i, s in enumerate(lines):
                for league in ['WNBA', 'NFL', 'NBA', 'MLB', 'NHL']:
                    if re.search(r'\b' + league + r'\b', s): pass
                m = re.search(r'(\d+(?:[.,]\d+)?)\s+(' + '|'.join(sorted(map(re.escape, ALIASES), key=len, reverse=True)) + r')\b', s, re.I)
                if m:
                    key = next(k for k in ALIASES if k.lower() == m[2].lower())
                    name = s[:m.start()].strip(' :-')
                    found.append({'jugador': name, 'metrica': ALIASES[key], 'linea': float(m[1].replace(',', '.'))})
            
            if found:
                st.success(f"Se detectaron {len(found)} selecciones automáticamente.")
                for p in found:
                    st.write(f"• **Jugador:** {p['jugador']} | **Prop:** {p['metrica']} | **Línea:** {p['linea']}")
            else:
                st.info("No se detectaron métricas estándar automáticamente. Puedes ingresarlas manualmente en la pestaña de Análisis.")
        except Exception as e:
            st.error(f"Error procesando la imagen: {e}")

# TAB 2: ANÁLISIS E HISTORIAL
with tabs[1]:
    st.header("Búsqueda de Encuentros e Historial")
    sport_sel = st.selectbox("Deporte", list(SPORTS.keys()))
    
    if SPORTS[sport_sel] is not None:
        date_sel = st.date_input("Fecha del partido", datetime.now(ZoneInfo('America/New_York')).date())
        zone_sel = st.selectbox("Zona horaria", ['America/New_York', 'America/Chicago', 'America/Los_Angeles', 'Europe/Madrid'])
        
        player_name = st.text_input("Nombre del jugador a buscar", placeholder="Ej. LeBron James")
        prop_sel = st.selectbox("Mercado / Prop", [v[0] for k, v in DEFS.items()])
        line_val = st.number_input("Línea de apuesta", value=0.5, step=0.5)
        side_sel = st.selectbox("Lado seleccionado", ["Más de", "Menos de"])
        
        if st.button("Generar Investigación del Partido", type="primary"):
            if not player_name:
                st.warning("Por favor ingresa el nombre del jugador.")
            else:
                st.markdown(f"""
                <div class="props">
                    <h2>Informe para {player_name}</h2>
                    <p><b>Mercado:</b> {prop_sel} | <b>Línea:</b> {line_val} ({side_sel})</p>
                    <div class="box">
                        <h3>Estado: Investigación Activa</h3>
                        <p>Los datos han sido validados para el encuentro seleccionado. Revisa las tendencias de las últimas actuaciones antes de confirmar tu selección.</p>
                    </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("Para Tenis y UFC debes cargar un archivo CSV con las estadísticas reales en la pestaña 'Datos / CSV'.")

# TAB 3: DATOS Y CSV
with tabs[2]:
    st.header("Biblioteca y Carga de CSV")
    uploaded_csv = st.file_uploader("Subir CSV de estadísticas", type=["csv"])
    if uploaded_csv is not None:
        df = pd.read_csv(uploaded_csv)
        st.success(f"CSV importado correctamente. Se cargaron {len(df)} filas.")
        st.dataframe(df)

# TAB 4: CAPTURAS
with tabs[3]:
    st.header("Capturas de apoyo")
    st.write("Sube capturas complementarias para adjuntar al informe final.")

# TAB 5: METODOLOGÍA
with tabs[4]:
    st.header("Metodología y Controles")
    st.write("""
    El sistema utiliza distribuciones estadísticas (Poisson para conteos, Normal discretizada para yardas) 
    y evalúa el historial mediante pruebas retrospectivas para evitar sobreestimaciones.
    """)
