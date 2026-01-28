import streamlit as st
import pandas as pd
import requests
import time
from streamlit_gsheets import GSheetsConnection
from datetime import datetime

# --- 1. CONFIG & SETUP ---
st.set_page_config(page_title="Tutoren Buchhaltung", layout="wide")
st.title("Buchhaltung Tutorenkasse")

# Verbindung vorbereiten
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. HILFSFUNKTIONEN ---

def upload_to_imgbb(file_obj):
    """Lädt Bild zu ImgBB hoch und gibt URL zurück."""
    try:
        if "imgbb" not in st.secrets:
            st.error("Fehler: [imgbb] key fehlt in secrets.toml")
            return None
            
        api_key = st.secrets["imgbb"]["key"]
        url = "https://api.imgbb.com/1/upload"
        payload = {"key": api_key}
        files = {"image": file_obj.getvalue()}
        
        response = requests.post(url, data=payload, files=files)
        result = response.json()
        
        if result["success"]:
            return result["data"]["url_viewer"]
        else:
            st.error(f"ImgBB Fehler: {result.get('error', {}).get('message')}")
            return None
    except Exception as e:
        st.error(f"Upload Fehler: {e}")
        return None

# KORREKTUR HIER: Parameter heißt jetzt 'ttl' statt 'ttl_seconds'
def load_data(ttl=5):
    """Lädt Daten und bereinigt Zahlenformate (Komma zu Punkt)."""
    try:
        # ttl steuert, wie lange der Cache gültig ist.
        df = conn.read(ttl=ttl)
        df = df.dropna(how="all")
        
        # Falls Sheet leer ist, Struktur aufbauen
        expected_cols = ["Datum", "Tutor", "Event", "Kosten", "Einnahmen", 
                         "Notiz", "Beleg", "Rückerstattet", "ÜberschussÜbergeben", "Bestätigt"]
        
        # Fehlende Spalten ergänzen
        for col in expected_cols:
            if col not in df.columns:
                df[col] = pd.NA

        # Datentypen und Komma-Korrektur erzwingen
        for col in ["Kosten", "Einnahmen"]:
            # Erst zu String, Komma ersetzen, dann zu Numeric
            df[col] = df[col].astype(str).str.replace(',', '.', regex=False)
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

        # Booleans sicherstellen
        for col in ["Rückerstattet", "ÜberschussÜbergeben", "Bestätigt"]:
            df[col] = df[col].fillna(False).astype(bool)

        # Datum sicherstellen
        df["Datum"] = pd.to_datetime(df["Datum"], errors='coerce').dt.date

        return df
    except Exception as e:
        st.error(f"Fehler beim Laden der Daten: {e}")
        return pd.DataFrame()

def style_table(row):
    """Färbt Zeilen basierend auf Event-Typ oder Gewinn/Verlust."""
    if row['Event'] == 'Getränkeeinkauf':
        return ['background-color: #e0e0e0; color: black'] * len(row) # Grau
    elif row['Einnahmen'] >= row['Kosten']:
        return ['background-color: #d4edda; color: black'] * len(row) # Grün
    else:
        return ['background-color: #f8d7da; color: black'] * len(row) # Rot

# --- 3. DATEN INITIAL LADEN (Für Anzeige) ---
df = load_data(ttl=5)

# Berechnungen für Anzeige
df["Überschuss"] = df["Einnahmen"] - df["Kosten"]
# Nur bestätigte Einträge zählen zum Kassenstand
df["RechnerischerWert"] = df["Überschuss"].where(df["Bestätigt"] == True, 0.0)
df["Kassenstand"] = df["RechnerischerWert"].cumsum()

# Liste der Tutoren
TUTOREN_LISTE = ["Sami", "Lucas", "Sun", "Consti", "Denice","Duc","Gramos","Irmak","Kristina","Lim","Oumaima","Zhouyu","Amelie","Anna","Lisa","Rion","Sophie","Valeria"]

# --- 4. SIDEBAR LOGIN ---
with st.sidebar:
    st.header("Login")
    admin_password = st.text_input("Admin Passwort", type="password")
    
    is_admin = False
    if "admin" in st.secrets and admin_password == st.secrets["admin"]["password"]:
        is_admin = True
        st.success("🔓 Admin-Modus")
    elif admin_password:
        st.error("Falsches Passwort")

# --- 5. TABS ---
if is_admin:
    tab1, tab2, tab3 = st.tabs(["📋 Übersicht & Eintrag", "⚙️ Admin / Status", "💸 Abrechnung"])
else:
    tab1, tab3 = st.tabs(["📋 Übersicht & Eintrag", "💸 Abrechnung"])
    tab2 = None

# === TAB 1: EINTRAGEN & ÜBERSICHT ===
with tab1:
    col_input, col_view = st.columns([1, 2])
    
    with col_input:
        st.subheader("Neues Event")
        with st.form("entry_form", clear_on_submit=True):
            tutor_name = st.selectbox("Dein Name", sorted(TUTOREN_LISTE))
            event_type = st.selectbox("Event Typ", ["Kochabend", "Backtag", "Getränkeeinkauf", "Getränkeverkauf", "Bereichsfest", "GAP Verleih", "Kassensturz", "Wohnheimsfrühstück", "Sonstiges"])
            date = st.date_input("Datum", datetime.today())
            
            c1, c2 = st.columns(2)
            kosten = c1.number_input("Kosten (€)", min_value=0.0, step=0.01)
            einnahmen = c2.number_input("Einnahmen (€)", min_value=0.0, step=0.01)
            
            note = st.text_area("Notiz")
            beleg = st.file_uploader("Beleg (Bild)", type=['png', 'jpg', 'jpeg'])
            
            submitted = st.form_submit_button("Eintragen")
            
            if submitted:
                beleg_link = "Kein Beleg"
                if beleg:
                    with st.spinner("Lade Beleg hoch..."):
                        link = upload_to_imgbb(beleg)
                        if link: beleg_link = link
                
                # --- FIX: RACE CONDITION ---
                # Daten frisch laden mit ttl=0
                current_df = load_data(ttl=0)
                
                new_entry = pd.DataFrame([{
                    "Datum": date, "Tutor": tutor_name, "Event": event_type,
                    "Kosten": kosten, "Einnahmen": einnahmen,
                    "Notiz": note, "Beleg": beleg_link,
                    "Rückerstattet": False, "ÜberschussÜbergeben": False, "Bestätigt": False
                }])
                
                # Alte Berechnungsspalten rauswerfen vor dem Speichern
                cols_to_save = ["Datum", "Tutor", "Event", "Kosten", "Einnahmen", 
                                "Notiz", "Beleg", "Rückerstattet", "ÜberschussÜbergeben", "Bestätigt"]
                
                final_df = pd.concat([current_df[cols_to_save], new_entry], ignore_index=True)
                
                conn.update(data=final_df)
                st.success("Gespeichert! Seite wird aktualisiert...")
                time.sleep(1)
                st.rerun()

    with col_view:
        st.subheader("Aktuelle Tabelle")
        
        # Tabelle anzeigen
        display_df = df.copy()
        display_df["Beleg"] = display_df["Beleg"].replace("Kein Beleg", None)
        
        st.dataframe(
            display_df.drop(columns=["RechnerischerWert"], errors='ignore').style.apply(style_table, axis=1).format({
                "Kosten": "{:.2f}€", "Einnahmen": "{:.2f}€", 
                "Überschuss": "{:.2f}€", "Kassenstand": "{:.2f}€"
            }),
            height=500,
            use_container_width=True,
            column_config={
                "Datum": st.column_config.DateColumn("Datum", format="DD.MM.YYYY"),
                "Beleg": st.column_config.LinkColumn("Beleg", display_text="Ansehen"),
                "Bestätigt": st.column_config.CheckboxColumn("OK?")
            }
        )
        
        st.divider()
        st.subheader("📈 Kassenstand-Verlauf")
        # Chart nach Datum sortieren
        chart_df = df.sort_values("Datum")
        st.line_chart(chart_df, x="Datum", y="Kassenstand", color="#2E8B57")

# === TAB 2: ADMIN (STATUS ÄNDERN) ===
if is_admin and tab2:
    with tab2:
        st.subheader("Verwaltung")
        st.info("Bearbeite hier den Status. Änderungen werden direkt ins Google Sheet geschrieben.")

        # Editor
        edit_cols = ["Datum", "Tutor", "Event", "Kosten", "Einnahmen", "Rückerstattet", "ÜberschussÜbergeben", "Bestätigt", "Notiz"]
        
        edited_df = st.data_editor(
            df[edit_cols],
            key="admin_editor",
            num_rows="dynamic",
            use_container_width=True
        )
        
        col_save, col_settle = st.columns([1, 1])

        # Button 1: Manuelle Änderungen speichern
        with col_save:
            if st.button("💾 Manuelle Änderungen speichern"):
                conn.update(data=edited_df)
                st.success("Update erfolgreich!")
                time.sleep(1)
                st.rerun()

        # Button 2: Alles Abrechnen
        with col_settle:
            if st.button("✅ Alle offenen Beträge als 'Erledigt' markieren", type="primary"):
                with st.spinner("Setze alle Geldflüsse auf TRUE..."):
                    # 1. Frische Daten laden
                    fresh_df = load_data(ttl=0)
                    
                    # 2. Alles auf True setzen
                    fresh_df["Rückerstattet"] = True
                    fresh_df["ÜberschussÜbergeben"] = True
                    
                    # 3. Speichern
                    conn.update(data=fresh_df)
                    st.success("Alles abgerechnet!")
                    time.sleep(1)
                    st.rerun()

# === TAB 3: ABRECHNUNG ===
with tab3:
    st.subheader("Offene Beträge (Salden)")
    st.caption("Berechnung basiert nur auf vom Admin **bestätigten** Einträgen.")

    tutors = sorted([t for t in df["Tutor"].unique() if t])
    has_open_items = False
    
    for t in tutors:
        # Filter: Tutor UND Bestätigt
        t_df = df[(df["Tutor"] == t) & (df["Bestätigt"] == True)]
        
        # Was hat Tutor ausgelegt und noch nicht wiederbekommen?
        schulden_an_tutor = t_df[t_df["Rückerstattet"] == False]["Kosten"].sum()
        
        # Was hat Tutor eingenommen und noch nicht abgegeben?
        schulden_von_tutor = t_df[t_df["ÜberschussÜbergeben"] == False]["Einnahmen"].sum()
        
        saldo = schulden_an_tutor - schulden_von_tutor
        
        # Nur anzeigen, wenn es etwas zu tun gibt
        if saldo != 0 or schulden_an_tutor > 0 or schulden_von_tutor > 0:
            has_open_items = True
            with st.container():
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.markdown(f"**{t}**")
                    st.text(f"Auslagen offen: {schulden_an_tutor:.2f}€ | Einnahmen einbehalten: {schulden_von_tutor:.2f}€")
                with c2:
                    if saldo > 0:
                        st.success(f"Bekommt: {saldo:.2f} €")
                    elif saldo < 0:
                        st.error(f"Zahlt: {abs(saldo):.2f} €")
                    else:
                        st.info("Ausgeglichen (Verrechnet)")
                st.divider()
    
    if not has_open_items:
        st.success("Alles ausgeglichen! Keine offenen Schulden.")