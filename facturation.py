import os
import uuid
from datetime import datetime, date, time
import json

import pandas as pd
import qrcode
from flask import (
    Blueprint, request, render_template_string, redirect, url_for,
    flash, send_file, current_app, jsonify, session
)
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image
import utils
import theme
from rdv import load_patients # This load_patients will now implicitly use dynamic paths from utils
from routes import LISTS_FILE
from utils import merge_with_background_pdf # Import added

facturation_bp = Blueprint('facturation', __name__, url_prefix='/facturation')

# Removed global excel_dir and pdf_dir here.
# They will be referenced directly from utils after utils.set_dynamic_base_dir is called.

def _json_default(obj):
    """
    Makes datetime/date/time objects serializable for Jinja |tojson.
    • datetime → 'YYYY-MM-DD HH:MM:SS'
    • date     → 'YYYY-MM-DD'
    • time     → 'HH:MM'
    All other non-JSON-compatible types are converted to str().
    """
    if isinstance(obj, datetime):
        return obj.strftime('%Y-%m-%d %H:%MM:%S')
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, time):
        return obj.strftime('%H:%M')
    return str(obj)

def _to_json_safe(obj):
    """
    Makes date/time objects serializable for Flask|tojson.
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
    raise TypeError(f"Non-serializable type: {type(obj)}")
  
class PDFInvoice(FPDF):
    def __init__(self, app, numero, patient, phone, date_str, services, currency, vat):
        super().__init__(orientation='P', unit='mm', format='A5')  # A5 for compactness
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
        # Utiliser utils.background_file qui est mis à jour dynamiquement
        bg = getattr(self.app, 'background_path', None) or getattr(utils, 'background_file', None)
        if bg and not os.path.isabs(bg):
            # Assurez-vous que BACKGROUND_FOLDER est défini avant d'y accéder
            if utils.BACKGROUND_FOLDER:
                bg = os.path.join(utils.BACKGROUND_FOLDER, bg)
            else:
                print("WARNING: utils.BACKGROUND_FOLDER not set. Cannot load background image.")
                bg = None # Prevent errors if path is not defined
        
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

        # === Styled header ===
        self.set_fill_color(50, 115, 220)        # strong blue
        self.set_text_color(255, 255, 255)       # white text
        self.set_font('Helvetica', 'B', 12)
        self.cell(w_service, 10, 'SERVICE', border=1, align='C', fill=True)
        self.cell(w_price,   10, f'PRIX ({self.currency})', border=1, align='C', fill=True)
        self.ln()

        # Body preparation
        line_height = self.font_size * 1.5
        total_ht    = 0.0
        fill        = False

        # Colors for alternation
        color_light = (245, 245, 245)
        color_dark  = (255, 255, 255)

        self.set_text_color(0, 0, 0)
        self.set_font('Helvetica', '', 11)

        for svc in self.services:
            # Text cleanup
            name  = svc['name']
            price = f"{svc['price']:.2f}"

            # Choose line background
            self.set_fill_color(*(color_light if fill else color_dark))

            # Calculate cell height based on text
            lines = self.multi_cell(w_service, line_height, name,
                                    border=0, align='L', split_only=True)
            cell_h = len(lines) * line_height

            x0, y0 = self.get_x(), self.get_y()

            # Service column (multi-cell)
            self.multi_cell(w_service, line_height, name,
                            border=1, align='L', fill=True)

            # Price column, repositioned
            self.set_xy(x0 + w_service, y0)
            self.cell(w_price, cell_h, price,
                      border=1, align='R', fill=True)

            # Go to next line
            self.ln(cell_h)
            total_ht += svc['price']
            fill = not fill

        # === Separator line before totals ===
        self.set_draw_color(50, 115, 220)
        self.set_line_width(0.5)
        y = self.get_y() + 2
        self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.ln(6)

        # Bold totals
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

@facturation_bp.route('/new_patient', methods=['GET', 'POST'])
def new_patient():
    # Ensure utils.EXCEL_FOLDER is defined before use
    if utils.EXCEL_FOLDER is None:
        return "Erreur: Les chemins de dossier ne sont pas définis. Veuillez vous connecter.", 500

    excel_path = os.path.join(utils.EXCEL_FOLDER, 'info_Base_patient.xlsx')
    
    # Ensure patient file exists
    if not os.path.exists(excel_path):
        os.makedirs(utils.EXCEL_FOLDER, exist_ok=True)
        # Required columns for listing patients
        df_empty = pd.DataFrame(columns=['ID', 'Nom', 'Prenom', 'Téléphone'])
        df_empty.to_excel(excel_path, index=False)
        
    if request.method == 'POST':
        id_     = request.form.get('ID')
        nom     = request.form.get('Nom')
        prenom  = request.form.get('Prenom')
        tel     = request.form.get('Téléphone', '')
        if not (id_ and nom and prenom):
            flash('Veuillez remplir ID, Nom et Prénom', 'danger')
            return redirect(url_for('facturation.new_patient'))
        df = pd.read_excel(excel_path)
        df = pd.concat([df, pd.DataFrame([{'ID': id_, 'Nom': nom, 'Prenom': prenom, 'Téléphone': tel}])], ignore_index=True)
        df.to_excel(excel_path, index=False)
        flash('Patient ajouté ✔', 'success')
        return redirect(url_for('facturation.facturation_home'))
    return render_template_string(new_patient_template)

@facturation_bp.route('/download/<path:filename>')
def download_invoice(filename):
    """
    Serves the requested PDF file if present in utils.PDF_FOLDER,
    otherwise returns 404/flash.
    """
    # Ensure utils.PDF_FOLDER is defined before use
    if utils.PDF_FOLDER is None:
        return "Erreur: Les chemins de dossier ne sont pas définis. Veuillez vous connecter.", 500
    file_path = os.path.join(utils.PDF_FOLDER, filename)
    if not os.path.isfile(file_path):
        flash("Fichier introuvable !", "danger")
        return redirect(url_for('facturation.facturation_home'))

    return send_file(
        file_path,
        as_attachment=True,
        download_name=filename,
        mimetype='application/pdf'
    )

@facturation_bp.route('/delete/<invoice_number>', methods=['DELETE'])
def delete_invoice(invoice_number):
    """
    Deletes an invoice entry from 'factures.xlsx' and its corresponding PDF file.
    """
    # Ensure utils.EXCEL_FOLDER and utils.PDF_FOLDER are defined before use
    if utils.EXCEL_FOLDER is None or utils.PDF_FOLDER is None:
        return jsonify(success=False, error="Les chemins de dossier ne sont pas définis."), 500

    factures_path = os.path.join(utils.EXCEL_FOLDER, 'factures.xlsx')
    pdf_file_name = f"Facture_{invoice_number}.pdf"
    pdf_path = os.path.join(utils.PDF_FOLDER, pdf_file_name)

    try:
        # Delete from Excel
        if os.path.exists(factures_path):
            df = pd.read_excel(factures_path, dtype={'Numero': str})
            # Filter out the invoice to be deleted
            df_filtered = df[df['Numero'] != invoice_number]
            if len(df_filtered) < len(df): # If an invoice was actually removed
                df_filtered.to_excel(factures_path, index=False)
            else:
                return jsonify(success=False, error="Facture non trouvée dans l'Excel."), 404
        else:
            return jsonify(success=False, error="Fichier Excel des factures introuvable."), 404

        # Delete PDF file
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        else:
            # It's not a critical error if PDF is already gone, but log it
            print(f"PDF file not found for deletion: {pdf_path}")

        return jsonify(success=True), 200

    except Exception as e:
        print(f"Error deleting invoice {invoice_number}: {e}")
        return jsonify(success=False, error=str(e)), 500


@facturation_bp.route('/', methods=['GET', 'POST'])
def facturation_home():
    # utils.set_dynamic_base_dir is called in app.before_request,
    # so utils.EXCEL_FOLDER and utils.PDF_FOLDER should be available here.

    # ---------- 0. Context, themes & BG ----------------------------------
    config      = utils.load_config()
    theme_vars  = theme.current_theme()

    # Assurez-vous que utils.BACKGROUND_FOLDER est défini avant de l'utiliser
    bg_folder = utils.BACKGROUND_FOLDER if utils.BACKGROUND_FOLDER else ""
    background_files = []
    if os.path.exists(bg_folder):
        background_files = [
            f for f in os.listdir(bg_folder)
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.pdf'))
        ]
    current_app.background_path = config.get('background_file_path')

    # ---------- 1. Available services/acts ---------------------------
    # LISTS_FILE est statique, donc son chemin n'est pas affecté
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

    # ---------- 2. Patient database ------------------------------------------
    # Utilise utils.EXCEL_FOLDER qui est maintenant dynamique
    info_path = os.path.join(utils.EXCEL_FOLDER, 'info_Base_patient.xlsx')
    # Initialize last_patient outside the if-else block
    patients_info = []
    last_patient  = {} 
    
    if os.path.exists(info_path):
        df_pat        = pd.read_excel(info_path, dtype=str)
        patients_info = df_pat.to_dict(orient='records')
        last_patient  = df_pat.iloc[-1].to_dict() if not df_pat.empty else {}
    # Moved initialization here:
    # else:
    #     patients_info = []
    #     last_patient  = {}


    # ---------- 3. POST : invoice creation --------------------------------
    if request.method == 'POST':
        # 3-A. Background
        sel_bg = request.form.get('background', config.get('background_file_path'))
        if sel_bg:
            if not os.path.isabs(sel_bg):
                # Assurez-vous que utils.BACKGROUND_FOLDER est défini
                if utils.BACKGROUND_FOLDER:
                    sel_bg = os.path.join(utils.BACKGROUND_FOLDER, sel_bg)
                else:
                    print("WARNING: utils.BACKGROUND_FOLDER not set. Cannot set background.")
                    sel_bg = None
            current_app.background_path   = sel_bg
            if sel_bg: # Only update config if sel_bg is valid
                config['background_file_path'] = os.path.basename(sel_bg)
                utils.save_config(config)

        # 3-B. VAT
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

        # 3-C. Patient info
        pid  = request.form.get('patient_id')
        rec  = next((p for p in patients_info if str(p['ID']) == pid), last_patient)
        patient_name = f"{rec.get('Nom','')} {rec.get('Prenom','')}".strip()
        phone        = rec.get('Téléphone', '')

        # 3-D. Invoice number
        date_str = request.form.get('date')
        date_key = date_str.replace('-', '')
        
        # Utilise utils.PDF_FOLDER qui est maintenant dynamique
        existing = []
        if utils.PDF_FOLDER and os.path.exists(utils.PDF_FOLDER): # Added check for utils.PDF_FOLDER existence
            existing = [
                fn for fn in os.listdir(utils.PDF_FOLDER)
                if fn.startswith(f"Facture_{date_key}")
            ]
        numero = f"{date_key}-{len(existing)+1:03d}"

        # 3-E. Selected services
        services = []
        for svc in request.form.getlist('services[]'):
            name, price = svc.split('|')
            services.append({'name': name, 'price': float(price)})
        if not services:
            flash('Veuillez sélectionner au moins un service', 'danger')
            return redirect(url_for('facturation.facturation_home'))

        # 3-F. Totals
        total_ht   = sum(s['price'] for s in services)
        tva_amount = total_ht * (config.get('vat', 20) / 100)
        total_ttc  = total_ht + tva_amount

        # 3-G. Currency
        selected_currency   = request.form.get('currency', config.get('currency', 'EUR'))
        config['currency']  = selected_currency
        utils.save_config(config)

        # 3-H. PDF Creation
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
        
        # Utilise utils.PDF_FOLDER qui est maintenant dynamique
        output_path = os.path.join(utils.PDF_FOLDER, f"Facture_{numero}.pdf")
        pdf.output(output_path)

        # 3-I. Background merge
        merge_with_background_pdf(output_path)

        # 3-J. Excel Save
        # Utilise utils.EXCEL_FOLDER qui est maintenant dynamique
        factures_path = os.path.join(utils.EXCEL_FOLDER, 'factures.xlsx')
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

    # ---------- 4. GET variables (default form) -------------------------
    from datetime import date # ensure date is imported
    today_iso         = date.today().isoformat()
    date_key          = today_iso.replace('-', '')
    
    # Utilise utils.PDF_FOLDER qui est maintenant dynamique
    existing_pdf      = []
    if utils.PDF_FOLDER and os.path.exists(utils.PDF_FOLDER): # Added check for utils.PDF_FOLDER existence
        existing_pdf = [
            fn for fn in os.listdir(utils.PDF_FOLDER)
            if fn.startswith(f"Facture_{date_key}")
        ]
    numero_default    = f"{date_key}-{len(existing_pdf)+1:03d}"
    vat_default       = config.get('vat', 20.0)
    selected_currency = config.get('currency', 'EUR')

    # ---------- 5. JSON-safe data for template ---------------------
    factures        = load_invoices() # load_invoices utilise utils.EXCEL_FOLDER/factures.xlsx
    report_summary  = generate_report_summary() # utilise load_invoices

    services_json       = json.loads(json.dumps(services_by_category, default=_json_default))
    patients_json       = json.loads(json.dumps(patients_info,       default=_json_default))
    factures_json       = json.loads(json.dumps(factures,            default=_json_default))
    report_summary_json = json.loads(json.dumps(report_summary,      default=_json_default))

    # ---------- Display message if no invoice ---------------------
    if not factures_json:
        flash("Aucune donnée de facturation disponible.", "warning")

    # ---------- 6. Render ---------------------------------------------------
    return render_template_string(
        facturation_template,
        config               = config,
        theme_vars           = theme_vars,
        theme_names          = list(theme.THEMES.keys()),
        services_by_category = services_json,
        patients_info        = patients_json,
        last_patient         = last_patient,
        today                = today_iso,
        numero_default       = numero_default,
        vat_default          = vat_default,
        currency             = selected_currency,
        background_files     = background_files,
        factures             = factures_json,
        report_summary       = report_summary_json
    )

@facturation_bp.route('/add_service', methods=['POST'])
def add_service():
    # LISTS_FILE est statique, donc son chemin n'est pas affecté
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

@facturation_bp.route('/report')
def report():
    start = request.args.get('start') or None
    end   = request.args.get('end')   or None
    summary = generate_report_summary(start, end)
    count = summary['count']
    summary['average'] = summary['total_ttc'] / count if count else 0.0
    return jsonify(summary)

def load_invoices():
    """
    Loads the 'factures.xlsx' workbook and returns a list of dictionaries
    ready for display.

    • Forces the 'Numero' column to remain a **string** (dtype={'Numero': str})
      to avoid any str + int concatenation in the template.
    • Formats the 'Date' column to DD/MM/YYYY format.
    • Returns records sorted from most recent to oldest.
    """
    # Utilise utils.EXCEL_FOLDER qui est maintenant dynamique
    if utils.EXCEL_FOLDER is None:
        print("ERROR: utils.EXCEL_FOLDER is None in load_invoices.")
        return []
        
    factures_path = os.path.join(utils.EXCEL_FOLDER, 'factures.xlsx')
    if os.path.exists(factures_path):
        df = pd.read_excel(factures_path, dtype={'Numero': str}).fillna("")

        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')\
                             .dt.strftime('%d/%m/%Y')

        return df.sort_values('Date', ascending=False, na_position='last')\
                 .to_dict('records')

    return []

def generate_report_summary(start=None, end=None):
    factures = load_invoices()
    config = utils.load_config() # S'assurer que la config est chargée pour la devise
    currency = config.get('currency', 'EUR')
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
    # LISTS_FILE est statique, donc son chemin n'est pas affecté
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), LISTS_FILE)
    if not os.path.exists(path):
        return []

    df = pd.read_excel(path, dtype=str)
    df = df.fillna("")
    return df.to_dict("records")
   
facturation_template = r"""
<!DOCTYPE html>
<html lang="fr">
{{ pwa_head()|safe }}
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
  <title>Facturation – {{ config.nom_clinique or 'EasyMedicaLink' }}</title>

  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.datatables.net/1.13.7/css/dataTables.bootstrap5.min.css" rel="stylesheet">
  <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700&family=Great+Vibes&display=swap" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>

  <style>
    :root {
      {% for var, val in theme_vars.items() %}
      --{{ var }}: {{ val }};
      {% endfor %}
      --font-primary: 'Poppins', sans-serif;
      --font-secondary: 'Great Vibes', cursive;
      --gradient-main: linear-gradient(45deg, var(--primary-color) 0%, var(--secondary-color) 100%);
      --shadow-light: 0 5px 15px rgba(0, 0, 0, 0.1);
      --shadow-medium: 0 8px 25px rgba(0, 0, 0, 0.2);
      --border-radius-lg: 1rem;
      --border-radius-md: 0.75rem;
      --border-radius-sm: 0.5rem;
    }

    body {
      font-family: var(--font-primary);
      background: var(--bg-color);
      color: var(--text-color);
      padding-top: 56px;
      transition: background 0.3s ease, color 0.3s ease;
    }

    .navbar {
      background: var(--gradient-main) !important;
      box-shadow: var(--shadow-medium);
    }
    .navbar-brand {
      font-family: var(--font-secondary);
      font-size: 2.0rem !important;
      color: white !important;
      display: flex;
      align-items: center;
      transition: transform 0.3s ease;
    }
    .navbar-brand:hover {
      transform: scale(1.05);
    }
    .navbar-toggler {
      border: none;
      outline: none;
    }
    .navbar-toggler i {
      color: white;
      font-size: 1.5rem;
    }

    .offcanvas-header {
      background: var(--gradient-main) !important;
      color: white;
    }
    .offcanvas-body {
      background: var(--card-bg) !important;
      color: var(--text-color) !important;
    }
    .offcanvas-title {
      font-weight: 600;
    }

    .card {
      border-radius: var(--border-radius-lg);
      box-shadow: var(--shadow-light);
      background: var(--card-bg) !important;
      color: var(--text-color) !important;
      border: none;
      transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .card:hover {
      box-shadow: var(--shadow-medium);
    }

    .card-header {
      background: var(--primary-color) !important;
      color: var(--button-text) !important;
      border-top-left-radius: var(--border-radius-lg);
      border-top-right-radius: var(--border-radius-lg);
      padding: 1.5rem;
      position: relative;
      overflow: hidden;
    }
    .card-header::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(255, 255, 255, 0.1);
      transform: skewY(-5deg);
      transform-origin: top left;
      z-index: 0;
    }
    .card-header h1, .card-header .header-item, .card-header p {
      position: relative;
      z-index: 1;
      font-size: 1.8rem !important;
      font-weight: 700;
    }
    .card-header i {
      font-size: 1.8rem !important;
      margin-right: 0.5rem;
    }
    .header-item {
      font-size: 1.2rem !important;
      font-weight: 400;
    }

    /* Floating Labels */
    .floating-label {
      position: relative;
      margin-bottom: 1rem;
    }
    .floating-label input,
    .floating-label select {
      padding: 1rem 0.75rem 0.5rem;
      height: auto;
      border-radius: var(--border-radius-sm);
      border: 1px solid var(--secondary-color);
      background-color: var(--card-bg);
      color: var(--text-color);
      transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }
    .floating-label input:focus,
    .floating-label select:focus {
      border-color: var(--primary-color);
      box-shadow: 0 0 0 0.25rem rgba(var(--primary-color-rgb), 0.25);
      background-color: var(--card-bg);
      color: var(--text-color);
    }
    .floating-label label {
      position: absolute;
      top: 0.75rem;
      left: 0.75rem;
      font-size: 1rem;
      color: var(--text-color-light);
      transition: all 0.2s ease;
      pointer-events: none;
    }
    .floating-label input:focus + label,
    .floating-label input:not(:placeholder-shown) + label,
    .floating-label select:focus + label,
    .floating-label select:not([value=""]) + label {
      top: 0.25rem;
      left: 0.75rem;
      font-size: 0.75rem;
      color: var(--primary-color);
      background-color: var(--card-bg);
      padding: 0 0.25rem;
      transform: translateX(-0.25rem);
    }
    .floating-label input[type="date"]:not([value=""])::-webkit-datetime-edit-text,
    .floating-label input[type="date"]:not([value=""])::-webkit-datetime-edit-month-field,
    .floating-label input[type="date"]:not([value=""])::-webkit-datetime-edit-day-field,
    .floating-label input[type="date"]:not([value=""])::-webkit-datetime-edit-year-field {
      color: var(--text-color);
    }
    .floating-label input[type="date"]::-webkit-calendar-picker-indicator {
      filter: {% if session.theme == 'dark' %}invert(1){% else %}none{% endif %};
    }

    /* Buttons */
    .btn {
      border-radius: var(--border-radius-md);
      font-weight: 600;
      transition: all 0.3s ease;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0.75rem 1.25rem;
    }
    .btn i {
      margin-right: 0.5rem;
    }
    .btn-primary {
      background: var(--gradient-main);
      border: none;
      color: var(--button-text);
      box-shadow: var(--shadow-light);
    }
    .btn-primary:hover {
      box-shadow: var(--shadow-medium);
      background: var(--gradient-main);
      opacity: 0.9;
    }
    .btn-success {
      background-color: var(--success-color);
      border-color: var(--success-color);
      color: white;
    }
    .btn-success:hover {
      background-color: var(--success-color-dark);
      border-color: var(--success-color-dark);
      box-shadow: var(--shadow-medium);
    }
    .btn-warning {
      background-color: var(--warning-color);
      border-color: var(--warning-color);
      color: white;
    }
    .btn-warning:hover {
      background-color: var(--warning-color-dark);
      border-color: var(--warning-color-dark);
      box-shadow: var(--shadow-medium);
    }
    .btn-danger {
      background-color: var(--danger-color);
      border-color: var(--danger-color);
      color: white;
    }
    .btn-danger:hover {
      background-color: var(--danger-color-dark);
      border-color: var(--danger-color-dark);
      box-shadow: var(--shadow-medium);
    }
    .btn-info { /* WhatsApp button */
      background-color: #25D366;
      border-color: #25D366;
      color: white;
    }
    .btn-info:hover {
      background-color: #1DA851;
      border-color: #1DA851;
      box-shadow: var(--shadow-medium);
    }
    .btn-outline-secondary {
      border-color: var(--secondary-color);
      color: var(--text-color);
      background-color: transparent;
    }
    .btn-outline-secondary:hover {
      background-color: var(--secondary-color);
      color: white;
      box-shadow: var(--shadow-light);
    }
    .btn-secondary {
      background-color: var(--secondary-color);
      border-color: var(--secondary-color);
      color: var(--button-text);
    }
    .btn-secondary:hover {
      background-color: var(--secondary-color-dark);
      border-color: var(--secondary-color-dark);
      box-shadow: var(--shadow-medium);
    }
    .btn-sm {
      padding: 0.5rem 0.8rem;
      font-size: 0.875rem;
    }

    /* DataTables */
    #invoiceTable_wrapper .dataTables_filter input,
    #invoiceTable_wrapper .dataTables_length select {
      border-radius: var(--border-radius-sm);
      border: 1px solid var(--secondary-color);
      padding: 0.5rem 0.75rem;
      background-color: var(--card-bg);
      color: var(--text-color);
    }
    #invoiceTable_wrapper .dataTables_filter input:focus,
    #invoiceTable_wrapper .dataTables_length select:focus {
      border-color: var(--primary-color);
      box-shadow: 0 0 0 0.25rem rgba(var(--primary-color-rgb), 0.25);
    }
    /* Hide the dropdown arrow for DataTables length select */
    #invoiceTable_wrapper .dataTables_length select {
      -webkit-appearance: none;
      -moz-appearance: none;
      appearance: none;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath fill='none' stroke='%23333' stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M2 5l6 6 6-6'/%3E%3C/svg%3E");
      background-repeat: no-repeat;
      background-position: right 0.75rem center;
      background-size: 0.65em auto;
      padding-right: 2rem;
    }
    body.dark-theme #invoiceTable_wrapper .dataTables_length select {
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath fill='none' stroke='%23fff' stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M2 5l6 6 6-6'/%3E%3C/svg%3E");
    }

    #invoiceTable_wrapper .dataTables_paginate .pagination .page-item .page-link {
      border-radius: var(--border-radius-sm);
      margin: 0 0.2rem;
      background-color: var(--card-bg);
      color: var(--text-color);
      border: 1px solid var(--secondary-color);
    }
    #invoiceTable_wrapper .dataTables_paginate .pagination .page-item.active .page-link {
      background: var(--gradient-main);
      border-color: var(--primary-color);
      color: var(--button-text);
    }
    #invoiceTable_wrapper .dataTables_paginate .pagination .page-item .page-link:hover {
      background-color: rgba(var(--primary-color-rgb), 0.1);
      color: var(--primary-color);
    }
    .table {
      --bs-table-bg: var(--card-bg);
      --bs-table-color: var(--text-color);
      --bs-table-striped-bg: var(--table-striped-bg);
      --bs-table-striped-color: var(--text-color);
      --bs-table-border-color: var(--border-color);
    }
    .table thead th {
      background-color: var(--primary-color);
      color: var(--button-text);
      border-color: var(--primary-color);
    }
    .table tbody tr {
      transition: background-color 0.2s ease;
    }
    .table tbody tr:hover {
      background-color: rgba(var(--primary-color-rgb), 0.05) !important;
    }

    /* Flash messages */
    .alert {
      border-radius: var(--border-radius-md);
      font-weight: 600;
      position: fixed;
      top: 70px;
      left: 50%;
      transform: translateX(-50%);
      z-index: 1060;
      width: 90%;
      max-width: 500px;
      box-shadow: var(--shadow-medium);
      animation: fadeInOut 5s forwards;
    }

    @keyframes fadeInOut {
      0% { opacity: 0; transform: translateX(-50%) translateY(-20px); }
      10% { opacity: 1; transform: translateX(-50%) translateY(0); }
      90% { opacity: 1; transform: translateX(-50%) translateY(0); }
      100% { opacity: 0; transform: translateX(-50%) translateY(-20px); }
    }

    /* Footer */
    footer {
      background: var(--gradient-main);
      color: white;
      font-weight: 300;
      box-shadow: 0 -5px 15px rgba(0, 0, 0, 0.1);
    }
    footer a {
      color: white;
      text-decoration: none;
      transition: color 0.2s ease;
    }
    footer a:hover {
      color: var(--text-color-light);
    }

    /* Nav Tabs */
    .nav-tabs .nav-link {
      border: none;
      color: var(--text-color-light); /* Adjusted for theme */
      font-weight: 500;
      font-size: 1.1rem; /* Adjusted for consistency */
      transition: all 0.2s ease;
      position: relative;
      padding: 0.75rem 1.25rem; /* Adjusted padding */
    }
    .nav-tabs .nav-link i { font-size: 1.2rem; margin-right: 0.5rem; } /* Adjusted icon size */
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

    /* Service Cards */
    .service-card {
      border-radius: var(--border-radius-md);
      box-shadow: var(--shadow-light);
      background: var(--card-bg) !important;
      color: var(--text-color) !important;
      border: 1px solid var(--border-color); /* Use theme border color */
      transition: all 0.2s ease;
      cursor: pointer;
    }
    .service-card:hover {
      transform: translateY(-3px); /* Subtle lift on hover */
      box-shadow: var(--shadow-medium);
    }
    .service-card.active {
      background: var(--gradient-main) !important; /* Use gradient for active state */
      color: var(--button-text) !important;
      border-color: var(--primary-color);
      box-shadow: var(--shadow-medium);
    }
    .service-card i {
      font-size: 2rem !important; /* Adjusted icon size */
      margin-bottom: 0.25rem; /* Reduced margin */
    }
    .service-card .small {
      font-size: 0.85rem; /* Adjusted text size */
      font-weight: 600;
    }

    /* Responsive adjustments */
    @media (max-width: 768px) {
      .card-header h1 {
        font-size: 1.5rem !important;
      }
      .card-header .header-item {
        font-size: 1rem !important;
      }
      .card-header i {
        font-size: 1.5rem !important;
      }
      .nav-tabs .nav-link {
        font-size: 0.9rem;
        padding: 0.5rem 0.75rem;
      }
      .nav-tabs .nav-link i {
        font-size: 1rem;
      }
      .btn {
        width: 100%;
        margin-bottom: 0.5rem;
      }
      .d-flex.gap-2 {
        flex-direction: column;
      }
      .dataTables_filter, .dataTables_length {
        text-align: center !important;
      }
      .dataTables_filter input, .dataTables_length select {
        width: 100%;
        margin-bottom: 0.5rem;
      }
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
       href="{{ url_for('accueil.accueil') }}">
      <i class="fas fa-home me-2"></i>
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
    <div class="d-flex gap-2 mb-4">
      <a href="{{ url_for('login.change_password') }}" class="btn btn-outline-secondary flex-fill">
        <i class="fas fa-key me-2"></i>Modifier passe
      </a>
      <a href="{{ url_for('login.logout') }}" class="btn btn-outline-secondary flex-fill">
        <i class="fas fa-sign-out-alt me-2"></i>Déconnexion
      </a>
    </div>

    <form id="settingsForm" action="{{ url_for('settings') }}" method="POST">
      <div class="mb-3 floating-label">
        <input type="text" class="form-control" name="nom_clinique" id="nom_clinique" value="{{ config.nom_clinique or '' }}" placeholder=" ">
        <label for="nom_clinique">Nom de la clinique</label>
      </div>
      <div class="mb-3 floating-label">
        <input type="text" class="form-control" name="cabinet" id="cabinet" value="{{ config.cabinet or '' }}" placeholder=" ">
        <label for="cabinet">Cabinet</label>
      </div>
      <div class="mb-3 floating-label">
        <input type="text" class="form-control" name="centre_medecin" id="centre_medecin" value="{{ config.centre_medical or '' }}" placeholder=" ">
        <label for="centre_medecin">Centre médical</label>
      </div>
      <div class="mb-3 floating-label">
        <input type="text" class="form-control" name="nom_medecin" id="nom_medecin" value="{{ config.doctor_name or '' }}" placeholder=" ">
        <label for="nom_medecin">Nom du médecin</label>
      </div>
      <div class="mb-3 floating-label">
        <input type="text" class="form-control" name="lieu" id="lieu" value="{{ config.location or '' }}" placeholder=" ">
        <label for="lieu">Lieu</label>
      </div>
      <div class="mb-3 floating-label">
        <select class="form-select" name="theme" id="theme_select" placeholder=" ">
          {% for t in theme_names %}<option value="{{ t }}" {% if config.theme == t %}selected{% endif %}>{{ t.capitalize() }}</option>{% endfor %}
        </select>
        <label for="theme_select">Thème</label>
      </div>
      <div class="d-flex gap-2 mt-4">
        <button type="submit" class="btn btn-success flex-fill">
          <i class="fas fa-save me-2"></i>Enregistrer
        </button>
      </div>
    </form>
  </div>
</div>

<script>
  // Soumission AJAX paramètres
  document.getElementById('settingsForm').addEventListener('submit', e=>{
    e.preventDefault();
    fetch(e.target.action,{method:e.target.method,body:new FormData(e.target),credentials:'same-origin'})
      .then(r=>{ if(!r.ok) throw new Error('Échec réseau'); return r; })
      .then(()=>Swal.fire({icon:'success',title:'Enregistré',text:'Paramètres sauvegardés.'}).then(()=>location.reload()))
      .catch(err=>Swal.fire({icon:'error',title:'Erreur',text:err.message}));
  });
</script>
<div class="container-fluid my-4">
  <div class="row justify-content-center">
    <div class="col-12">
      <div class="card shadow-lg">
        <div class="card-header py-3 text-center">
          <h1 class="mb-2 header-item">
            <i class="fas fa-hospital me-2"></i>
            {{ config.nom_clinique or config.cabinet or 'NOM CLINIQUE/CABINET' }}
          </h1>
          <div class="d-flex justify-content-center gap-4 flex-wrap">
            <div class="d-flex align-items-center header-item">
              <i class="fas fa-user-md me-2"></i><span>{{ config.doctor_name or 'NOM MEDECIN' }}</span>
            </div>
            <div class="d-flex align-items-center header-item">
              <i class="fas fa-map-marker-alt me-2"></i><span>{{ config.location or 'LIEU' }}</span>
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
    <div class="tab-pane fade show active" id="facturation" role="tabpanel">
      <div class="row justify-content-center">
        <div class="col-12">

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

          <div class="card">
            <div class="card-header text-center">
              <h5><i class="fas fa-file-invoice-dollar me-2"></i>Générer une facture</h5>
            </div>
            <div class="card-body">
              <form method="post" id="invoiceForm">
                <div class="row gy-3">
                  <div class="col-md-4 floating-label">
                    <input type="text" 
                          class="form-control" 
                          value="{{ config.get('background_file_path') or 'Aucun arrière-plan' }}"
                          readonly
                          placeholder=" ">
                    <label>Arrière-plan</label>
                    <input type="hidden" name="background" value="{{ config.get('background_file_path') }}">
                  </div>
                  
                  <div class="col-md-4 floating-label">
                    <input type="text" name="numero" class="form-control" value="{{ numero_default }}" readonly placeholder=" ">
                    <label>Numéro</label>
                  </div>
                  <div class="col-md-4 floating-label">
                    <input type="date" name="date" class="form-control" value="{{ today }}" placeholder=" ">
                    <label>Date</label>
                  </div>
                  {% set currencies = [
                    ('EUR','Euro'),('USD','Dollar US'),
                    ('MAD','Dirham marocain'),('DZD','Dinar algérien'),
                    ('TND','Dinar tunisien'),('XOF','Franc CFA (BCEAO)'),
                    ('XAF','Franc CFA (BEAC)'),('CHF','Franc suisse'),
                    ('CAD','Dollar canadien'),('HTG','Gourde haïtienne'),
                    ('GNF','Franc guinéen')
                  ] %}
                  <div class="col-md-4 floating-label">
                    <input type="number"
                           id="vatInput"
                           name="vat"
                           class="form-control"
                           value="{{ vat_default }}"
                           step="0.01"
                           min="0"
                           max="100"
                           required
                           placeholder=" ">
                    <label>TVA (%)</label>
                  </div>
                  <div class="col-md-4 floating-label">
                    <select name="currency" class="form-select" placeholder=" ">
                      {% for code, name in currencies %}
                        <option value="{{ code }}" {% if currency == code %}selected{% endif %}>
                          {{ name }} ({{ code }})
                        </option>
                      {% endfor %}
                    </select>
                    <label>Devise</label>
                  </div>
                  <div class="col-md-4 floating-label">
                    <select id="patientSelect" name="patient_id" class="form-select" placeholder=" ">
                      {% for p in patients_info %}
                      <option value="{{ p.ID }}" {% if p.ID == last_patient.ID %}selected{% endif %}>
                        {{ p.ID }} – {{ p.Nom }} {{ p.Prenom }}
                      </option>
                      {% endfor %}
                    </select>
                    <label>Patient</label>
                  </div>
                </div>

                <div class="card mb-4 mt-4">
                  <div class="card-header"><h6><i class="fas fa-cubes me-2"></i>Services</h6></div>
                  <div class="card-body">

                    <div class="row mb-3">
                      {% for cat in services_by_category.keys() %}
                      <div class="col-6 col-md-3 mb-2">
                        <div class="card service-card h-100 text-center" data-cat="{{ cat }}">
                          <div class="card-body p-2">
                            {% if cat.lower() == 'consultation' %}
                              <i class="fas fa-stethoscope mb-1"></i>
                            {% elif cat.lower() == 'analyses' %}
                              <i class="fas fa-vial mb-1"></i>
                            {% elif cat.lower() == 'radiologies' %}
                              <i class="fas fa-x-ray mb-1"></i>
                            {% else %}
                              <i class="fas fa-briefcase-medical mb-1"></i>
                            {% endif %}
                            <div class="small text-uppercase">{{ cat }}</div>
                          </div>
                        </div>
                      </div>
                      {% endfor %}
                    </div>

                    <div class="d-flex gap-2 mb-3">
                      <div class="floating-label flex-grow-1">
                        <input list="serviceList" id="serviceSelect" class="form-control" placeholder=" ">
                        <label for="serviceSelect">Rechercher ou saisir un service…</label>
                      </div>
                      <div class="floating-label" style="width:100px">
                        <input type="number" id="servicePrice" class="form-control" placeholder=" " step="0.01">
                        <label for="servicePrice">Prix</label>
                      </div>
                      <datalist id="serviceList"></datalist>
                      <button type="button" id="addServiceBtn" class="btn btn-primary">
                        <i class="fas fa-plus"></i>
                      </button>
                      <button type="button" id="addToCatalogBtn" class="btn btn-secondary">
                        <i class="fas fa-folder-plus"></i>
                      </button>
                    </div>

                    <div class="modal fade" id="catalogModal" tabindex="-1">
                      <div class="modal-dialog"><div class="modal-content">
                        <form id="catalogForm">
                          <div class="modal-header">
                            <h5 class="modal-title">Ajouter un service au catalogue</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                          </div>
                          <div class="modal-body">
                            <div class="mb-3 floating-label">
                              <select id="catalogCategory" class="form-select" placeholder=" ">
                                {% for cat in services_by_category.keys() %}
                                <option value="{{ cat }}">{{ cat.capitalize() }}</option>
                                {% endfor %}
                              </select>
                              <label for="catalogCategory">Catégorie</label>
                            </div>
                            <div class="mb-3 floating-label">
                              <input type="text" id="catalogName" class="form-control" required placeholder=" ">
                              <label for="catalogName">Désignation</label>
                            </div>
                            <div class="mb-3 floating-label">
                              <input type="number" id="catalogPrice" class="form-control" step="0.01" required placeholder=" ">
                              <label for="catalogPrice">Prix</label>
                            </div>
                          </div>
                          <div class="modal-footer">
                            <button type="submit" class="btn btn-primary">Enregistrer</button>
                          </div>
                        </form>
                      </div></div>
                    </div>

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
          <div class="row">
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
                    <i class="fas fa-money-bill-wave fa-3x text-info"></i>
                  </div>
                </div>
              </div>
            </div>

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
                    <i class="fas fa-percent fa-3x text-danger"></i>
                  </div>
                </div>
              </div>
            </div>

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
                    <i class="fas fa-chart-bar fa-3x text-warning"></i>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="mt-4">
            <h5><i class="fas fa-filter me-2"></i>Filtrer par période</h5>
            <div class="row g-3">
              <div class="col-md-4 floating-label">
                <input type="date" class="form-control" id="startDate" placeholder=" ">
                <label for="startDate">Date de début</label>
              </div>
              <div class="col-md-4 floating-label">
                <input type="date" class="form-control" id="endDate" placeholder=" ">
                <label for="endDate">Date de fin</label>
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
                  <th>Services</th> <!-- New Services Column -->
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
                  <td>{{ f.Services }}</td> <!-- Display Services -->
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
                  <td colspan="8" class="text-center text-muted">Aucune facture trouvée</td> <!-- Adjusted colspan -->
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

<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://cdn.datatables.net/1.13.7/js/jquery.dataTables.min.js"></script>
<script src="https://cdn.datatables.net/1.13.7/js/dataTables.bootstrap5.min.js"></script>
<script>
// Function to show a custom confirmation dialog using SweetAlert2
function showConfirmDialog(message, confirmAction) {
  Swal.fire({
    title: 'Êtes-vous sûr ?',
    text: message,
    icon: 'warning',
    showCancelButton: true,
    confirmButtonColor: '#3085d6',
    cancelButtonColor: '#d33',
    confirmButtonText: 'Oui, supprimer !',
    cancelButtonText: 'Annuler'
  }).then((result) => {
    if (result.isConfirmed) {
      confirmAction();
    }
  });
}

// Delete invoice
document.querySelectorAll('.delete-invoice').forEach(btn => {
  btn.addEventListener('click', function() {
    const invoiceId = this.dataset.id;
    showConfirmDialog(`Supprimer la facture ${invoiceId} ? Cette action est irréversible !`, () => {
      fetch(`/facturation/delete/${invoiceId}`, { method: 'DELETE' })
        .then(response => {
          if (response.ok) {
            Swal.fire({
              icon: 'success',
              title: 'Supprimé !',
              text: 'La facture a été supprimée.',
              confirmButtonText: 'OK'
            }).then(() => {
              // Stay on the same tab after deletion
              const currentTab = document.querySelector('.nav-link.active').id;
              window.location.hash = '#' + currentTab.replace('tab-', ''); // Set hash to keep tab active
              location.reload(); // Reload to reflect changes
            });
          } else {
            Swal.fire({
              icon: 'error',
              title: 'Erreur',
              text: 'Erreur lors de la suppression.',
              confirmButtonText: 'OK'
            });
          }
        })
        .catch(() => {
          Swal.fire({
            icon: 'error',
            title: 'Erreur',
            text: 'Erreur réseau lors de la suppression.',
            confirmButtonText: 'OK'
          });
        });
    });
  });
});

// Export Excel (unchanged)
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

// Update report
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
    .catch(() => Swal.fire({icon:'error', title:'Erreur', text:'Erreur lors de la mise à jour du rapport.'}));
}

// Last patient
const patientsInfo = {{ patients_info|tojson }};
const selP = document.getElementById('patientSelect');
if (selP) { // Check if element exists before adding listener
  selP.addEventListener('change', () => {
    const r = patientsInfo.find(p => String(p.ID) === selP.value) || {};
    document.getElementById('last_patient_id').innerHTML   = `<strong>ID :</strong> ${r.ID||''}`;
    document.getElementById('last_patient_name').innerHTML = `<strong>Nom :</strong> ${(r.Nom||'')+' '+(r.Prenom||'')}`.trim();
    document.getElementById('last_patient_phone').innerHTML= `<strong>Téléphone :</strong> ${r.Téléphone||''}`;
  });
}

// Global variables
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

// VAT validation
vatInput.addEventListener('change', () => {
  const val = parseFloat(vatInput.value);
  if (isNaN(val) || val < 0 || val > 100) {
      Swal.fire({icon:'error', title:'Erreur', text:"Le taux de TVA doit être entre 0 et 100"});
      vatInput.value = "{{ vat_default }}";
      return;
  }
  vatRate = val;
  vatPercent.textContent = val.toFixed(2);
  recalcTotals();
});

// Recalcul totals
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

// Fill datalist
function fillDatalist(cat) {
  datalist.innerHTML = '';
  // Check if servicesByCategory[cat] is defined and not empty
  if (servicesByCategory[cat] && servicesByCategory[cat].length > 0) {
    servicesByCategory[cat].forEach(svc => {
      let name, price;
      if (svc.includes('|')) [name, price] = svc.split('|');
      else { name=svc; price=''; } // If no price, use empty string
      const opt = document.createElement('option');
      opt.value = price ? `${name}|${price}` : name;
      datalist.appendChild(opt);
    });
  } else {
    // Add a placeholder option if category is empty
    const opt = document.createElement('option');
    opt.value = "Aucun service disponible pour cette catégorie";
    opt.disabled = true; // Make it non-selectable
    datalist.appendChild(opt);
  }
}


// Clickable categories
cards.forEach(card => {
  card.addEventListener('click', () => {
    cards.forEach(c => c.classList.remove('active'));
    card.classList.add('active');
    fillDatalist(card.dataset.cat);
    serviceSelect.focus();
  });
});
// Initial population on page load
if (cards.length > 0 && servicesByCategory[cards[0].dataset.cat]) { // Check if the first category has data
  cards[0].classList.add('active');
  fillDatalist(cards[0].dataset.cat);
} else if (cards.length > 0) { // If first category is empty, still activate it
  cards[0].classList.add('active');
  fillDatalist(cards[0].dataset.cat); // Will show "Aucun service..."
}


// Price field binding
serviceSelect.addEventListener('change', () => {
  const val = serviceSelect.value.trim();
  let price = '';
  if (val.includes('|')) {
    [, price] = val.split('|');
  }
  servicePrice.value = parseFloat(price) || '';
  servicePrice.focus();
});

// Add service line
addServiceBtn.addEventListener('click', () => {
  const raw   = serviceSelect.value.trim();
  if (!raw || raw === "Aucun service disponible pour cette catégorie") { // Prevent adding placeholder text
    Swal.fire({icon:'warning', title:'Attention', text:'Veuillez sélectionner un service valide.'});
    return;
  }
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

// Add to catalog
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
      Swal.fire({icon:'success', title:'Service ajouté', text:'Le service a été ajouté au catalogue.'});
    } else Swal.fire({icon:'error', title:'Erreur', text:res.error||'Erreur'});
  })
  .catch(()=>Swal.fire({icon:'error', title:'Erreur réseau', text:'Impossible d’ajouter le service.'}));
});

// Activate search, sort and pagination on invoice table
$(document).ready(function () {
  $('#invoiceTable').DataTable({
    language: {
      url: '//cdn.datatables.net/plug-ins/1.13.7/i18n/fr-FR.json'
    },
    order: [[ 1, 'desc' ]],
    pageLength: 25
  });

  // Handle tab persistence on page reload
  const urlParams = new URLSearchParams(window.location.search);
  const activeTabId = urlParams.get('tab');
  if (activeTabId) {
    const tabElement = document.getElementById(`tab-${activeTabId}`);
    if (tabElement) {
      const tab = new bootstrap.Tab(tabElement);
      tab.show();
    }
  } else {
    // If no tab specified, default to the first tab (Facturation)
    const firstTab = document.querySelector('#factTab .nav-link.active');
    if (firstTab) {
      const tab = new bootstrap.Tab(firstTab);
      tab.show();
    }
  }

  // Update URL hash when a tab is shown
  $('button[data-bs-toggle="tab"]').on('shown.bs.tab', function (e) {
    const targetTabId = e.target.id.replace('tab-', '');
    // Replace current history state to avoid adding multiple entries
    history.replaceState(null, '', `?tab=${targetTabId}`);
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
