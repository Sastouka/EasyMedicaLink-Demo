# rdv.py

"""
Blueprint RDV – version mise à jour avec calcul automatique de l'âge
• Ajout 'Date de naissance' (input type="date")
• Ajout 'Sexe' (input type="select")
• Ajout 'Prénom'
• Calcul âge sous forme "x ans y mois"
• Toutes les fonctionnalités originales sont conservées
• Design aligné avec la page d’accueil (navbar, offcanvas, cartes principales)
• Interface responsive pour mobiles et tablettes
"""

import os
import re
import uuid
import shutil
from datetime import datetime, timedelta, date
from pathlib import Path

import pandas as pd
from fpdf import FPDF
from openpyxl import Workbook
from flask import (
    Blueprint, request, render_template_string,
    redirect, url_for, flash, send_file, session, jsonify
)
import utils
import theme

# ------------------------------------------------------------------
# CONFIGURATION DES RÉPERTOIRES
# ------------------------------------------------------------------
def backup_info_base_patient():
    source_file = os.path.join(utils.EXCEL_FOLDER, "info_Base_patient.xlsx")
    if os.path.exists(source_file):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(
            utils.EXCEL_FOLDER,
            f"backup_info_Base_patient_{timestamp}.xlsx"
        )
        shutil.copy2(source_file, backup_file)

EXCEL_DIR = Path(utils.EXCEL_FOLDER)
PDF_DIR   = Path(utils.PDF_FOLDER)
os.makedirs(EXCEL_DIR, exist_ok=True)
os.makedirs(PDF_DIR, exist_ok=True)

EXCEL_FILE        = EXCEL_DIR / "DonneesRDV.xlsx"
CONSULT_FILE      = EXCEL_DIR / "ConsultationData.xlsx"
BASE_PATIENT_FILE = EXCEL_DIR / "info_Base_patient.xlsx"

def initialize_base_patient_file():
    wb = Workbook()
    sheet = wb.active
    sheet.title = "BasePatients"
    sheet.append([
        "Num Ordre", "ID", "Nom", "Prenom", "DateNaissance", "Sexe", "Âge",
        "Antécédents", "Téléphone", "Date", "Heure"
    ])
    wb.save(BASE_PATIENT_FILE)

def save_base_patient_df(df_new: pd.DataFrame):
    if not BASE_PATIENT_FILE.exists():
        initialize_base_patient_file()
        df_existing = pd.DataFrame(columns=df_new.columns)
    else:
        df_existing = pd.read_excel(BASE_PATIENT_FILE, dtype=str)
    df_combined = pd.concat([df_existing, df_new], ignore_index=True)
    if all(col in df_combined.columns for col in ["ID", "Date", "Heure"]):
        df_combined.drop_duplicates(
            subset=["ID", "Date", "Heure"],
            keep="last", inplace=True
        )
    df_combined.to_excel(BASE_PATIENT_FILE, index=False)

# ------------------------------------------------------------------
# HELPER EXCEL
# ------------------------------------------------------------------
def initialize_excel_file():
    wb = Workbook()
    sheet = wb.active
    sheet.title = "RDV"
    sheet.append([
        "Num Ordre", "ID", "Nom", "Prenom", "DateNaissance", "Sexe", "Âge",
        "Antécédents", "Téléphone", "Date", "Heure"
    ])
    wb.save(EXCEL_FILE)

def load_df() -> pd.DataFrame:
    if not EXCEL_FILE.exists():
        initialize_excel_file()
    df = pd.read_excel(EXCEL_FILE, dtype=str)
    if 'Prenom' not in df.columns:
        df.insert(loc=3, column='Prenom', value='')
    if 'DateNaissance' not in df.columns:
        df.insert(loc=4, column='DateNaissance', value='')
    if 'Sexe' not in df.columns:
        df.insert(loc=5, column='Sexe', value='')
    return df

def save_df(df: pd.DataFrame):
    df.to_excel(EXCEL_FILE, index=False)

def load_patients() -> dict:
    patients = {}
    df = load_df()
    for _, row in df.iterrows():
        pid = str(row["ID"]).strip()
        if not pid:
            continue
        patients[pid] = {
            "name":          f"{row['Nom']} {row['Prenom']}".strip(),
            "date_of_birth": str(row["DateNaissance"]),
            "gender":        str(row["Sexe"]),
            "age":           str(row["Âge"]),
            "phone":         str(row["Téléphone"]),
            "antecedents":   str(row["Antécédents"]),
        }
    return patients

# ------------------------------------------------------------------
# CALCULS / VALIDATIONS
# ------------------------------------------------------------------
def generate_time_slots():
    start = datetime.strptime("08:00", "%H:%M")
    return [
        (start + timedelta(minutes=i*15)).strftime("%H:%M")
        for i in range(36)
    ]

def calculate_order_number(time_str: str):
    rdv_time = datetime.strptime(time_str, "%H:%M").time()
    delta = (rdv_time.hour - 8) * 60 + rdv_time.minute
    return (delta // 15) + 1 if 8 <= rdv_time.hour <= 17 else "N/A"

def compute_age_str(dob: date) -> str:
    today_date = date.today()
    years = today_date.year - dob.year - (
        (today_date.month, today_date.day) < (dob.month, dob.day)
    )
    months = today_date.month - dob.month - (today_date.day < dob.day)
    if months < 0:
        months += 12
    return f"{years} ans {months} mois"

PHONE_RE = re.compile(r"^[+0]\d{6,14}$")

# ------------------------------------------------------------------
# DÉCLARATION DU BLUEPRINT
# ------------------------------------------------------------------
rdv_bp = Blueprint("rdv", __name__, url_prefix="/rdv")

# ------------------------------------------------------------------
# ROUTE DE TRANSFERT EN CONSULTATION
# ------------------------------------------------------------------
@rdv_bp.route("/consult/<int:index>", methods=["GET", "POST"])
def consult_rdv(index):
    df_rdv = load_df()
    if not (0 <= index < len(df_rdv)):
        flash("Sélection invalide.", "warning")
        return redirect(url_for("rdv.rdv_home"))
    rdv_row = df_rdv.iloc[index]

    cols = [
        "consultation_date", "patient_id", "patient_name", "date_of_birth",
        "gender", "age", "patient_phone", "antecedents", "clinical_signs",
        "bp", "temperature", "heart_rate", "respiratory_rate", "diagnosis",
        "medications", "analyses", "radiologies", "certificate_category",
        "certificate_content", "rest_duration", "doctor_comment",
        "consultation_id"
    ]
    if CONSULT_FILE.exists():
        df_consult = pd.read_excel(CONSULT_FILE, dtype=str)
    else:
        df_consult = pd.DataFrame(columns=cols)

    form      = request.form
    med_list  = form.getlist("medications_list")
    anal_list = form.getlist("analyses_list")
    rad_list  = form.getlist("radiologies_list")

    consultation_date = datetime.now().strftime("%Y-%m-%d")
    new_row = {
        "consultation_date":    consultation_date,
        "patient_id":           rdv_row["ID"],
        "patient_name":         f"{rdv_row['Nom']} {rdv_row['Prenom']}".strip(),
        "date_of_birth":        form.get("patient_dob", rdv_row.get("DateNaissance", "")).strip(),
        "gender":               form.get("gender", rdv_row.get("Sexe", "")).strip(),
        "age":                  form.get("patient_age", rdv_row.get("Âge", "")).strip(),
        "patient_phone":        form.get("patient_phone", rdv_row.get("Téléphone", "")).strip(),
        "antecedents":          form.get("antecedents", rdv_row.get("Antécédents", "")).strip(),
        "clinical_signs":       form.get("clinical_signs", "").strip(),
        "bp":                   form.get("bp", "").strip(),
        "temperature":          form.get("temperature", "").strip(),
        "heart_rate":           form.get("heart_rate", "").strip(),
        "respiratory_rate":     form.get("respiratory_rate", "").strip(),
        "diagnosis":            form.get("diagnosis", "").strip(),
        "medications":          "; ".join(med_list),
        "analyses":             "; ".join(anal_list),
        "radiologies":          "; ".join(rad_list),
        "certificate_category": form.get("certificate_category", "").strip(),
        "certificate_content":  form.get("certificate_content", "").strip(),
        "rest_duration":        utils.extract_rest_duration(form.get("certificate_content", "")),
        "doctor_comment":       form.get("doctor_comment", "").strip(),
        "consultation_id":      str(uuid.uuid4()),
    }

    df_consult = pd.concat([df_consult, pd.DataFrame([new_row])], ignore_index=True)
    df_consult.to_excel(CONSULT_FILE, index=False)

    df_rdv = df_rdv.drop(df_rdv.index[index]).reset_index(drop=True)
    save_df(df_rdv)

    flash("Patient transféré et consultation enregistrée ✔", "success")
    return redirect(url_for("rdv.rdv_home"))

# ------------------------------------------------------------------
# ROUTE PRINCIPALE RDV
# ------------------------------------------------------------------
@rdv_bp.route("/", methods=["GET", "POST"])
def rdv_home():
    config       = utils.load_config()
    session['theme'] = config.get('theme', theme.DEFAULT_THEME)
    theme_vars   = theme.current_theme()
    theme_names  = list(theme.THEMES.keys())

    df       = load_df()
    patients = load_base_patients()

    if request.method == "POST":
        f         = request.form
        pid       = f.get("patient_id", "").strip()
        nom       = f.get("patient_nom", "").strip()
        prenom    = f.get("patient_prenom", "").strip()
        gender    = f.get("patient_gender", "").strip()
        dob_str   = f.get("patient_dob", "").strip()
        ant       = f.get("patient_ant", "").strip()
        phone     = f.get("patient_phone", "").strip()
        date_rdv  = f.get("rdv_date", "").strip()
        time_rdv  = f.get("rdv_time", "").strip()

        if ((df["Date"] == date_rdv) & (df["Heure"] == time_rdv)).any():
            return render_template_string("""
            <!DOCTYPE html><html><head>
              <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
            </head><body>
              <script>
                Swal.fire({
                  icon: 'warning',
                  title: 'Créneau déjà réservé',
                  text: 'Le rendez-vous du {{ date_rdv }} à {{ time_rdv }} existe déjà.',
                  confirmButtonText: 'OK'
                }).then(() => {
                  window.location.href = '{{ url_for("rdv.rdv_home") }}';
                });
              </script>
            </body></html>
            """, date_rdv=date_rdv, time_rdv=time_rdv)

        if not all([pid, nom, prenom, gender, dob_str, ant, phone, date_rdv, time_rdv]):
            flash("Veuillez remplir tous les champs.", "warning")
            return redirect(url_for("rdv.rdv_home"))
        if not PHONE_RE.fullmatch(phone):
            flash("Téléphone invalide.", "warning")
            return redirect(url_for("rdv.rdv_home"))

        try:
            dob_date = datetime.strptime(dob_str, "%Y-%m-%d").date()
            if dob_date > date.today():
                raise ValueError
        except ValueError:
            flash("Date de naissance invalide.", "warning")
            return redirect(url_for("rdv.rdv_home"))

        age_text = compute_age_str(dob_date)
        full_name = f"{nom} {prenom}".strip()
        if pid in patients and patients[pid]["name"].lower() != full_name.lower():
            flash(f"ID {pid} appartient déjà à {patients[pid]['name']}.", "danger")
            return redirect(url_for("rdv.rdv_home"))

        if pid in patients and (
            patients[pid]["gender"] != gender or
            patients[pid]["age"] != age_text or
            patients[pid]["phone"] != phone or
            patients[pid]["antecedents"] != ant or
            patients[pid]["date_of_birth"] != dob_str
        ):
            df.loc[df["ID"] == pid, [
                "DateNaissance","Sexe","Âge","Téléphone","Antécédents"
            ]] = [dob_str, gender, age_text, phone, ant]

        num_ord = calculate_order_number(time_rdv)
        new_row = pd.DataFrame([[
            num_ord, pid, nom, prenom, dob_str,
            gender, age_text, ant, phone,
            date_rdv, time_rdv
        ]], columns=df.columns)

        df = pd.concat([df, new_row], ignore_index=True)
        df.drop_duplicates(subset=["ID","Date","Heure"], keep="last", inplace=True)
        save_df(df)
        save_base_patient_df(df)

        flash("RDV confirmé ✅", "success")
        return redirect(url_for("rdv.rdv_home"))

    filt_date = request.args.get("date", "")
    df_view   = df[df["Date"] == filt_date] if filt_date else df
    df_view   = df_view.sort_values("Num Ordre", key=lambda s: pd.to_numeric(s, errors="coerce"))

    today     = datetime.now().strftime("%d/%m/%Y")
    iso_today = datetime.now().strftime("%Y-%m-%d")

    return render_template_string(
        rdv_template,
        config=config,
        theme_vars=theme_vars,
        theme_names=theme_names,
        patients=patients,
        df=df_view.to_dict(orient="records"),
        timeslots=generate_time_slots(),
        today=today,
        iso_today=iso_today,
        filt_date=filt_date,
        enumerate=enumerate
    )

# ------------------------------------------------------------------
# SUPPRESSION D’UN RDV
# ------------------------------------------------------------------
@rdv_bp.route("/delete/<int:index>")
def delete_rdv(index):
    df = load_df()
    if 0 <= index < len(df):
        df = df.drop(df.index[index]).reset_index(drop=True)
        save_df(df)
        flash("RDV supprimé.", "info")
    return redirect(url_for("rdv.rdv_home"))

# ------------------------------------------------------------------
# IMPRESSION DES RDV DU JOUR
# ------------------------------------------------------------------
@rdv_bp.route("/pdf_today")
def pdf_today():
    try:
        df = load_df()
        df["Date_parsed"] = pd.to_datetime(
            df["Date"], dayfirst=True, errors="coerce"
        ).dt.date
        today = date.today()
        df_today = df[df["Date_parsed"] == today]

        if df_today.empty:
            flash("Aucun RDV pour aujourd'hui.", "warning")
            return redirect(url_for("rdv.rdv_home"))

        headers = ["ID", "Nom", "Prénom", "Âge", "Téléphonique", "Antécédents", "Date", "Heure", "Num Ordre"]
        data = []
        for _, row in df_today.iterrows():
            data.append([
                row.get("ID", ""),
                row.get("Nom", ""),
                row.get("Prenom", ""),
                row.get("Âge", ""),
                row.get("Téléphone", ""),
                row.get("Antécédents", ""),
                row.get("Date", ""),
                row.get("Heure", ""),
                row.get("Num Ordre", "")
            ])

        today_str = today.strftime("%d-%m-%Y")
        pdf_path = PDF_DIR / f"RDV_du_{today_str.replace('-', '')}.pdf"
        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        pdf.set_font("Arial", size=20, style='B')
        pdf.cell(0, 10, txt=f"RDV du {today.strftime('%d/%m/%Y')}", ln=True, align='C')
        pdf.ln(5)

        col_widths = calculate_pdf_column_widths(headers, data, pdf)

        pdf.set_font("Arial", size=12, style='B')
        for i, header in enumerate(headers):
            pdf.cell(col_widths[i], 10, header, border=1, align='C')
        pdf.ln()

        pdf.set_font("Arial", size=12)
        for row in data:
            for i, item in enumerate(row):
                text = str(item)
                align = 'C' if headers[i] in ["ID", "Âge", "Téléphonique", "Date", "Heure", "Num Ordre"] else 'L'
                pdf.cell(col_widths[i], 8, text, border=1, align=align)
            pdf.ln()

        pdf.output(str(pdf_path), 'F')
        return send_file(str(pdf_path), as_attachment=True, download_name=pdf_path.name)

    except Exception as e:
        flash(f"Erreur génération PDF : {e}", "danger")
        return redirect(url_for("rdv.rdv_home"))

def calculate_pdf_column_widths(headers, data, pdf: FPDF):
    col_widths = [pdf.get_string_width(h) + 8 for h in headers]
    for row in data:
        for i, item in enumerate(row):
            w = pdf.get_string_width(str(item)) + 8
            if w > col_widths[i]:
                col_widths[i] = w
    page_width = pdf.w - pdf.l_margin - pdf.r_margin
    total = sum(col_widths)
    if total > page_width:
        scale = page_width / total
        col_widths = [w * scale for w in col_widths]
    return col_widths

# ------------------------------------------------------------------
# MODIFICATION D’UN RDV
# ------------------------------------------------------------------
@rdv_bp.route("/edit/<int:index>", methods=["GET", "POST"])
def edit_rdv(index):
    config       = utils.load_config()
    session['theme'] = config.get('theme', theme.DEFAULT_THEME)
    theme_vars   = theme.current_theme()
    theme_names  = list(theme.THEMES.keys())
    patients     = load_patients()

    df = load_df()
    filt_date = request.args.get("date", "")
    df_view   = df[df["Date"] == filt_date] if filt_date else df
    df_view   = df_view.sort_values("Num Ordre", key=lambda s: pd.to_numeric(s, errors="coerce"))
    today     = datetime.now().strftime("%d/%m/%Y")
    iso_today = datetime.now().strftime("%Y-%m-%d")

    if not (0 <= index < len(df)):
        flash("RDV introuvable.", "warning")
        return redirect(url_for("rdv.rdv_home"))

    if request.method == "POST":
        f = request.form
        required = [
            "patient_id","patient_nom","patient_prenom","patient_gender",
            "patient_dob","patient_ant","patient_phone","rdv_date","rdv_time"
        ]
        if not all(f.get(k) for k in required):
            flash("Veuillez remplir tous les champs.", "warning")
            return redirect(url_for("rdv.edit_rdv", index=index))

        dob_date = datetime.strptime(f["patient_dob"], "%Y-%m-%d").date()
        age_text = compute_age_str(dob_date)
        num_ord  = calculate_order_number(f["rdv_time"])

        df.at[index, "ID"]            = f["patient_id"]
        df.at[index, "Nom"]           = f["patient_nom"]
        df.at[index, "Prenom"]        = f["patient_prenom"]
        df.at[index, "Sexe"]          = f["patient_gender"]
        df.at[index, "DateNaissance"] = f["patient_dob"]
        df.at[index, "Âge"]           = age_text
        df.at[index, "Antécédents"]   = f["patient_ant"]
        df.at[index, "Téléphone"]     = f["patient_phone"]
        df.at[index, "Date"]          = f["rdv_date"]
        df.at[index, "Heure"]         = f["rdv_time"]
        df.at[index, "Num Ordre"]     = num_ord

        save_df(df)
        flash("RDV mis à jour ✅", "success")
        return redirect(url_for("rdv.rdv_home"))

    edit_row = df.iloc[index]
    edit_date = edit_row["Date"]
    all_rdv = df.to_dict(orient="records")
    reserved_slots = [
        r["Heure"] for r in all_rdv
        if r["Date"] == edit_date and r["Heure"] != edit_row["Heure"]
    ]

    return render_template_string(
        rdv_template,
        config=config,
        theme_vars=theme_vars,
        theme_names=theme_names,
        patients=patients,
        df=df_view.to_dict(orient="records"),
        timeslots=generate_time_slots(),
        today=today,
        iso_today=iso_today,
        filt_date=filt_date,
        enumerate=enumerate,
        edit_index=index,
        edit_row=edit_row,
        reserved_slots=reserved_slots
    )

# ------------------------------------------------------------------
# CHARGEMENT PATIENT_INFO
# ------------------------------------------------------------------
def load_base_patient_df() -> pd.DataFrame:
    if not BASE_PATIENT_FILE.exists():
        initialize_base_patient_file()
    return pd.read_excel(BASE_PATIENT_FILE, dtype=str)

def load_base_patients() -> dict:
    patients = {}
    df = load_base_patient_df()
    for _, row in df.iterrows():
        pid = str(row["ID"]).strip()
        if not pid:
            continue
        patients[pid] = {
            "name":          f"{row['Nom']} {row['Prenom']}".strip(),
            "date_of_birth": str(row["DateNaissance"]),
            "gender":        str(row["Sexe"]),
            "age":           str(row["Âge"]),
            "antecedents":   str(row["Antécédents"]),
            "phone":         str(row["Téléphone"]),
        }
    return patients

@rdv_bp.route("/patient_info/<patient_id>")
def patient_info(patient_id):
    patients = load_base_patients()
    p = patients.get(patient_id)
    if not p:
        return jsonify({}), 404
    return jsonify(p) 

# ------------------------------------------------------------------
# TEMPLATE JINJA (interface responsive + menu thème + cartes)
# ------------------------------------------------------------------
rdv_template = r"""
<!DOCTYPE html>
<html lang="fr">
{{ pwa_head()|safe }}
<head>
<link href="https://fonts.googleapis.com/css2?family=Great+Vibes&display=swap" rel="stylesheet">
<style>
  .card-header h1,
  .card-header .header-item,
  .card-header p {
    font-size: 30px !important;
  }
  .card-header h1 i,
  .card-header .header-item i,
  .card-header p i {
    font-size: 30px !important;
  }
  .header-item {
    font-size: 28px !important;
  }
</style>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
<title>RDV – {{ config.nom_clinique or 'EasyMedicaLink' }}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdn.datatables.net/1.13.7/css/dataTables.bootstrap5.min.css" rel="stylesheet">
<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Great+Vibes&display=swap" rel="stylesheet">
<script src="https://cdn.tailwindcss.com"></script>
<style>
  :root {
    {% for var, val in theme_vars.items() %}
    --{{ var }}: {{ val }};
    {% endfor %}
  }
  body {
    background: var(--bg-color);
    color: var(--text-color);
    padding-top: 56px;
  }
  .navbar, .offcanvas-header {
    background: linear-gradient(45deg, var(--primary-color), var(--secondary-color)) !important;
  }
  .offcanvas-body, .card {
    background: var(--card-bg) !important;
    color: var(--text-color) !important;
  }
  .card-header {
    background: var(--primary-color) !important;
    color: var(--button-text) !important;
  }
  .card {
    border-radius: 15px;
    box-shadow: 0 4px 20px var(--card-shadow) !important;
  }
</style>
</head>
<body>

<nav class="navbar navbar-dark fixed-top">
  <div class="container-fluid d-flex align-items-center">
    <button class="navbar-toggler" type="button" data-bs-toggle="offcanvas" data-bs-target="#settingsOffcanvas">
      <i class="fas fa-bars"></i>
    </button>
    <a class="navbar-brand ms-auto d-flex align-items-center"
       href="{{ url_for('accueil.accueil') }}"
       style="font-family:'Great Vibes',cursive;font-size:2rem;color:white;">
      <i class="fas fa-home me-2" style="transform: translateX(-0.5cm);"></i>
      <i class="fas fa-heartbeat me-2"></i>EasyMedicaLink
    </a>
  </div>
</nav>

<div class="offcanvas offcanvas-start" tabindex="-1" id="settingsOffcanvas">
  <div class="offcanvas-header text-white">
    <h5 class="offcanvas-title"><i class="fas fa-cog me-2"></i>Paramètres</h5>
    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="offcanvas"></button>
  </div>
  <div class="offcanvas-body">
    <form id="rdvSettingsForm" action="{{ url_for('settings') }}" method="POST">
      <div class="mb-3">
        <label for="rdvThemeSelect" class="form-label"><i class="fas fa-palette me-1"></i>Thème</label>
        <select id="rdvThemeSelect" name="theme" class="form-select">
          {% for t in theme_names %}
          <option value="{{ t }}" {% if config.theme == t %}selected{% endif %}>{{ t.capitalize() }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="d-flex gap-2 mb-4">
        <button type="button" id="saveRdvSettings" class="btn btn-success flex-fill">
          <i class="fas fa-save me-2"></i>Enregistrer
        </button>
      </div>
    </form>
    <div class="d-flex gap-2">
      <a href="{{ url_for('login.change_password') }}" class="btn btn-outline-secondary flex-fill">
        <i class="fas fa-key me-2"></i>Modifier passe
      </a>
      <a href="{{ url_for('login.logout') }}" class="btn btn-outline-secondary flex-fill">
        <i class="fas fa-sign-out-alt me-2"></i>Déconnexion
      </a>
    </div>
  </div>
</div>

<script>
  document.getElementById('saveRdvSettings').addEventListener('click', function() {
    fetch("{{ url_for('settings') }}", {
      method: 'POST',
      body: new FormData(document.getElementById('rdvSettingsForm')),
      credentials: 'same-origin'
    }).then(function(res) {
      if (res.ok) {
        window.location.reload();
      } else {
        alert('Erreur lors de l’enregistrement');
      }
    }).catch(function() {
      alert('Erreur réseau');
    });
  });
</script>

<!-- Carte identité -->
<div class="container-fluid my-4">
  <div class="row justify-content-center">
    <div class="col-12">
      <div class="card shadow-lg">
        <div class="card-header py-3 text-center">
          <h1 class="mb-2 header-item">
            <i class="fas fa-hospital me-2"></i>
            {{ config.nom_clinique or config.cabinet or 'EasyMedicaLink' }}
          </h1>
          <div class="d-flex justify-content-center gap-4 flex-wrap">
            <div class="d-flex align-items-center header-item">
              <i class="fas fa-user-md me-2"></i><span>{{ config.doctor_name or '' }}</span>
            </div>
            <div class="d-flex align-items-center header-item">
              <i class="fas fa-map-marker-alt me-2"></i><span>{{ config.location or '' }}</span>
            </div>
          </div>
          <p class="mt-2 header-item">
            <i class="fas fa-calendar-day me-2"></i>{{ today }}
          </p>
        </div>
      </div>
    </div>
  </div>
</div>

<div class="container-fluid my-4">
  <div class="row justify-content-center">
    <div class="col-12">
  <link href="https://fonts.googleapis.com/css2?family=Great+Vibes&display=swap" rel="stylesheet">
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,shrink-to-fit=no">
  <title>RDV – {{ config.nom_clinique or 'EasyMedicaLink' }}</title>

  <!-- Librairies CSS -->
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.datatables.net/1.13.7/css/dataTables.bootstrap5.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">

  <!-- Tailwind (variables dynamiques) -->
  <script src="https://cdn.tailwindcss.com"></script>

  <style>
   .card-header h1, .header-item{ font-size:1.5rem !important; }
    :root{ {% for v,c in theme_vars.items() %}--{{v}}:{{c}};{% endfor %}}

    body{background:var(--bg-color);color:var(--text-color);padding-top:56px;}

    /* NAVBAR / CARDS */
    .navbar,.offcanvas-header{background:linear-gradient(45deg,var(--primary-color),var(--secondary-color))!important;}
    .offcanvas-body,.card{background:var(--card-bg)!important;color:var(--text-color)!important;}
    .card{border-radius:15px;box-shadow:0 4px 20px var(--card-shadow)!important;}
    .card-header{background:var(--primary-color)!important;color:var(--button-text)!important;}

    /* WIZARD */
    .step-circle{width:2.5rem;height:2.5rem;border-radius:50%;background:var(--secondary-color);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;}
    .step-circle.active{background:var(--primary-color);transform:scale(1.1);}
    .step-line{flex:1;height:4px;background:var(--secondary-color);}
    .step-line.active{background:var(--primary-color);}

    /* Floating-label */
    .floating-label{position:relative;}
    .floating-label input,.floating-label select{padding-top:1.25rem;}
    .floating-label label{position:absolute;top:0.25rem;left:0.75rem;font-size:.85rem;color:var(--primary-color);transition:all .2s;}
    .floating-label input:focus+label,.floating-label input:not(:placeholder-shown)+label,
    .floating-label select:focus+label,.floating-label select:not([value=""])+label{top:-0.75rem;font-size:.75rem;color:var(--secondary-color);}

    /* == BOUTONS RADIO SEXE (nouveaux réglages anti-chevauchement) == */
    .gender-btn{display:flex;gap:.5rem;flex-wrap:wrap;}
    .gender-btn input{display:none;}
    .gender-btn label{
      flex:1 1 calc(33.333% - .5rem);
      border:2px solid var(--secondary-color);
      border-radius:10px;padding:.45rem 0;
      cursor:pointer;transition:.2s;
      display:flex;align-items:center;justify-content:center;gap:.4rem;
      text-align:center;user-select:none;
    }
    .gender-btn input:checked+label{
      background:var(--primary-color);color:#fff;
      transform:translateY(-2px);box-shadow:0 3px 10px rgba(0,0,0,.15);
    }
  </style>
</head>
<body>

<!-- NAVBAR, OFFCANVAS, CARTE D’IDENTITÉ, etc. inchangés… -->

<!-- FORMULAIRE WIZARD -->
<div class="container-fluid my-4">
  <div class="row justify-content-center">
    <div class="col-12 col-lg-10">
      <button id="togglePatientForm" class="btn btn-secondary btn-sm mb-3 d-block mx-auto">
        <i class="fas fa-eye-slash me-1"></i>Masquer le formulaire
      </button>
      <div id="patientFormContainer">
        <div class="d-flex align-items-center mb-3">
          <div class="step-circle active" id="step1Circle">1</div>
          <div class="step-line" id="line1"></div>
          <div class="step-circle" id="step2Circle">2</div>
        </div>
        <form method="POST" class="card p-4 shadow-sm" id="wizardForm">
          <!-- === STEP 1 : Identité patient === -->
          <div id="step1">
            <h4 class="text-primary mb-3"><i class="fas fa-user me-2"></i>Identité Patient</h4>
            <div class="row g-3">
              <div class="col-md-4 floating-label">
                <input list="idlist" name="patient_id" id="patient_id"
                       value="{{ edit_row['ID'] if edit_row is defined else '' }}"
                       class="form-control" placeholder=" " required>
                <label>ID Patient</label>
                <datalist id="idlist">
                  {% for pid in patients %}
                  <option value="{{ pid }}">
                  {% endfor %}
                </datalist>
              </div>
              <div class="col-md-4 floating-label">
                <input type="text" name="patient_nom" id="patient_nom"
                      value="{{ edit_row['Nom'] if edit_row is defined else '' }}"
                      class="form-control" placeholder=" " required>
                <label>Nom</label>
              </div>
              <div class="col-md-4 floating-label">
                <input type="text" name="patient_prenom" id="patient_prenom"
                      value="{{ edit_row['Prenom'] if edit_row is defined else '' }}"
                      class="form-control" placeholder=" " required>
                <label>Prénom</label>
              </div>
              <div class="col-12">
                <div class="gender-btn">
                  <input type="radio" id="genderM" name="patient_gender" value="Masculin" required
                         {% if edit_index is defined and edit_row['Sexe']=='Masculin' %}checked{% endif %}>
                  <label for="genderM"><i class="fas fa-mars"></i> Masculin</label>
                  <input type="radio" id="genderF" name="patient_gender" value="Féminin"
                         {% if edit_index is defined and edit_row['Sexe']=='Féminin' %}checked{% endif %}>
                  <label for="genderF"><i class="fas fa-venus"></i> Féminin</label>
                  <input type="radio" id="genderO" name="patient_gender" value="Autre"
                         {% if edit_index is defined and edit_row['Sexe'] not in ['Masculin','Féminin'] %}checked{% endif %}>
                  <label for="genderO"><i class="fas fa-genderless"></i> Autre</label>
                </div>
              </div>
              <div class="col-md-4 floating-label">
                <input type="date" name="patient_dob" id="patient_dob"
                       value="{{ edit_row['DateNaissance'] if edit_row is defined else '' }}"
                       class="form-control" placeholder=" " required>
                <label>Date de naissance</label>
              </div>
              <div class="col-md-4 floating-label">
                <input type="tel" name="patient_phone" id="patient_phone"
                       value="{{ edit_row['Téléphone'] if edit_row is defined else '' }}"
                       class="form-control" placeholder=" " required>
                <label>Téléphone</label>
              </div>
              <div class="col-md-4 floating-label">
                <input type="text" name="patient_ant" id="patient_ant"
                       value="{{ edit_row['Antécédents'] if edit_row is defined else '' }}"
                       class="form-control" placeholder=" ">
                <label>Antécédents médicaux</label>
              </div>
            </div>
            <button type="button" id="toStep2" class="btn btn-primary mt-4 w-100">
              Suivant <i class="fas fa-arrow-right ms-1"></i>
            </button>
          </div>
          <!-- === STEP 2 : Détails RDV === -->
          <div id="step2" class="d-none">
            <h4 class="text-primary mb-3"><i class="fas fa-calendar-plus me-2"></i>Détails du RDV</h4>
            <div class="row g-3">
              <div class="col-md-6 floating-label">
                <input type="date" name="rdv_date"
                       value="{{ edit_row['Date'] if edit_row is defined else (filt_date or iso_today) }}"
                       class="form-control" placeholder=" " required>
                <label>Date</label>
              </div>
              <div class="col-md-6 floating-label">
                <select name="rdv_time" class="form-select" required>
                  {% for t in timeslots %}
                  <option value="{{t}}"
                    {% if edit_index is defined and t == edit_row['Heure'] %}selected{% endif %}
                    {% if edit_index is defined and t in reserved_slots %}disabled{% endif %}>
                    {{t}}
                  </option>
                  {% endfor %}
                </select>
                <label>Heure</label>
              </div>
            </div>
            <div class="d-flex justify-content-between mt-4">
              <button type="button" id="backStep1" class="btn btn-outline-secondary">
                <i class="fas fa-arrow-left me-1"></i>Précédent
              </button>
              <button class="btn btn-success">
                <i class="fas fa-check-circle me-1"></i>Confirmer le RDV
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  </div>
</div>

  <!-- ═════════════════════ FILTRES & TABLE ═════════════════════ -->
  <div class="row mt-4 justify-content-center">
    <div class="col-12 col-md-8 d-flex justify-content-between align-items-center mb-2">
      <form method="get" class="d-flex gap-1">
        <input type="date" name="date" value="{{ filt_date }}" class="form-control form-control-sm">
        <button class="btn btn-sm btn-primary"><i class="fas fa-filter me-1"></i>Filtrer</button>
      </form>
      <div class="d-flex gap-2">
        <a href="{{ url_for('rdv.rdv_home') }}" class="btn btn-outline-secondary btn-sm"><i class="fas fa-list me-1"></i>Tous</a>
        <a href="{{ url_for('rdv.pdf_today') }}" target="_blank" class="btn btn-danger btn-sm">
          <i class="fas fa-file-pdf me-1"></i>RDV du Jour
        </a>
      </div>
    </div>
  </div>

  <div class="row justify-content-center">
    <div class="col-12">
      <div class="card p-3 shadow-sm">
        <h4 class="text-primary m-0 mb-3"><i class="fas fa-calendar-check me-2"></i>Rendez-vous Confirmés</h4>
        <div class="table-responsive">
          <table id="rdvTable" class="table table-striped table-bordered align-middle">
            <thead>
              <tr>
                <th>#</th><th>ID</th><th>Nom</th><th>Prénom</th><th>Sexe</th><th>Âge</th><th>Téléphonique</th><th>Antéc.</th><th>Date</th><th>Heure</th><th>Ordre</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {% for idx,r in enumerate(df) %}
              <tr>
                <td>{{ idx }}</td><td>{{ r["ID"] }}</td><td>{{ r["Nom"] }}</td><td>{{ r["Prenom"] }}</td><td>{{ r["Sexe"] }}</td>
                <td>{{ r["Âge"] }}</td><td>{{ r["Téléphone"] }}</td><td>{{ r["Antécédents"] }}</td>
                <td>{{ r["Date"] }}</td><td>{{ r["Heure"] }}</td><td>{{ r["Num Ordre"] }}</td><td class="text-center">
                  <a href="{{ url_for('rdv.consult_rdv', index=idx) }}"
                     class="btn btn-sm btn-success me-1" title="Consultation" data-bs-toggle="tooltip">
                    <i class="fas fa-stethoscope"></i>
                  </a>
                  <a href="{{ url_for('rdv.edit_rdv', index=idx) }}"
                     class="btn btn-sm btn-warning me-1" title="Modifier" data-bs-toggle="tooltip">
                    <i class="fas fa-pen"></i>
                  </a>
                  <a onclick="return confirm('Supprimer ?')" href="{{ url_for('rdv.delete_rdv', index=idx) }}"
                     class="btn btn-sm btn-outline-danger" title="Supprimer" data-bs-toggle="tooltip">
                    <i class="fas fa-trash"></i>
                  </a>
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</div>

<footer class="text-center py-3 small">
  SASTOUKA DIGITAL © 2025 • <i class="fas fa-envelope me-1"></i>sastoukadigital@gmail.com • <i class="fab fa-whatsapp me-1"></i>+212652084735
</footer>

<!-- ═════════════════════ JS ═════════════════════ -->
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://cdn.datatables.net/1.13.7/js/jquery.dataTables.min.js"></script>
<script src="https://cdn.datatables.net/1.13.7/js/dataTables.bootstrap5.min.js"></script>
<script>
  $(function(){ $('#rdvTable').DataTable({order:[[10,'asc']]}); });
</script>

<script>
document.addEventListener('DOMContentLoaded',()=>{
  const toggleBtn=document.getElementById('togglePatientForm');
  const formCont=document.getElementById('patientFormContainer');
  toggleBtn.onclick=()=>{
    formCont.classList.toggle('d-none');
    toggleBtn.innerHTML=formCont.classList.contains('d-none')?
      '<i class="fas fa-eye me-1"></i>Afficher le formulaire':
      '<i class="fas fa-eye-slash me-1"></i>Masquer le formulaire';
  };

  /* Wizard navigation */
  const step1=document.getElementById('step1'),step2=document.getElementById('step2');
  const s1c=document.getElementById('step1Circle'),s2c=document.getElementById('step2Circle'),line1=document.getElementById('line1');
  document.getElementById('toStep2').onclick=()=>{
    step1.classList.add('d-none');step2.classList.remove('d-none');
    s1c.classList.remove('active');line1.classList.add('active');s2c.classList.add('active');
  };
  document.getElementById('backStep1').onclick=()=>{
    step2.classList.add('d-none');step1.classList.remove('d-none');
    s2c.classList.remove('active');line1.classList.remove('active');s1c.classList.add('active');
  };

  /* Tooltips */
  new bootstrap.Tooltip(document.body,{selector:'[data-bs-toggle="tooltip"]'});
});
</script>

<script>
/* Auto-remplissage patient + radio sexe */
document.getElementById('patient_id').addEventListener('change',function(){
  fetch(`/rdv/patient_info/${encodeURIComponent(this.value)}`)
    .then(r=>r.json())
    .then(d=>{
      document.getElementById('patient_nom').value    = d.name.split(' ')[0]||'';
      document.getElementById('patient_prenom').value = d.name.split(' ').slice(1).join(' ')||'';
      document.getElementById('patient_dob').value    = d.date_of_birth || '';
      document.getElementById('patient_phone').value  = d.phone || '';
      document.getElementById('patient_ant').value    = d.antecedents || '';

      /* reset radios */
      ['genderM','genderF','genderO'].forEach(id=>document.getElementById(id).checked=false);
      if(d.gender==='Masculin')        document.getElementById('genderM').checked=true;
      else if(d.gender==='Féminin')    document.getElementById('genderF').checked=true;
      else if(d.gender)                document.getElementById('genderO').checked=true;
    });
});
</script>
</body>
</html>
"""
