import os
import uuid
from datetime import datetime, date

import pandas as pd
import qrcode
from flask import (
    Blueprint, request, render_template_string, redirect, url_for,
    flash, send_file, current_app, jsonify
)
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image
import utils
import theme
from rdv import load_patients
from routes import LISTS_FILE
from utils import merge_with_background_pdf  # Import ajouté

facturation_bp = Blueprint('facturation', __name__, url_prefix='/facturation')
app_dir        = os.path.dirname(os.path.abspath(__file__))
excel_dir      = utils.EXCEL_FOLDER
pdf_dir        = utils.PDF_FOLDER

# ---------------------------------------------------------------------------
#  À placer tout en haut de facturation.py, juste après les autres imports
# ---------------------------------------------------------------------------
from datetime import date, datetime, time
import json

def _json_default(obj):
    """
    Rend sérialisables les objets datetime/date/time pour Jinja |tojson.
    • datetime → 'YYYY-MM-DD HH:MM:SS'
    • date     → 'YYYY-MM-DD'
    • time     → 'HH:MM'
    Tous les autres types non JSON-compatibles sont convertis en str().
    """
    if isinstance(obj, datetime):
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, time):
        return obj.strftime('%H:%M')
    return str(obj)

from datetime import time, datetime, date
import json

def _to_json_safe(obj):
    """
    Rend sérialisables les objets date/heure pour Flask|tojson.
    • datetime  → 'YYYY-MM-DD HH:MM:SS'
    • date      → 'YYYY-MM-DD'
    • time      → 'HH:MM'
    """
    if isinstance(obj, datetime):
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(obj, date):
        return obj.strftime('%Y-%m-%d')
    if isinstance(obj, time):
        return obj.strftime('%H:%M')
    raise TypeError(f"Type non sérialisable : {type(obj)}")
  
# ---------------------------------------------------------------------------
# ----------------------------- CLASSE PDF ----------------------------------
# ---------------------------------------------------------------------------
class PDFInvoice(FPDF):
    def __init__(self, app, numero, patient, phone, date_str, services, currency, vat):
        super().__init__(orientation='P', unit='mm', format='A5')  # A5 pour compacité
        self.app      = app
        self.numero   = numero
        self.patient  = patient
        self.phone    = phone
        self.date_str = date_str
        self.services = services
        self.currency = currency
        self.vat      = float(vat)
        self.set_left_margin(20)
        self.set_right_margin(20)
        self.set_top_margin(17)
        self.set_auto_page_break(auto=False)
        self.add_page()

    def header(self):
        bg = getattr(self.app, 'background_path', None) or getattr(utils, 'background_file', None)
        if bg and not os.path.isabs(bg):
            bg = os.path.join(utils.BACKGROUND_FOLDER, bg)
        if bg and os.path.isfile(bg) and bg.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
            try:
                self.image(bg, x=0, y=0, w=self.w, h=self.h)
            except Exception:
                pass
        self.set_font('Helvetica', 'B', 18)
        self.set_text_color(0, 0, 0)
        self.ln(15)
        self.cell(0, 8, 'Facture', align='C')
        self.ln(8)
        y_numero = self.get_y()
        self.set_font('Helvetica', '', 10)
        self.cell(0, 6, f"Numéro : {self.numero}", align='C')
        self.ln(4)
        self.cell(0, 6, f"Date : {self.date_str}", align='C')

        qr_data = f"Facture {self.numero} le {self.date_str}"
        qr_img = self._generate_qr(qr_data)
        tmp_qr = "temp_qr.png"
        qr_img.save(tmp_qr)
        self.image(tmp_qr, x=self.w - self.r_margin - 20, y=y_numero, w=20, h=20)
        os.remove(tmp_qr)
        self.ln(15)

    def footer(self):
        pass

    def _generate_qr(self, data):
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        return img.resize((100, 100), Image.Resampling.LANCZOS)

    def add_invoice_details(self):
        self.set_font('Helvetica', 'B', 12)
        lh = 8
        cw = 50
        details = [
            ('Patient', self.patient),
            ('Téléphone', self.phone),
            ('Date facture', self.date_str),
            ('Taux TVA', f"{self.vat}%")
        ]
        for label, val in details:
            self.cell(cw, lh, f"{label}:", ln=0)
            self.set_font('Helvetica', '', 12)
            self.cell(0, lh, str(val), ln=1)
            self.set_font('Helvetica', 'B', 12)
        self.ln(5)

    def add_invoice_table(self):
        # Dimensions
        table_width = self.w - self.l_margin - self.r_margin
        w_service   = table_width * 0.7
        w_price     = table_width * 0.3

        # === En-tête stylé ===
        self.set_fill_color(50, 115, 220)        # bleu soutenu
        self.set_text_color(255, 255, 255)       # texte blanc
        self.set_font('Helvetica', 'B', 12)
        self.cell(w_service, 10, 'SERVICE', border=1, align='C', fill=True)
        self.cell(w_price,   10, f'PRIX ({self.currency})', border=1, align='C', fill=True)
        self.ln()

        # Préparation corps
        line_height = self.font_size * 1.5
        total_ht    = 0.0
        fill        = False

        # Couleurs pour alternance
        color_light = (245, 245, 245)
        color_dark  = (255, 255, 255)

        self.set_text_color(0, 0, 0)
        self.set_font('Helvetica', '', 11)

        for svc in self.services:
            # Nettoyage texte
            name  = svc['name']
            price = f"{svc['price']:.2f}"

            # Choix du fond de ligne
            self.set_fill_color(*(color_light if fill else color_dark))

            # Calcule hauteur de cellule en fonction du texte
            lines = self.multi_cell(w_service, line_height, name,
                                    border=0, align='L', split_only=True)
            cell_h = len(lines) * line_height

            x0, y0 = self.get_x(), self.get_y()

            # Colonne Service (multi-cell)
            self.multi_cell(w_service, line_height, name,
                            border=1, align='L', fill=True)

            # Colonne Prix, repositionnée
            self.set_xy(x0 + w_service, y0)
            self.cell(w_price, cell_h, price,
                      border=1, align='R', fill=True)

            # Passer à la ligne suivante
            self.ln(cell_h)
            total_ht += svc['price']
            fill = not fill

        # === Ligne de séparation avant totaux ===
        self.set_draw_color(50, 115, 220)
        self.set_line_width(0.5)
        y = self.get_y() + 2
        self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.ln(6)

        # Totaux en gras
        tva_amount = total_ht * (self.vat / 100)
        total_ttc  = total_ht + tva_amount

        self.set_font('Helvetica', 'B', 12)
        labels = [('Sous-total HT', total_ht),
                  (f'TVA {self.vat:.0f}%',    tva_amount),
                  ('TOTAL TTC', total_ttc)]
        for label, amt in labels:
            self.cell(w_service, 8, label, border=1, align='R')
            self.cell(w_price,   8, f"{amt:.2f}", border=1, align='R')
            self.ln()

# ---------------------------------------------------------------------------
# ------------------------------- ROUTES ------------------------------------
# ---------------------------------------------------------------------------
@facturation_bp.route('/new_patient', methods=['GET', 'POST'])
def new_patient():
    excel_path = os.path.join(excel_dir, 'info_Base_patient.xlsx')
        # ── Veiller à ce que le fichier patients existe ─────────────────────────
    if not os.path.exists(excel_path):
        os.makedirs(excel_dir, exist_ok=True)
        # colonnes requises pour lister les patients
        df_empty = pd.DataFrame(columns=['ID', 'Nom', 'Prenom', 'Téléphone'])
        df_empty.to_excel(excel_path, index=False)
    # ─────────────────────────────────────────────────────────────────────────    
    if request.method == 'POST':
        id_     = request.form.get('ID')
        nom     = request.form.get('Nom')
        prenom  = request.form.get('Prenom')
        tel     = request.form.get('Téléphone', '')
        if not (id_ and nom and prenom):
            flash('Veuillez remplir ID, Nom et Prénom', 'danger')
            return redirect(url_for('facturation.new_patient'))
        df = pd.read_excel(excel_path)
        df = df.append({'ID': id_, 'Nom': nom, 'Prenom': prenom, 'Téléphone': tel},
                       ignore_index=True)
        df.to_excel(excel_path, index=False)
        flash('Patient ajouté ✔', 'success')
        return redirect(url_for('facturation.facturation_home'))
    return render_template_string(new_patient_template)

# ---------------------------------------------------------------------------
#  ROUTE « /facturation » – version mise à jour (100 % autonome)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
#  JSON helper (déjà présent, conservé intégralement)
# ---------------------------------------------------------------------------
from datetime import date, datetime, time
import json

def _json_default(obj):
    """
    Rend sérialisables les objets datetime/date/time pour Jinja |tojson.
    • datetime → 'YYYY-MM-DD HH:MM:SS'
    • date     → 'YYYY-MM-DD'
    • time     → 'HH:MM'
    Tous les autres types non JSON-compatibles sont convertis en str().
    """
    if isinstance(obj, datetime):
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, time):
        return obj.strftime('%H:%M')
    return str(obj)


# ---------------------------------------------------------------------------
#  Téléchargement d’une facture PDF  ← NOUVELLE ROUTE (aucune ligne d’origine supprimée)
# ---------------------------------------------------------------------------
@facturation_bp.route('/download/<path:filename>')
def download_invoice(filename):
    """
    Sert le fichier PDF demandé si présent dans utils.PDF_FOLDER,
    sinon renvoie 404/flash.
    """
    file_path = os.path.join(pdf_dir, filename)
    if not os.path.isfile(file_path):
        flash("Fichier introuvable !", "danger")
        return redirect(url_for('facturation.facturation_home'))

    return send_file(
        file_path,
        as_attachment=True,
        download_name=filename,
        mimetype='application/pdf'
    )


# ---------------------------------------------------------------------------
#  ROUTE « /facturation » – mise à jour complète (aucune ligne perdue)
# ---------------------------------------------------------------------------
@facturation_bp.route('/', methods=['GET', 'POST'])
def facturation_home():
    # ---------- 0. Contexte, thèmes & BG ----------------------------------
    config      = utils.load_config()
    theme_vars  = theme.current_theme()

    bg_folder        = utils.BACKGROUND_FOLDER
    background_files = [
        f for f in os.listdir(bg_folder)
        if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.pdf'))
    ]
    current_app.background_path = config.get('background_file_path')

    # ---------- 1. Services / actes disponibles ---------------------------
    df_lists = pd.read_excel(LISTS_FILE, sheet_name=1)
    cols     = list(df_lists.columns)
    services_by_category = {}
    for cat in ['Consultation', 'Analyses', 'Radiologies', 'Autre_Acte']:
        match = next((c for c in cols if c.strip().lower() == cat.lower()), None)
        if not match:
            match = next((c for c in cols if cat.lower() in c.strip().lower()), None)
        services_by_category[cat] = (
            df_lists[match].dropna().astype(str).tolist() if match else []
        )

    # ---------- 2. Base patients ------------------------------------------
    info_path = os.path.join(excel_dir, 'info_Base_patient.xlsx')

    if os.path.exists(info_path):
        df_pat        = pd.read_excel(info_path, dtype=str)
        patients_info = df_pat.to_dict(orient='records')

        # ── Garde-fou : uniquement s’il y a au moins une ligne ────────────
        if not df_pat.empty:
            last_patient = df_pat.iloc[-1].to_dict()
        else:
            last_patient = {}
    else:
        patients_info = []
        last_patient  = {}

    # ---------- 3. POST : création facture --------------------------------
    if request.method == 'POST':
        # 3-A. Arrière-plan
        sel_bg = request.form.get('background', config.get('background_file_path'))
        if sel_bg:
            if not os.path.isabs(sel_bg):
                sel_bg = os.path.join(utils.BACKGROUND_FOLDER, sel_bg)
            current_app.background_path   = sel_bg
            config['background_file_path'] = os.path.basename(sel_bg)
            utils.save_config(config)

        # 3-B. TVA
        vat_value = request.form.get('vat')
        if not vat_value:
            flash('Le taux de TVA est requis', 'danger')
            return redirect(url_for('facturation.facturation_home'))
        try:
            vat_float = float(vat_value)
            if not 0 <= vat_float <= 100:
                raise ValueError
            if config.get('vat') != vat_float:
                config['vat'] = vat_float
                utils.save_config(config)
                flash(f'Taux TVA mis à jour à {vat_float} %', 'success')
        except ValueError:
            flash('Le taux de TVA doit être un nombre entre 0 et 100', 'danger')
            return redirect(url_for('facturation.facturation_home'))

        # 3-C. Infos patient
        pid  = request.form.get('patient_id')
        rec  = next((p for p in patients_info if str(p['ID']) == pid), last_patient)
        patient_name = f"{rec.get('Nom','')} {rec.get('Prenom','')}".strip()
        phone        = rec.get('Téléphone', '')

        # 3-D. Numéro facture
        date_str = request.form.get('date')
        date_key = date_str.replace('-', '')
        existing = [
            fn for fn in os.listdir(pdf_dir)
            if fn.startswith(f"Facture_{date_key}")
        ]
        numero = f"{date_key}-{len(existing)+1:03d}"

        # 3-E. Services sélectionnés
        services = []
        for svc in request.form.getlist('services[]'):
            name, price = svc.split('|')
            services.append({'name': name, 'price': float(price)})
        if not services:
            flash('Veuillez sélectionner au moins un service', 'danger')
            return redirect(url_for('facturation.facturation_home'))

        # 3-F. Totaux
        total_ht   = sum(s['price'] for s in services)
        tva_amount = total_ht * (config.get('vat', 20) / 100)
        total_ttc  = total_ht + tva_amount

        # 3-G. Devise
        selected_currency   = request.form.get('currency', config.get('currency', 'EUR'))
        config['currency']  = selected_currency
        utils.save_config(config)

        # 3-H. Création PDF
        pdf = PDFInvoice(
            app      = current_app,
            numero   = numero,
            patient  = patient_name,
            phone    = phone,
            date_str = date_str,
            services = services,
            currency = selected_currency,
            vat      = config.get('vat', 20)
        )
        pdf.add_invoice_details()
        pdf.add_invoice_table()
        output_path = os.path.join(pdf_dir, f"Facture_{numero}.pdf")
        pdf.output(output_path)

        # 3-I. Fusion arrière-plan
        merge_with_background_pdf(output_path)

        # 3-J. Sauvegarde Excel
        factures_path = os.path.join(excel_dir, 'factures.xlsx')
        if os.path.exists(factures_path):
            df_fact = pd.read_excel(factures_path, dtype={'Numero': str})
        else:
            df_fact = pd.DataFrame(columns=[
                'Numero', 'Patient', 'Téléphone', 'Date',
                'Services', 'Sous-total', 'TVA', 'Total'
            ])
        df_fact = pd.concat([
            df_fact,
            pd.DataFrame([{
                'Numero'    : numero,
                'Patient'   : patient_name,
                'Téléphone' : phone,
                'Date'      : date_str,
                'Services'  : "; ".join(f"{s['name']}({s['price']:.2f})" for s in services),
                'Sous-total': total_ht,
                'TVA'       : tva_amount,
                'Total'     : total_ttc
            }])
        ], ignore_index=True)
        df_fact.to_excel(factures_path, index=False)

        flash('Facture générée et enregistrée ✔', 'success')
        return redirect(url_for(
            'facturation.download_invoice',
            filename=os.path.basename(output_path)
        ))

    # ---------- 4. Variables GET (form par défaut) -------------------------
    today_iso       = date.today().isoformat()
    date_key        = today_iso.replace('-', '')
    existing_pdf    = [
        fn for fn in os.listdir(pdf_dir)
        if fn.startswith(f"Facture_{date_key}")
    ]
    numero_default  = f"{date_key}-{len(existing_pdf)+1:03d}"
    vat_default     = config.get('vat', 20.0)
    selected_currency = config.get('currency', 'EUR')

    # ---------- 5. Données JSON-sûres pour le template ---------------------
    factures        = load_invoices()
    report_summary  = generate_report_summary()

    services_json        = json.loads(json.dumps(services_by_category, default=_json_default))
    patients_json        = json.loads(json.dumps(patients_info,       default=_json_default))
    factures_json        = json.loads(json.dumps(factures,            default=_json_default))
    report_summary_json  = json.loads(json.dumps(report_summary,      default=_json_default))

    # ---------- 6. Rendu ---------------------------------------------------
    return render_template_string(
        facturation_template,
        config=config,
        theme_vars=theme_vars,
        theme_names=list(theme.THEMES.keys()),
        services_by_category=services_json,
        patients_info=patients_json,
        last_patient=last_patient,
        today=today_iso,
        numero_default=numero_default,
        vat_default=vat_default,
        currency=selected_currency,
        background_files=background_files,
        factures=factures_json,
        report_summary=report_summary_json
    )


@facturation_bp.route('/add_service', methods=['POST'])
def add_service():
    data = request.get_json() or {}
    cat = data.get('category', '').strip()
    name = data.get('name', '').strip()
    price = data.get('price', '').strip()
    if not (cat and name and price):
        return jsonify(success=False, error="Données incomplètes"), 400
    xls = pd.read_excel(LISTS_FILE, sheet_name=None)
    sheet_name = list(xls.keys())[1]
    df = xls[sheet_name]
    col = next((c for c in df.columns if c.strip().lower() == cat.lower()), None)
    if col is None:
        col = cat
        df[col] = pd.NA
    df.loc[len(df), col] = f"{name}|{price}"
    with pd.ExcelWriter(LISTS_FILE, engine='openpyxl') as writer:
        for sname, sheet_df in xls.items():
            if sname == sheet_name:
                sheet_df = df
            sheet_df.to_excel(writer, sheet_name=sname, index=False)
    return jsonify(success=True)

# ---------------------------------------------------------------------------
# ------------------------- ROUTE RAPPORT JSON ------------------------------
# ---------------------------------------------------------------------------
@facturation_bp.route('/report')
def report():
    start = request.args.get('start') or None
    end   = request.args.get('end')   or None
    summary = generate_report_summary(start, end)
    count = summary['count']
    summary['average'] = summary['total_ttc'] / count if count else 0.0
    return jsonify(summary)

# ---------------------------------------------------------------------------
# ----------------------- FONCTIONS UTILITAIRES -----------------------------
# ---------------------------------------------------------------------------
def load_invoices():
    """
    Charge le classeur « factures.xlsx » et renvoie une liste de dictionnaires
    prêts pour l’affichage.  

    • Force la colonne « Numero » à rester une **chaîne** (dtype={'Numero': str})
      pour éviter toute concaténation str + int dans le template.  
    • Formate la colonne « Date » au format JJ/MM/AAAA.  
    • Retourne les enregistrements triés du plus récent au plus ancien.
    """
    factures_path = os.path.join(excel_dir, 'factures.xlsx')
    if os.path.exists(factures_path):
        # ← seule ligne modifiée : on impose Numero comme texte
        df = pd.read_excel(factures_path, dtype={'Numero': str}).fillna("")

        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')\
                             .dt.strftime('%d/%m/%Y')

        return df.sort_values('Date', ascending=False, na_position='last')\
                 .to_dict('records')

    return []

def generate_report_summary(start=None, end=None):
    factures = load_invoices()
    currency = utils.load_config().get('currency', 'EUR')
    if not factures:
        return {
            'count': 0,
            'total_ht': 0.0,
            'total_tva': 0.0,
            'total_ttc': 0.0,
            'currency': currency
        }
    df = pd.DataFrame(factures)
    df['Date_dt'] = pd.to_datetime(df['Date'], format='%d/%m/%Y')
    if start:
        df = df[df['Date_dt'] >= pd.to_datetime(start)]
    if end:
        df = df[df['Date_dt'] <= pd.to_datetime(end)]
    count = len(df)
    total_ht  = df['Sous-total'].sum()
    total_tva = df['TVA'].sum()
    total_ttc = df['Total'].sum()
    return {
        'count': int(count),
        'total_ht': float(total_ht),
        'total_tva': float(total_tva),
        'total_ttc': float(total_ttc),
        'currency': currency
    }
    
def load_services():
    path = os.path.join(excel_dir, LISTS_FILE)
    if not os.path.exists(path):
        return []

    df = pd.read_excel(path, dtype=str)      # ← force tout en texte
    df = df.fillna("")
    return df.to_dict("records")
   
# ---------------------------------------------------------------------------
# ------------------------------ TEMPLATE HTML ------------------------------
# ---------------------------------------------------------------------------
facturation_template = r"""
<!DOCTYPE html>
<html lang="fr">
{{ pwa_head()|safe }}
<head>
  <link href="https://fonts.googleapis.com/css2?family=Great+Vibes&display=swap" rel="stylesheet">
  <style>
    .card-header h1,
    .card-header .header-item,
    .card-header p { font-size: 30px!important; }
    .card-header h1 i,
    .card-header .header-item i,
    .card-header p i { font-size: 30px!important; }
    .header-item { font-size: 28px!important; }
  </style>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
  <title>RDV – {{ config.nom_clinique or 'EasyMedicaLink' }}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.datatables.net/1.13.7/css/dataTables.bootstrap5.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
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
      background: linear-gradient(45deg, var(--primary-color), var(--secondary-color))!important;
    }
    .offcanvas-body, .card {
      background: var(--card-bg)!important;
      color: var(--text-color)!important;
    }
    .card-header {
      background: var(--primary-color)!important;
      color: var(--button-text)!important;
    }
    .card {
      border-radius: 15px;
      box-shadow: 0 4px 20px var(--card-shadow)!important;
    }
    .nav-tabs .nav-link {
      border: none;
      color: #64748b;
      font-weight: 500;
      font-size: 24px;
      transition: all 0.2s ease;
      position: relative;
    }
    .nav-tabs .nav-link i { font-size: 28px; }
    .nav-tabs .nav-link::after {
      content: '';
      position: absolute;
      bottom: 0; left: 0;
      width: 0; height: 3px;
      background: var(--primary-color);
      transition: width 0.3s ease;
    }
    .nav-tabs .nav-link.active {
      background: transparent;
      color: var(--primary-color)!important;
    }
    .nav-tabs .nav-link.active::after { width: 100%; }
    .service-card.active {
      background: var(--primary-color)!important;
      color: var(--button-text)!important;
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
  document.getElementById('saveRdvSettings').addEventListener('click', () => {
    fetch("{{ url_for('settings') }}", {
      method:'POST',
      body:new FormData(document.getElementById('rdvSettingsForm')),
      credentials:'same-origin'
    }).then(res => res.ok ? location.reload() : alert('Erreur lors de l’enregistrement'))
      .catch(() => alert('Erreur réseau'));
  });
</script>

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
  <ul class="nav nav-tabs justify-content-center" id="factTab" role="tablist">
    <li class="nav-item" role="presentation">
      <button class="nav-link active" id="tab-facturation"
              data-bs-toggle="tab" data-bs-target="#facturation"
              type="button" role="tab">
        <i class="fas fa-file-invoice-dollar me-2"></i>Facturation
      </button>
    </li>
    <li class="nav-item" role="presentation">
      <button class="nav-link" id="tab-rapports"
              data-bs-toggle="tab" data-bs-target="#rapports"
              type="button" role="tab">
        <i class="fas fa-chart-line me-2"></i>Rapport global
      </button>
    </li>
    <li class="nav-item" role="presentation">
      <button class="nav-link" id="tab-historique"
              data-bs-toggle="tab" data-bs-target="#historique"
              type="button" role="tab">
        <i class="fas fa-history me-2"></i>Factures antérieures
      </button>
    </li>
  </ul>

  <div class="tab-content mt-3" id="factTabContent">
    <!-- ====================== ONGLET 1 : FACTURATION ======================= -->
    <div class="tab-pane fade show active" id="facturation" role="tabpanel">
      <div class="row justify-content-center">
        <div class="col-12">

          <!-- Carte Dernier patient -->
          <div class="card mb-4">
            <div class="card-header text-center">
              <h5><i class="fas fa-user me-2"></i>Dernier patient</h5>
            </div>
            <div class="card-body">
              <p id="last_patient_id"><strong>ID :</strong> {{ last_patient.get('ID','') }}</p>
              <p id="last_patient_name"><strong>Nom :</strong> {{ last_patient.get('Nom','') }} {{ last_patient.get('Prenom','') }}</p>
              <p id="last_patient_phone"><strong>Téléphone :</strong> {{ last_patient.get('Téléphone','') }}</p>
              <a href="{{ url_for('facturation.new_patient') }}" class="btn btn-secondary">
                <i class="fas fa-user-plus me-1"></i>Ajouter un nouveau patient
              </a>
            </div>
          </div>

          <!-- Génération de facture -->
          <div class="card">
            <div class="card-header text-center">
              <h5><i class="fas fa-file-invoice-dollar me-2"></i>Générer une facture</h5>
            </div>
            <div class="card-body">
              <form method="post" id="invoiceForm">
                <div class="row gy-3">
                  <!-- Sélecteur arrière-plan -->
                  <div class="col-md-4">
                    <label class="form-label">Arrière-plan</label>
                    <select name="background" class="form-select">
                      {% for fname in background_files %}
                        <option value="{{ fname }}" 
                          {% if fname == config.get('background_file_path') %}selected{% endif %}>
                          {{ fname }}
                        </option>
                      {% endfor %}
                    </select>
                  </div>
                  
                  <div class="col-md-4">
                    <label class="form-label">Numéro</label>
                    <input type="text" name="numero" class="form-control" value="{{ numero_default }}" readonly>
                  </div>
                  <div class="col-md-4">
                    <label class="form-label">Date</label>
                    <input type="date" name="date" class="form-control" value="{{ today }}">
                  </div>
                  {% set currencies = [
                    ('EUR','Euro'),('USD','Dollar US'),
                    ('MAD','Dirham marocain'),('DZD','Dinar algérien'),
                    ('TND','Dinar tunisien'),('XOF','Franc CFA (BCEAO)'),
                    ('XAF','Franc CFA (BEAC)'),('CHF','Franc suisse'),
                    ('CAD','Dollar canadien'),('HTG','Gourde haïtienne'),
                    ('GNF','Franc guinéen')
                  ] %}
                  <div class="col-md-4">
                    <label class="form-label">TVA (%)</label>
                    <input type="number"
                           id="vatInput"
                           name="vat"
                           class="form-control"
                           value="{{ vat_default }}"
                           step="0.01"
                           min="0"
                           max="100"
                           required>
                  </div>
                  <div class="col-md-4">
                    <label class="form-label">Devise</label>
                    <select name="currency" class="form-select">
                      {% for code, name in currencies %}
                        <option value="{{ code }}" {% if currency == code %}selected{% endif %}>
                          {{ name }} ({{ code }})
                        </option>
                      {% endfor %}
                    </select>
                  </div>
                  <div class="col-md-4">
                    <label class="form-label">Patient</label>
                    <select id="patientSelect" name="patient_id" class="form-select">
                      {% for p in patients_info %}
                      <option value="{{ p.ID }}" {% if p.ID == last_patient.ID %}selected{% endif %}>
                        {{ p.ID }} – {{ p.Nom }} {{ p.Prenom }}
                      </option>
                      {% endfor %}
                    </select>
                  </div>
                </div>

                <!-- Section Services -->
                <div class="card mb-4 mt-4">
                  <div class="card-header"><h6><i class="fas fa-cubes me-2"></i>Services</h6></div>
                  <div class="card-body">

                    <!-- Cartes catégories -->
                    <div class="row mb-3">
                      {% for cat in services_by_category.keys() %}
                      <div class="col-6 col-md-3 mb-2">
                        <div class="card service-card h-100 text-center" data-cat="{{ cat }}">
                          <div class="card-body p-2">
                            {% if cat.lower() == 'consultation' %}
                              <i class="fas fa-stethoscope fa-2x mb-1"></i>
                            {% elif cat.lower() == 'analyses' %}
                              <i class="fas fa-vial fa-2x mb-1"></i>
                            {% elif cat.lower() == 'radiologies' %}
                              <i class="fas fa-x-ray fa-2x mb-1"></i>
                            {% else %}
                              <i class="fas fa-briefcase-medical fa-2x mb-1"></i>
                            {% endif %}
                            <div class="small text-uppercase">{{ cat }}</div>
                          </div>
                        </div>
                      </div>
                      {% endfor %}
                    </div>

                    <!-- Recherche / Autocomplétion -->
                    <div class="d-flex gap-2 mb-3">
                      <input list="serviceList" id="serviceSelect" class="form-control flex-grow-1"
                            placeholder="Rechercher ou saisir un service…">
                      <input type="number" id="servicePrice" class="form-control" style="width:100px"
                            placeholder="Prix" step="0.01">
                      <datalist id="serviceList"></datalist>
                      <button type="button" id="addServiceBtn" class="btn btn-primary">
                        <i class="fas fa-plus"></i>
                      </button>
                      <button type="button" id="addToCatalogBtn" class="btn btn-secondary">
                        <i class="fas fa-folder-plus"></i>
                      </button>
                    </div>

                    <!-- Modal catalogue -->
                    <div class="modal fade" id="catalogModal" tabindex="-1">
                      <div class="modal-dialog"><div class="modal-content">
                        <form id="catalogForm">
                          <div class="modal-header">
                            <h5 class="modal-title">Ajouter un service au catalogue</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                          </div>
                          <div class="modal-body">
                            <div class="mb-3">
                              <label class="form-label">Catégorie</label>
                              <select id="catalogCategory" class="form-select">
                                {% for cat in services_by_category.keys() %}
                                <option value="{{ cat }}">{{ cat.capitalize() }}</option>
                                {% endfor %}
                              </select>
                            </div>
                            <div class="mb-3">
                              <label class="form-label">Désignation</label>
                              <input type="text" id="catalogName" class="form-control" required>
                            </div>
                            <div class="mb-3">
                              <label class="form-label">Prix</label>
                              <input type="number" id="catalogPrice" class="form-control" step="0.01" required>
                            </div>
                          </div>
                          <div class="modal-footer">
                            <button type="submit" class="btn btn-primary">Enregistrer</button>
                          </div>
                        </form>
                      </div></div>
                    </div>

                    <!-- Tableau services & totaux -->
                    <div class="table-responsive mb-3">
                      <table class="table table-bordered" id="servicesTable">
                        <thead class="table-light">
                          <tr>
                            <th>Désignation</th>
                            <th style="width:120px">Prix ({{ currency }})</th>
                            <th style="width:50px"></th>
                          </tr>
                        </thead>
                        <tbody></tbody>
                      </table>
                    </div>
                    <div class="d-flex justify-content-end gap-4">
                      <div><strong>Sous-total HT :</strong> <span id="totalHT">0.00</span> {{ currency }}</div>
                      <div>
                        <strong>TVA (<span id="vatPercent">{{ vat_default }}</span>%) :</strong>
                        <span id="totalTVA">0.00</span> {{ currency }}
                      </div>
                      <div><strong>Total TTC :</strong> <span id="totalTTC">0.00</span> {{ currency }}</div>
                    </div>

                  </div>
                </div>
                <div class="text-end mt-4">
                  <button type="button" id="submitInvoiceBtn" class="btn btn-primary">
                    <i class="fas fa-receipt me-1"></i>Générer la facture
                  </button>
                </div>
                <script>
                  document.getElementById('submitInvoiceBtn').addEventListener('click', function() {
                    document.getElementById('invoiceForm').submit();
                  });
                </script>
              </form>
            </div>
          </div>

        </div>
      </div>
    </div>

<!-- ========================= ONGLET 2 : RAPPORTS ========================= -->
<div class="tab-pane fade" id="rapports" role="tabpanel">
  <div class="row justify-content-center">
    <div class="col-12">
      <div class="card shadow-lg">
        <div class="card-header bg-primary text-white">
          <h5 class="mb-0"><i class="fas fa-chart-pie me-2"></i>Rapport financier</h5>
        </div>
        <div class="card-body">
          <div class="row">
            <div class="col-md-6">
              <div class="card mb-3">
                <div class="card-body">
                  <h6 class="text-muted">Statistiques globales</h6>
                  <div class="d-flex justify-content-between align-items-center">
                    <div>
                      <p class="mb-0">Total des factures</p>
                      <h3 id="invoiceCount" class="text-primary">{{ report_summary.count }}</h3>
                    </div>
                    <i class="fas fa-file-invoice fa-3x text-primary"></i>
                  </div>
                </div>
              </div>
            </div>
            <div class="col-md-6">
              <div class="card mb-3">
                <div class="card-body">
                  <h6 class="text-muted">Chiffre d'affaires</h6>
                  <div class="d-flex justify-content-between align-items-center">
                    <div>
                      <p class="mb-0">Total TTC</p>
                      <h3 id="totalTTCCard" class="text-success">{{ "%.2f"|format(report_summary.total_ttc) }} {{ report_summary.currency }}</h3>
                    </div>
                    <i class="fas fa-chart-line fa-3x text-success"></i>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <!-- ──────────────────── ligne des totaux HT / TVA / Moyenne ─────────────────── -->
          <div class="row">
            <!-- ──────────────── TOTAL HT ──────────────── -->
            <div class="col-md-4">
              <div class="card mb-3">
                <div class="card-body">
                  <h6 class="text-muted">Total HT</h6>
                  <div class="d-flex justify-content-between align-items-center">
                    <div>
                      <h4 id="totalHTCard" class="text-info">
                        {{ "%.2f"|format(report_summary.total_ht) }} {{ report_summary.currency }}
                      </h4>
                      <span class="text-muted small">Hors taxes</span>
                    </div>
                    <!-- icône -->
                    <i class="fas fa-money-bill-wave fa-3x text-info"></i>
                  </div>
                </div>
              </div>
            </div>

            <!-- ──────────────── TOTAL TVA ──────────────── -->
            <div class="col-md-4">
              <div class="card mb-3">
                <div class="card-body">
                  <h6 class="text-muted">Total TVA</h6>
                  <div class="d-flex justify-content-between align-items-center">
                    <div>
                      <h4 id="totalTVACard" class="text-danger">
                        {{ "%.2f"|format(report_summary.total_tva) }} {{ report_summary.currency }}
                      </h4>
                      <span class="text-muted small">TVA collectée</span>
                    </div>
                    <!-- icône -->
                    <i class="fas fa-percent fa-3x text-danger"></i>
                  </div>
                </div>
              </div>
            </div>

            <!-- ─────────────── MOYENNE / FACTURE ─────────────── -->
            <div class="col-md-4">
              <div class="card mb-3">
                <div class="card-body">
                  <h6 class="text-muted">Moyenne/facture</h6>
                  <div class="d-flex justify-content-between align-items-center">
                    <div>
                      <h4 id="averageCard" class="text-warning">
                        {{ "%.2f"|format(report_summary.total_ttc / report_summary.count if report_summary.count else 0) }}
                        {{ report_summary.currency }}
                      </h4>
                      <span class="text-muted small">Montant moyen</span>
                    </div>
                    <!-- icône -->
                    <i class="fas fa-chart-bar fa-3x text-warning"></i>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <!-- ───────────────────────────────────────────────────────────────────────────── -->
          <div class="mt-4">
            <h5><i class="fas fa-filter me-2"></i>Filtrer par période</h5>
            <div class="row g-3">
              <div class="col-md-4">
                <input type="date" class="form-control" id="startDate">
              </div>
              <div class="col-md-4">
                <input type="date" class="form-control" id="endDate">
              </div>
              <div class="col-md-4">
                <button class="btn btn-primary w-100" onclick="updateReport()">
                  <i class="fas fa-sync me-2"></i>Actualiser
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ====================== ONGLET 3 : HISTORIQUE ========================== -->
<div class="tab-pane fade" id="historique" role="tabpanel">
  <div class="row justify-content-center">
    <div class="col-12">
      <div class="card shadow-lg">
        <div class="card-header bg-primary text-white">
          <h5 class="mb-0"><i class="fas fa-history me-2"></i>Historique des factures</h5>
        </div>
        <div class="card-body">
          <div class="table-responsive">
            <table class="table table-hover" id="invoiceTable">
              <thead class="table-light">
                <tr>
                  <th>Numéro</th>
                  <th>Date</th>
                  <th>Patient</th>
                  <th class="text-end">Montant HT</th>
                  <th class="text-end">TVA</th>
                  <th class="text-end">Total</th>
                  <th class="text-center">Actions</th>
                </tr>
              </thead>
              <tbody>
                {% for f in factures %}
                <tr>
                  <td>{{ f.Numero }}</td>
                  <td>{{ f.Date }}</td>
                  <td>{{ f.Patient }}</td>
                  <td class="text-end">{{ "%.2f"|format(f['Sous-total']) }} {{ report_summary.currency }}</td>
                  <td class="text-end">{{ "%.2f"|format(f.TVA) }} {{ report_summary.currency }}</td>
                  <td class="text-end">{{ "%.2f"|format(f.Total) }} {{ report_summary.currency }}</td>
                  <td class="text-center">
                    <a href="{{ url_for('facturation.download_invoice', filename='Facture_' ~ (f.Numero|string) ~ '.pdf') }}" 
                       class="btn btn-sm btn-outline-primary" title="Télécharger">
                      <i class="fas fa-download"></i>
                    </a>
                    <button class="btn btn-sm btn-outline-danger delete-invoice" 
                            data-id="{{ f.Numero }}" title="Supprimer">
                      <i class="fas fa-trash"></i>
                    </button>
                  </td>
                </tr>
                {% else %}
                <tr>
                  <td colspan="7" class="text-center text-muted">Aucune facture trouvée</td>
                </tr>
                {% endfor %}
              </tbody>
            </table>
          </div>
          
          <div class="d-flex justify-content-between align-items-center mt-3">
            <div class="text-muted small">
              Affichage de {{ factures|length }} factures
            </div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ------------------------ SCRIPTS JAVASCRIPT --------------------------- -->
<script>
// Suppression facture
document.querySelectorAll('.delete-invoice').forEach(btn => {
  btn.addEventListener('click', function() {
    const invoiceId = this.dataset.id;
    if (confirm(`Supprimer la facture ${invoiceId} ? Cette action est irréversible !`)) {
      fetch(`/facturation/delete/${invoiceId}`, { method: 'DELETE' })
        .then(response => {
          if (response.ok) location.reload();
          else alert('Erreur lors de la suppression');
        });
    }
  });
});

// Export Excel
function exportToExcel() {
  fetch('/facturation/export')
    .then(response => response.blob())
    .then(blob => {
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `export_factures_${new Date().toISOString().slice(0,10)}.xlsx`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
    });
}

// Mise à jour rapport
function updateReport() {
  const start = document.getElementById('startDate').value;
  const end   = document.getElementById('endDate').value;
  
  fetch(`/facturation/report?start=${start}&end=${end}`)
    .then(res => res.json())
    .then(data => {
      document.getElementById('invoiceCount' ).textContent = data.count;
      document.getElementById('totalHTCard' ).textContent = data.total_ht.toFixed(2)  + ' ' + data.currency;
      document.getElementById('totalTVACard').textContent = data.total_tva.toFixed(2) + ' ' + data.currency;
      document.getElementById('totalTTCCard').textContent = data.total_ttc.toFixed(2) + ' ' + data.currency;
      document.getElementById('averageCard').textContent = data.average.toFixed(2)   + ' ' + data.currency;
    })
    .catch(() => alert('Erreur lors de la mise à jour'));
}

// Dernier patient
const patientsInfo = {{ patients_info|tojson }};
const selP = document.getElementById('patientSelect');
selP.addEventListener('change', () => {
  const r = patientsInfo.find(p => String(p.ID) === selP.value) || {};
  document.getElementById('last_patient_id').innerHTML   = `<strong>ID :</strong> ${r.ID||''}`;
  document.getElementById('last_patient_name').innerHTML = `<strong>Nom :</strong> ${(r.Nom||'')+' '+(r.Prenom||'')}`.trim();
  document.getElementById('last_patient_phone').innerHTML= `<strong>Téléphone :</strong> ${r.Téléphone||''}`;
});

// Variables globales
const vatInput      = document.getElementById('vatInput');
const vatPercent    = document.getElementById('vatPercent');
let vatRate         = parseFloat(vatInput.value) || 0;
const serviceInput  = document.getElementById('serviceSelect');
const addServiceBtn = document.getElementById('addServiceBtn');
const addToCatalog  = document.getElementById('addToCatalogBtn');
const servicesTable = document.querySelector('#servicesTable tbody');
const totalHTElm    = document.getElementById('totalHT');
const totalTVAElem  = document.getElementById('totalTVA');
const totalTTCElem  = document.getElementById('totalTTC');
const datalist      = document.getElementById('serviceList');
const cards         = document.querySelectorAll('.service-card');
const servicesByCategory = {{ services_by_category|tojson }};

// Validation TVA
vatInput.addEventListener('change', () => {
  const val = parseFloat(vatInput.value);
  if (isNaN(val) || val < 0 || val > 100) {
      alert("Le taux de TVA doit être entre 0 et 100");
      vatInput.value = "{{ vat_default }}";
      return;
  }
  vatRate = val;
  vatPercent.textContent = val.toFixed(2);
  recalcTotals();
});

// Recalcul totaux
function recalcTotals() {
  let ht = 0;
  servicesTable.querySelectorAll('.price-input').forEach(i => {
    ht += parseFloat(i.value) || 0;
  });
  const tva = ht * vatRate / 100;
  totalHTElm.textContent   = ht.toFixed(2);
  totalTVAElem.textContent = tva.toFixed(2);
  totalTTCElem.textContent = (ht + tva).toFixed(2);
}

// Remplir datalist
function fillDatalist(cat) {
  datalist.innerHTML = '';
  servicesByCategory[cat].forEach(svc => {
    let name, price;
    if (svc.includes('|')) [name, price] = svc.split('|');
    else { name=svc; price=''; }
    const opt = document.createElement('option');
    opt.value = price ? `${name}|${price}` : name;
    datalist.appendChild(opt);
  });
}

// Catégories cliquables
cards.forEach(card => {
  card.addEventListener('click', () => {
    cards.forEach(c => c.classList.remove('active'));
    card.classList.add('active');
    fillDatalist(card.dataset.cat);
    serviceSelect.focus();
  });
});
if (cards.length) {
  cards[0].classList.add('active');
  fillDatalist(cards[0].dataset.cat);
}

// Liaison champ prix
serviceSelect.addEventListener('change', () => {
  const val = serviceSelect.value.trim();
  let price = '';
  if (val.includes('|')) {
    [, price] = val.split('|');
  }
  servicePrice.value = parseFloat(price) || '';
  servicePrice.focus();
});

// Ajouter service ligne
addServiceBtn.addEventListener('click', () => {
  const raw   = serviceSelect.value.trim();
  if (!raw) return;
  const name  = raw.includes('|') ? raw.split('|')[0] : raw;
  const price = parseFloat(servicePrice.value) || 0;
  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td>${name}</td>
    <td>
      <input type="number" class="form-control form-control-sm price-input"
             value="${price.toFixed(2)}" step="0.01">
    </td>
    <td class="text-center">
      <button type="button" class="btn btn-sm btn-outline-danger remove-btn">
        <i class="fas fa-trash"></i>
      </button>
    </td>
    <input type="hidden" name="services[]" value="${name}|${price}">
  `;
  tr.querySelector('.remove-btn').onclick    = () => { tr.remove(); recalcTotals(); };
  tr.querySelector('.price-input').oninput   = recalcTotals;
  servicesTable.appendChild(tr);
  recalcTotals();
  serviceSelect.value = '';
  servicePrice.value  = '';
  serviceSelect.focus();
});

// Ajouter au catalogue
addToCatalog.addEventListener('click', () => {
  const active = document.querySelector('.service-card.active');
  if (active) document.getElementById('catalogCategory').value = active.dataset.cat;
  new bootstrap.Modal(document.getElementById('catalogModal')).show();
});
document.getElementById('catalogForm').addEventListener('submit', e => {
  e.preventDefault();
  const cat = document.getElementById('catalogCategory').value;
  const name = document.getElementById('catalogName').value.trim();
  const price= document.getElementById('catalogPrice').value;
  fetch("{{ url_for('facturation.add_service') }}", {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({category:cat,name,price})
  })
  .then(r => r.json())
  .then(res => {
    if (res.success) {
      servicesByCategory[cat].push(`${name}|${price}`);
      if (document.querySelector('.service-card.active').dataset.cat===cat) fillDatalist(cat);
      serviceSelect.value = price?`${name}|${price}`:name;
      addServiceBtn.click();
      bootstrap.Modal.getInstance(document.getElementById('catalogModal')).hide();
    } else alert(res.error||'Erreur');
  })
  .catch(()=>alert('Erreur réseau'));
});
</script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://cdn.datatables.net/1.13.7/js/jquery.dataTables.min.js"></script>
<script src="https://cdn.datatables.net/1.13.7/js/dataTables.bootstrap5.min.js"></script>
<script>
  // Active la recherche, le tri et la pagination sur le tableau des factures
  $(document).ready(function () {
    $('#invoiceTable').DataTable({
      // interface 100 % française (optionnel)
      language: {
        url: '//cdn.datatables.net/plug-ins/1.13.7/i18n/fr-FR.json'
      },
      order: [[ 1, 'desc' ]],   // tri initial : date décroissante
      pageLength: 25            // nombre de lignes par page
    });
  });
</script>
<!-- 1) jQuery (obligatoire pour DataTables) -->
<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>

<!-- 2) DataTables cœur + adaptation Bootstrap 5 -->
<script src="https://cdn.datatables.net/1.13.7/js/jquery.dataTables.min.js"></script>
<script src="https://cdn.datatables.net/1.13.7/js/dataTables.bootstrap5.min.js"></script>

<!-- 3) Activation de la recherche sur #invoiceTable -->
<script>
  $(function () {
    $('#invoiceTable').DataTable({
      language: {               // interface française (optionnel)
        url: '//cdn.datatables.net/plug-ins/1.13.7/i18n/fr-FR.json'
      },
      order: [[1, 'desc']],     // tri initial : Date décroissante
      pageLength: 25            // 25 lignes par page
    });
  });
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# --------------------------- TEMPLATE PATIENT ------------------------------
# ---------------------------------------------------------------------------
new_patient_template = r"""
<!DOCTYPE html>
<html lang="fr">
{{ pwa_head()|safe }}
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
  <title>Ajouter un patient</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
<div class="container py-5">
  <h1 class="mb-4">Ajouter un nouveau patient</h1>
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for cat, msg in messages %}
      <div class="alert alert-{{ cat }}">{{ msg }}</div>
    {% endfor %}
  {% endwith %}
  <form method="post">
    <div class="mb-3">
      <label class="form-label">ID</label>
      <input type="text" name="ID" class="form-control" required>
    </div>
    <div class="mb-3">
      <label class="form-label">Nom</label>
      <input type="text" name="Nom" class="form-control" required>
    </div>
    <div class="mb-3">
      <label class="form-label">Prénom</label>
      <input type="text" name="Prenom" class="form-control" required>
    </div>
    <div class="mb-3">
      <label class="form-label">Téléphone</label>
      <input type="text" name="Téléphone" class="form-control">
    </div>
    <button type="submit" class="btn btn-primary">Enregistrer</button>
    <a href="{{ url_for('facturation.facturation_home') }}" class="btn btn-secondary ms-2">Annuler</a>
  </form>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

