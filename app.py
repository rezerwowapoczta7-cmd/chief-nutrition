import streamlit as st
import requests
import json
import base64
import io
import re
import calendar
from PIL import Image
import pandas as pd
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
# CSS / MOBILE UI
# ==================================================
st.set_page_config(
    page_title="Chief Nutrition",
    layout="centered",
    page_icon="⚓"
)

st.markdown("""
<style>
    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 5rem;
        max-width: 760px;
    }

    div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #eeeeee;
        padding: 12px;
        border-radius: 18px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }

    div[data-testid="stMetricLabel"] {
        font-size: 0.85rem;
    }

    .chief-card {
        background: #ffffff;
        border: 1px solid #eeeeee;
        border-radius: 20px;
        padding: 16px;
        margin: 10px 0;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    }

    .chief-card-soft {
        background: #f7f8fb;
        border-radius: 20px;
        padding: 16px;
        margin: 10px 0;
    }

    .meal-title {
        font-size: 1.05rem;
        font-weight: 700;
        margin-bottom: 6px;
    }

    .meal-time {
        font-size: 0.82rem;
        color: #777;
        margin-bottom: 8px;
    }

    .macro-row {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-top: 8px;
    }

    .macro-pill {
        background: #f0f2f6;
        border-radius: 999px;
        padding: 6px 10px;
        font-size: 0.88rem;
    }

    .safe-pill {
        background: #e8f7ee;
        color: #157347;
        border-radius: 14px;
        padding: 10px 12px;
        margin-top: 10px;
        font-weight: 600;
    }

    .warn-pill {
        background: #fff4d8;
        color: #8a5a00;
        border-radius: 14px;
        padding: 10px 12px;
        margin-top: 10px;
        font-weight: 600;
    }

    .danger-pill {
        background: #ffe7e7;
        color: #a10000;
        border-radius: 14px;
        padding: 10px 12px;
        margin-top: 10px;
        font-weight: 600;
    }

    .small-muted {
        color: #777;
        font-size: 0.86rem;
    }

    .month-row {
        background: #ffffff;
        border: 1px solid #eeeeee;
        border-radius: 16px;
        padding: 12px 14px;
        margin: 8px 0;
    }

    .month-date {
        font-weight: 700;
        margin-bottom: 5px;
    }

    .chief-title {
        font-size: 2.0rem;
        font-weight: 800;
        margin-bottom: 0.2rem;
    }

    .chief-subtitle {
        color: #777;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# ==================================================
# SESSION STATE
# ==================================================
defaults = {
    "ai_result": None,
    "upload_key": 0,
    "text_key": 0,
    "note_key": 0,
    "manual_key": 0,
    "last_saved_msg": "",
    "screen": "🏠 Dzisiaj"
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ==================================================
# TIME HELPERS
# ==================================================
def now_local():
    return datetime.datetime.now(TZ)

def today_str():
    return now_local().strftime("%Y-%m-%d")

def current_time_str():
    return now_local().strftime("%H:%M:%S")

def display_date_pl(date_obj=None):
    if date_obj is None:
        date_obj = now_local().date()
    return date_obj.strftime("%d.%m.%Y")

def reset_inputs():
    st.session_state.ai_result = None
    st.session_state.upload_key += 1
    st.session_state.text_key += 1
    st.session_state.note_key += 1
    st.session_state.manual_key += 1

# ==================================================
# SUPABASE DATA
# ==================================================
def insert_meal(data, meal_type):
    payload = {
        "meal_date": today_str(),
        "meal_time": current_time_str(),
        "name": str(data.get("nazwa", "Posiłek")),
        "kcal": int(data.get("kcal", 0)),
        "protein": int(data.get("b", 0)),
        "fat": int(data.get("t", 0)),
        "carbs": int(data.get("w", 0)),
        "meal_type": meal_type,
        "keto_alert": str(data.get("alert", "SAFE")),
        "carb_reason": str(data.get("carb_reason", "")),
        "insulin_alert": str(data.get("insulin_alert", "")),
        "insulin_reason": str(data.get("insulin_reason", "")),
        "ai_note": str(data.get("ai_note", ""))
    }

    supabase.table("meals").insert(payload).execute()

def get_day_meals(date_s=None):
    if date_s is None:
        date_s = today_str()

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
    last_day = calendar.monthrange(year, month)[1]
    end = datetime.date(year, month, last_day)

    res = (
        supabase.table("meals")
        .select("*")
        .gte("meal_date", start.strftime("%Y-%m-%d"))
        .lte("meal_date", end.strftime("%Y-%m-%d"))
        .order("meal_date", desc=False)
        .execute()
    )

    return res.data or []

def delete_last_meal_today():
    meals = get_day_meals(today_str())
    if not meals:
        return False

    last = sorted(meals, key=lambda x: (x.get("meal_date", ""), x.get("meal_time", ""), x.get("id", 0)))[-1]
    supabase.table("meals").delete().eq("id", last["id"]).execute()
    return True

def sums_from_meals(meals):
    return {
        "kcal": sum(int(m.get("kcal") or 0) for m in meals),
        "b": sum(int(m.get("protein") or 0) for m in meals),
        "t": sum(int(m.get("fat") or 0) for m in meals),
        "w": sum(int(m.get("carbs") or 0) for m in meals),
    }

# ==================================================
# GEMINI — ZACHOWANY SNIPER
# ==================================================
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
        "insulin_reason": str(data.get("insulin_reason", "")),
        "ai_note": str(data.get("ai_note", ""))
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
# PROMPTY
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
    prompt = build_prompt(note)

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

# ==================================================
# UI HELPERS
# ==================================================
def goals_for_day(is_gym):
    return {
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

def metric_card(col, label, used, goal):
    remaining = int(goal - used)

    if remaining >= 0:
        delta = f"{remaining} zostało"
        color = "normal"
    else:
        delta = f"{abs(remaining)} ponad"
        color = "inverse"

    col.metric(
        f"{label} ({goal})",
        int(used),
        delta,
        delta_color=color
    )

def show_ai_result_card(data):
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
        st.markdown('<div class="warn-pill">⚠️ Posiłek może nie być keto-safe albo ma podwyższone węgle.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="safe-pill">✅ Low Carb / Keto Safe</div>', unsafe_allow_html=True)

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
    keto_alert = meal.get("keto_alert", "SAFE")
    carb_reason = meal.get("carb_reason", "")
    insulin_alert = meal.get("insulin_alert", "")
    insulin_reason = meal.get("insulin_reason", "")
    ai_note = meal.get("ai_note", "")

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

    if "WARN" in str(keto_alert) or w > 20:
        st.markdown('<div class="warn-pill">⚠️ Keto / węgle: uwaga</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="safe-pill">✅ Low Carb / Keto Safe</div>', unsafe_allow_html=True)

    if carb_reason:
        st.info(f"🍞 Co podbiło węgle: {carb_reason}")

    if insulin_alert == "HIGH":
        st.warning(f"🩸 Insulina HIGH: {insulin_reason}")
    elif insulin_alert == "MEDIUM":
        st.info(f"🩸 Insulina MEDIUM: {insulin_reason}")
    elif insulin_reason:
        st.caption(f"🩸 Insulina LOW: {insulin_reason}")

    if ai_note:
        st.caption(f"AI note: {ai_note}")

# ==================================================
# MAIN DATA
# ==================================================
today_meals = get_day_meals(today_str())
today_sum = sums_from_meals(today_meals)

# ==================================================
# HEADER / NAV
# ==================================================
st.markdown('<div class="chief-title">⚓ Chief Nutrition v4</div>', unsafe_allow_html=True)
st.markdown('<div class="chief-subtitle">Low carb tracker • mobile build</div>', unsafe_allow_html=True)

screen = st.radio(
    "Ekran",
    ["🏠 Dzisiaj", "📋 Raport dnia", "📅 Miesiąc"],
    horizontal=True,
    label_visibility="collapsed",
    key="screen"
)

# ==================================================
# SCREEN 1 — TODAY
# ==================================================
if screen == "🏠 Dzisiaj":
    is_gym = st.toggle("💪 TRENING (Gym Day)", value=False)
    goals = goals_for_day(is_gym)

    c1, c2, c3, c4 = st.columns(4)
    metric_card(c1, "Kcal", today_sum["kcal"], goals["kcal"])
    metric_card(c2, "B", today_sum["b"], goals["p"])
    metric_card(c3, "T", today_sum["t"], goals["f"])
    metric_card(c4, "W", today_sum["w"], goals["c"])

    st.progress(min(float(today_sum["kcal"]) / float(goals["kcal"]), 1.0))

    if st.session_state.last_saved_msg:
        st.success(st.session_state.last_saved_msg)
        st.session_state.last_saved_msg = ""

    st.divider()

    st.subheader("📸 Dodaj posiłek")

    source = st.radio(
        "Źródło:",
        ["Galeria", "Aparat", "Opis"],
        horizontal=True,
        key="source_choice"
    )

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
            key=f"text_desc_{st.session_state.text_key}"
        )

    note = st.text_input(
        "Dodatkowe info",
        placeholder="np. sos, ukryte składniki, ilość masła",
        key=f"note_{st.session_state.note_key}"
    )

    can_analyze = img_file is not None or text_description.strip() != ""

    analyze_clicked = st.button(
        "ANALIZUJ POSIŁEK",
        disabled=not can_analyze,
        use_container_width=True
    )

    if analyze_clicked:
        with st.spinner("Analizuję posiłek..."):
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
        data = st.session_state.ai_result
        show_ai_result_card(data)

        save_col, cancel_col = st.columns(2)

        with save_col:
            if st.button("💾 ZAPISZ", use_container_width=True):
                insert_meal(data, "AI")
                reset_inputs()
                st.session_state.last_saved_msg = "✅ Zapisano posiłek. Gotowe na kolejny."
                st.rerun()

        with cancel_col:
            if st.button("❌ ANULUJ", use_container_width=True):
                reset_inputs()
                st.rerun()

    st.divider()

    st.subheader("⚡ Szybkie")

    q1, q2 = st.columns(2)

    with q1:
        if st.button("☕ Kawa z mlekiem", use_container_width=True):
            insert_meal({
                "nazwa": "Kawa z mlekiem",
                "kcal": 40,
                "b": 2,
                "t": 2,
                "w": 3,
                "alert": "SAFE",
                "carb_reason": "",
                "insulin_alert": "LOW",
                "insulin_reason": "mała ilość mleka"
            }, "QUICK")
            st.session_state.last_saved_msg = "✅ Dodano kawę."
            st.rerun()

    with q2:
        if st.button("🥜 Garść orzechów", use_container_width=True):
            insert_meal({
                "nazwa": "Mix orzechów",
                "kcal": 180,
                "b": 5,
                "t": 17,
                "w": 4,
                "alert": "SAFE",
                "carb_reason": "",
                "insulin_alert": "LOW",
                "insulin_reason": "tłuszczowo-białkowy produkt low carb"
            }, "QUICK")
            st.session_state.last_saved_msg = "✅ Dodano orzechy."
            st.rerun()

    st.divider()

    st.subheader("📝 Ręcznie")

    with st.form(f"manual_form_{st.session_state.manual_key}", clear_on_submit=True):
        n = st.text_input("Nazwa")
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        ck = col_m1.number_input("Kcal", min_value=0, value=0)
        cb = col_m2.number_input("B", min_value=0, value=0)
        ct = col_m3.number_input("T", min_value=0, value=0)
        cw = col_m4.number_input("W", min_value=0, value=0)

        submitted = st.form_submit_button("Dodaj ręcznie", use_container_width=True)

        if submitted:
            if not n.strip():
                st.error("Podaj nazwę.")
            else:
                insert_meal({
                    "nazwa": n.strip(),
                    "kcal": ck,
                    "b": cb,
                    "t": ct,
                    "w": cw,
                    "alert": "MANUAL",
                    "carb_reason": "",
                    "insulin_alert": "MANUAL",
                    "insulin_reason": ""
                }, "MANUAL")

                st.session_state.manual_key += 1
                st.session_state.last_saved_msg = "✅ Dodano ręcznie. Pola wyczyszczone."
                st.rerun()

# ==================================================
# SCREEN 2 — DAY REPORT
# ==================================================
elif screen == "📋 Raport dnia":
    st.subheader(f"📋 Raport dnia — {display_date_pl()}")

    if not today_meals:
        st.info("Brak wpisów na dziś.")
    else:
        s = today_sum

        st.markdown(f"""
        <div class="chief-card-soft">
            <div class="meal-title">Podsumowanie dnia</div>
            <div class="macro-row">
                <span class="macro-pill">🔥 {s["kcal"]} kcal</span>
                <span class="macro-pill">B {s["b"]} g</span>
                <span class="macro-pill">T {s["t"]} g</span>
                <span class="macro-pill">W {s["w"]} g</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("### Posiłki")

        for meal in today_meals:
            meal_card(meal)

        st.divider()

        if st.button("↩️ Cofnij ostatni wpis z dziś", use_container_width=True):
            ok = delete_last_meal_today()
            if ok:
                st.success("Cofnięto ostatni wpis.")
            else:
                st.info("Nie ma czego cofać.")
            st.rerun()

# ==================================================
# SCREEN 3 — MONTH REPORT
# ==================================================
elif screen == "📅 Miesiąc":
    now = now_local()
    year = now.year
    month = now.month
    month_name = now.strftime("%m.%Y")

    st.subheader(f"📅 Raport miesiąca — {month_name}")

    month_meals = get_month_meals(year, month)

    last_day = calendar.monthrange(year, month)[1]

    grouped = {}
    for m in month_meals:
        d = m.get("meal_date")
        grouped.setdefault(d, []).append(m)

    month_total = sums_from_meals(month_meals)
    days_with_entries = len(grouped)

    st.markdown(f"""
    <div class="chief-card-soft">
        <div class="meal-title">Suma miesiąca</div>
        <div class="macro-row">
            <span class="macro-pill">🔥 {month_total["kcal"]} kcal</span>
            <span class="macro-pill">B {month_total["b"]} g</span>
            <span class="macro-pill">T {month_total["t"]} g</span>
            <span class="macro-pill">W {month_total["w"]} g</span>
        </div>
        <div class="small-muted" style="margin-top:8px;">Dni z wpisami: {days_with_entries}</div>
    </div>
    """, unsafe_allow_html=True)

    for day in range(1, last_day + 1):
        date_obj = datetime.date(year, month, day)
        date_s = date_obj.strftime("%Y-%m-%d")
        meals = grouped.get(date_s, [])
        s = sums_from_meals(meals)

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
