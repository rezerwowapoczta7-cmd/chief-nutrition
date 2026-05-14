import streamlit as st
import requests
import json
import base64
import io
import re
import calendar
from PIL import Image
import datetime
from zoneinfo import ZoneInfo
from supabase import create_client

# ==================================================
# CONFIG
# ==================================================
API_KEY = st.secrets["API_KEY"]
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

TZ = ZoneInfo("Europe/Warsaw")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==================================================
# STREAMLIT / CSS
# ==================================================
st.set_page_config(page_title="Chief Nutrition", layout="centered", page_icon="⚓")

st.markdown("""
<style>
#MainMenu, header, footer {visibility: hidden;}
[data-testid="stToolbar"] {display: none !important;}
[data-testid="stDecoration"] {display: none !important;}
[data-testid="stStatusWidget"] {display: none !important;}

.block-container {
    padding-top: 2.8rem;
    padding-bottom: 5rem;
    max-width: 760px;
}

/* HEADER */
.chief-header {
    background: linear-gradient(135deg, #f7f9ff, #ffffff);
    border: 1px solid #eeeeee;
    border-radius: 24px;
    padding: 18px 18px 14px 18px;
    margin-bottom: 14px;
    box-shadow: 0 3px 14px rgba(0,0,0,0.05);
}

.chief-title {
    font-size: 1.75rem;
    font-weight: 850;
    line-height: 1.1;
}

.chief-subtitle {
    color: #777;
    margin-top: 5px;
    font-size: 0.92rem;
}

/* NAV */
div[role="radiogroup"] {
    gap: 6px;
}

div[role="radiogroup"] label {
    background: #f4f5f7;
    border-radius: 14px;
    padding: 7px 10px;
    margin-right: 4px;
}

/* MACRO GRID - custom, mobile safe */
.macro-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin: 10px 0 14px 0;
}

.macro-card {
    background: #ffffff;
    border: 1px solid #eeeeee;
    border-radius: 18px;
    padding: 12px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.04);
    min-height: 92px;
}

.macro-label {
    color: #666;
    font-size: 0.82rem;
    margin-bottom: 3px;
}

.macro-value {
    font-size: 1.75rem;
    font-weight: 800;
    line-height: 1.05;
}

.good-pill {
    display: inline-block;
    background: #e8f7ee;
    color: #157347;
    border-radius: 999px;
    padding: 4px 9px;
    margin-top: 7px;
    font-size: 0.78rem;
    font-weight: 700;
}

.bad-pill {
    display: inline-block;
    background: #ffe7e7;
    color: #a10000;
    border-radius: 999px;
    padding: 4px 9px;
    margin-top: 7px;
    font-size: 0.78rem;
    font-weight: 700;
}

/* CARDS */
.chief-card {
    background: #ffffff;
    border: 1px solid #eeeeee;
    border-radius: 20px;
    padding: 15px;
    margin: 10px 0;
    box-shadow: 0 2px 10px rgba(0,0,0,0.04);
}

.soft-card {
    background: #f7f8fb;
    border-radius: 20px;
    padding: 15px;
    margin: 10px 0;
}

.meal-title {
    font-size: 1.05rem;
    font-weight: 750;
    margin-bottom: 6px;
}

.meal-time {
    font-size: 0.82rem;
    color: #777;
    margin-bottom: 7px;
}

.macro-row {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
    margin-top: 8px;
}

.macro-pill {
    background: #f0f2f6;
    border-radius: 999px;
    padding: 6px 10px;
    font-size: 0.86rem;
}

.safe-box {
    background: #e8f7ee;
    color: #157347;
    border-radius: 14px;
    padding: 10px 12px;
    margin-top: 9px;
    font-weight: 650;
}

.warn-box {
    background: #fff4d8;
    color: #8a5a00;
    border-radius: 14px;
    padding: 10px 12px;
    margin-top: 9px;
    font-weight: 650;
}

/* QUICK ITEMS */
.quick-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 9px;
    margin-top: 8px;
}

.quick-tile {
    background: #ffffff;
    border: 1px solid #eeeeee;
    border-radius: 18px;
    padding: 11px 8px;
    text-align: center;
    box-shadow: 0 2px 9px rgba(0,0,0,0.035);
    font-size: 0.86rem;
    font-weight: 750;
    min-height: 58px;
    display: flex;
    align-items: center;
    justify-content: center;
}

.quick-delete {
    font-size: 0.72rem;
    text-align: center;
    color: #999;
    margin-top: -5px;
    margin-bottom: 6px;
}

/* MONTH */
.month-row {
    background: #ffffff;
    border: 1px solid #eeeeee;
    border-radius: 16px;
    padding: 12px 14px;
    margin: 8px 0;
}

.month-date {
    font-weight: 800;
    margin-bottom: 5px;
}

.small-muted {
    color: #777;
    font-size: 0.84rem;
}

/* BUTTONS */
button[kind="secondary"] {
    border-radius: 14px !important;
}

.stButton > button {
    border-radius: 14px !important;
}

/* MOBILE */
@media (max-width: 480px) {
    .block-container {
        padding-left: 0.75rem;
        padding-right: 0.75rem;
    }

    .quick-grid {
        grid-template-columns: repeat(3, 1fr);
    }

    .macro-value {
        font-size: 1.55rem;
    }

    .chief-title {
        font-size: 1.55rem;
    }
}
</style>
""", unsafe_allow_html=True)

# ==================================================
# SESSION
# ==================================================
defaults = {
    "ai_result": None,
    "upload_key": 0,
    "text_key": 0,
    "note_key": 0,
    "manual_key": 0,
    "saved_msg": "",
    "settings_preview": None,
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ==================================================
# SAFE INPUT HELPERS
# ==================================================
def to_int(value, default=0):
    try:
        if value is None:
            return default
        txt = str(value).replace(",", ".").strip()
        if txt == "":
            return default
        return int(float(txt))
    except Exception:
        return default

def to_float(value, default=0.0):
    try:
        if value is None:
            return default
        txt = str(value).replace(",", ".").strip()
        if txt == "":
            return default
        return float(txt)
    except Exception:
        return default

# ==================================================
# TIME
# ==================================================
def now_local():
    return datetime.datetime.now(TZ)

def today_str():
    return now_local().strftime("%Y-%m-%d")

def time_str():
    return now_local().strftime("%H:%M:%S")

def reset_inputs():
    st.session_state.ai_result = None
    st.session_state.upload_key += 1
    st.session_state.text_key += 1
    st.session_state.note_key += 1
    st.session_state.manual_key += 1

# ==================================================
# SETTINGS
# ==================================================
def activity_factor(level):
    mapping = {
        "bardzo niska": 1.2,
        "niska": 1.35,
        "umiarkowana": 1.55,
        "wysoka": 1.75,
        "bardzo wysoka": 1.9,
    }
    return mapping.get(level, 1.55)

def calculate_bmr_tdee(age, sex, height_cm, weight_kg, activity):
    if sex == "female":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161
    else:
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5

    tdee = bmr * activity_factor(activity)
    suggested_protein = int(round(weight_kg * 1.8))
    return int(round(bmr)), int(round(tdee)), suggested_protein

def get_settings():
    res = supabase.table("settings").select("*").eq("id", 1).execute()
    data = res.data[0] if res.data else {}

    defaults = {
        "id": 1,
        "age": 35,
        "sex": "male",
        "height_cm": 180,
        "weight_kg": 90,
        "activity_level": "umiarkowana",
        "normal_kcal": 2150,
        "normal_protein": 170,
        "normal_fat": 140,
        "normal_carbs": 50,
        "gym_kcal": 2350,
        "gym_protein": 200,
        "gym_fat": 140,
        "gym_carbs": 50,
    }

    for k, v in defaults.items():
        data.setdefault(k, v)

    bmr, tdee, prot = calculate_bmr_tdee(
        int(data["age"]),
        data["sex"],
        int(data["height_cm"]),
        float(data["weight_kg"]),
        data["activity_level"]
    )

    data["calculated_bmr"] = bmr
    data["calculated_tdee"] = tdee
    data["suggested_protein"] = prot

    return data

def save_settings(data):
    supabase.table("settings").upsert(data).execute()

def goals_from_settings(settings, is_gym):
    if is_gym:
        return {
            "kcal": int(settings["gym_kcal"]),
            "p": int(settings["gym_protein"]),
            "f": int(settings["gym_fat"]),
            "c": int(settings["gym_carbs"]),
        }

    return {
        "kcal": int(settings["normal_kcal"]),
        "p": int(settings["normal_protein"]),
        "f": int(settings["normal_fat"]),
        "c": int(settings["normal_carbs"]),
    }

# ==================================================
# SUPABASE DATA
# ==================================================
def insert_meal(data, meal_type):
    payload = {
        "meal_date": today_str(),
        "meal_time": time_str(),
        "name": str(data.get("nazwa", data.get("name", "Posiłek"))),
        "kcal": int(data.get("kcal", 0)),
        "protein": int(data.get("b", data.get("protein", 0))),
        "fat": int(data.get("t", data.get("fat", 0))),
        "carbs": int(data.get("w", data.get("carbs", 0))),
        "meal_type": meal_type,
        "keto_alert": str(data.get("alert", data.get("keto_alert", "SAFE"))),
        "carb_reason": str(data.get("carb_reason", "")),
        "insulin_alert": str(data.get("insulin_alert", "")),
        "insulin_reason": str(data.get("insulin_reason", "")),
        "ai_note": str(data.get("ai_note", "")),
    }
    supabase.table("meals").insert(payload).execute()

def get_day_meals(date_s=None):
    date_s = date_s or today_str()
    res = (
        supabase.table("meals")
        .select("*")
        .eq("meal_date", date_s)
        .order("meal_time", desc=False)
        .execute()
    )
    return res.data or []

def get_month_meals(year, month):
    start = datetime.date(year, month, 1)
    last = calendar.monthrange(year, month)[1]
    end = datetime.date(year, month, last)

    res = (
        supabase.table("meals")
        .select("*")
        .gte("meal_date", start.strftime("%Y-%m-%d"))
        .lte("meal_date", end.strftime("%Y-%m-%d"))
        .order("meal_date", desc=False)
        .execute()
    )
    return res.data or []

def delete_last_today():
    meals = get_day_meals()
    if not meals:
        return False

    last = sorted(meals, key=lambda x: (x.get("meal_time", ""), x.get("id", 0)))[-1]
    supabase.table("meals").delete().eq("id", last["id"]).execute()
    return True

def sum_meals(meals):
    return {
        "kcal": sum(int(m.get("kcal") or 0) for m in meals),
        "b": sum(int(m.get("protein") or 0) for m in meals),
        "t": sum(int(m.get("fat") or 0) for m in meals),
        "w": sum(int(m.get("carbs") or 0) for m in meals),
    }

# ==================================================
# QUICK ITEMS
# ==================================================
def get_quick_items():
    res = supabase.table("quick_items").select("*").order("created_at", desc=False).execute()
    return res.data or []

def add_quick_item(name, kcal, protein, fat, carbs, note=""):
    supabase.table("quick_items").insert({
        "name": name,
        "kcal": int(kcal),
        "protein": int(protein),
        "fat": int(fat),
        "carbs": int(carbs),
        "note": note or ""
    }).execute()

def delete_quick_item(item_id):
    supabase.table("quick_items").delete().eq("id", item_id).execute()

# ==================================================
# GEMINI — SNIPER ZACHOWANY
# ==================================================
def get_available_models():
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"

    try:
        resp = requests.get(url, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            valid_models = []

            preferred_keywords = ["flash", "gemini"]

            for m in data.get("models", []):
                name = m.get("name", "").split("/")[-1]
                methods = m.get("supportedGenerationMethods", [])

                if "generateContent" in methods:
                    if any(k in name.lower() for k in preferred_keywords):
                        valid_models.append(name)

            valid_models = sorted(
                valid_models,
                key=lambda x: (0 if "flash" in x.lower() else 1, x)
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
        "insulin_reason": str(data.get("insulin_reason", "")),
        "ai_note": str(data.get("ai_note", "")),
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

# ==================================================
# PROMPT
# ==================================================
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
11. Jeśli użytkownik poda markowy produkt lub dokładną gramaturę/objętość, użyj tej porcji dokładnie.
12. Jeśli dane produktu są niepewne, wpisz krótką uwagę w ai_note.

DODATKOWE INFO OD UŻYTKOWNIKA:
{extra_info}

Zwróć WYŁĄCZNIE JSON:
{{
  "nazwa": "krótka nazwa posiłku",
  "kcal": 0,
  "b": 0,
  "t": 0,
  "w": 0,
  "alert": "SAFE albo WARN",
  "carb_reason": "krótki opis co podbiło węgle albo pusty tekst",
  "insulin_alert": "LOW albo MEDIUM albo HIGH",
  "insulin_reason": "krótkie wyjaśnienie",
  "ai_note": "krótka uwaga lub pusty tekst"
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

def analyze_text_direct(description, note=""):
    payload = {
        "contents": [{
            "parts": [{
                "text": f"""
Przeanalizuj opis posiłku lub napoju użytkownika.

Opis:
{description}

{build_prompt(note)}
"""
            }]
        }],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.1
        }
    }

    return ask_gemini(payload)
    # ==================================================
# UI HELPERS
# ==================================================
def macro_html(label, used, goal):
    remaining = int(goal - used)

    if remaining >= 0:
        pill = f'<span class="good-pill">↑ {remaining} zostało</span>'
    else:
        pill = f'<span class="bad-pill">↓ {abs(remaining)} ponad</span>'

    return f"""
    <div class="macro-card">
        <div class="macro-label">{label} ({goal})</div>
        <div class="macro-value">{int(used)}</div>
        {pill}
    </div>
    """

def show_ai_result(data):
    st.markdown(f"""
    <div class="chief-card">
        <div class="meal-title">Wynik: {data.get("nazwa", "Posiłek")}</div>
        <div class="macro-row">
            <span class="macro-pill">🔥 {data.get("kcal", 0)} kcal</span>
            <span class="macro-pill">Białko {data.get("b", 0)} g</span>
            <span class="macro-pill">Tłuszcze {data.get("t", 0)} g</span>
            <span class="macro-pill">Węgle {data.get("w", 0)} g</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    carbs = int(data.get("w", 0))
    alert = data.get("alert", "SAFE")
    insulin_alert = data.get("insulin_alert", "LOW")

    if "WARN" in alert or carbs > 20:
        st.markdown('<div class="warn-box">⚠️ Uwaga: posiłek może nie być keto-safe albo ma podwyższone węgle.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="safe-box">✅ Low Carb / Keto Safe</div>', unsafe_allow_html=True)

    if data.get("carb_reason"):
        st.info(f"🍞 Co podbiło węgle: {data.get('carb_reason')}")

    if insulin_alert == "HIGH":
        st.warning(f"🩸 Możliwy większy wyrzut insuliny: {data.get('insulin_reason', '')}")
    elif insulin_alert == "MEDIUM":
        st.info(f"🩸 Umiarkowany wpływ na insulinę: {data.get('insulin_reason', '')}")
    elif data.get("insulin_reason"):
        st.caption(f"🩸 Insulina: niskie ryzyko — {data.get('insulin_reason', '')}")

def meal_card(meal):
    name = meal.get("name", "Posiłek")
    time_s = str(meal.get("meal_time", ""))[:5]
    kcal = int(meal.get("kcal") or 0)
    b = int(meal.get("protein") or 0)
    t = int(meal.get("fat") or 0)
    w = int(meal.get("carbs") or 0)

    st.markdown(f"""
    <div class="chief-card">
        <div class="meal-time">🕒 {time_s}</div>
        <div class="meal-title">{name}</div>
        <div class="macro-row">
            <span class="macro-pill">🔥 {kcal} kcal</span>
            <span class="macro-pill">Białko {b} g</span>
            <span class="macro-pill">Tłuszcze {t} g</span>
            <span class="macro-pill">Węgle {w} g</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ==================================================
# LOAD DATA
# ==================================================
settings = get_settings()
today_meals = get_day_meals()
today_sum = sum_meals(today_meals)

# ==================================================
# HEADER
# ==================================================
st.markdown("""
<div class="chief-header">
    <div class="chief-title">⚓ Chief Nutrition v4.2</div>
    <div class="chief-subtitle">Low carb tracker • mobile optimized</div>
</div>
""", unsafe_allow_html=True)

screen = st.radio(
    "Ekran",
    ["🏠 Dzisiaj", "📋 Dzień", "📅 Miesiąc", "⚙️ Ustawienia"],
    horizontal=True,
    label_visibility="collapsed"
)

# ==================================================
# SCREEN 1
# ==================================================
if screen == "🏠 Dzisiaj":
    is_gym = st.toggle("💪 TRENING (Gym Day)", value=False)
    goals = goals_from_settings(settings, is_gym)

    st.markdown(f"""
    <div class="macro-grid">
        {macro_html("Kalorie", today_sum["kcal"], goals["kcal"])}
        {macro_html("Białko", today_sum["b"], goals["p"])}
        {macro_html("Tłuszcze", today_sum["t"], goals["f"])}
        {macro_html("Węgle", today_sum["w"], goals["c"])}
    </div>
    """, unsafe_allow_html=True)

    st.progress(min(float(today_sum["kcal"]) / max(float(goals["kcal"]), 1.0), 1.0))

    if st.session_state.saved_msg:
        st.success(st.session_state.saved_msg)
        st.session_state.saved_msg = ""

    st.divider()
    st.subheader("📸 Dodaj posiłek")

    source = st.radio("Źródło:", ["Galeria", "Aparat", "Opis"], horizontal=True)

    img_file = None
    text_description = ""

    if source == "Galeria":
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
            placeholder="np. jajecznica z 4 jaj albo kufel 500 ml Kozel",
            key=f"text_{st.session_state.text_key}"
        )

    note = st.text_input(
        "Dodatkowe info",
        key=f"note_{st.session_state.note_key}"
    )

    can_analyze = bool(img_file) or bool(text_description.strip())

    if st.button("ANALIZUJ POSIŁEK", disabled=not can_analyze, use_container_width=True):
        with st.spinner("Analizuję..."):
            try:
                if source == "Opis":
                    st.session_state.ai_result = analyze_text_direct(text_description.strip(), note)
                else:
                    img = Image.open(img_file)
                    st.session_state.ai_result = analyze_image_direct(img, note)
                st.rerun()
            except Exception as e:
                st.error(f"Problem z analizą: {e}")

    if st.session_state.ai_result:
        show_ai_result(st.session_state.ai_result)

        a, b = st.columns(2)
        with a:
            if st.button("💾 ZAPISZ", use_container_width=True):
                insert_meal(st.session_state.ai_result, "AI")
                reset_inputs()
                st.session_state.saved_msg = "✅ Zapisano."
                st.rerun()
        with b:
            if st.button("❌ ANULUJ", use_container_width=True):
                reset_inputs()
                st.rerun()

    st.divider()
    st.subheader("⚡ Szybkie")

    quick_items = get_quick_items()

    if quick_items:
        cols = st.columns(3)

        for idx, item in enumerate(quick_items):
            col = cols[idx % 3]
            with col:
                if st.button(item["name"], key=f"quick_{item['id']}", use_container_width=True):
                    insert_meal({
                        "nazwa": item["name"],
                        "kcal": item["kcal"],
                        "b": item["protein"],
                        "t": item["fat"],
                        "w": item["carbs"],
                        "alert": "SAFE"
                    }, "QUICK")
                    st.session_state.saved_msg = f"✅ Dodano {item['name']}"
                    st.rerun()

                if st.button("Usuń", key=f"del_{item['id']}", use_container_width=True):
                    delete_quick_item(item["id"])
                    st.rerun()
    else:
        st.info("Brak szybkich produktów.")

    st.divider()
    st.subheader("📝 Ręcznie")

    with st.form(f"manual_{st.session_state.manual_key}", clear_on_submit=True):
        n = st.text_input("Nazwa")
        kcal = st.text_input("Kalorie", value="")
        protein = st.text_input("Białko", value="")
        fat = st.text_input("Tłuszcze", value="")
        carbs = st.text_input("Węgle", value="")
        note_manual = st.text_input("Notatka")

        c1, c2 = st.columns(2)

        with c1:
            save_manual = st.form_submit_button("💾 Zapisz", use_container_width=True)

        with c2:
            add_quick = st.form_submit_button("⚡ Do szybkich", use_container_width=True)

        if save_manual or add_quick:
            if not n.strip():
                st.error("Podaj nazwę.")
            else:
                kcal_i = to_int(kcal)
                protein_i = to_int(protein)
                fat_i = to_int(fat)
                carbs_i = to_int(carbs)

                if save_manual:
                    insert_meal({
                        "nazwa": n,
                        "kcal": kcal_i,
                        "b": protein_i,
                        "t": fat_i,
                        "w": carbs_i
                    }, "MANUAL")
                    st.session_state.saved_msg = "✅ Dodano ręcznie."
                    st.session_state.manual_key += 1
                    st.rerun()

                if add_quick:
                    add_quick_item(n, kcal_i, protein_i, fat_i, carbs_i, note_manual)
                    st.session_state.saved_msg = "✅ Dodano do szybkich."
                    st.session_state.manual_key += 1
                    st.rerun()

elif screen == "📋 Dzień":
    st.subheader(f"📋 Raport dnia — {now_local().strftime('%d.%m.%Y')}")

    if not today_meals:
        st.info("Brak wpisów.")
    else:
        for meal in today_meals:
            meal_card(meal)

        if st.button("↩️ Cofnij ostatni wpis", use_container_width=True):
            delete_last_today()
            st.rerun()

elif screen == "📅 Miesiąc":
    now = now_local()
    year = now.year
    month = now.month
    last_day = calendar.monthrange(year, month)[1]

    month_meals = get_month_meals(year, month)
    grouped = {}
    for m in month_meals:
        grouped.setdefault(m["meal_date"], []).append(m)

    for day in range(1, last_day + 1):
        d = datetime.date(year, month, day).strftime("%Y-%m-%d")
        meals = grouped.get(d, [])
        s = sum_meals(meals)

        st.markdown(f"""
        <div class="month-row">
            <div class="month-date">{day:02d}.{month:02d}</div>
            <div class="macro-row">
                <span class="macro-pill">🔥 {s["kcal"]}</span>
                <span class="macro-pill">B {s["b"]}</span>
                <span class="macro-pill">T {s["t"]}</span>
                <span class="macro-pill">W {s["w"]}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

elif screen == "⚙️ Ustawienia":
    st.subheader("⚙️ Ustawienia")

    age = st.text_input("Wiek", value=str(settings["age"]))
    sex = st.selectbox("Płeć", ["male", "female"])
    height = st.text_input("Wzrost cm", value=str(settings["height_cm"]))
    weight = st.text_input("Waga kg", value=str(settings["weight_kg"]))
    activity = st.selectbox(
        "Aktywność",
        ["bardzo niska", "niska", "umiarkowana", "wysoka", "bardzo wysoka"]
    )

    if st.button("Przelicz", use_container_width=True):
        bmr, tdee, prot = calculate_bmr_tdee(
            to_int(age, 35),
            sex,
            to_int(height, 180),
            to_float(weight, 90),
            activity
        )
        st.session_state.settings_preview = (bmr, tdee, prot)

    preview = st.session_state.settings_preview
    if preview:
        st.info(f"BMR: {preview[0]} | Zero kcal: {preview[1]} | Białko: {preview[2]} g")
