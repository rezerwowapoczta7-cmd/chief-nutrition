import streamlit as st
import requests
import json
import base64
import io
from PIL import Image
import pandas as pd
import datetime
import sqlite3

# --- TWOJE DANE ---
API_KEY = st.secrets["API_KEY"]

# Baza danych
CONN = sqlite3.connect('statek_diet.db', check_same_thread=False)
C = CONN.cursor()
C.execute('''CREATE TABLE IF NOT EXISTS posilki 
             (data TEXT, nazwa TEXT, kcal INT, b INT, t INT, w INT, typ TEXT, insul_alert TEXT)''')
CONN.commit()

# --- RADAR MODELI ---
def get_available_models():
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    resp = requests.get(url, timeout=15)

    if resp.status_code == 200:
        data = resp.json()
        valid_models = []
        for m in data.get('models', []):
            if 'generateContent' in m.get('supportedGenerationMethods', []):
                valid_models.append(m['name'].split('/')[-1])
        return valid_models

    return []

# --- FUNKCJA BEZPOŚREDNIEGO POŁĄCZENIA ---
def analyze_image_direct(image, note):
    image = image.convert("RGB")
    image.thumbnail((1280, 1280))

    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=85)
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

    payload = {
        "contents": [{
            "parts": [
                {
                    "text": f"Jesteś dietetykiem Keto. Analizuj zdjęcie. KALIBRACJA: Biały Talerz=24cm, Miska=18cm. ZASADY: Wędliny/Sery tłuste. Szukaj węgli. Info: {note}. JSON Format: {{\"nazwa\": \"x\", \"kcal\": 0, \"b\": 0, \"t\": 0, \"w\": 0, \"alert\": \"SAFE/WARN\"}}"
                },
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": img_str
                    }
                }
            ]
        }],
        "generationConfig": {
            "response_mime_type": "application/json"
        }
    }

    models_to_try = get_available_models()

    if not models_to_try:
        models_to_try = [
            "gemini-2.0-flash",
            "gemini-flash-latest",
            "gemini-1.5-flash"
        ]

    errors = []

    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}"

        try:
            response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=40
            )

            if response.status_code == 200:
                return response.json()
            else:
                errors.append(f"{model} (Błąd {response.status_code}: {response.text[:150]})")

        except Exception as e:
            errors.append(f"{model} (Exception: {e})")

    raise Exception(f"Wyczerpano modele lub limity. Logi: {errors}")

# --- INTERFEJS ---
st.set_page_config(page_title="Chief Nutrition", layout="centered", page_icon="⚓")
st.title("⚓ Chief Nutrition v3.0 (Radar)")

if 'ai_result' not in st.session_state:
    st.session_state.ai_result = None

is_gym = st.toggle("💪 TRENING (Gym Day)", value=False)
goals = {'kcal': 2350, 'p': 200, 'f': 140, 'c': 50} if is_gym else {'kcal': 2150, 'p': 170, 'f': 140, 'c': 50}

dzis = datetime.date.today().strftime("%Y-%m-%d")
df = pd.read_sql(f"SELECT * FROM posilki WHERE data='{dzis}'", CONN)
suma = df[['kcal', 'b', 't', 'w']].sum() if not df.empty else pd.Series({'kcal': 0, 'b': 0, 't': 0, 'w': 0})

c1, c2, c3, c4 = st.columns(4)
c1.metric("Kcal", f"{int(suma['kcal'])}", f"{int(goals['kcal'] - suma['kcal'])}", delta_color="inverse")
c2.metric("B", f"{int(suma['b'])}", f"{int(goals['p'] - suma['b'])}")
c3.metric("T", f"{int(suma['t'])}", f"{int(goals['f'] - suma['t'])}", delta_color="inverse")
c4.metric("W", f"{int(suma['w'])}", f"{int(goals['c'] - suma['w'])}", delta_color="inverse")

st.progress(min(suma['kcal'] / goals['kcal'], 1.0))

st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["📸 SKANER", "⚡ SZYBKIE", "📝 RĘCZNIE", "📊 HISTORIA"])

with tab1:
    img_source = st.radio("Źródło:", ["Aparat", "Galeria"], horizontal=True, label_visibility="collapsed")
    img_file = st.camera_input("Foto") if img_source == "Aparat" else st.file_uploader("Wgraj", type=['jpg', 'png', 'jpeg'])
    note = st.text_input("Dodatkowe info (np. sos, ukryte składniki)")

    if img_file and st.button("ANALIZUJ POSIŁEK"):
        img = Image.open(img_file)

        with st.spinner('Namierzam wolne serwery...'):
            try:
                raw_response = analyze_image_direct(img, note)
                text_content = raw_response['candidates'][0]['content']['parts'][0]['text']
                data = json.loads(text_content)

                if isinstance(data, list):
                    data = data[0]

                st.session_state.ai_result = data

            except Exception as e:
                st.error(f"Problem z połączeniem: {e}")

    if st.session_state.ai_result:
        data = st.session_state.ai_result

        st.success(f"Wynik: {data.get('nazwa', 'Danie')}")

        col_res = st.columns(4)
        col_res[0].write(f"Kcal: {data.get('kcal', 0)}")
        col_res[1].write(f"B: {data.get('b', 0)}")
        col_res[2].write(f"T: {data.get('t', 0)}")
        col_res[3].write(f"W: {data.get('w', 0)}")

        alert = data.get('alert', 'SAFE')

        if "WARN" in alert or "OSTRZ" in alert:
            st.warning(f"Ostrzeżenie: {alert}")
        else:
            st.success("✅ Keto Safe")

        if st.button("ZAPISZ DO DZIENNIKA"):
            C.execute(
                "INSERT INTO posilki VALUES (?,?,?,?,?,?,?,?)",
                (
                    dzis,
                    data.get('nazwa', 'Danie'),
                    data.get('kcal', 0),
                    data.get('b', 0),
                    data.get('t', 0),
                    data.get('w', 0),
                    'AI',
                    alert
                )
            )
            CONN.commit()
            st.session_state.ai_result = None
            st.rerun()

        if st.button("❌ Anuluj"):
            st.session_state.ai_result = None
            st.rerun()

with tab2:
    if st.button("☕ Kawa z mlekiem"):
        C.execute("INSERT INTO posilki VALUES (?,?,?,?,?,?,?,?)", (dzis, "Kawa z mlekiem", 40, 2, 2, 3, 'QUICK', 'SAFE'))
        CONN.commit()
        st.rerun()

    if st.button("🥜 Garść orzechów"):
        C.execute("INSERT INTO posilki VALUES (?,?,?,?,?,?,?,?)", (dzis, "Mix Orzechów", 180, 5, 17, 4, 'QUICK', 'SAFE'))
        CONN.commit()
        st.rerun()

with tab3:
    with st.form("manual"):
        n = st.text_input("Nazwa")

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        ck = col_m1.number_input("Kcal", 0)
        cb = col_m2.number_input("B", 0)
        ct = col_m3.number_input("T", 0)
        cw = col_m4.number_input("W", 0)

        if st.form_submit_button("Dodaj"):
            C.execute("INSERT INTO posilki VALUES (?,?,?,?,?,?,?,?)", (dzis, n, ck, cb, ct, cw, 'MANUAL', 'SAFE'))
            CONN.commit()
            st.rerun()

with tab4:
    if not df.empty:
        st.dataframe(df[['nazwa', 'kcal', 'b', 't', 'w']], use_container_width=True, hide_index=True)

        if st.button("Cofnij ostatni"):
            C.execute("DELETE FROM posilki WHERE rowid = (SELECT MAX(rowid) FROM posilki)")
            CONN.commit()
            st.rerun()
