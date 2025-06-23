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
    Blueprint, request, render_template_string,
    redirect, url_for, flash, send_file, session, jsonify, abort
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
    canvas_obj.setFont("Helvetica-Bold", 14)
    canvas_obj.drawCentredString(
        doc.pagesize[0]/2,  # Centre horizontal
        doc.pagesize[1] - 2*cm,  # Même position verticale
        f"Rapport statistique • {datetime.now().strftime('%d %B %Y')}"
    )
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.drawCentredString(doc.pagesize[0]/2, 1*cm,
                                 f"Page {canvas_obj.getPageNumber()}")
    canvas_obj.restoreState()

def to_mpl_color(c):
    """Convertit tous les formats ReportLab/autres en format Matplotlib valide."""
    # Conversion des objets Color de ReportLab
    if hasattr(c, 'hexval'):
        hex_val = c.hexval()
        return f"#{hex_val[2:]}" if hex_val.startswith('0x') else f"#{hex_val}"
    
    # Conversion des tuples RGBA (valeurs 0-1)
    if isinstance(c, tuple) and len(c) in (3, 4):
        return (c[0], c[1], c[2], c[3]) if len(c) == 4 else (c[0], c[1], c[2])
    
    # Conversion des chaînes sans préfixe #
    if isinstance(c, str) and not c.startswith('#'):
        return f"#{c}"
    
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
        return redirect(url_for("accueil.accueil")) # Assurez-vous que 'accueil.accueil' est une route valide

    # 2. Chargement des données
    df_map = _load_all_excels(utils.EXCEL_FOLDER)
    df_consult = df_map.get("ConsultationData.xlsx", pd.DataFrame())
    df_patient = df_map.get("info_Base_patient.xlsx", pd.DataFrame())
    df_facture = df_map.get("factures.xlsx", pd.DataFrame())

    # 3. Récupération filtres (INITIALISATION EXPLICITE)
    start_str = request.args.get("start_date", "")
    end_str = request.args.get("end_date", "")
    start_dt = None  # <-- Initialisation obligatoire
    end_dt = None    # <-- Initialisation obligatoire

    try:
        if start_str:
            start_dt = datetime.strptime(start_str, "%Y-%m-%d")
        if end_str:
            end_dt = datetime.strptime(end_str, "%Y-%m-%d")
    except ValueError:
        flash("Format de date invalide, utilisezYYYY-MM-DD.", "warning")
        return redirect(url_for(".stats_home"))

    # 4. Filtrage des consultations (GESTION DES VALEURS NULLES)
    if not df_consult.empty:
        df_consult["consultation_date"] = pd.to_datetime(
            df_consult["consultation_date"].astype(str).str.strip(),
            errors="coerce"
        )
        # Correction ici ▼
        mask = pd.Series([True] * len(df_consult), index=df_consult.index)  # <-- Série de True
        if start_dt:
            mask &= (df_consult["consultation_date"] >= start_dt)
        if end_dt:
            mask &= (df_consult["consultation_date"] <= end_dt)
        df_consult = df_consult[mask]
        
    # 5. Filtrage des factures
    if not df_facture.empty and (start_dt or end_dt):
        date_col = _find_column(df_facture, ["date", "jour", "day"])
        if date_col:
            df_facture[date_col] = pd.to_datetime(
                df_facture[date_col].astype(str).str.strip(),
                errors="coerce"
            )
            mask = True
            if start_dt:
                mask &= (df_facture[date_col] >= start_dt)
            if end_dt:
                mask &= (df_facture[date_col] <= end_dt)
            df_facture = df_facture[mask]

    # 6. Filtrage des patients : on ne garde que ceux ayant consulté dans la période
    if not df_patient.empty and not df_consult.empty:
        if "ID" in df_patient.columns and "ID" in df_consult.columns:
            df_patient = df_patient[df_patient["ID"].isin(df_consult["ID"].unique())]

    # 7. Vérification des données disponibles pour l'export
    data_available = not (df_consult.empty and df_facture.empty and df_patient.empty)

    # 7.a. Aucun résultat ? On flash un warning mais on continue le rendu
    if all(d.empty for d in (df_consult, df_patient, df_facture)):
        flash("Aucune donnée disponible pour la période sélectionnée.", "warning")   

    # 8. KPI
    metrics = {
        "total_factures":  len(df_facture),
        "total_patients": df_patient["ID"].nunique() if "ID" in df_patient.columns else 0,
        "total_revenue":  _total_revenue(df_facture), # _total_revenue est mis à jour pour le TTC
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
    else:
        charts["activite_labels"] = []
        charts["activite_values"] = []


    # 9b. Chiffre d’affaires mensuel (utilisera _finance_timeseries mis à jour pour le TTC)
    charts.update(_finance_timeseries(df_facture))

    # 9c. Répartition par sexe
    if {"Sexe", "ID"}.issubset(df_patient.columns):
        genre = df_patient.groupby("Sexe")["ID"].count()
        charts["genre_labels"] = genre.index.tolist()
        charts["genre_values"] = genre.values.tolist()
    else:
        charts["genre_labels"] = []
        charts["genre_values"] = []


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
        today=datetime.now().strftime("%Y-%m-%d"),
        data_available=data_available,
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
        df_patient = df_map.get("info_Base_patient.xlsx", pd.DataFrame()) # Charger le df_patient ici
        if not df_patient.empty and not df_consult.empty: # Filtrer df_patient si nécessaire
            if "ID" in df_patient.columns and "ID" in df_consult.columns:
                df_patient = df_patient[df_patient["ID"].isin(df_consult["ID"].unique())]

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
        h_chart = 180
        # Utiliser la largeur de la page PDF moins les marges latérales
        w = A4[0] - 4*cm 

        # Dessin des graphiques en PNG et insertion dans le PDF
        # Chaque appel à draw_chart consomme une hauteur h_chart + un petit espace
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
        y = draw_chart(
            c,
            lambda ax: plot_genre_distribution(ax, df_patient, primary_color),
            "Répartition par sexe",
            2*cm, y, w, h_chart, primary_color
        )
        y = draw_chart(
            c,
            lambda ax: plot_age_distribution(ax, df_patient, secondary_color),
            "Tranches d'âge",
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
        filename = f"rapport_statistique_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        return send_file(buffer, as_attachment=True,
                         download_name=filename,
                         mimetype="application/pdf")

    except Exception:
        logging.exception("Erreur génération PDF")
        abort(500, "Erreur lors de la génération du rapport")

# ────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────
def process_consultations(df, start_dt=None, end_dt=None):
    if df.empty:
        return df
    df["consultation_date"] = pd.to_datetime(df["consultation_date"], errors="coerce")
    if start_dt or end_dt:
        mask = True
        if start_dt:
            mask &= (df["consultation_date"] >= start_dt)
        if end_dt:
            mask &= (df["consultation_date"] <= end_dt)
        return df[mask]
    return df

def process_factures(df, start_dt=None, end_dt=None):
    date_col = _find_column(df, ["date", "jour", "day"])
    if date_col and (start_dt or end_dt):
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        mask = True
        if start_dt:
            mask &= (df[date_col] >= start_dt)
        if end_dt:
            mask &= (df[date_col] <= end_dt)
        return df[mask]
    return df

def prepare_table_data(df):
    """Prépare data pour le tableau ReportLab avec Paragraph pour retours à la ligne."""
    if df.empty:
        # Renvoie une liste avec juste les en-têtes si le DataFrame est vide
        return [['ID', 'Date', 'Type', 'Description', 'Montant']] 
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
    color = to_mpl_color(color)
    """Trace le bar chart des consultations mensuelles."""
    if df.empty:
        return False
    s = df.groupby(df["consultation_date"].dt.to_period("M")).size()
    s.index = s.index.strftime("%Y-%m")
    s.plot.bar(ax=ax, color=color)
    ax.tick_params(axis='x', rotation=45)
    return True

def plot_ca(ax, df, color):
    color = to_mpl_color(color)
    """Trace le bar chart du chiffre d’affaires mensuel."""
    if df.empty:
        return False
    # Appel _finance_timeseries pour obtenir les valeurs TTC calculées
    finance_data = _finance_timeseries(df)
    if not finance_data["ca_labels"]: # Si aucune donnée générée
        return False
    ax.bar(finance_data["ca_labels"], finance_data["ca_values"], color=color)
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
    """Calcule la somme totale TTC en utilisant 'Sous-total' et 'TVA'."""

    sous_total_col = _find_column(df_facture, ["Sous-total", "HT", "subtotal"])
    tva_col = _find_column(df_facture, ["TVA", "tax", "vat"])

    if not sous_total_col or not tva_col:
        # Si les colonnes essentielles pour le calcul sont manquantes, retourne 0.0
        print("WARNING: Missing 'Sous-total' or 'TVA' columns for total revenue calculation.")
        return 0.0

    df = df_facture.copy() # Travailler sur une copie pour éviter de modifier le DataFrame original
    
    # Nettoyage et conversion de la colonne 'Sous-total'
    vals_sous_total = (df[sous_total_col].astype(str)
                       .str.replace(r"[^\d,.\-]", "", regex=True)
                       .str.replace(",", ".", regex=False))
    numeric_sous_total = pd.to_numeric(vals_sous_total, errors="coerce").fillna(0)

    # Nettoyage et conversion de la colonne 'TVA'
    vals_tva = (df[tva_col].astype(str)
                .str.replace(r"[^\d,.\-]", "", regex=True)
                .str.replace(",", ".", regex=False))
    numeric_tva = pd.to_numeric(vals_tva, errors="coerce").fillna(0)

    # Calcul du TTC
    ttc_calculated = numeric_sous_total + numeric_tva
    return round(ttc_calculated.sum(), 2)

def _finance_timeseries(df_facture: pd.DataFrame) -> dict:
    """Renvoie dict avec ca_labels/list et ca_values/list par mois."""
    if df_facture.empty:
        return {"ca_labels": [], "ca_values": []}

    date_col = _find_column(df_facture, ["date", "jour", "day"])
    sous_total_col = _find_column(df_facture, ["Sous-total", "HT", "subtotal"])
    tva_col = _find_column(df_facture, ["TVA", "tax", "vat"])

    if not date_col or not sous_total_col or not tva_col:
        # Si les colonnes essentielles pour le calcul sont manquantes, retourne vide
        print("WARNING: Missing 'Date', 'Sous-total' or 'TVA' columns for finance timeseries.")
        return {"ca_labels": [], "ca_values": []}

    df = df_facture.copy()
    df[date_col] = pd.to_datetime(df[date_col].astype(str).str.strip(), errors="coerce")

    # Calcul explicite du TTC
    df['calculated_total_ttc'] = (
        df[sous_total_col].astype(str).str.replace(r"[^\d,.\-]", "", regex=True).str.replace(",", ".", regex=False).pipe(pd.to_numeric, errors="coerce").fillna(0) +
        df[tva_col].astype(str).str.replace(r"[^\d,.\-]", "", regex=True).str.replace(",", ".", regex=False).pipe(pd.to_numeric, errors="coerce").fillna(0)
    )

    df = df.dropna(subset=[date_col, 'calculated_total_ttc']) # Supprime les lignes où la date ou le total calculé est NaN
    
    df["period"] = df[date_col].dt.to_period("M")
    
    ca = df.groupby("period")['calculated_total_ttc'].sum()
    
    # Réindexer pour s'assurer que tous les mois sont présents, même s'il n'y a pas de données
    if not ca.empty:
        all_months = pd.period_range(ca.index.min(), ca.index.max(), freq="M")
        ca = ca.reindex(all_months, fill_value=0)
    else:
        return {"ca_labels": [], "ca_values": []}

    labels = [p.strftime("%Y-%m") for p in ca.index]
    values = ca.round(2).tolist()
    
    return {"ca_labels": labels, "ca_values": values}

def _age_distribution(df_patient: pd.DataFrame) -> dict:
    """Renvoie distribution d’âge en tranches fixes."""
    if "DateNaissance" not in df_patient.columns:
        return {"age_labels": [], "age_values": []} # Retourne des listes vides si la colonne n'existe pas
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
    grp = df_age.groupby("group", observed=False)["age"].count().reindex(labels, fill_value=0)
    return {"age_labels": grp.index.tolist(), "age_values": grp.values.tolist()}

def plot_genre_distribution(ax, df_patient, color):
    """Répartition par sexe (camembert troué)."""
    if df_patient.empty or "Sexe" not in df_patient.columns:
        return False
    
    counts = df_patient["Sexe"].value_counts()
    
    # Correction pour gérer les cas où il n'y aurait qu'un seul sexe ou aucun
    if len(counts) == 0:
        return False # Pas de données de genre à afficher

    colors_list = [to_mpl_color(c) for c in COLORS['gender']] # Utilise les couleurs définies dans le JS
    
    ax.pie(
        counts, 
        labels=counts.index, 
        autopct='%1.1f%%', 
        colors=colors_list[:len(counts)], # S'assure d'utiliser le bon nombre de couleurs
        wedgeprops={'width': 0.6}
    )
    
    return True


def plot_age_distribution(ax, df_patient, color):
    color = to_mpl_color(color)
    """Tranches d'âge (histogramme)."""
    if df_patient.empty or "DateNaissance" not in df_patient.columns:
        return False
    age_data = _age_distribution(df_patient)
    if not age_data["age_labels"]: # Si pas de données d'âge après traitement
        return False
    ax.bar(age_data["age_labels"], age_data["age_values"], color=color)
    ax.tick_params(axis='x', rotation=45)
    return True 

# --------------------------------------------------------------------------- #
#  HTML – Amazon-style, sans onglets                                          #
# --------------------------------------------------------------------------- #
_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="fr">
{{ pwa_head()|safe }}
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
<title>Statistiques – {{ config.nom_clinique or 'EasyMedicaLink' }}</title>
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

  /* KPI Cards */
  .kpi-card {
    background: var(--card-bg);
    border: 2px solid var(--primary-color); /* Use primary color for border */
    border-radius: var(--border-radius-md);
    transition: transform .2s ease, box-shadow .2s ease;
    box-shadow: var(--shadow-light);
  }
  .kpi-card:hover {
    transform: translateY(-5px);
    box-shadow: var(--shadow-medium);
  }
  .kpi-value {
    font-size: 2.2rem;
    font-weight: 700;
    color: var(--primary-color); /* Use primary color for value */
  }
  .kpi-label {
    font-size: 1rem;
    color: var(--text-color);
  }

  /* Chart Cards */
  .chart-card {
    background: var(--card-bg);
    border-radius: var(--border-radius-lg);
    box-shadow: var(--shadow-light);
    border: none;
  }
  .chart-card .card-header {
    background: var(--secondary-color) !important; /* Use secondary color for chart headers */
    color: var(--button-text) !important;
    border-top-left-radius: var(--border-radius-lg);
    border-top-right-radius: var(--border-radius-lg);
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

  /* Form controls */
  .form-control, .form-select {
    border-radius: var(--border-radius-sm);
    border: 1px solid var(--secondary-color);
    padding: 0.5rem 0.75rem;
    background-color: var(--card-bg);
    color: var(--text-color);
  }
  .form-control:focus, .form-select:focus {
    border-color: var(--primary-color);
    box-shadow: 0 0 0 0.25rem rgba(var(--primary-color-rgb), 0.25);
  }

  /* Footer */
  footer {
    background: var(--gradient-main);
    color: white;
    font-weight: 300;
    box-shadow: 0 -5px 15px rgba(0, 0, 0, 0.1);
    padding-top: 0.75rem; /* Reduced padding */
    padding-bottom: 0.75rem; /* Reduced padding */
    margin-top: 2rem; /* Added margin-top for space from buttons */
  }
  footer p {
    margin-bottom: 0.25rem; /* Reduced margin for paragraphs */
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
        <input type="text" class="form-control" name="nom_clinique" id="nom_clinique"
               value="{{ config.nom_clinique | default('') }}" placeholder=" ">
        <label for="nom_clinique">Nom Clinique / Cabinet</label>
      </div>
      <div class="mb-3 floating-label">
        <input type="text" class="form-control" name="centre_medecin" id="centre_medecin"
               value="{{ config.centre_medical | default('') }}" placeholder=" ">
        <label for="centre_medecin">Centre Médical</label>
      </div>
      <div class="mb-3 floating-label">
        <input type="text" class="form-control" name="nom_medecin" id="nom_medecin"
               value="{{ config.doctor_name | default('') }}" placeholder=" ">
        <label for="nom_medecin">Nom Médecin</label>
      </div>
      <div class="mb-3 floating-label">
        <input type="text" class="form-control" name="lieu" id="lieu"
               value="{{ config.location | default('') }}" placeholder=" ">
        <label for="lieu">Lieu</label>
      </div>
      <div class="mb-3 floating-label">
        <select id="theme" name="theme" class="form-select" placeholder=" ">
          {% for t in theme_names %}
            <option value="{{ t }}" {% if config.theme == t %}selected{% endif %}>{{ t.capitalize() }}</option>
          {% endfor %}
        </select>
        <label for="theme">Thème</label>
      </div>
      <button type="submit" class="btn btn-success w-100">
        <i class="fas fa-save me-2"></i>Enregistrer
      </button>
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
  <div class="row justify-content-center">
    <div class="col-12">
      <form class="row g-2 mb-4 justify-content-center" method="get">
        <div class="col-auto">
          <a href="{{ url_for('statistique.export_pdf', start_date=start_date, end_date=end_date) if data_available else '#' }}"
            class="btn btn-outline-secondary {{ 'disabled pe-none' if not data_available }}"
            {% if not data_available %}aria-disabled="true" tabindex="-1"{% endif %}>
            <i class="fas fa-file-pdf me-2"></i>Générer le Rapport PDF
          </a>
        </div>
      </form>

      <div class="row g-4">
        <div class="col-12 col-lg-4">
          <div class="p-3 kpi-card h-100 text-center">
            <div class="kpi-value">{{ metrics.total_factures }}</div>
            <div class="kpi-label">Nombre total des factures</div>
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
            <div class="kpi-value">{{ "%.2f"|format(metrics.total_revenue) }} {{ currency }}</div>
            <div class="kpi-label">Chiffre d’affaires (TTC)</div>
          </div>
        </div>
      </div>

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
  </div>
</div>

<footer class="text-center py-3">
  <p class="small mb-1" style="color: white;">
    <i class="fas fa-heartbeat me-1"></i>
    SASTOUKA DIGITAL © 2025 • sastoukadigital@gmail.com tel +212652084735
  </p>
</footer>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0"></script>
<script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
<script>
const CHARTS={{ charts|tojson }};
Chart.defaults.color='var(--text-color)'; /* Use theme variable */
Chart.defaults.font.family="'Poppins', sans-serif"; /* Use theme font */
Chart.defaults.devicePixelRatio = 2;

/* Plugin datalabels si présent */
if(window.ChartDataLabels){ Chart.register(window.ChartDataLabels); }

Chart.defaults.plugins.datalabels.font={weight:'600'};
const noLegend={plugins:{legend:{display:false}}};

/* Palettes dédiées avec des couleurs vives */
const COLORS={
  consult:'#FF5733', /* Vibrant Orange-Red */
  ca:'#33FF57',    /* Bright Green */
  age:'#8A2BE2',   /* Blue Violet */
  gender:['#00BFFF', '#FF1493', '#FFD700'] /* Deep Sky Blue, Deep Pink, Gold */
};

/* Activité */
if(CHARTS.activite_labels?.length){
 new Chart(document.getElementById('consultChart'),
   {type:'bar',data:{labels:CHARTS.activite_labels,
                     datasets:[{data:CHARTS.activite_values,backgroundColor:COLORS.consult,borderRadius:4}]},
    options:noLegend});
} else {
  // Afficher un graphique vide avec un message si aucune donnée
  new Chart(document.getElementById('consultChart'), {
    type: 'bar',
    data: {
      labels: ['Aucune donnée'],
      datasets: [{
        data: [0], // Valeur zéro pour un graphique vide
        backgroundColor: '#cccccc', // Couleur neutre
        borderRadius: 4
      }]
    },
    options: {
      ...noLegend,
      plugins: {
        ...noLegend.plugins,
        datalabels: {
          color: 'var(--text-color)',
          formatter: () => 'Aucune donnée disponible'
        }
      },
      scales: {
        x: { display: false }, // Cacher l'axe X
        y: { display: false }  // Cacher l'axe Y
      }
    }
  });
}

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
      plugins: {
        legend: { display: false }
      },
      scales: {
        x: {
          type: 'category',
          title: {
            display: true,
            text: '',
            color: 'var(--text-color)'
          },
          ticks: {
            color: 'var(--text-color)'
          }
        },
        y: {
          ticks: {
            color: 'var(--text-color)'
          }
        }
      }
    }
  });
} else {
  // Afficher un graphique vide avec un message si aucune donnée
  new Chart(document.getElementById('caChart'), {
    type: 'bar',
    data: {
      labels: ['Aucune donnée'],
      datasets: [{
        data: [0],
        backgroundColor: '#cccccc',
        borderRadius: 4
      }]
    },
    options: {
      ...noLegend,
      plugins: {
        ...noLegend.plugins,
        datalabels: {
          color: 'var(--text-color)',
          formatter: () => 'Aucune donnée disponible'
        }
      },
      scales: {
        x: { display: false },
        y: { display: false }
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
       datalabels:{color:'#000000',font:{size:14},
         formatter:(v,ctx)=>ctx.chart.data.labels[ctx.dataIndex]+' '+(v*100/total).toFixed(0)+'%'}
     }}
 });
} else {
  // Afficher un graphique vide avec un message si aucune donnée
  new Chart(document.getElementById('genderChart'), {
    type: 'doughnut',
    data: {
      labels: ['Aucune donnée'],
      datasets: [{
        data: [1], // Une seule tranche pour représenter l'absence de données
        backgroundColor: ['#cccccc'],
        borderWidth: 0
      }]
    },
    options: {
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        datalabels: {
          color: 'var(--text-color)',
          formatter: () => 'Aucune donnée disponible'
        }
      }
    }
  });
}

/* Âge */
if(CHARTS.age_labels?.length){
 new Chart(document.getElementById('ageChart'),
   {type:'bar',data:{labels:CHARTS.age_labels,
                     datasets:[{data:CHARTS.age_values,backgroundColor:COLORS.age,borderRadius:4}]},
    options:noLegend});
} else {
  // Afficher un graphique vide avec un message si aucune donnée
  new Chart(document.getElementById('ageChart'), {
    type: 'bar',
    data: {
      labels: ['Aucune donnée'],
      datasets: [{
        data: [0],
        backgroundColor: '#cccccc',
        borderRadius: 4
      }]
    },
    options: {
      ...noLegend,
      plugins: {
        ...noLegend.plugins,
        datalabels: {
          color: 'var(--text-color)',
          formatter: () => 'Aucune donnée disponible'
        }
      },
      scales: {
        x: { display: false },
        y: { display: false }
      }
    }
  });
}
</script>
<div class="modal fade" id="dataAlertModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content">
      <div class="modal-header bg-warning">
        <h5 class="modal-title">
          <i class="fas fa-database me-2"></i>Données manquantes
        </h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        <div class="d-flex align-items-center gap-3">
          <i class="fas fa-exclamation-triangle text-warning fs-2"></i>
          <div>
            <p class="mb-0">Impossible de générer le rapport car :</p>
            <ul class="mt-2">
              <li>Aucune consultation enregistrée</li>
              <li>Aucun patient répertorié</li>
              <li>Aucune facture disponible</li>
            </ul>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Fermer</button>
      </div>
    </div>
  </div>
</div>

<style>
  /* Styles pour le modal d'alerte */
  #dataAlertModal .modal-content {
    border: 2px solid var(--warning-color);
    border-radius: var(--border-radius-lg);
    box-shadow: 0 0 15px rgba(255, 193, 7, 0.3);
  }

  #dataAlertModal .modal-header {
    border-bottom: 2px dashed var(--warning-color);
  }

  #dataAlertModal ul {
    list-style: none;
    padding-left: 1.5rem;
  }

  #dataAlertModal ul li {
    position: relative;
    padding-left: 1.5rem;
    margin-bottom: 0.5rem;
  }

  #dataAlertModal ul li::before {
    content: "❌";
    position: absolute;
    left: 0;
  }
</style>

<script>
document.addEventListener('DOMContentLoaded', function() {
    // Check for flashed messages and show modal if a warning is present
    const urlParams = new URLSearchParams(window.location.search);
    const hasWarning = urlParams.get('warning') === 'true'; // Assuming you pass a 'warning' param from Flask

    // Or, if you have a way to check flashed messages directly in JS (e.g., via a hidden element or JSON endpoint)
    // For now, let's assume a simple check or a direct call if Flask flashes a warning
    // This part would ideally be driven by a server-side check of flashed messages.
    // As a placeholder, let's use a simple condition.
    // In a real Flask app, you'd render this script conditionally based on get_flashed_messages()
    const flashedMessagesDiv = document.querySelector('.alert.alert-warning');
    if (flashedMessagesDiv) { // If a warning alert is rendered on the page
        new bootstrap.Modal(document.getElementById('dataAlertModal')).show();
    }
});
</script>
</body>
</html>
"""