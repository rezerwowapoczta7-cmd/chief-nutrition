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

.chief-header {
    background: linear-gradient(135deg, #f7f9ff, #ffffff);
    border: 1px solid #eeeeee;
    border-radius: 24px;
    padding: 18px 18px 14px 18px;
    margin-bottom: 14px;
    box-shadow: 0 3px 14px rgba(0,0,0,0.05);
}

.chief-title {
    font-size: 1.85rem;
    font-weight: 850;
    line-height: 1.1;
}

.chief-subtitle {
    color: #777;
    margin-top: 5px;
    font-size: 0.95rem;
}

.nav-card {
    background: #ffffff;
    border: 1px solid #eeeeee;
    border-radius: 20px;
    padding: 10px;
    margin-bottom: 14px;
}

.macro-card {
    background: #ffffff;
    border: 1px solid #eeeeee;
    border-radius: 20px;
    padding: 13px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.04);
    min-height: 104px;
}

.macro-label {
    color: #666;
    font-size: 0.86rem;
    margin-bottom: 4px;
}

.macro-value {
    font-size: 2.0rem;
    font-weight: 750;
    line-height: 1.1;
}

.good-pill {
    display: inline-block;
    background: #e8f7ee;
    color: #157347;
    border-radius: 999px;
    padding: 5px 10px;
    margin-top: 8px;
    font-size: 0.82rem;
    font-weight: 700;
}

.bad-pill {
    display: inline-block;
    background: #ffe7e7;
    color: #a10000;
    border-radius: 999px;
    padding: 5px 10px;
    margin-top: 8px;
    font-size: 0.82rem;
    font-weight: 700;
}

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

button[kind="secondary"] {
    border-radius: 14px !important;
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
    "quick_edit_id": None,
    "saved_msg": "",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

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
    # Mifflin-St Jeor
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

def update_quick_item(item_id, name, kcal, protein, fat, carbs, note=""):
    supabase.table("quick_items").update({
        "name": name,
        "kcal": int(kcal),
        "protein": int(protein),
        "fat": int(fat),
        "carbs": int(carbs),
        "note": note or ""
    }).eq("id", item_id).execute()

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
def show_macro_card(label, used, goal):
    remaining = int(goal - used)
    if remaining >= 0:
        pill = f'<span class="good-pill">↑ {remaining} zostało</span>'
    else:
        pill = f'<span class="bad-pill">↓ {abs(remaining)} ponad</span>'

    st.markdown(f"""
    <div class="macro-card">
        <div class="macro-label">{label} ({goal})</div>
        <div class="macro-value">{int(used)}</div>
        {pill}
    </div>
    """, unsafe_allow_html=True)

def show_ai_result(data):
    st.markdown(f"""
    <div class="chief-card">
        <div class="meal-title">Wynik: {data.get("nazwa", "Posiłek")}</div>
        <div class="macro-row">
            <span class="macro-pill">🔥 {data.get("kcal", 0)} kcal</span>
            <span class="macro-pill">B {data.get("b", 0)} g</span>
            <span class="macro-pill">T {data.get("t", 0)} g</span>
            <span class="macro-pill">W {data.get("w", 0)} g</span>
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

    if data.get("ai_note"):
        st.caption(f"AI note: {data.get('ai_note')}")

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
            <span class="macro-pill">B {b} g</span>
            <span class="macro-pill">T {t} g</span>
            <span class="macro-pill">W {w} g</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if "WARN" in str(meal.get("keto_alert", "")) or w > 20:
        st.markdown('<div class="warn-box">⚠️ Keto / węgle: uwaga</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="safe-box">✅ Low Carb / Keto Safe</div>', unsafe_allow_html=True)

    if meal.get("carb_reason"):
        st.info(f"🍞 Co podbiło węgle: {meal.get('carb_reason')}")

    insulin_alert = meal.get("insulin_alert", "")
    insulin_reason = meal.get("insulin_reason", "")

    if insulin_alert == "HIGH":
        st.warning(f"🩸 Insulina HIGH: {insulin_reason}")
    elif insulin_alert == "MEDIUM":
        st.info(f"🩸 Insulina MEDIUM: {insulin_reason}")
    elif insulin_reason:
        st.caption(f"🩸 Insulina LOW: {insulin_reason}")

# ==================================================
# APP DATA
# ==================================================
settings = get_settings()
today_meals = get_day_meals()
today_sum = sum_meals(today_meals)

# ==================================================
# HEADER / NAV
# ==================================================
st.markdown("""
<div class="chief-header">
    <div class="chief-title">⚓ Chief Nutrition v4.1</div>
    <div class="chief-subtitle">Low carb tracker • daily build</div>
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

    r1c1, r1c2 = st.columns(2)
    with r1c1:
        show_macro_card("Kcal", today_sum["kcal"], goals["kcal"])
    with r1c2:
        show_macro_card("B", today_sum["b"], goals["p"])

    r2c1, r2c2 = st.columns(2)
    with r2c1:
        show_macro_card("T", today_sum["t"], goals["f"])
    with r2c2:
        show_macro_card("W", today_sum["w"], goals["c"])

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
            placeholder="np. jajecznica z 4 jaj na maśle albo kufel 500 ml piwa Kozel czarny",
            key=f"text_{st.session_state.text_key}"
        )

    note = st.text_input(
        "Dodatkowe info",
        placeholder="np. sos, ukryte składniki, ilość masła",
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

        csave, ccancel = st.columns(2)
        with csave:
            if st.button("💾 ZAPISZ", use_container_width=True):
                insert_meal(st.session_state.ai_result, "AI")
                reset_inputs()
                st.session_state.saved_msg = "✅ Zapisano. Gotowe na kolejny posiłek."
                st.rerun()

        with ccancel:
            if st.button("❌ ANULUJ", use_container_width=True):
                reset_inputs()
                st.rerun()

    st.divider()
    st.subheader("⚡ Szybkie")

    quick_items = get_quick_items()

    if not quick_items:
        st.info("Brak szybkich produktów. Dodaj je z sekcji Ręcznie.")
    else:
        for item in quick_items:
            with st.container():
                st.markdown(f"""
                <div class="chief-card">
                    <div class="meal-title">{item["name"]}</div>
                    <div class="macro-row">
                        <span class="macro-pill">🔥 {item["kcal"]} kcal</span>
                        <span class="macro-pill">B {item["protein"]} g</span>
                        <span class="macro-pill">T {item["fat"]} g</span>
                        <span class="macro-pill">W {item["carbs"]} g</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                a, b, c = st.columns(3)
                with a:
                    if st.button("➕ Dodaj", key=f"quick_add_{item['id']}", use_container_width=True):
                        insert_meal({
                            "nazwa": item["name"],
                            "kcal": item["kcal"],
                            "b": item["protein"],
                            "t": item["fat"],
                            "w": item["carbs"],
                            "alert": "SAFE",
                            "carb_reason": "",
                            "insulin_alert": "LOW",
                            "insulin_reason": item.get("note", "")
                        }, "QUICK")
                        st.session_state.saved_msg = f"✅ Dodano: {item['name']}"
                        st.rerun()

                with b:
                    if st.button("✏️ Edytuj", key=f"quick_edit_{item['id']}", use_container_width=True):
                        st.session_state.quick_edit_id = item["id"]
                        st.rerun()

                with c:
                    if st.button("🗑 Usuń", key=f"quick_del_{item['id']}", use_container_width=True):
                        delete_quick_item(item["id"])
                        st.session_state.saved_msg = "✅ Usunięto szybki produkt."
                        st.rerun()

                if st.session_state.quick_edit_id == item["id"]:
                    with st.form(f"edit_quick_{item['id']}"):
                        en = st.text_input("Nazwa", value=item["name"])
                        ec1, ec2, ec3, ec4 = st.columns(4)
                        ek = ec1.number_input("Kcal", min_value=0, value=int(item["kcal"]))
                        eb = ec2.number_input("B", min_value=0, value=int(item["protein"]))
                        et = ec3.number_input("T", min_value=0, value=int(item["fat"]))
                        ew = ec4.number_input("W", min_value=0, value=int(item["carbs"]))
                        enote = st.text_input("Notatka", value=item.get("note", "") or "")

                        s1, s2 = st.columns(2)
                        with s1:
                            if st.form_submit_button("Zapisz zmiany", use_container_width=True):
                                update_quick_item(item["id"], en, ek, eb, et, ew, enote)
                                st.session_state.quick_edit_id = None
                                st.session_state.saved_msg = "✅ Zmieniono szybki produkt."
                                st.rerun()
                        with s2:
                            if st.form_submit_button("Anuluj", use_container_width=True):
                                st.session_state.quick_edit_id = None
                                st.rerun()

    st.divider()
    st.subheader("📝 Ręcznie")

    with st.form(f"manual_{st.session_state.manual_key}", clear_on_submit=True):
        n = st.text_input("Nazwa")
        mc1, mc2, mc3, mc4 = st.columns(4)
        kcal = mc1.number_input("Kcal", min_value=0, value=0)
        b = mc2.number_input("B", min_value=0, value=0)
        t = mc3.number_input("T", min_value=0, value=0)
        w = mc4.number_input("W", min_value=0, value=0)
        note_manual = st.text_input("Notatka / opis", value="")

        save_col, quick_col = st.columns(2)

        with save_col:
            save_manual = st.form_submit_button("💾 Zapisz", use_container_width=True)

        with quick_col:
            add_to_quick = st.form_submit_button("⚡ Dodaj do szybkich", use_container_width=True)

        if save_manual or add_to_quick:
            if not n.strip():
                st.error("Podaj nazwę.")
            else:
                if save_manual:
                    insert_meal({
                        "nazwa": n.strip(),
                        "kcal": kcal,
                        "b": b,
                        "t": t,
                        "w": w,
                        "alert": "MANUAL",
                        "carb_reason": "",
                        "insulin_alert": "MANUAL",
                        "insulin_reason": note_manual
                    }, "MANUAL")
                    st.session_state.saved_msg = "✅ Dodano ręcznie."
                    st.session_state.manual_key += 1
                    st.rerun()

                if add_to_quick:
                    add_quick_item(n.strip(), kcal, b, t, w, note_manual)
                    st.session_state.saved_msg = "✅ Dodano do szybkich."
                    st.session_state.manual_key += 1
                    st.rerun()

# ==================================================
# SCREEN 2 DAY
# ==================================================
elif screen == "📋 Dzień":
    st.subheader(f"📋 Raport dnia — {now_local().strftime('%d.%m.%Y')}")

    if not today_meals:
        st.info("Brak wpisów na dziś.")
    else:
        st.markdown(f"""
        <div class="soft-card">
            <div class="meal-title">Podsumowanie dnia</div>
            <div class="macro-row">
                <span class="macro-pill">🔥 {today_sum["kcal"]} kcal</span>
                <span class="macro-pill">B {today_sum["b"]} g</span>
                <span class="macro-pill">T {today_sum["t"]} g</span>
                <span class="macro-pill">W {today_sum["w"]} g</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        for meal in today_meals:
            meal_card(meal)

        if st.button("↩️ Cofnij ostatni wpis z dziś", use_container_width=True):
            delete_last_today()
            st.rerun()

# ==================================================
# SCREEN 3 MONTH
# ==================================================
elif screen == "📅 Miesiąc":
    now = now_local()
    year = now.year
    month = now.month
    last_day = calendar.monthrange(year, month)[1]

    st.subheader(f"📅 Raport miesiąca — {month:02d}.{year}")

    month_meals = get_month_meals(year, month)
    grouped = {}
    for m in month_meals:
        grouped.setdefault(m["meal_date"], []).append(m)

    total = sum_meals(month_meals)

    st.markdown(f"""
    <div class="soft-card">
        <div class="meal-title">Suma miesiąca</div>
        <div class="macro-row">
            <span class="macro-pill">🔥 {total["kcal"]} kcal</span>
            <span class="macro-pill">B {total["b"]} g</span>
            <span class="macro-pill">T {total["t"]} g</span>
            <span class="macro-pill">W {total["w"]} g</span>
        </div>
        <div class="small-muted" style="margin-top:8px;">Dni z wpisami: {len(grouped)}</div>
    </div>
    """, unsafe_allow_html=True)

    for day in range(1, last_day + 1):
        d = datetime.date(year, month, day).strftime("%Y-%m-%d")
        meals = grouped.get(d, [])
        s = sum_meals(meals)

        if meals:
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
        else:
            st.markdown(f"""
            <div class="month-row" style="opacity:0.45;">
                <div class="month-date">{day:02d}.{month:02d}</div>
                <div class="small-muted">Brak wpisów</div>
            </div>
            """, unsafe_allow_html=True)

# ==================================================
# SCREEN 4 SETTINGS
# ==================================================
elif screen == "⚙️ Ustawienia":
    st.subheader("⚙️ Ustawienia")

    st.markdown("### Dane do wyliczeń")

    with st.form("settings_form"):
        age = st.number_input("Wiek", min_value=10, max_value=100, value=int(settings["age"]))
        sex_label = st.selectbox(
            "Płeć",
            ["male", "female"],
            index=0 if settings["sex"] == "male" else 1,
            format_func=lambda x: "Mężczyzna" if x == "male" else "Kobieta"
        )
        height = st.number_input("Wzrost cm", min_value=120, max_value=230, value=int(settings["height_cm"]))
        weight = st.number_input("Waga kg", min_value=30.0, max_value=250.0, value=float(settings["weight_kg"]), step=0.5)

        activity_options = ["bardzo niska", "niska", "umiarkowana", "wysoka", "bardzo wysoka"]
        activity = st.selectbox(
            "Aktywność",
            activity_options,
            index=activity_options.index(settings["activity_level"]) if settings["activity_level"] in activity_options else 2
        )

        bmr, tdee, suggested_p = calculate_bmr_tdee(age, sex_label, height, weight, activity)

        st.markdown(f"""
        <div class="soft-card">
            <div class="meal-title">Wyliczenia</div>
            <div class="macro-row">
                <span class="macro-pill">BMR: {bmr}</span>
                <span class="macro-pill">Zero kcal: {tdee}</span>
                <span class="macro-pill">Białko sugerowane: {suggested_p} g</span>
            </div>
            <div class="small-muted" style="margin-top:8px;">Zero kcal = orientacyjne utrzymanie wagi. Poniżej deficyt, powyżej nadwyżka.</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("### Cele — dzień zwykły")
        n1, n2, n3, n4 = st.columns(4)
        normal_kcal = n1.number_input("Kcal", min_value=0, value=int(settings["normal_kcal"]), key="normal_kcal")
        normal_p = n2.number_input("B", min_value=0, value=int(settings["normal_protein"]), key="normal_p")
        normal_f = n3.number_input("T", min_value=0, value=int(settings["normal_fat"]), key="normal_f")
        normal_c = n4.number_input("W", min_value=0, value=int(settings["normal_carbs"]), key="normal_c")

        st.markdown("### Cele — dzień treningowy")
        g1, g2, g3, g4 = st.columns(4)
        gym_kcal = g1.number_input("Kcal", min_value=0, value=int(settings["gym_kcal"]), key="gym_kcal")
        gym_p = g2.number_input("B", min_value=0, value=int(settings["gym_protein"]), key="gym_p")
        gym_f = g3.number_input("T", min_value=0, value=int(settings["gym_fat"]), key="gym_f")
        gym_c = g4.number_input("W", min_value=0, value=int(settings["gym_carbs"]), key="gym_c")

        if st.form_submit_button("💾 Zapisz ustawienia", use_container_width=True):
            save_settings({
                "id": 1,
                "age": int(age),
                "sex": sex_label,
                "height_cm": int(height),
                "weight_kg": float(weight),
                "activity_level": activity,
                "calculated_bmr": int(bmr),
                "calculated_tdee": int(tdee),
                "suggested_protein": int(suggested_p),
                "normal_kcal": int(normal_kcal),
                "normal_protein": int(normal_p),
                "normal_fat": int(normal_f),
                "normal_carbs": int(normal_c),
                "gym_kcal": int(gym_kcal),
                "gym_protein": int(gym_p),
                "gym_fat": int(gym_f),
                "gym_carbs": int(gym_c),
                "updated_at": now_local().isoformat()
            })
            st.success("✅ Zapisano ustawienia.")
            st.rerun()
