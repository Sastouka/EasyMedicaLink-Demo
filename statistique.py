# statistique.py

import os
import io
import re
import locale

try:
    # tentative de passer en français
    locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
except locale.Error:
    # échec (locale non disponible) → on retombe sur le locale système
    locale.setlocale(locale.LC_TIME, '')
import logging
from datetime import datetime
from functools import lru_cache
from typing import Optional

import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from flask import (
    Blueprint, render_template_string, session,
    redirect, url_for, flash, request,
    send_file, abort
)
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Table, TableStyle, Paragraph,
    Spacer, SimpleDocTemplate, PageTemplate, Frame
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader

import utils
import theme

statistique_bp = Blueprint("statistique", __name__, url_prefix="/statistique")

# Styles ReportLab
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    name='HeaderStyle',
    parent=styles['Normal'],
    fontSize=10,
    textColor=colors.white,
    alignment=1
))

@lru_cache(maxsize=1)
def load_cached_data():
    return _load_all_excels(utils.EXCEL_FOLDER)

class LandscapeTemplate(PageTemplate):
    def __init__(self):
        w, h = landscape(A4)
        frame = Frame(2*cm, 2*cm, w - 4*cm, h - 4*cm)
        super().__init__(id='Landscape', frames=[frame], pagesize=landscape(A4))

def add_header_footer(canvas_obj, doc):
    canvas_obj.saveState()
    canvas_obj.setFont("Helvetica-Bold", 12)
    canvas_obj.drawString(2*cm, doc.pagesize[1] - 2*cm,
                          f"Rapport statistique • {datetime.now().strftime('%d %B %Y')}")
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.drawCentredString(doc.pagesize[0]/2, 1*cm,
                                 f"Page {canvas_obj.getPageNumber()}")
    canvas_obj.restoreState()

def to_mpl_color(c):
    """
    Convertit un reportlab.lib.colors.Color ou une chaîne hexadécimale
    en chaîne hexadécimale acceptée par Matplotlib.
    """
    # Pour un objet Color de ReportLab, on utilise hexval()
    if hasattr(c, 'hexval'):
        val = c.hexval()
        # Suppression du préfixe '0x' éventuel
        if val.lower().startswith('0x'):
            val = val[2:]
        # Retourne la couleur au format '#rrggbb'
        return f"#{val}"
    # Pour une chaîne, on s'assure du préfixe '#'
    if isinstance(c, str):
        return c if c.startswith('#') else f"#{c}"
    # Sinon, on retourne tel quel (tuple RGBA, etc.)
    return c

def draw_chart(canvas_obj, plot_func, title, x, y, w, h, color):
    buf = io.BytesIO()
    fig, ax = plt.subplots(figsize=(w/200, h/200), dpi=200)
    try:
        ok = plot_func(ax)
        if not ok:
            ax.text(0.5, 0.5, "Données indisponibles",
                    ha='center', va='center', color='gray')
    except Exception as e:
        ax.text(0.5, 0.5, "Erreur de rendu",
                ha='center', va='center', color='red')
        logging.error(f"Erreur graphique '{title}': {e}")
    # Couleur du titre
    mpl_color = to_mpl_color(color)
    ax.set_title(title, color=mpl_color, fontsize=10)
    fig.tight_layout(pad=1)
    fig.savefig(buf, format='PNG', dpi=200, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    # drawImage position y is bottom-left
    canvas_obj.drawImage(ImageReader(buf), x, y - h, width=w, height=h)
    return y - h - 10

@statistique_bp.route("/", methods=["GET"])
def stats_home():
    # 1. Autorisation
    role = session.get("role")
    if role not in ["admin", "medecin"]:
        flash("Accès réservé aux administrateurs et médecins.", "danger")
        return redirect(url_for("accueil.accueil"))

    # 2. Chargement des données
    df_map     = _load_all_excels(utils.EXCEL_FOLDER)
    df_consult = df_map.get("ConsultationData.xlsx",  pd.DataFrame())
    df_patient = df_map.get("info_Base_patient.xlsx", pd.DataFrame())
    df_facture = df_map.get("factures.xlsx",          pd.DataFrame())

    # 3. Récupération filtres
    start_str = request.args.get("start_date", "")
    end_str   = request.args.get("end_date", "")
    start_dt = end_dt = None
    try:
        if start_str:
            start_dt = datetime.strptime(start_str, "%Y-%m-%d")
        if end_str:
            end_dt   = datetime.strptime(end_str,   "%Y-%m-%d")
    except ValueError:
        flash("Format de date invalide, utilisez YYYY-MM-DD.", "warning")
        return redirect(url_for(".stats_home"))

    # 4. Filtrage des consultations
    if not df_consult.empty:
        df_consult["consultation_date"] = pd.to_datetime(
            df_consult["consultation_date"].astype(str).str.strip(),
            errors="coerce"
        )
        if start_dt and end_dt:
            df_consult = df_consult[
                (df_consult["consultation_date"] >= start_dt) &
                (df_consult["consultation_date"] <= end_dt)
            ]

    # 5. Filtrage des factures
    if not df_facture.empty and start_dt and end_dt:
        date_col = _find_column(df_facture, ["date", "jour", "day"])
        if date_col:
            df_facture[date_col] = pd.to_datetime(
                df_facture[date_col].astype(str).str.strip(),
                errors="coerce"
            )
            df_facture = df_facture[
                (df_facture[date_col] >= start_dt) &
                (df_facture[date_col] <= end_dt)
            ]

    # 6. Filtrage des patients : on ne garde que ceux ayant consulté dans la période
    if not df_patient.empty and not df_consult.empty:
        if "ID" in df_patient.columns and "ID" in df_consult.columns:
            df_patient = df_patient[df_patient["ID"].isin(df_consult["ID"].unique())]

    # 7. Aucun résultat ? On flash un warning mais on continue le rendu
    if all(d.empty for d in (df_consult, df_patient, df_facture)):
        flash("Aucune donnée disponible pour la période sélectionnée.", "warning")
        # on ne redirige plus, on laisse metrics = 0 et charts = {} pour l'affichage

    # 8. KPI
    metrics = {
        "total_consult":  len(df_consult),
        "total_patients": df_patient["ID"].nunique() if "ID" in df_patient.columns else 0,
        "total_revenue":  _total_revenue(df_facture),
    }

    # 9. Graphiques Chart.js
    charts = {}

    # 9a. Consultations mensuelles
    if not df_consult.empty:
        activ = (
            df_consult
            .dropna(subset=["consultation_date"])
            .groupby(df_consult["consultation_date"].dt.to_period("M"))
            .size()
            .rename("count")
            .reset_index()
        )
        charts["activite_labels"] = activ["consultation_date"].dt.strftime("%Y-%m").tolist()
        charts["activite_values"] = activ["count"].tolist()

    # 9b. Chiffre d’affaires mensuel
    charts.update(_finance_timeseries(df_facture))

    # 9c. Répartition par sexe
    if {"Sexe", "ID"}.issubset(df_patient.columns):
        genre = df_patient.groupby("Sexe")["ID"].count()
        charts["genre_labels"] = genre.index.tolist()
        charts["genre_values"] = genre.values.tolist()

    # 9d. Tranches d’âge
    charts.update(_age_distribution(df_patient))

    # 10. Rendu
    return render_template_string(
        _TEMPLATE,
        config=utils.load_config(),
        theme_vars=theme.current_theme(),
        metrics=metrics,
        charts=charts,
        theme_names=list(theme.THEMES.keys()),
        currency=utils.load_config().get("currency", "EUR"),
        start_date=start_str,
        end_date=end_str,
        today=datetime.now().strftime("%Y-%m-%d")
    )


@statistique_bp.route("/export_pdf", methods=["GET"])
def export_pdf():
    try:
        # 1. Paramètres
        start_str = request.args.get("start_date", "")
        end_str   = request.args.get("end_date", "")
        try:
            start_dt = datetime.strptime(start_str, "%Y-%m-%d") if start_str else None
            end_dt   = datetime.strptime(end_str,   "%Y-%m-%d") if end_str   else None
            if start_dt and end_dt and start_dt > end_dt:
                return "Date de début > date de fin", 400
        except ValueError:
            return "Format date invalide", 400

        # 2. Chargement & filtrage
        df_map     = load_cached_data().copy()
        df_consult = process_consultations(df_map.get("ConsultationData.xlsx", pd.DataFrame()), start_dt, end_dt)
        df_facture = process_factures(df_map.get("factures.xlsx", pd.DataFrame()), start_dt, end_dt)

        # 3. Préparation PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
        doc.addPageTemplates([LandscapeTemplate()])
        doc.onFirstPage = add_header_footer
        doc.onLaterPages = add_header_footer

        story = []
        theme_vars = theme.current_theme()
        primary_color = colors.HexColor(theme_vars["primary-color"])
        secondary_color = colors.HexColor(theme_vars["secondary-color"])

        # 4. Dessin des graphiques (portrait)
        c = canvas.Canvas(buffer, pagesize=landscape(A4))
        y = A4[1] - 4*cm
        w = A4[0] - 4*cm
        h_chart = 180

        y = draw_chart(
            c,
            lambda ax: plot_consultations(ax, df_consult, primary_color),
            "Consultations mensuelles",
            2*cm, y, w, h_chart, primary_color
        )
        y = draw_chart(
            c,
            lambda ax: plot_ca(ax, df_facture, secondary_color),
            "Chiffre d'affaires mensuel",
            2*cm, y, w, h_chart, primary_color
        )

        c.showPage()
        c.save()

        # 5. Tableau (paysage)
        table_data = prepare_table_data(df_facture)
        table = Table(
            table_data,
            colWidths=[(landscape(A4)[0] - 4*cm)/len(table_data[0])] * len(table_data[0]),
            repeatRows=1
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0,0),(-1,0), primary_color),
            ("TEXTCOLOR", (0,0),(-1,0), colors.white),
            ("FONTNAME",  (0,0),(-1,0), "Helvetica-Bold"),
            ("FONTSIZE",  (0,0),(-1,0), 10),
            ("FONTSIZE",  (0,1),(-1,-1), 8),
            ("GRID",      (0,0),(-1,-1), 0.5, colors.black),
            ("ALIGN",     (0,0),(-1,-1), "CENTER"),
            ("ROWBACKGROUNDS", (0,1),(-1,-1), [colors.whitesmoke, colors.lightgrey]),
            ("LEFTPADDING",(0,0),(-1,-1), 4),
            ("RIGHTPADDING",(0,0),(-1,-1), 4),
        ]))

        story.append(Spacer(1, 2*cm))
        story.append(table)
        doc.build(story)

        buffer.seek(0)
        filename = f"rapport_{start_str}_{end_str}.pdf"
        return send_file(buffer, as_attachment=True,
                         download_name=filename,
                         mimetype="application/pdf")

    except Exception:
        logging.exception("Erreur génération PDF")
        abort(500, "Erreur lors de la génération du rapport")

# ────────────────────────────────────────────────────────────
# Helpers (inchangés)
# ────────────────────────────────────────────────────────────
def process_consultations(df, start_dt, end_dt):
    if not df.empty:
        df["consultation_date"] = pd.to_datetime(
            df["consultation_date"], errors="coerce"
        )
        if start_dt and end_dt:
            return df[
                (df["consultation_date"] >= start_dt) & (df["consultation_date"] <= end_dt)
            ]
    return df

def process_factures(df, start_dt, end_dt):
    date_col = _find_column(df, ["date", "jour", "day"])
    if date_col and start_dt and end_dt:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        return df[(df[date_col] >= start_dt) & (df[date_col] <= end_dt)]
    return df

def prepare_table_data(df):
    """Prépare data pour le tableau ReportLab avec Paragraph pour retours à la ligne."""
    headers = [Paragraph(str(c), styles['HeaderStyle']) for c in df.columns]
    body = []
    body_style = ParagraphStyle(
        name="BodyStyle", parent=styles['Normal'],
        fontSize=8, leading=10
    )
    for _, row in df.fillna('').iterrows():
        body.append([Paragraph(str(cell), body_style) for cell in row])
    return [headers] + body

def plot_consultations(ax, df, color):
    """Trace le bar chart des consultations mensuelles."""
    if df.empty:
        return False
    s = df.groupby(df["consultation_date"].dt.to_period("M")).size()
    s.index = s.index.strftime("%Y-%m")
    s.plot.bar(ax=ax, color=color)
    ax.tick_params(axis='x', rotation=45)
    return True

def plot_ca(ax, df, color):
    """Trace le bar chart du chiffre d’affaires mensuel."""
    if df.empty:
        return False
    ca = _finance_timeseries(df)
    ax.bar(ca["ca_labels"], ca["ca_values"], color=color)
    ax.tick_params(axis='x', rotation=45)
    return True

def _load_excel(path: str) -> pd.DataFrame:
    """Charge un fichier Excel en DataFrame, même s’il est absent."""
    if os.path.exists(path):
        return pd.read_excel(path, dtype=str).fillna("")
    return pd.DataFrame()

def _load_all_excels(folder: str) -> dict:
    """Charge tous les fichiers .xlsx/.xls du dossier `folder`."""
    df_map = {}
    if not os.path.isdir(folder):
        return df_map
    for fname in os.listdir(folder):
        if not fname.lower().endswith((".xlsx", ".xls")):
            continue
        try:
            df_map[fname] = pd.read_excel(os.path.join(folder, fname), dtype=str).fillna("")
        except Exception:
            df_map[fname] = pd.DataFrame()
    return df_map

def _find_column(df: pd.DataFrame, keys: list[str]) -> Optional[str]:
    """Cherche une colonne contenant un mot-clé (insensible à la casse)."""
    keys_l = [k.lower() for k in keys]
    for col in df.columns:
        if any(k in col.lower() for k in keys_l):
            return col
    return None

def _total_revenue(df_facture: pd.DataFrame) -> float:
    """Somme totale TTC même si la colonne ne porte pas exactement « Total »."""
    col = _find_column(df_facture, ["total", "montant", "amount"])
    if not col:
        return 0.0
    vals = (df_facture[col].astype(str)
            .str.replace(r"[^\d,.\-]", "", regex=True)
            .str.replace(",", ".", regex=False))
    return round(pd.to_numeric(vals, errors="coerce").sum(), 2)

def _finance_timeseries(df_facture: pd.DataFrame) -> dict:
    """Renvoie dict avec ca_labels/list et ca_values/list par mois."""
    if df_facture.empty:
        return {"ca_labels": [], "ca_values": []}
    date_col = _find_column(df_facture, ["date", "jour", "day"])
    tot_col  = _find_column(df_facture, ["total", "montant", "amount"])
    if not date_col or not tot_col:
        return {"ca_labels": [], "ca_values": []}
    df = df_facture.copy()
    df[date_col] = pd.to_datetime(df[date_col].astype(str).str.strip(), errors="coerce")
    df[tot_col]  = (df[tot_col].astype(str)
                       .str.replace(r"[^\d,.\-]", "", regex=True)
                       .str.replace(",", ".", regex=False)
                       .pipe(pd.to_numeric, errors="coerce"))
    df = df.dropna(subset=[date_col, tot_col])
    df["period"] = df[date_col].dt.to_period("M")
    ca = df.groupby("period")[tot_col].sum()
    all_months = pd.period_range(ca.index.min(), ca.index.max(), freq="M")
    ca = ca.reindex(all_months, fill_value=0)
    labels = [p.strftime("%Y-%m") for p in ca.index]
    values = ca.round(2).tolist()
    return {"ca_labels": labels, "ca_values": values}

def _age_distribution(df_patient: pd.DataFrame) -> dict:
    """Renvoie distribution d’âge en tranches fixes."""
    if "DateNaissance" not in df_patient.columns:
        return {}
    naissance = pd.to_datetime(
        df_patient["DateNaissance"].astype(str).str.strip()
                  .str.replace(r"\s+\d{1,2}:\d{2}(:\d{2})?$", "", regex=True),
        errors="coerce", dayfirst=True
    )
    today = pd.Timestamp.today()
    age_y = ((today - naissance).dt.days / 365.25).round().astype("Int64")
    age_y = age_y.where((age_y >= 0) & (age_y <= 120))
    df_age = pd.DataFrame({"age": age_y}).dropna()
    labels = ["0-2","3-5","6-11","12-14","15-17","18-29","30-39","40-49","50-59","60-69","70+"]
    if df_age.empty:
        return {"age_labels": labels, "age_values": [0]*11}
    bins = [0,3,6,12,15,18,30,40,50,60,70,120]
    df_age["group"] = pd.cut(df_age["age"], bins=bins, labels=labels, right=False)
    grp = df_age.groupby("group")["age"].count().reindex(labels, fill_value=0)
    return {"age_labels": grp.index.tolist(), "age_values": grp.values.tolist()}

def _parse_age(value):
    """Convertit « 23 ans 4 mois » ou « 23,4 » → float années."""
    s = str(value).lower().strip()
    if not s or s in {"nan","na"}:
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        pass
    m = re.search(r"(\d+)\s*(?:ans?|years?)?[\s,]*(\d+)?", s)
    if m:
        years, months = int(m.group(1)), int(m.group(2) or 0)
        return years + months/12
    return None
# --------------------------------------------------------------------------- #
#  HTML – Amazon-style, sans onglets                                          #
# --------------------------------------------------------------------------- #
_TEMPLATE = r"""
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
<style>
  .card-header h1, .card-header .header-item, .card-header p{font-size:30px!important;}
  .card-header h1 i, .card-header .header-item i, .card-header p i{font-size:30px!important;}
  .header-item{font-size:28px!important;}
</style>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,shrink-to-fit=no">
<title>Statistiques – {{ config.nom_clinique or 'EasyMedicaLink' }}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
<script src="https://cdn.tailwindcss.com"></script>
<style>
  :root{ {% for v,c in theme_vars.items() %}--{{v}}:{{c}};{% endfor %} --amazon-orange:#FF9900;}
  body{background:var(--bg-color);color:var(--text-color);padding-top:56px;}
  .navbar, .offcanvas-header{background:linear-gradient(45deg,var(--amazon-orange),var(--primary-color))!important;}
  .offcanvas-body, .card{background:var(--card-bg)!important;color:var(--text-color)!important;}
  .card-header{background:var(--primary-color)!important;color:var(--button-text)!important;}
  .card{border-radius:15px;box-shadow:0 4px 20px var(--card-shadow)!important;}
  .kpi-card{background:var(--card-bg);border:2px solid var(--amazon-orange);border-radius:12px;transition:transform .2s;}
  .kpi-card:hover{transform:translateY(-4px);}
  .kpi-value{font-size:2.2rem;font-weight:700;color:var(--amazon-orange);}
  .kpi-label{font-size:1rem;color:var(--text-color);}
  .chart-card{background:var(--card-bg);border-radius:15px;box-shadow:0 4px 20px var(--card-shadow)!important;}
</style>
</head>
<body>

{% include 'navbar.html' ignore missing %}

<div class="container-fluid my-4">

  <!-- Filtre par période et export PDF -->
  <form class="row g-2 mb-4 justify-content-center" method="get">
    <div class="col-auto">
      <a href="{{ url_for('statistique.export_pdf', start_date=start_date, end_date=end_date) }}"
         class="btn btn-outline-secondary">Générer Historique des Facturations en PDF</a>
    </div>
  </form>
  <!-- KPI -->
  <div class="row g-4">
    <div class="col-12 col-lg-4">
      <div class="p-3 kpi-card h-100 text-center">
        <div class="kpi-value">{{ metrics.total_consult }}</div>
        <div class="kpi-label">Consultations totales</div>
      </div>
    </div>
    <div class="col-12 col-lg-4">
      <div class="p-3 kpi-card h-100 text-center">
        <div class="kpi-value">{{ metrics.total_patients }}</div>
        <div class="kpi-label">Patients uniques</div>
      </div>
    </div>
    <div class="col-12 col-lg-4">
      <div class="p-3 kpi-card h-100 text-center">
        {# Ancien format conservé pour référence — ligne commentée #}
        {# <div class="kpi-value">{{ "{:,2f}".format(metrics.total_revenue) }}</div> #}
        <div class="kpi-value">{{ "%.2f"|format(metrics.total_revenue) }} {{ currency }}</div>  <!-- ← NEW -->
        <div class="kpi-label">Chiffre d’affaires (TTC)</div>
      </div>
    </div>
  </div>

  <!-- Graphiques -->
  <div class="row g-4 mt-4">
    <div class="col-12 col-xl-6">
      <div class="card chart-card">
        <div class="card-header"><i class="fas fa-chart-line me-2"></i>Consultations mensuelles</div>
        <div class="card-body"><canvas id="consultChart"></canvas></div>
      </div>
    </div>
    <div class="col-12 col-xl-6">
      <div class="card chart-card">
        <div class="card-header"><i class="fas fa-coins me-2"></i>Chiffre d’affaires mensuel</div>
        <div class="card-body"><canvas id="caChart"></canvas></div>
      </div>
    </div>
    <div class="col-12 col-xl-6">
      <div class="card chart-card">
        <div class="card-header"><i class="fas fa-venus-mars me-2"></i>Répartition par sexe</div>
        <div class="card-body"><canvas id="genderChart"></canvas></div>
      </div>
    </div>
    <div class="col-12 col-xl-6">
      <div class="card chart-card">
        <div class="card-header"><i class="fas fa-chart-area me-2"></i>Tranches d’âge</div>
        <div class="card-body"><canvas id="ageChart"></canvas></div>
      </div>
    </div>
  </div>
</div>

{% include 'footer.html' ignore missing %}

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0"></script>
<script>
const CHARTS={{ charts|tojson }};
Chart.defaults.color='#333';
Chart.defaults.font.family="'Segoe UI','Helvetica Neue',Arial'";
Chart.defaults.devicePixelRatio = 2;

/* Plugin datalabels si présent */
if(window.ChartDataLabels){ Chart.register(window.ChartDataLabels); }

Chart.defaults.plugins.datalabels.font={weight:'600'};
const noLegend={plugins:{legend:{display:false}}};

/* Palettes dédiées */
const COLORS={
  consult:'#FF9800',
  ca:'#4CAF50',
  age:'#9C27B0',
  gender:['#2196F3','#E91E63','#9E9E9E']
};

/* Activité */
if(CHARTS.activite_labels?.length){
 new Chart(document.getElementById('consultChart'),
   {type:'bar',data:{labels:CHARTS.activite_labels,
                     datasets:[{data:CHARTS.activite_values,backgroundColor:COLORS.consult,borderRadius:4}]},
    options:noLegend});
}
/* CA */
/* CA */
if (CHARTS.ca_labels?.length) {
  new Chart(document.getElementById('caChart'), {
    type: 'bar',
    data: {
      labels: CHARTS.ca_labels,
      datasets: [{
        data: CHARTS.ca_values,
        backgroundColor: COLORS.ca,
        borderRadius: 4
      }]
    },
    options: {
      // on conserve juste la légende désactivée
      plugins: {
        legend: { display: false }
      },
      // on force l’axe X en « category » pour n’afficher que le label exact
      scales: {
        x: {
          type: 'category',
          title: {
            display: true,
            text: 'Mois'
          }
        }
      }
    }
  });
}
/* Sexe */
if(CHARTS.genre_labels?.length){
 const total=CHARTS.genre_values.reduce((a,b)=>a+b,0)||1;
 new Chart(document.getElementById('genderChart'),{
   type:'doughnut',
   data:{labels:CHARTS.genre_labels,
         datasets:[{data:CHARTS.genre_values,
                    backgroundColor:COLORS.gender,borderWidth:0}]},
   options:{
     maintainAspectRatio:false,
     plugins:{
       legend:{display:false},
       datalabels:{color:'#fff',font:{size:14},
         formatter:(v,ctx)=>ctx.chart.data.labels[ctx.dataIndex]+' '+(v*100/total).toFixed(0)+'%'}
     }}
 });
}
/* Âge */
if(CHARTS.age_labels?.length){
 new Chart(document.getElementById('ageChart'),
   {type:'bar',data:{labels:CHARTS.age_labels,
                     datasets:[{data:CHARTS.age_values,backgroundColor:COLORS.age,borderRadius:4}]},
    options:noLegend});
}
</script>
</body>
</html>
"""
