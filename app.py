import streamlit as st
import pandas as pd
import requests # Für ImgBB
from streamlit_gsheets import GSheetsConnection
from datetime import datetime

# --- 1. IMGBB UPLOAD FUNKTION ---
def upload_to_imgbb(file_obj):
    try:
        # API Key aus secrets.toml holen
        if "imgbb" not in st.secrets:
            st.error("Fehler: [imgbb] key fehlt in secrets.toml")
            return None
            
        api_key = st.secrets["imgbb"]["key"]
        url = "https://api.imgbb.com/1/upload"
        
        # Daten vorbereiten
        payload = {
            "key": api_key,
        }
        files = {
            "image": file_obj.getvalue()
        }
        
        # Senden
        response = requests.post(url, data=payload, files=files)
        result = response.json()
        
        # Ergebnis prüfen
        if result["success"]:
            return result["data"]["url_viewer"] # Link zum Ansehen
        else:
            st.error(f"Fehler von ImgBB: {result['status_code']} - {result.get('error', {}).get('message')}")
            return None
            
    except Exception as e:
        st.error(f"Upload Fehler: {e}")
        return None

# --- 2. SETUP & DATEN ---
# Liste aller Tutoren
TUTOREN_LISTE = ["Sami", "Lucas", "Sun", "Consti", "Denice","Duc","Gramos","Irmak","Kristina","Lim","Oumaima","Zhouyu","Amelie","Anna","Lisa","Rion","Sophie","Valeria"]

st.set_page_config(page_title="Tutoren Buchhaltung", layout="wide")
st.title("💰 Buchhaltung Tutorenkasse")

# Verbindung zu Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# Daten laden
try:
    df = conn.read(ttl=5)
    df = df.dropna(how="all")
except:
    # Fallback bei leerem Sheet
    df = pd.DataFrame(columns=[
        "Datum", "Tutor", "Event", "Kosten", "Einnahmen", 
        "Notiz", "Beleg", "Rückerstattet", "ÜberschussÜbergeben", "Bestätigt"
    ])

# Datentypen erzwingen
df["Kosten"] = pd.to_numeric(df["Kosten"], errors='coerce').fillna(0.0)
df["Einnahmen"] = pd.to_numeric(df["Einnahmen"], errors='coerce').fillna(0.0)
df["Rückerstattet"] = df["Rückerstattet"].astype(bool)
df["ÜberschussÜbergeben"] = df["ÜberschussÜbergeben"].astype(bool)

if "Bestätigt" not in df.columns:
    df["Bestätigt"] = False
df["Bestätigt"] = df["Bestätigt"].astype(bool)

# Berechnungen
df["Überschuss"] = df["Einnahmen"] - df["Kosten"]

# LOGIK: Kassenstand berechnet sich NUR aus BESTÄTIGTEN Einträgen
# Wir erstellen eine temporäre Spalte "RechnerischerWert". 
df["RechnerischerWert"] = df["Überschuss"].where(df["Bestätigt"] == True, 0.0)

# Styling Funktion
def style_table(row):
    color = '' 
    if row['Event'] == 'Getränkeeinkauf':
        color = 'background-color: #d5d5d5; color: black' # Grau
    elif row['Einnahmen'] >= row['Kosten']:
        color = 'background-color: #c6efce; color: black' # Grün
    else:
        color = 'background-color: #ffc7ce; color: black' # Rot
    return [color] * len(row)

# --- 3. SIDEBAR & LOGIN LOGIK ---
with st.sidebar:
    st.header("Login")
    admin_password = st.text_input("Admin Passwort", type="password")
    
    is_admin = False
    if "admin" in st.secrets and admin_password == st.secrets["admin"]["password"]:
        is_admin = True
        st.success("🔓 Admin-Modus freigeschaltet")
    elif admin_password:
        st.error("Falsches Passwort")

# --- 4. TABS ERSTELLEN ---
if is_admin:
    # Admin sieht ALLE 3 Tabs
    tab1, tab2, tab3 = st.tabs(["📋 Übersicht & Eintrag", "⚙️ Admin / Status ändern", "💸 Abrechnung"])
else:
    # Normale User sehen nur 2 Tabs (Tab 2 wird übersprungen)
    tab1, tab3 = st.tabs(["📋 Übersicht & Eintrag", "💸 Abrechnung"])
    tab2 = None # Wichtig: Variable auf None setzen

# === TAB 1: EINTAGEN & ANSEHEN (FÜR ALLE) ===
with tab1:
    col_input, col_view = st.columns([1, 2])
    
    with col_input:
        st.subheader("Neues Event eintragen")
        st.info("Wichtig: Beleg als Bild hochladen (jpg, png)!")
        with st.form("entry_form"):
            tutor_name = st.selectbox("Dein Name", sorted(TUTOREN_LISTE))
            event_type = st.selectbox("Event Typ", ["Kochabend", "Backtag", "Getränkeeinkauf", "Getränkeverkauf", "Bereichsfest", "GAP Verleih"])
            date = st.date_input("Datum", datetime.today(), format="DD/MM/YYYY")
            
            c1, c2 = st.columns(2)
            kosten = c1.number_input("Kosten (€)", min_value=0.0, step=0.01)
            einnahmen = c2.number_input("Einnahmen (€)", min_value=0.0, step=0.01)
            
            note = st.text_area("Notiz")
            beleg = st.file_uploader("Beleg hochladen (Bild)")
            
            submitted = st.form_submit_button("Eintragen")
            
            if submitted:
                beleg_link = "Kein Beleg"
                
                if beleg is not None:
                    with st.spinner("Lade Beleg hoch..."):
                        link = upload_to_imgbb(beleg)
                        if link:
                            beleg_link = link
                
                new_data = pd.DataFrame([{
                    "Datum": date,
                    "Tutor": tutor_name,
                    "Event": event_type,
                    "Kosten": kosten,
                    "Einnahmen": einnahmen,
                    "Notiz": note,
                    "Beleg": beleg_link,
                    "Rückerstattet": False,
                    "ÜberschussÜbergeben": False,
                    "Bestätigt": False
                }])
                
                # Speichern
                updated_df = pd.concat([df.drop(columns=["Überschuss", "Kassenstand", "RechnerischerWert"], errors='ignore'), new_data], ignore_index=True)
                conn.update(data=updated_df)
                st.success("Gespeichert! Bitte Seite neu laden (R) um Tabelle zu aktualisieren.")

    with col_view:
        st.subheader("Aktuelle Kassen-Tabelle")
        # Kassenstand berechnen
        df["Kassenstand"] = df["RechnerischerWert"].cumsum()       
        
        # --- FIX: Daten für die Anzeige vorbereiten ---
        display_df = df.copy()
        # Ersetze "Kein Beleg" mit None, damit Streamlit keinen falschen Link anzeigt
        display_df["Beleg"] = display_df["Beleg"].replace("Kein Beleg", None)

        st.dataframe(
            display_df.drop(columns=["RechnerischerWert"], errors='ignore').style.apply(style_table, axis=1).format({
                "Kosten": "{:.2f}€", 
                "Einnahmen": "{:.2f}€", 
                "Überschuss": "{:.2f}€", 
                "Kassenstand": "{:.2f}€"
            }),
            height=600,
            use_container_width=True,
            column_config={
                "Datum": st.column_config.DateColumn("Datum", format="DD/MM/YY", step=1),
                "Kassenstand": st.column_config.NumberColumn("Saldo", help="Aktueller Kassenstand", step=0.01),
                "Bestätigt": st.column_config.CheckboxColumn(label="Bestätigt", help="Erst nach Bestätigung vom Admin wird Saldo & Abrechnung angepasst"),
                "Beleg": st.column_config.LinkColumn("Beleg", display_text="Ansehen", help="Klicken zum Öffnen")
            }
        )
        st.divider()
        st.subheader("📈 Kassenstand-Verlauf")
        
        # Chart Daten vorbereiten (Datum sortieren ist wichtig für die Linie)
        chart_data = df.sort_values("Datum")[["Datum", "Kassenstand"]].set_index("Datum")
        st.line_chart(chart_data, color="#2E8B57")

# === TAB 2: NUR ADMIN (Nur anzeigen, wenn tab2 existiert) ===
if tab2 is not None:
    with tab2:
        st.warning("⚠️ Hier können Rückerstattungen und Geldübergaben bestätigt werden. Erst dann zählen sie zum Saldo!")
        
        edited_df = st.data_editor(
            df.drop(columns=["Überschuss", "Kassenstand", "RechnerischerWert"], errors='ignore'),
            key="editor",
            num_rows="dynamic",
            column_config={
                "Bestätigt": st.column_config.CheckboxColumn("Admin-OK", help="Haken setzen für Berechnung"),
                "Rückerstattet": st.column_config.CheckboxColumn("Geld erstattet?", help="Habe ich dem Tutor Geld gegeben?"),
                "ÜberschussÜbergeben": st.column_config.CheckboxColumn("Überschuss erhalten?", help="Hat mir Tutor Gewinn gegeben?"),
            }
        )
        
        if st.button("Änderungen speichern"):
            conn.update(data=edited_df)
            st.success("Status aktualisiert!")

# === TAB 3: ABRECHNUNG (FÜR ALLE) ===
with tab3:
    st.subheader("Offene Beträge")
    st.info("Hier siehst du, wie viel du bekommst oder abgeben musst (nur bestätigte Einträge).")

    tutors = sorted([t for t in df["Tutor"].unique() if t])
    
    for t in tutors:
        # Nur bestätigte Einträge zählen
        t_df = df[(df["Tutor"] == t) & (df["Bestätigt"] == True)]
        
        schulden_an_tutor = t_df[t_df["Rückerstattet"] == False]["Kosten"].sum()
        schulden_von_tutor = t_df[t_df["ÜberschussÜbergeben"] == False]["Einnahmen"].sum()
        
        saldo = schulden_an_tutor - schulden_von_tutor
        
        # Leere überspringen
        if saldo == 0 and schulden_an_tutor == 0 and schulden_von_tutor == 0:
            continue
        
        col_t1, col_t2 = st.columns([3, 1])
        with col_t1:
            st.markdown(f"**{t}**")
            st.caption(f"Offene Auslagen: {schulden_an_tutor:.2f}€ | Einbehaltener Überschuss: {schulden_von_tutor:.2f}€")
        with col_t2:
            if saldo > 0:
                st.success(f"{t} bekommt {saldo:.2f} €")
            elif saldo < 0:
                st.error(f"{t} muss {abs(saldo):.2f} € abgeben")
            else:
                st.metric("Ausgeglichen", "0.00 €")
        st.divider()