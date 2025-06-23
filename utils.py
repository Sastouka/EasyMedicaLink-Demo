# utils.py
# ---------------------------------------------------------------------------
#  Tous les utilitaires, constantes et fonctions partagées
#  (aucune route Flask ni template HTML ici)
#  Compatible Python 3.9 : pas d’opérateur "|" dans les annotations
# ---------------------------------------------------------------------------

import os, sys, platform, json, uuid, hashlib, re, copy, base64, io, subprocess, socket, requests
from datetime import datetime, date, timedelta
from typing import Optional
import pandas as pd
from werkzeug.utils import secure_filename # Importation ajoutée pour être explicite

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A5, A4
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
    Table, TableStyle, PageBreak, ListFlowable, SimpleDocTemplate
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY
from PyPDF2 import PdfReader, PdfWriter
from PIL import Image, ImageDraw
from textwrap import dedent

# ---------------------------------------------------------------------------
#  1. Constantes globales & répertoires
# ---------------------------------------------------------------------------

# ─── Chemin de base de l'application ───────────────────────────────────────
if getattr(sys, "frozen", False):
    # Mode exécutable : on se place dans le dossier où se trouve le .exe
    application_path = os.path.dirname(sys.executable)
else:
    # Mode développement : on se place dans le dossier du script .py
    application_path = os.path.dirname(os.path.abspath(__file__))

# Global variable to store the dynamic base directory
DYNAMIC_BASE_DIR: Optional[str] = None
# Global variable for admin's email
ADMIN_EMAIL: Optional[str] = None

# These will be set dynamically based on ADMIN_EMAIL
EXCEL_FOLDER: Optional[str] = None
EXCEL_FILE_PATH: Optional[str] = None
CONSULT_FILE_PATH: Optional[str] = None
PDF_FOLDER: Optional[str] = None
CONFIG_FOLDER: Optional[str] = None
BACKGROUND_FOLDER: Optional[str] = None
CONFIG_FILE: Optional[str] = None
STORAGE_CONFIG_FILE: Optional[str] = None
PATIENT_BASE_FILE: Optional[str] = None
SQLITE_DB_PATH: Optional[str] = None

# This remains static as per your requirement
LISTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Liste_Medications_Analyses_Radiologies.xlsx')

def set_dynamic_base_dir(admin_email: str):
    global DYNAMIC_BASE_DIR, ADMIN_EMAIL
    global EXCEL_FOLDER, EXCEL_FILE_PATH, CONSULT_FILE_PATH, PDF_FOLDER, CONFIG_FOLDER, BACKGROUND_FOLDER
    global CONFIG_FILE, STORAGE_CONFIG_FILE, PATIENT_BASE_FILE, SQLITE_DB_PATH

    ADMIN_EMAIL = admin_email.lower().replace('@', '_at_').replace('.', '_dot_') # Sanitize email for folder name

    DYNAMIC_BASE_DIR = os.path.join(application_path, "MEDICALINK_DATA", ADMIN_EMAIL)
    os.makedirs(DYNAMIC_BASE_DIR, exist_ok=True)

    EXCEL_FOLDER      = os.path.join(DYNAMIC_BASE_DIR, "Excel")
    EXCEL_FILE_PATH = os.path.join(EXCEL_FOLDER, "ConsultationData.xlsx")
    CONSULT_FILE_PATH = EXCEL_FILE_PATH
    PDF_FOLDER        = os.path.join(DYNAMIC_BASE_DIR, "PDF")
    CONFIG_FOLDER     = os.path.join(DYNAMIC_BASE_DIR, "Config")
    BACKGROUND_FOLDER = os.path.join(DYNAMIC_BASE_DIR, "Background")
    SQLITE_DB_PATH = os.path.join(DYNAMIC_BASE_DIR, "database.db") # New SQLite DB path

    for _dir in (DYNAMIC_BASE_DIR, EXCEL_FOLDER, PDF_FOLDER, CONFIG_FOLDER, BACKGROUND_FOLDER):
        os.makedirs(_dir, exist_ok=True)

    CONFIG_FILE         = os.path.join(CONFIG_FOLDER, "config.json")
    STORAGE_CONFIG_FILE = os.path.join(CONFIG_FOLDER, "storage_config.json")
    PATIENT_BASE_FILE = os.path.join(EXCEL_FOLDER, "info_Base_patient.xlsx")
    
    print(f"DEBUG: Dynamic base directory set to: {DYNAMIC_BASE_DIR}")
    print(f"DEBUG: SQLite DB path set to: {SQLITE_DB_PATH}")


# The following variables now depend on set_dynamic_base_dir being called.
# They are initialized to None and will be set when an admin logs in or is identified.
# For initial load, we might need a default or a way to ensure they are set before use.


LOCAL_IP = socket.gethostbyname(socket.gethostname())

background_file: Optional[str] = None # This global variable needs to be updated

def init_app(app):
    """Initialisation de l'application Flask avec les valeurs du fichier de configuration."""
    global background_file # Declare global to modify it

    # Ensure set_dynamic_base_dir has been called and DYNAMIC_BASE_DIR is set
    if ADMIN_EMAIL is None:
        # Fallback or error if ADMIN_EMAIL is not set before init_app
        # For a practical app, this means login/session management needs to happen earlier.
        print("WARNING: ADMIN_EMAIL not set. Using a default for initialization.")
        set_dynamic_base_dir("default_admin@example.com") # Or raise an error

    config = load_config()
    app.config.update(config)

    # When loading config, update the global background_file path
    # If the path in config is relative, make it absolute by joining with BACKGROUND_FOLDER
    configured_bg_path = config.get("background_file_path")
    if configured_bg_path and BACKGROUND_FOLDER:
        background_file = os.path.join(BACKGROUND_FOLDER, configured_bg_path)
        if not os.path.exists(background_file):
            print(f"WARNING: Configured background file not found at {background_file}. Resetting to None.")
            background_file = None # In case the configured file doesn't exist anymore
    else:
        background_file = None # No background configured or BACKGROUND_FOLDER not set yet
    print(f"DEBUG (utils.py - init_app): Global background_file set to: {background_file}")


# ---------------------------------------------------------------------------
# 4. Configuration & listes par défaut
# ---------------------------------------------------------------------------
def load_config() -> dict:
    if CONFIG_FILE is None:
        # This means set_dynamic_base_dir was not called. Handle accordingly.
        print("ERROR: CONFIG_FILE path is not set. Cannot load config.")
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_config(cfg: dict):
    if CONFIG_FILE is None:
        print("ERROR: CONFIG_FILE path is not set. Cannot save config.")
        return
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def extract_rest_duration(text: str) -> str:
    placeholders = ["[Nom du Médecin]", "[Nom du Patient]", "[Lieu]", "[Date]", "[X]"]
    for p in placeholders:
        text = text.replace(p, "")
    match = re.search(r"durée de\s*(\d+)\s*jours", text, re.IGNORECASE)
    return match.group(1) if match else ""

default_medications_options = [
    "Paracétamol (500 mg, 3 fois/jour, durant 5 jours)",
    "Ibuprofène (200 mg, 3 fois/jour, durant 1 semaine)",
    "Amoxicilline (500 mg, 3 fois/jour, durant 10 jours)",
    "Azithromycine (500 mg, 1 fois/jour, durant 3 jours)",
    "Oméprazole (20 mg, 1 fois/jour, durant 4 semaines)",
    "Salbutamol inhalé (2 bouffées, 3 fois/jour, au besoin)",
    "Metformine (500 mg, 2 fois/jour, en continu)",
    "Lisinopril (10 mg, 1 fois/jour, en continu)",
    "Simvastatine (20 mg, 1 fois/jour, le soir)",
    "Furosémide (40 mg, 1 fois/jour, au besoin)",
    "Acide acétylsalicylique (100 mg, 1 fois/jour, en continu)",
    "Warfarine (selon INR, en continu)",
    "Insuline rapide (doses variables, avant les repas)",
    "Levothyroxine (50 µg, 1 fois/jour, le matin)",
    "Diclofénac (50 mg, 3 fois/jour, durant 5 jours)"
]

default_analyses_options = [
    "Glycémie à jeun",
    "Hémogramme complet",
    "Bilan hépatique",
    "Bilan rénal",
    "TSH",
    "CRP",
    "Ionogramme sanguin",
    "Analyse d'urine",
    "Profil lipidique",
    "Test de grossesse",
    "Hémoglobine glyquée (HbA1c)",
    "Temps de prothrombine (TP/INR)",
    "Bilan martial (fer sérique, ferritine)",
    "Groupage sanguin ABO et Rh",
    "Sérologie hépatite B et C"
]

default_radiologies_options = [
    "Radiographie thoracique",
    "Échographie abdominale",
    "IRM cérébrale",
    "Scanner thoracique",
    "Échographie cardiaque",
    "Radiographie du genou",
    "IRM de la colonne vertébrale",
    "Scanner abdominal",
    "Mammographie",
    "Échographie pelvienne",
    "Radiographie du poignet",
    "Échographie thyroïdienne",
    "IRM du genou",
    "Scanner cérébral",
    "Radiographie du rachis cervical"
]

certificate_categories = {
    "Attestation de bonne santé": "Je soussigné(e) [Nom du Médecin], Docteur en médecine, atteste par la présente que [Nom du Patient], âgé(e) de [Âge], est en bonne santé générale. Après examen clinique, aucune condition médicale ne contre-indique sa participation à [activité]. Ce certificat est délivré à la demande du patient pour servir et valoir ce que de droit.",
    "Certificat de maladie": "Je soussigné(e) [Nom du Médecin], certifie que [Nom du Patient], âgé(e) de [Âge], présente des symptômes compatibles avec [diagnostic]. En conséquence, il/elle nécessite un repos médical et est dispensé(e) de toute activité professionnelle ou scolaire pour une durée de [X] jours à compter du [Date].",
    "Certificat de grossesse": "Je soussigné(e) [Nom du Médecin], certifie que [Nom du Patient], âgée(e) de [Âge], est actuellement enceinte de [X] semaines. Cet état de grossesse a été confirmé par un examen médical réalisé le [Date], et le suivi se poursuit normalement.",
    "Certificat de vaccination": "Je soussigné(e) [Nom du Médecin], certifie que [Nom du Patient], âgé(e) de [Âge], a reçu les vaccins suivants conformément aux recommandations de santé publique : [Liste des vaccins avec dates]. Ce certificat est délivré pour attester de l'état vaccinal du patient.",
    "Certificat d'inaptitude sportive": "Je soussigné(e) [Nom du Médecin], après avoir examiné [Nom du Patient], atteste que celui/celle-ci est temporairement inapte à pratiquer des activités sportives en raison de [raison médicale]. La durée de cette inaptitude est estimée à [X] semaines, sous réserve de réévaluation médicale.",
    "Certificat d'aptitude au sport": "Je soussigné(e) [Nom du Médecin], certifie que [Nom du Patient], après un examen physique complet, est en bonne condition physique et apte à pratiquer le sport suivant : [sport]. Aucun signe de contre-indication médicale n'a été détecté lors de la consultation.",
    "Certificat médical pour voyage": "Je soussigné(e) [Nom du Médecin], atteste que [Nom du Patient], âgé(e) de [Âge], est médicalement apte à entreprendre un voyage prévu du [Date de début] au [Date de fin]. Aucun problème de santé majeur n'a été identifié pouvant contre-indiquer le déplacement.",
    "Certificat d'arrêt de travail": "Je soussigné(e) [Nom du Médecin], certifie que [Nom du Patient], après consultation le [Date], nécessite un arrêt de travail d'une durée de [X] jours en raison de [motif médical]. Cet arrêt est nécessaire pour permettre au patient de récupérer de manière optimale.",
    "Certificat de reprise du travail": "Je soussigné(e) [Nom du Médecin], certifie que [Nom du Patient], ayant été en arrêt de travail pour [motif], est désormais apte à reprendre son activité professionnelle à compter du [Date]. Le patient ne présente plus de signes d'incapacité liés à la condition précédemment diagnostiquée.",
    "Certificat pour soins prolongés": "Je soussigné(e) [Nom du Médecin], atteste que [Nom du Patient] nécessite des soins médicaux prolongés pour le motif suivant : [raison]. Ces soins incluent [description des soins] et sont requis pour une période estimée de [X] semaines/mois].",
    "Certificat de visite médicale": "Je soussigné(e) [Nom du Médecin], atteste avoir examiné [Nom du Patient] lors d'une visite médicale effectuée le [Date]. Aucun problème de santé particulier n'a été détecté lors de cet examen, sauf mention contraire ci-dessous : [Observations supplémentaires].",
    "Certificat d'éducation physique": "Je soussigné(e) [Nom du Médecin], certifie que [Nom du Patient] est médicalement apte à participer aux activités d'éducation physique organisées par [Institution scolaire]. Aucun risque pour la santé n'a été identifié à ce jour.",
    "Certificat pour les assurances": "Je soussigné(e) [Nom du Médecin], atteste que [Nom du Patient], après un examen médical effectué le [Date], est en état de [décrire état de santé pertinent]. Ce certificat est délivré pour répondre à la demande de l’assureur concernant [motif].",
    "Certificat pour permis de conduire": "Je soussigné(e) [Nom du Médecin], certifie que [Nom du Patient] a subi un examen médical complet et est jugé(e) apte à conduire un véhicule. Aucun signe de trouble de la vision, de coordination ou de toute autre condition pouvant entraver la conduite n'a été détecté.",
    "Certificat de non-contagion": "Je soussigné(e) [Nom du Médecin], atteste que [Nom du Patient] ne présente aucun signe de maladie contagieuse à ce jour. Cet état de santé a été confirmé par un examen clinique et, le cas échéant, des tests complémentaires.",
    "Certificat pour compétition sportive": "Je soussigné(e) [Nom du Médecin], certifie que [Nom du Patient], après examen physique réalisé le [Date], est médicalement apte à participer à la compétition suivante : [compétition]. Aucun signe de contre-indication n'a été observé lors de l'évaluation.",
    "Certificat de consultation": "Je soussigné(e) [Nom du Médecin], atteste avoir consulté [Nom du Patient] le [Date] pour le motif suivant : [raison]. Un examen complet a été effectué et les recommandations nécessaires ont été fournies au patient.",
    "Certificat pour institutions scolaires": "Je soussigné(e) [Nom du Médecin], certifie que [Nom du Patient] est médicalement apte à reprendre les activités scolaires à compter du [Date]. Aucun problème de santé susceptible de gêner la participation aux cours n'a été relevé.",
    "Certificat de suivi médical": "Je soussigné(e) [Nom du Médecin], certifie que [Nom du Patient] est actuellement sous suivi médical régulier pour la gestion de [motif]. Le suivi inclut [description du traitement] et est prévu pour [durée estimée].",
    "Certificat de confirmation de traitement": "Je soussigné(e) [Nom du Médecin], confirme que [Nom du Patient] est actuellement sous traitement pour [diagnostic]. Le traitement a débuté le [Date] et comprend [détails du traitement], visant à [objectif du traitement].",
    "Certificat d'incapacité partielle": "Je soussigné(e) [Nom du Médecin], atteste que [Nom du Patient], âgé(e) de [Âge], présente une incapacité partielle en raison de [condition médicale], nécessitant des aménagements au travail ou à l'école pendant [durée].",
    "Certificat de soins palliatifs": "Je soussigné(e) [Nom du Médecin], certifie que [Nom du Patient], âgé(e) de [Âge], bénéficie de soins palliatifs pour [motif]. Ces soins ont pour objectif de soulager les symptômes et d'améliorer la qualité de vie.",
    "Certificat de guérison": "Je soussigné(e) [Nom du Médecin], atteste que [Nom du Patient] est guéri(e) de [condition] et est désormais en mesure de reprendre ses activités sans restriction médicale.",
    "Certificat de non-contraindication au jeûne": "Je soussigné(e) [Nom du Médecin], certifie que [Nom du Patient], âgé(e) de [Âge], ne présente aucune contre-indication médicale au jeûne durant [période ou événement spécifique].",
    "Certificat de non-consommation d'alcool": "Je soussigné(e) [Nom du Médecin], certifie que [Nom du Patient] a été examiné(e) et ne présente aucun signe de consommation d'alcool récent. Ce certificat est délivré pour [motif].",
    "Certificat de handicap": "Je soussigné(e) [Nom du Médecin], certifie que [Nom du Patient] présente un handicap lié à [type de handicap] nécessitant des aménagements spécifiques dans son environnement de travail ou scolaire.",
    "Certificat de non-fumeur": "Je soussigné(e) [Nom du Médecin], atteste que [Nom du Patient] est non-fumeur et ne présente aucun signe de consommation récente de tabac. Ce certificat est délivré pour des raisons administratives ou de sécurité.",
    "Certificat d'aptitude pour adoption": "Je soussigné(e) [Nom du Médecin], atteste que [Nom du Patient], âgé(e) de [Âge], présente les conditions physiques et psychologiques favorables pour entamer une démarche d'adoption.",
    "Certificat d'aptitude au travail en hauteur": "Je soussigné(e) [Nom du Médecin], certifie que [Nom du Patient], âgé(e) de [Âge], est médicalement apte à travailler en hauteur. Aucun signe de vertige, trouble de l'équilibre ou autre condition médicale contre-indiquant ce type d'activité n'a été observé lors de l'examen.",
    "Certificat pour greffe d'organe": "Je soussigné(e) [Nom du Médecin], atteste que [Nom du Patient] est en état de recevoir un organe pour une greffe. Ce certificat est délivré pour la validation médicale du processus de transplantation pour [type d'organe].",
    "Certificat de fin de traitement": "Je soussigné(e) [Nom du Médecin], atteste que [Nom du Patient], ayant suivi un traitement pour [diagnostic], a terminé le processus de soins et ne nécessite plus d'interventions médicales pour cette condition.",
    "Certificat de restriction alimentaire": "Je soussigné(e) [Nom du Médecin], atteste que [Nom du Patient], en raison de [diagnostic], doit suivre une restriction alimentaire spécifique incluant : [détails des restrictions].",
    "Certificat d'aptitude pour la plongée sous-marine": "Je soussigné(e) [Nom du Médecin], certifie que [Nom du Patient], âgé(e) de [Âge], est apte à pratiquer la plongée sous-marine après évaluation médicale. Aucun signe de contre-indication n'a été détecté pour cette activité.",
    "Certificat de transport sanitaire": "Je soussigné(e) [Nom du Médecin], atteste que [Nom du Patient], âgé(e) de [Âge], nécessite un transport sanitaire pour des raisons de santé spécifiques. Ce transport est nécessaire pour des déplacements vers [destination] à des fins de suivi médical.",
    "Certificat d'aptitude au travail de nuit": "Je soussigné(e) [Nom du Médecin], certifie que [Nom du Patient], après examen, est apte à travailler de nuit sans contre-indications médicales détectées.",
    "Certificat de non-allergie": "Je soussigné(e) [Nom du Médecin], atteste que [Nom du Patient], après examen, ne présente aucune allergie connue aux substances suivantes : [liste des substances]. Ce certificat est délivré pour des raisons administratives ou de sécurité.",
    "Certificat d'aptitude pour opérations chirurgicales": "Je soussigné(e) [Nom du Médecin], certifie que [Nom du Patient], âgé(e) de [Âge], est médicalement apte pour subir une opération chirurgicale pour [type d'opération]. Un bilan pré-opératoire a été réalisé pour valider cette aptitude.",
    "Certificat d'aptitude pour formation militaire": "Je soussigné(e) [Nom du Médecin], atteste que [Nom du Patient], après un examen médical, est en condition physique pour participer à une formation militaire et ne présente aucun trouble incompatible avec ce type d'entraînement.",
    "Certificat d'aptitude pour sports extrêmes": "Je soussigné(e) [Nom du Médecin], certifie que [Nom du Patient], après un examen approfondi, est apte à pratiquer les sports extrêmes suivants : [liste des sports]. Aucun problème de santé n'a été détecté pour interdire cette pratique.",
    "Certificat d'invalidité temporaire": "Je soussigné(e) [Nom du Médecin], atteste que [Nom du Patient] est temporairement en situation d'invalidité due à [motif médical] et requiert une assistance pour ses activités quotidiennes pour une durée de [durée].",
    "Certificat de soins dentaires": "Je soussigné(e) [Nom du Médecin], atteste que [Nom du Patient] suit actuellement des soins dentaires pour [motif], comprenant [détails des soins]. Un suivi est recommandé jusqu'à la résolution complète de la condition.",
    "Certificat de soins orthopédiques": "Je soussigné(e) [Nom du Médecin], atteste que [Nom du Patient] est en cours de traitement orthopédique pour [condition], incluant des séances de rééducation pour une période estimée de [durée].",
    "Certificat de non-consommation de stupéfiants": "Je soussigné(e) [Nom du Médecin], atteste que [Nom du Patient] ne présente aucun signe de consommation récente de substances stupéfiantes, sur la base d'un examen clinique et de tests.",
    "Certificat pour activités à risque": "Je soussigné(e) [Nom du Médecin], certifie que [Nom du Patient], âgé(e) de [Âge], est médicalement apte à participer aux activités suivantes à risque : [liste des activités]. Aucun signe de contre-indication n'a été détecté.",
    "Certificat pour maternité à risque": "Je soussigné(e) [Nom du Médecin], atteste que [Nom du Patient], enceinte de [X] semaines, présente un risque médical nécessitant des soins supplémentaires et des restrictions spécifiques pour le bon déroulement de sa grossesse.",
    "Certificat pour soins psychiatriques": "Je soussigné(e) [Nom du Médecin], atteste que [Nom du Patient] est actuellement en traitement psychiatrique pour [diagnostic]. Le suivi inclut [description du traitement] et est prévu pour [durée estimée].",
    "Certificat de décès": "Je soussigné(e) [Nom du Médecin], certifie que [Nom du Patient] est décédé(e) le [Date de décès]. Ce certificat est délivré à des fins légales pour l'enregistrement du décès auprès des autorités compétentes.",
    "Certificat de non-aptitude à la baignade": "Je soussigné(e) [Nom du Médecin], atteste que [Nom du Patient], âgé(e) de [Âge], ne peut pas pratiquer la baignade en raison de [raison médicale]. Cette restriction est valable jusqu'à nouvel ordre médical."
}

default_certificate_text = """Je soussigné(e) [Nom du Médecin], certifie que le patient [Nom du Patient], né(e) le [Date de naissance], présente un état de santé nécessitant un arrêt de travail et un repos médical d'une durée de [X] jours à compter du [Date]. Ce repos est nécessaire pour permettre au patient de récupérer pleinement de [préciser la nature de l'affection ou des symptômes].

Fait à [Lieu], le [Date]."""

# ---------------------------------------------------------------------------
# 5. Gestion des patients (Excel)
# ---------------------------------------------------------------------------
patient_ids, patient_names = [], []
patient_id_to_name = {} # Nom Complet
patient_name_to_id = {} # Nom Complet -> ID
patient_id_to_age = {}
patient_id_to_phone = {}
patient_id_to_antecedents = {}
patient_id_to_dob = {}
patient_id_to_gender = {}
patient_id_to_nom = {}    # Nom de famille
patient_id_to_prenom = {} # Prénom

def load_patient_data():
    global patient_ids, patient_names
    global patient_id_to_name, patient_name_to_id
    global patient_id_to_age, patient_id_to_phone, patient_id_to_antecedents
    global patient_id_to_dob, patient_id_to_gender
    global patient_id_to_nom, patient_id_to_prenom

    # Ensure dynamic paths are set before proceeding
    if EXCEL_FOLDER is None:
        print("ERROR: Dynamic base directory not set. Call set_dynamic_base_dir first.")
        return

    # Fichiers sources distincts
    # These paths are now global variables set by set_dynamic_base_dir
    # PATIENT_BASE_FILE = os.path.join(EXCEL_FOLDER, 'info_Base_patient.xlsx')
    # CONSULT_FILE_PATH = os.path.join(EXCEL_FOLDER, 'ConsultationData.xlsx')

    # Réinitialisation des variables globales
    def reset_globals():
        patient_ids.clear(); patient_names.clear()
        patient_id_to_name.clear(); patient_name_to_id.clear()
        patient_id_to_age.clear(); patient_id_to_phone.clear(); patient_id_to_antecedents.clear()
        patient_id_to_dob.clear(); patient_id_to_gender.clear()
        patient_id_to_nom.clear(); patient_id_to_prenom.clear()
        print("DEBUG: Toutes les données patient globales ont été réinitialisées.")

    # Toujours réinitialiser les globales au début de load_patient_data pour assurer un état propre
    reset_globals()

    # 1. Chargement des données de base patients (info_Base_patient.xlsx)
    if not os.path.exists(PATIENT_BASE_FILE):
        print(f"DEBUG: Fichier de base patient non trouvé: {PATIENT_BASE_FILE}. Les données patient ne seront pas chargées depuis ce fichier.")
    else:
        try:
            df_base = pd.read_excel(PATIENT_BASE_FILE, sheet_name=0, dtype=str).fillna('')
            print(f"DEBUG: df_base (info_Base_patient.xlsx) chargé avec {len(df_base)} lignes.")
            print(f"DEBUG: Colonnes de df_base avant renommage: {df_base.columns.tolist()}")

            # Définir le mappage des colonnes attendues dans info_Base_patient.xlsx vers les noms internes
            column_mapping = {
                'ID': 'patient_id',
                'Nom': 'nom', # Nom de famille
                'Prenom': 'prenom', # Prénom
                'DateNaissance': 'date_of_birth',
                'Sexe': 'gender',
                'Âge': 'age',
                'Téléphone': 'patient_phone',
                'Antécédents': 'antecedents'
            }
            
            # Renommer les colonnes pour qu'elles correspondent aux noms internes
            df_base_renamed = df_base.rename(columns=column_mapping)
            print(f"DEBUG: Colonnes de df_base après renommage: {df_base_renamed.columns.tolist()}")
            
            # Vérification des colonnes requises APRES renommage
            # patient_name sera construit, donc pas une colonne requise directe ici
            required_internal_columns = set(column_mapping.values())
            missing_columns = required_internal_columns.difference(df_base_renamed.columns)
            if missing_columns:
                print(f"ATTENTION: Colonnes internes requises manquantes dans info_Base_patient.xlsx: {missing_columns}. Certaines données patient pourraient être incomplètes.")
            
            # Nettoyage et population des mappings globaux
            for _, row in df_base_renamed.iterrows():
                pid = str(row['patient_id']).strip() if 'patient_id' in row else None
                if pid:
                    nom = str(row.get('nom', '')).strip()
                    prenom = str(row.get('prenom', '')).strip()
                    full_name = f"{nom} {prenom}".strip()

                    patient_id_to_name[pid] = full_name
                    patient_id_to_nom[pid] = nom
                    patient_id_to_prenom[pid] = prenom
                    patient_id_to_age[pid] = str(row.get('age', '')).strip()
                    patient_id_to_phone[pid] = str(row.get('patient_phone', '')).strip()
                    patient_id_to_antecedents[pid] = str(row.get('antecedents', '')).strip()
                    patient_id_to_dob[pid] = str(row.get('date_of_birth', '')).strip()
                    patient_id_to_gender[pid] = str(row.get('gender', '')).strip()

                    if pid not in patient_ids:
                        patient_ids.append(pid)
                    if full_name and full_name not in patient_names:
                        patient_names.append(full_name)
                    if full_name: # Assurez-vous que le nom complet n'est pas vide
                        patient_name_to_id[full_name] = pid # Mappage Nom Complet -> ID

            print(f"DEBUG: Données chargées depuis info_Base_patient.xlsx.")
            print(f"DEBUG: patient_id_to_name (Nom Complet) ex: {list(patient_id_to_name.items())[:2]}")
            print(f"DEBUG: patient_id_to_nom (Nom) ex: {list(patient_id_to_nom.items())[:2]}")
            print(f"DEBUG: patient_id_to_prenom (Prénom) ex: {list(patient_id_to_prenom.items())[:2]}")

        except Exception as e:
            print(f"ERREUR: Erreur de chargement ou de traitement des données patient depuis info_Base_patient.xlsx: {str(e)}")

    # 2. Chargement et fusion des données de suivi (ConsultationData.xlsx)
    if os.path.exists(CONSULT_FILE_PATH):
        try:
            df_consult = pd.read_excel(CONSULT_FILE_PATH, sheet_name=0, dtype=str).fillna('')
            print(f"DEBUG: df_consult (ConsultationData.xlsx) chargé avec {len(df_consult)} lignes.")
            print(f"DEBUG: Colonnes de df_consult: {df_consult.columns.tolist()}")

            if 'consultation_date' in df_consult.columns:
                df_consult['consultation_date'] = pd.to_datetime(df_consult['consultation_date'].astype(str).str[:10], errors='coerce')
                df_consult = df_consult.dropna(subset=['consultation_date'])
                df_consult = df_consult.sort_values(by='consultation_date')
                consult_data_latest = df_consult.groupby('patient_id').last().to_dict(orient='index')
                print(f"DEBUG: consult_data_latest chargé avec {len(consult_data_latest)} entrées pour la fusion.")

                for pid, consult_info in consult_data_latest.items():
                    pid = str(pid).strip() # Assurez-vous que l'ID est une chaîne propre

                    # Mettre à jour/ajouter les données, en donnant la priorité aux données existantes
                    # de info_Base_patient si elles sont plus complètes.
                    # Sinon, utiliser les données de la dernière consultation.

                    # Nom et Prénom (séparés)
                    consult_nom = str(consult_info.get('nom', '')).strip()
                    consult_prenom = str(consult_info.get('prenom', '')).strip()
                    
                    patient_id_to_nom[pid] = patient_id_to_nom.get(pid) or consult_nom
                    patient_id_to_prenom[pid] = patient_id_to_prenom.get(pid) or consult_prenom
                    
                    # Nom Complet (patient_name)
                    derived_full_name_from_consult = f"{patient_id_to_nom[pid]} {patient_id_to_prenom[pid]}".strip()
                    patient_id_to_name[pid] = patient_id_to_name.get(pid) or derived_full_name_from_consult or str(consult_info.get('patient_name', '')).strip()

                    # Autres champs
                    patient_id_to_age[pid] = patient_id_to_age.get(pid) or str(consult_info.get('age', '')).strip()
                    patient_id_to_phone[pid] = patient_id_to_phone.get(pid) or str(consult_info.get('patient_phone', '')).strip()
                    patient_id_to_antecedents[pid] = patient_id_to_antecedents.get(pid) or str(consult_info.get('antecedents', '')).strip()
                    patient_id_to_dob[pid] = patient_id_to_dob.get(pid) or str(consult_info.get('date_of_birth', '')).strip()
                    patient_id_to_gender[pid] = patient_id_to_gender.get(pid) or str(consult_info.get('gender', '')).strip()

                    # Ajouter l'ID et le nom complet aux listes si ce sont de nouveaux patients
                    if pid not in patient_ids:
                        patient_ids.append(pid)
                    if patient_id_to_name.get(pid) and patient_id_to_name[pid] not in patient_names:
                        patient_names.append(patient_id_to_name[pid])
                    if patient_id_to_name.get(pid): # Mappage Nom Complet -> ID
                        patient_name_to_id[patient_id_to_name[pid]] = pid

            else:
                print("DEBUG: La colonne 'consultation_date' est manquante dans ConsultationData.xlsx. Impossible de trier par date.")

        except Exception as e:
            print(f"ERREUR: Erreur lors du chargement ou du traitement de ConsultationData.xlsx: {str(e)}")
    else:
        print(f"DEBUG: Fichier de consultation non trouvé: {CONSULT_FILE_PATH}. Les données de consultation ne seront pas fusionnées.")

    # Finalisation des listes et mappings après toutes les fusions
    patient_ids = sorted(list(set(patient_ids)), key=str.lower)
    patient_names = sorted(list(set(patient_names)), key=str.lower)
    # Reconstruire patient_name_to_id pour s'assurer qu'il est cohérent avec patient_id_to_name
    patient_name_to_id.clear()
    for pid, name in patient_id_to_name.items():
        if name:
            patient_name_to_id[name] = pid

    print(f"DEBUG: patient_ids finaux chargés: {patient_ids[:5] if patient_ids else 'Vide'}...")
    print(f"DEBUG: patient_names finaux chargés: {patient_names[:5] if patient_names else 'Vide'}...")
    print(f"DEBUG: patient_id_to_name final (exemples): {list(patient_id_to_name.items())[:2] if patient_id_to_name else 'Vide'}...")
    print(f"DEBUG: patient_id_to_nom final (exemples): {list(patient_id_to_nom.items())[:2] if patient_id_to_nom else 'Vide'}...")
    print(f"DEBUG: patient_id_to_prenom final (exemples): {list(patient_id_to_prenom.items())[:2] if patient_id_to_prenom else 'Vide'}...")


# Do NOT call load_patient_data() here anymore directly.
# It should be called after `set_dynamic_base_dir` has been invoked
# (e.g., after an admin logs in and their email is known).
# ---------------------------------------------------------------------------
# 6. PDF : arrière plan, génération & fusion
# ---------------------------------------------------------------------------
def apply_background(pdf_canvas, width, height):
    if background_file and os.path.exists(background_file):
        if background_file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
            try:
                pdf_canvas.drawImage(background_file, 0, 0, width=width, height=height)
            except Exception:
                pass

def merge_with_background_pdf(foreground_path: str):
    if not (background_file and os.path.exists(background_file) and background_file.lower().endswith('.pdf')):
        return
    bg_reader = PdfReader(background_file)
    fg_reader = PdfReader(foreground_path)
    writer = PdfWriter()
    for i in range(len(fg_reader.pages)):
        fg_page = fg_reader.pages[i]
        bg_page = copy.deepcopy(bg_reader.pages[i] if i < len(bg_reader.pages) else bg_reader.pages[-1])
        bg_page.merge_page(fg_page)
        writer.add_page(bg_page)
    with open(foreground_path, "wb") as f:
        writer.write(f)

def generate_pdf_file(save_path: str, form_data: dict,
                      medication_list: list, analyses_list: list, radiologies_list: list):
    """Génère un PDF de consultation + ordonnance + certificat."""
    # Récupération des champs
    doctor_name   = form_data.get("doctor_name","").strip()
    patient_name  = form_data.get("patient_name","").strip()
    age           = form_data.get("patient_age","").strip()
    location      = form_data.get("location","").strip()
    date_of_birth = form_data.get("date_of_birth","").strip()
    gender        = form_data.get("gender","").strip()
    computed_age  = age
    if date_of_birth:
        try:
            birth = datetime.strptime(date_of_birth, '%Y-%m-%d')
            now   = datetime.now()
            years = now.year - birth.year - ((now.month, now.day) < (birth.month, birth.day))
            months= (now.month - birth.month) % 12
            computed_age = f"{years} ans {months} mois" if years else f"{months} mois"
        except Exception:
            computed_age = age

    clinical_signs      = form_data.get("clinical_signs","").strip()
    bp                  = form_data.get("bp","").strip()
    temperature         = form_data.get("temperature","").strip()
    heart_rate          = form_data.get("heart_rate","").strip()
    respiratory_rate    = form_data.get("respiratory_rate","").strip()
    diagnosis           = form_data.get("diagnosis","").strip()
    certificate_content = form_data.get("certificate_content","").strip()
    include_certificate = form_data.get("include_certificate","off") == "on"
    date_str            = datetime.now().strftime('%d/%m/%Y')

    # Initialisation du canvas
    c = canvas.Canvas(save_path, pagesize=A5)
    width, height = A5
    left_margin, header_margin, footer_margin = 56.7, 130, 56.7
    max_line_width = width - 2*left_margin

    # Arrière plan image
    if background_file and background_file.lower().endswith(('.png','.jpg','.jpeg','.gif','.bmp')):
        apply_background(c, width, height)

    # Fonctions internes
    def draw_header(pdf, title):
        pdf.setFont("Helvetica", 10)
        pdf.drawCentredString(width/2, height-header_margin, f"{location}, le {date_str}")
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawCentredString(width/2, height-header_margin-25, title)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(left_margin, height-header_margin-50, "Médecin :")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(left_margin+50, height-header_margin-50, doctor_name)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(left_margin, height-header_margin-70, "Patient :")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(left_margin+50, height-header_margin-70, patient_name)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(left_margin, height-header_margin-90, "Sexe :")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(left_margin+50, height-header_margin-90, gender)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(left_margin, height-header_margin-110, "Âge :")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(left_margin+50, height-header_margin-110, computed_age)

    def justify_text(pdf, text, max_w, y_pos, x_left, foot, h):
        paragraphs = text.splitlines()
        for para in paragraphs:
            lines, current = [], ""
            for word in para.split():
                test = f"{current} {word}".strip()
                if pdf.stringWidth(test, "Helvetica", 10) <= max_w:
                    current = test
                else:
                    lines.append(current)
                    current = word
            lines.append(current)
            for line in lines:
                lw = pdf.stringWidth(line, "Helvetica", 10)
                pdf.drawString((max_w - lw)/2 + x_left, y_pos, line)
                y_pos -= 15
                if y_pos < foot:
                    pdf.showPage()
                    if background_file and background_file.lower().endswith(('.png','.jpg','.jpeg','.gif','.bmp')):
                        apply_background(pdf, width, h)
                    draw_header(pdf, "Certificat Médical")
                    pdf.setFont("Helvetica",10)
                    y_pos = h - header_margin - 130
        return y_pos

    def draw_signature(pdf, y_pos):
        y_pos -= 30
        pdf.setFont("Helvetica", 12)
        pdf.drawCentredString(width/2, y_pos, "Signature")
        return y_pos

    def draw_list(title, items, y_pos, pdf, x_left, foot, h):
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(x_left, y_pos, title)
        y_pos -= 20
        pdf.setFont("Helvetica", 10)
        max_w = 300
        for idx, item in enumerate(items, 1):
            words, current = item.split(), f"{idx}. "
            for w in words:
                test = f"{current} {w}".strip()
                if pdf.stringWidth(test, "Helvetica", 10) <= max_w:
                    current = test
                else:
                    pdf.drawString(x_left, y_pos, current)
                    y_pos -= 20
                    if y_pos < foot:
                        pdf.showPage()
                        if background_file and background_file.lower().endswith(('.png','.jpg','.jpeg','.gif','.bmp')):
                            apply_background(pdf, width, h)
                        draw_header(pdf, title)
                        pdf.setFont("Helvetica",10)
                        y_pos = h - header_margin - 130
                    current = w
            pdf.drawString(x_left, y_pos, current)
            y_pos -= 20
            if y_pos < foot:
                pdf.showPage()
                if background_file and background_file.lower().endswith(('.png','.jpg','.jpeg','.gif','.bmp')):
                    apply_background(pdf, width, h)
                draw_header(pdf, title)
                pdf.setFont("Helvetica",10)
                y_pos = h - header_margin - 130
        return y_pos

    def draw_multiline(pdf, text, x_left, y_pos, max_w, foot, h):
        for line in text.split('\n'):
            if y_pos < foot:
                pdf.showPage()
                if background_file and background_file.lower().endswith(('.png','.jpg','.jpeg','.gif','.bmp')):
                    apply_background(pdf, width, h)
                draw_header(pdf, "Consultation")
                y_pos = h - header_margin - 130
            pdf.drawString(x_left, y_pos, line)
            y_pos -= 15
        return y_pos

    has_content = False
    def add_section(stitle, items):
        nonlocal has_content
        # Vérifie si la liste d'éléments n'est pas vide et contient au moins un élément non vide après nettoyage
        if items and any(item.strip() for item in items):
            if has_content:
                c.showPage()
                if background_file and background_file.lower().endswith(('.png','.jpg','.jpeg','.gif','.bmp')):
                    apply_background(c, width, height)
            draw_header(c, stitle)
            y = height - header_margin - 130
            # Filtre les éléments vides avant de les dessiner
            filtered_items = [item.strip() for item in items if item.strip()]
            y = draw_list(stitle, filtered_items, y, c, left_margin, footer_margin, height)
            draw_signature(c, y)
            has_content = True

    # Sections ordonnance/analyses/radiologies
    # Suppression de la logique qui ajoute des exemples si les listes sont vides
    add_section("Ordonnance Médicale", medication_list)
    add_section("Analyses", analyses_list)
    add_section("Radiologies", radiologies_list)

    # Section consultation
    if any([clinical_signs, bp, temperature, heart_rate, respiratory_rate, diagnosis]):
        if has_content:
            c.showPage()
            if background_file and background_file.lower().endswith(('.png','.jpg','.jpeg','.gif','.bmp')):
                apply_background(c, width, height)
        draw_header(c, "Consultation")
        y0 = height - header_margin - 130
        if clinical_signs: # Ajout de cette condition
            c.setFont("Helvetica-Bold",12); c.drawString(left_margin, y0, "Signes Cliniques / Motifs de Consultation :")
            y0 -= 20
            c.setFont("Helvetica",10)
            y0 = draw_multiline(c, clinical_signs, left_margin, y0, max_line_width, footer_margin, height)
        if any([bp, temperature, heart_rate, respiratory_rate]):
            c.setFont("Helvetica-Bold",12); c.drawString(left_margin, y0, "Paramètres Vitaux :")
            y0 -= 20
            c.setFont("Helvetica",10)
            if bp:
                c.drawString(left_margin+20, y0, f"Tension Artérielle : {bp} mmHg"); y0 -= 15
            if temperature:
                c.drawString(left_margin+20, y0, f"Température : {temperature} °C"); y0 -= 15
            if heart_rate:
                c.drawString(left_margin+20, y0, f"Fréquence Cardiaque : {heart_rate} bpm"); y0 -= 15
            if respiratory_rate:
                c.drawString(left_margin+20, y0, f"Fréquence Respiratoire : {respiratory_rate} rpm"); y0 -= 15
        if diagnosis: # Ajout de cette condition
            c.setFont("Helvetica-Bold",12); c.drawString(left_margin, y0, "Diagnostic :"); y0 -= 20
            c.setFont("Helvetica",10)
            y0 = draw_multiline(c, diagnosis, left_margin, y0, max_line_width, footer_margin, height)
        draw_signature(c, y0)
        has_content = True

    # Section certificat médical
    if include_certificate and certificate_content:
        if has_content:
            c.showPage()
            if background_file and background_file.lower().endswith(('.png','.jpg','.jpeg','.gif','.bmp')):
                apply_background(c, width, height)
        draw_header(c, "Certificat Médical")
        yc = height - header_margin - 130
        c.setFont("Helvetica-Bold",12); c.drawString(left_margin, yc, "Certificat Médical :"); yc -= 20
        c.setFont("Helvetica",10)
        cert = (certificate_content
                .replace("[Nom du Médecin]", doctor_name)
                .replace("[Nom du Patient]", patient_name)
                .replace("[Lieu]", location)
                .replace("[Date]", date_str)
                .replace("[Âge]", computed_age)
                .replace("[Date de naissance]", date_of_birth))
        cert = cert.replace("[X]", extract_rest_duration(cert))
        yc = justify_text(c, cert, max_line_width, yc, left_margin, footer_margin, height)
        draw_signature(c, yc)

    c.save()
    if background_file and background_file.lower().endswith('.pdf'):
        try:
            merge_with_background_pdf(save_path)
        except Exception:
            pass

def add_background_platypus(canvas_obj, doc):
    bg = background_file if background_file and os.path.exists(background_file) else None
    if bg and bg.lower().endswith(('.png','.jpg','.jpeg','.gif','.bmp')):
        try:
            canvas_obj.drawImage(bg, 0, 0, width=doc.pagesize[0], height=doc.pagesize[1])
        except Exception:
            pass

def generate_history_pdf_file(pdf_path: str, df_filtered: pd.DataFrame):
    """Génère un PDF d’historique de consultations."""
    doc = SimpleDocTemplate(pdf_path, pagesize=A5,
                            rightMargin=56.7, leftMargin=56.7,
                            topMargin=130, bottomMargin=56.7)
    elements = []
    styles = getSampleStyleSheet()
    style_heading = ParagraphStyle(
        'CustomHeading', parent=styles["Heading1"],
        fontSize=styles["Heading1"].fontSize - 2,
        leading=styles["Heading1"].leading - 2
    )
    style_normal = ParagraphStyle(
        'JustifiedNormal', parent=styles["Normal"],
        fontSize=styles["Normal"].fontSize - 2,
        alignment=TA_JUSTIFY
    )
    style_sub = styles["Heading2"]

    if not df_filtered.empty:
        row0 = df_filtered.iloc[0]
        # Utiliser 'nom' et 'prenom' si disponibles, sinon 'patient_name'
        patient_full_name = ""
        if pd.notnull(row0.get('nom')) and pd.notnull(row0.get('prenom')):
            patient_full_name = f"{str(row0.get('nom')).strip()} {str(row0.get('prenom')).strip()}"
        elif pd.notnull(row0.get('patient_name')):
            patient_full_name = str(row0.get('patient_name')).strip()

        title = (
            f"Historique des Consultations de {patient_full_name} "
            f"(ID: {str(row0.get('patient_id', '')).strip()}, Age: {str(row0.get('age', '')).strip()}, Sexe: {str(row0.get('gender', '')).strip()}, "
            f"Téléphone: {str(row0.get('patient_phone', '')).strip()}, Antécédents: {str(row0.get('antecedents', '')).strip()})"
        )
        elements.append(Paragraph(title, style_heading))
        elements.append(Spacer(1, 12))
        for _, row in df_filtered.iterrows():
            elements.append(Paragraph(f"Date : {str(row.get('consultation_date', '')).strip()}", style_sub))
            elements.append(Spacer(1, 6))
            if pd.notnull(row.get("clinical_signs")) and str(row["clinical_signs"]).strip(): # Ajout de la condition pour vérifier si le champ est vide
                elements.append(Paragraph("<b>Signes Cliniques / Motifs :</b>", style_normal))
                elements.append(Paragraph(str(row["clinical_signs"]).strip(), style_normal)) # Ensure string conversion
            vitals = []
            if pd.notnull(row.get("bp")) and str(row.bp).strip(): vitals.append(f"TA: {str(row.bp).strip()} mmHg")
            if pd.notnull(row.get("temperature")) and str(row.temperature).strip(): vitals.append(f"T°: {str(row.temperature).strip()} °C")
            if pd.notnull(row.get("heart_rate")) and str(row.heart_rate).strip(): vitals.append(f"FC: {str(row.heart_rate).strip()} bpm")
            if pd.notnull(row.get("respiratory_rate")) and str(row.respiratory_rate).strip(): vitals.append(f"FR: {str(row.respiratory_rate).strip()} rpm")
            if vitals:
                elements.append(Paragraph("<b>Paramètres Vitaux :</b> " + "; ".join(vitals), style_normal))
            if pd.notnull(row.get("diagnosis")) and str(row['diagnosis']).strip(): # Ajout de la condition pour vérifier si le champ est vide
                elements.append(Paragraph(f"<b>Diagnostic :</b> {str(row['diagnosis']).strip()}", style_normal))
            if pd.notnull(row.get("medications")):
                meds = [m.strip() for m in str(row.medications).split("; ") if m.strip()]
                if meds: # Vérifier si la liste filtrée n'est pas vide
                    elements.append(Paragraph("<b>Médicaments prescrits :</b>", style_normal))
                    for m in meds:
                        elements.append(Paragraph(f"- {m}", style_normal))
            if pd.notnull(row.get("analyses")):
                analyses = [a.strip() for a in str(row.analyses).split("; ") if a.strip()]
                if analyses: # Vérifier si la liste filtrée n'est pas vide
                    elements.append(Paragraph("<b>Analyses demandées :</b>", style_normal))
                    for a in analyses:
                        elements.append(Paragraph(f"- {a}", style_normal))
            if pd.notnull(row.get("radiologies")):
                radios = [r.strip() for r in str(row.radiologies).split("; ") if r.strip()]
                if radios: # Vérifier si la liste filtrée n'est pas vide
                    elements.append(Paragraph("<b>Radiologies demandées :</b>", style_normal))
                    for r in radios:
                        elements.append(Paragraph(f"- {r}", style_normal))
            if pd.notnull(row.get("certificate_category")) and str(row['certificate_category']).strip(): # Ajout de la condition pour vérifier si le champ est vide
                elements.append(Paragraph(f"<b>Certificat :</b> {str(row['certificate_category']).strip()}", style_normal))
            if pd.notnull(row.get("rest_duration")) and str(row['rest_duration']).strip(): # Ajout de la condition pour vérifier si le champ est vide
                elements.append(Paragraph(f"<b>Durée du repos :</b> {str(row['rest_duration']).strip()} jours", style_normal))
            if pd.notnull(row.get("doctor_comment")) and str(row['doctor_comment']).strip():
                elements.append(Paragraph("<b>Commentaire :</b>", style_normal))
                elements.append(Paragraph(str(row['doctor_comment']).strip(), style_normal))
            elements.append(Spacer(1, 12))

    doc.build(elements, onFirstPage=add_background_platypus, onLaterPages=add_background_platypus)
    if background_file and background_file.lower().endswith('.pdf'):
        try:
            merge_with_background_pdf(pdf_path)
        except Exception:
            pass
