import streamlit as st
import requests
import json
import base64
import io
import re
from PIL import Image
import pandas as pd
import datetime
import sqlite3

# --- KONFIG ---
API_KEY = st.secrets["API_KEY"]
DB_NAME = "statek_diet.db"

# --- BAZA ---
CONN = sqlite3.connect(DB_NAME, check_same_thread=False)
C = CONN.cursor()

C.execute("""
CREATE TABLE IF NOT EXISTS posilki (
    data TEXT,
    nazwa TEXT,
    kcal INT,
    b INT,
    t INT,
    w INT,
    typ TEXT,
    insul_alert TEXT
)
""")
CONN.commit()

# Migracje dla nowych pól
for col in ["carb_reason", "insulin_reason"]:
    try:
        C.execute(f"ALTER TABLE posilki ADD COLUMN {col} TEXT DEFAULT ''")
        CONN.commit()
    except sqlite3.OperationalError:
        pass


# --- SESSION STATE ---
if "ai_result" not in st.session_state:
    st.session_state.ai_result = None

if "upload_key" not in st.session_state:
    st.session_state.upload_key = 0

if "manual_saved" not in st.session_state:
    st.session_state.manual_saved = False


# --- MODELE GEMINI / SNIPER ---
def get_available_models():
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"

    try:
        resp = requests.get(url, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            valid_models = []

            preferred_keywords = [
                "flash",
                "gemini"
            ]

            for m in data.get("models", []):
                name = m.get("name", "").split("/")[-1]
                methods = m.get("supportedGenerationMethods", [])

                if "generateContent" in methods:
                    if any(k in name.lower() for k in preferred_keywords):
                        valid_models.append(name)

            # najpierw modele flash, bo szybkie i tanie
            valid_models = sorted(
                valid_models,
                key=lambda x: (
                    0 if "flash" in x.lower() else 1,
                    x
                )
            )

            return valid_models

    except Exception:
        pass

    return []


def extract_json(text):
    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))

    raise ValueError("Nie udało się odczytać JSON z odpowiedzi AI.")


def normalize_result(data):
    if isinstance(data, list):
        data = data[0]

    return {
        "nazwa": str(data.get("nazwa", "Posiłek")),
        "kcal": int(float(data.get("kcal", 0))),
        "b": int(float(data.get("b", 0))),
        "t": int(float(data.get("t", 0))),
        "w": int(float(data.get("w", 0))),
        "alert": str(data.get("alert", "SAFE")),
        "carb_reason": str(data.get("carb_reason", "")),
        "insulin_alert": str(data.get("insulin_alert", "LOW")),
        "insulin_reason": str(data.get("insulin_reason", ""))
    }


def ask_gemini(payload):
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
                timeout=45
            )

            if response.status_code == 200:
                raw = response.json()
                text_content = raw["candidates"][0]["content"]["parts"][0]["text"]
                data = extract_json(text_content)
                return normalize_result(data)

            errors.append(f"{model}: {response.status_code}")

        except Exception as e:
            errors.append(f"{model}: {e}")

    raise Exception(f"Wyczerpano modele lub limity. Logi: {errors}")


# --- PROMPTY ---
def build_prompt(extra_info=""):
    return f"""
Jesteś praktycznym dietetykiem low carb / keto.
Masz szacować kalorie i makro realistycznie, bez przesadnego zawyżania tłuszczu.

ZASADY SZACOWANIA:
1. Nie zakładaj dużej ilości masła/oleju, jeśli nie widać tłuszczu albo użytkownik tego nie podał.
2. Przy jajecznicy domyślnie przyjmuj 1 jajko = ok. 70 kcal.
3. Przy jajecznicy domyślnie zakładaj maksymalnie 10 g tłuszczu do smażenia, chyba że użytkownik poda inaczej.
4. Plaster sera żółtego licz zwykle jako 20-25 g.
5. Plaster salami/wędliny licz zwykle jako 8-12 g.
6. Jeśli danie jest low carb, ale kaloryczne, nie dawaj ostrzeżenia keto.
7. WARN dawaj tylko gdy posiłek nie jest keto-safe, ma dużo węgli albo może mocno podbić insulinę.
8. Jeśli węgle są powyżej 20 g albo posiłek nie jest keto-safe, koniecznie napisz w carb_reason, co podbiło węgle.
9. Oceń insulinę:
   - LOW: niskie ryzyko wyrzutu insuliny,
   - MEDIUM: umiarkowane,
   - HIGH: wysokie.
10. insulin_reason ma krótko wyjaśnić, dlaczego.

DODATKOWE INFO OD UŻYTKOWNIKA:
{extra_info}

Zwróć WYŁĄCZNIE JSON w tym formacie:
{{
  "nazwa": "krótka nazwa posiłku",
  "kcal": 0,
  "b": 0,
  "t": 0,
  "w": 0,
  "alert": "SAFE albo WARN",
  "carb_reason": "krótki opis co podbiło węgle albo pusty tekst",
  "insulin_alert": "LOW albo MEDIUM albo HIGH",
  "insulin_reason": "krótkie wyjaśnienie"
}}
"""


def analyze_image_direct(image, note):
    image = image.convert("RGB")
    image.thumbnail((1280, 1280))

    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=85)
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

    payload = {
        "contents": [{
            "parts": [
                {"text": build_prompt(note)},
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": img_str
                    }
                }
            ]
        }],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.1
        }
    }

    return ask_gemini(payload)


def analyze_text_direct(description):
    prompt = build_prompt(description)

    payload = {
        "contents": [{
            "parts": [
                {
                    "text": f"""
Przeanalizuj opis posiłku lub napoju użytkownika.
Opis:
{description}

{prompt}
"""
                }
            ]
        }],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.1
        }
    }

    return ask_gemini(payload)


def save_meal(data, meal_type):
    C.execute(
        """
        INSERT INTO posilki
        (data, nazwa, kcal, b, t, w, typ, insul_alert, carb_reason, insulin_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.date.today().strftime("%Y-%m-%d"),
            data.get("nazwa", "Posiłek"),
            int(data.get("kcal", 0)),
            int(data.get("b", 0)),
            int(data.get("t", 0)),
            int(data.get("w", 0)),
            meal_type,
            data.get("insulin_alert", ""),
            data.get("carb_reason", ""),
            data.get("insulin_reason", "")
        )
    )
    CONN.commit()


# --- UI ---
st.set_page_config(page_title="Chief Nutrition", layout="centered", page_icon="⚓")
st.title("⚓ Chief Nutrition v3.2")

is_gym = st.toggle("💪 TRENING (Gym Day)", value=False)

goals = {
    "kcal": 2350,
    "p": 200,
    "f": 140,
    "c": 50
} if is_gym else {
    "kcal": 2150,
    "p": 170,
    "f": 140,
    "c": 50
}

dzis = datetime.date.today().strftime("%Y-%m-%d")

df = pd.read_sql(
    "SELECT rowid, * FROM posilki WHERE data = ?",
    CONN,
    params=(dzis,)
)

suma = df[["kcal", "b", "t", "w"]].sum() if not df.empty else pd.Series({
    "kcal": 0,
    "b": 0,
    "t": 0,
    "w": 0
})


def show_metric(col, label, used, goal):
    remaining = int(goal - used)

    if remaining >= 0:
        delta = f"{remaining} zostało"
    else:
        delta = f"{remaining} przekroczone"

    col.metric(
        f"{label} (cel {goal})",
        int(used),
        delta,
        delta_color="normal"
    )


c1, c2, c3, c4 = st.columns(4)
show_metric(c1, "Kcal", suma["kcal"], goals["kcal"])
show_metric(c2, "B", suma["b"], goals["p"])
show_metric(c3, "T", suma["t"], goals["f"])
show_metric(c4, "W", suma["w"], goals["c"])

st.progress(min(float(suma["kcal"]) / float(goals["kcal"]), 1.0))

st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["📸 SKANER", "⚡ SZYBKIE", "📝 RĘCZNIE", "📊 HISTORIA"])


# --- SKANER ---
with tab1:
    source = st.radio(
        "Źródło:",
        ["Galeria / Wgraj zdjęcie", "Aparat", "Opis tekstowy"],
        horizontal=True
    )

    img_file = None
    text_description = ""

    if source == "Galeria / Wgraj zdjęcie":
        img_file = st.file_uploader(
            "Wgraj zdjęcie",
            type=["jpg", "png", "jpeg"],
            key=f"upload_{st.session_state.upload_key}"
        )

    elif source == "Aparat":
        img_file = st.camera_input(
            "Zrób zdjęcie",
            key=f"camera_{st.session_state.upload_key}"
        )

    else:
        text_description = st.text_area(
            "Opisz posiłek lub napój",
            placeholder="np. jajecznica z 4 jaj na maśle albo kufel 500 ml piwa Kozel czarny"
        )

    note = st.text_input("Dodatkowe info (np. sos, ukryte składniki)")

    can_analyze = img_file is not None or text_description.strip() != ""

    if can_analyze and st.button("ANALIZUJ POSIŁEK"):
        with st.spinner("Analizuję posiłek..."):
            try:
                if source == "Opis tekstowy":
                    result = analyze_text_direct(text_description.strip())
                    st.session_state.ai_result = result
                else:
                    img = Image.open(img_file)
                    result = analyze_image_direct(img, note)
                    st.session_state.ai_result = result

                    # reset pola zdjęcia po analizie
                    st.session_state.upload_key += 1

                st.rerun()

            except Exception as e:
                st.error(f"Problem z analizą: {e}")

    if st.session_state.ai_result:
        data = st.session_state.ai_result

        st.success(f"Wynik: {data.get('nazwa', 'Posiłek')}")

        col_res = st.columns(4)
        col_res[0].write(f"Kcal: {data.get('kcal', 0)}")
        col_res[1].write(f"B: {data.get('b', 0)}")
        col_res[2].write(f"T: {data.get('t', 0)}")
        col_res[3].write(f"W: {data.get('w', 0)}")

        alert = data.get("alert", "SAFE")
        carbs = int(data.get("w", 0))

        if "WARN" in alert or carbs > 20:
            st.warning("⚠️ Uwaga: posiłek może nie być keto-safe albo ma podwyższone węgle.")
        else:
            st.success("✅ Low Carb / Keto Safe")

        if data.get("carb_reason"):
            st.info(f"🍞 Co podbiło węgle: {data.get('carb_reason')}")

        insulin_alert = data.get("insulin_alert", "LOW")
        insulin_reason = data.get("insulin_reason", "")

        if insulin_alert == "HIGH":
            st.warning(f"🩸 Możliwy większy wyrzut insuliny: {insulin_reason}")
        elif insulin_alert == "MEDIUM":
            st.info(f"🩸 Umiarkowany wpływ na insulinę: {insulin_reason}")
        elif insulin_reason:
            st.caption(f"🩸 Insulina: niskie ryzyko — {insulin_reason}")

        if st.button("ZAPISZ DO DZIENNIKA"):
            save_meal(data, "AI")
            st.session_state.ai_result = None
            st.success("✅ Zapisano do dziennika")
            st.rerun()

        if st.button("❌ Anuluj"):
            st.session_state.ai_result = None
            st.rerun()


# --- SZYBKIE ---
with tab2:
    if st.button("☕ Kawa z mlekiem"):
        save_meal({
            "nazwa": "Kawa z mlekiem",
            "kcal": 40,
            "b": 2,
            "t": 2,
            "w": 3,
            "insulin_alert": "LOW",
            "carb_reason": "",
            "insulin_reason": "mała ilość mleka"
        }, "QUICK")
        st.success("✅ Dodano kawę")
        st.rerun()

    if st.button("🥜 Garść orzechów"):
        save_meal({
            "nazwa": "Mix orzechów",
            "kcal": 180,
            "b": 5,
            "t": 17,
            "w": 4,
            "insulin_alert": "LOW",
            "carb_reason": "",
            "insulin_reason": "tłuszczowo-białkowy produkt low carb"
        }, "QUICK")
        st.success("✅ Dodano orzechy")
        st.rerun()


# --- RĘCZNIE ---
with tab3:
    if st.session_state.manual_saved:
        st.success("✅ Dodano ręcznie do dziennika")
        st.session_state.manual_saved = False

    with st.form("manual_form", clear_on_submit=True):
        n = st.text_input("Nazwa")

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        ck = col_m1.number_input("Kcal", min_value=0, value=0)
        cb = col_m2.number_input("B", min_value=0, value=0)
        ct = col_m3.number_input("T", min_value=0, value=0)
        cw = col_m4.number_input("W", min_value=0, value=0)

        submitted = st.form_submit_button("Dodaj")

        if submitted:
            if not n.strip():
                st.error("Podaj nazwę produktu/posiłku.")
            else:
                save_meal({
                    "nazwa": n,
                    "kcal": ck,
                    "b": cb,
                    "t": ct,
                    "w": cw,
                    "insulin_alert": "MANUAL",
                    "carb_reason": "",
                    "insulin_reason": ""
                }, "MANUAL")

                st.session_state.manual_saved = True
                st.rerun()


# --- HISTORIA ---
with tab4:
    if df.empty:
        st.info("Brak wpisów na dziś.")
    else:
        cols_to_show = ["nazwa", "kcal", "b", "t", "w"]

        st.dataframe(
            df[cols_to_show],
            use_container_width=True,
            hide_index=True
        )

        if st.button("Cofnij ostatni"):
            C.execute("DELETE FROM posilki WHERE rowid = (SELECT MAX(rowid) FROM posilki)")
            CONN.commit()
            st.success("✅ Cofnięto ostatni wpis")
            st.rerun()
