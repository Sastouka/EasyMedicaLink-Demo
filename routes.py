from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Dict
LISTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Liste_Medications_Analyses_Radiologies.xlsx')

from flask import (
    request, render_template_string, redirect, url_for,
    send_file, flash, jsonify, session  # ← on ajoute session
)
import theme  # ← on importe notre module de thèmes

# Dépendances internes
import utils  # noqa: E402 – doit être importé avant l'enregistrement des routes
from templates import (
    main_template,
    settings_template,
    alert_template,
)

# ---------------------------------------------------------------------------
#  HELPERS INTERNES AU MODULE
# ---------------------------------------------------------------------------

def _config() -> Dict:
    return utils.load_config()

# ---------------------------------------------------------------------------
#  ENREGISTREMENT DES ROUTES DANS L'APP
# ---------------------------------------------------------------------------

def register_routes(app):
    """Attache toutes les routes à l'instance Flask passée en argument."""
    import theme

    # ---------------------------------------------------------------------
    #  PAGE PRINCIPALE – ENREGISTREMENT CONSULTATION
    # ---------------------------------------------------------------------
    @app.route("/consultation", methods=["GET", "POST"])
    def index():
        import theme
        from pathlib import Path

        config      = _config()
        theme_names = list(theme.THEMES.keys())
        utils.background_file = config.get("background_file_path")

        # 1️⃣ Charger la liste "de base" depuis Excel ou constantes par défaut
        if os.path.exists(LISTS_FILE):
            df_lists      = utils.pd.read_excel(LISTS_FILE, sheet_name=0, dtype=str).fillna('')
            base_meds     = df_lists['Medications'].dropna().astype(str).tolist()
            base_analyses = df_lists['Analyses'].dropna().astype(str).tolist()
            base_radios   = df_lists['Radiologies'].dropna().astype(str).tolist()
        else:
            base_meds     = utils.default_medications_options
            base_analyses = utils.default_analyses_options
            base_radios   = utils.default_radiologies_options

        # 2️⃣ Récupérer les ajouts du menu Paramètres
        cfg_meds     = config.get("medications_options", [])
        cfg_analyses = config.get("analyses_options", [])
        cfg_radios   = config.get("radiologies_options", [])

        # 2️⃣5️⃣ Récupérer la dernière consultation
        consult_file = Path(utils.EXCEL_FILE_PATH)
        if consult_file.exists():
            df_last       = utils.pd.read_excel(consult_file, sheet_name=0, dtype=str).fillna('')
            last_consult  = df_last.iloc[-1].to_dict()
        else:
            last_consult = {}

        # 3️⃣ Fusionner Excel + Paramètres en supprimant les doublons
        meds_options        = list(dict.fromkeys(base_meds     + cfg_meds))
        analyses_options    = list(dict.fromkeys(base_analyses + cfg_analyses))
        radiologies_options = list(dict.fromkeys(base_radios   + cfg_radios))

        saved_medications, saved_analyses, saved_radiologies = [], [], []

        if request.method == "POST":
            form_data        = request.form.to_dict()
            medication_list  = request.form.getlist("medications_list")
            analyses_list    = request.form.getlist("analyses_list")
            radiologies_list = request.form.getlist("radiologies_list")

            consultation_date = datetime.now().strftime("%Y-%m-%d")
            patient_id        = form_data.get("patient_id", "").strip()
            patient_name      = form_data.get("patient_name", "").strip()

            if not patient_id:
                return render_template_string(
                    alert_template,
                    alert_type="warning",
                    alert_title="Attention",
                    alert_text="Veuillez entrer l'ID du patient.",
                    redirect_url=url_for("index"),
                )

            # Vérification de l'unicité ID ↔ nom
            if os.path.exists(utils.EXCEL_FILE_PATH):
                df_existing = utils.pd.read_excel(utils.EXCEL_FILE_PATH, sheet_name=0, dtype=str)
                if patient_id in df_existing["patient_id"].astype(str).tolist():
                    existing_name = df_existing.loc[
                        df_existing["patient_id"].astype(str) == patient_id,
                        "patient_name"
                    ].iloc[0]
                    if existing_name.strip().lower() != patient_name.strip().lower():
                        flash("L'ID existe déjà avec un autre patient.", "error")
                        return render_template_string(
                            alert_template,
                            alert_type="error",
                            alert_title="Erreur",
                            alert_text="ID déjà associé à un autre patient.",
                            redirect_url=url_for("index"),
                        )

            # Chargement ou création du DataFrame de consultation
            if os.path.exists(utils.EXCEL_FILE_PATH):
                df = utils.pd.read_excel(utils.EXCEL_FILE_PATH, sheet_name=0, dtype=str)
            else:
                df = utils.pd.DataFrame(columns=[
                    "consultation_date","patient_id","patient_name","date_of_birth","gender","age",
                    "patient_phone","antecedents","clinical_signs","bp","temperature","heart_rate",
                    "respiratory_rate","diagnosis","medications","analyses","radiologies",
                    "certificate_category","certificate_content","rest_duration","doctor_comment",
                    "consultation_id",
                ])

            # Préparation de la nouvelle ligne
            new_row = {
                "consultation_date":   consultation_date,
                "patient_id":          patient_id,
                "patient_name":        patient_name,
                "date_of_birth":       form_data.get("date_of_birth", "").strip(),
                "gender":              form_data.get("gender", "").strip(),
                "age":                 form_data.get("patient_age", "").strip(),
                "patient_phone":       form_data.get("patient_phone", "").strip(),
                "antecedents":         form_data.get("antecedents", "").strip(),
                "clinical_signs":      form_data.get("clinical_signs", "").strip(),
                "bp":                  form_data.get("bp", "").strip(),
                "temperature":         form_data.get("temperature", "").strip(),
                "heart_rate":          form_data.get("heart_rate", "").strip(),
                "respiratory_rate":    form_data.get("respiratory_rate", "").strip(),
                "diagnosis":           form_data.get("diagnosis", "").strip(),
                "medications":         "; ".join(medication_list),
                "analyses":            "; ".join(analyses_list),
                "radiologies":         "; ".join(radiologies_list),
                "certificate_category": form_data.get("certificate_category", "").strip(),
                "certificate_content":  "",
                "rest_duration":        utils.extract_rest_duration(form_data.get("certificate_content", "")),
                "doctor_comment":       form_data.get("doctor_comment", "").strip(),
                "consultation_id":      str(uuid.uuid4()),
            }

            # Sauvegarde de la consultation
            df = utils.pd.concat([df, utils.pd.DataFrame([new_row])], ignore_index=True)
            df.to_excel(utils.EXCEL_FILE_PATH, index=False)
            utils.load_patient_data()
            flash("Données du patient enregistrées.", "success")
            saved_medications, saved_analyses, saved_radiologies = (
                medication_list,
                analyses_list,
                radiologies_list,
            )

        # 4️⃣ Lecture en continu de MEDICALINK_FILES/Excel/ConsultationData.xlsx
        consult_path = Path(utils.EXCEL_FILE_PATH)
        if consult_path.exists():
            df_consult = utils.pd.read_excel(consult_path, sheet_name=0, dtype=str).fillna('')
        else:
            df_consult = utils.pd.DataFrame(columns=[
                "consultation_date","patient_id","patient_name","date_of_birth","gender","age",
                "patient_phone","antecedents","clinical_signs","bp","temperature","heart_rate",
                "respiratory_rate","diagnosis","medications","analyses","radiologies",
                "certificate_category","certificate_content","rest_duration","doctor_comment",
                "consultation_id",
            ])
        consult_rows = df_consult.to_dict(orient="records")

        # Préparation des données pour le template
        patient_data = {
            pid: {
                "name":          utils.patient_id_to_name.get(pid, ""),
                "age":           utils.patient_id_to_age.get(pid, ""),
                "phone":         utils.patient_id_to_phone.get(pid, ""),
                "antecedents":   utils.patient_id_to_antecedents.get(pid, ""),
                "date_of_birth": utils.patient_id_to_dob.get(pid, ""),
                "gender":        utils.patient_id_to_gender.get(pid, ""),
            }
            for pid in utils.patient_ids
        }

        return render_template_string(
            main_template,
            config=config,
            current_date=datetime.now().strftime("%d/%m/%Y"),
            medications_options=meds_options,
            analyses_options=analyses_options,
            radiologies_options=radiologies_options,
            certificate_categories=utils.certificate_categories,
            default_certificate_text=utils.default_certificate_text,
            patient_ids=utils.patient_ids,
            patient_names=utils.patient_names,
            host_address=f"http://{utils.LOCAL_IP}:3000",
            patient_data=patient_data,
            saved_medications=saved_medications,
            saved_analyses=saved_analyses,
            saved_radiologies=saved_radiologies,
            theme_names=theme_names,
            consult_rows=consult_rows,
            last_consult=last_consult
        )

    # ---------------------------------------------------------------------
    #  API JSON / TABLEAU SUIVI
    # ---------------------------------------------------------------------
    @app.route("/get_last_consultation")
    def get_last_consultation():
        pid = request.args.get("patient_id", "").strip()
        if pid and os.path.exists(utils.EXCEL_FILE_PATH):
            df = utils.pd.read_excel(utils.EXCEL_FILE_PATH, sheet_name=0)
            df = df[df["patient_id"].astype(str) == pid]
            if not df.empty:
                return utils.json.dumps(df.iloc[-1].to_dict())
        return utils.json.dumps({})

    @app.route("/get_consultations")
    def get_consultations():
        pid = request.args.get("patient_id", "").strip()
        if pid and os.path.exists(utils.EXCEL_FILE_PATH):
            df = utils.pd.read_excel(utils.EXCEL_FILE_PATH, sheet_name=0)
            df = df[df["patient_id"].astype(str) == pid]
            return df.to_json(orient="records", force_ascii=False)
        return "[]"

    @app.route("/delete_consultation", methods=["POST"])
    def delete_consultation():
        cid = request.form.get("consultation_id", "").strip()
        if cid:
            try:
                df = utils.pd.read_excel(utils.EXCEL_FILE_PATH, sheet_name=0)
                df = df[df["consultation_id"] != cid]
                df.to_excel(utils.EXCEL_FILE_PATH, index=False)
                return "OK", 200
            except Exception as e:
                return str(e), 500
        return "Missing parameters", 400

    # ---------------------------------------------------------------------
    #  PDF À LA VOLÉE
    # ---------------------------------------------------------------------
    @app.route("/generate_pdf_route")
    def generate_pdf_route():
        form_data = {
            k: request.args.get(k, "") for k in [
                "doctor_name", "patient_name", "patient_age", "date_of_birth", "gender",
                "location", "clinical_signs", "bp", "temperature", "heart_rate",
                "respiratory_rate", "diagnosis", "certificate_content",
            ]
        }
        form_data["include_certificate"] = request.args.get("include_certificate", "off")
        medications = request.args.get("medications_list", "").split("\n") or ["Médicament Exemple"]
        analyses    = request.args.get("analyses_list", "").split("\n") or ["Analyse Exemple"]
        radiologies = request.args.get("radiologies_list", "").split("\n") or ["Radiologie Exemple"]
        pdf_path = os.path.join(utils.PDF_FOLDER, f"Ordonnance_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf")
        utils.generate_pdf_file(pdf_path, form_data, medications, analyses, radiologies)
        return send_file(pdf_path, as_attachment=True)

    @app.route("/generate_history_pdf")
    def generate_history_pdf():
        pid   = request.args.get("patient_id_filter", "").strip()
        pname = request.args.get("patient_name_filter", "").strip()
        if not os.path.exists(utils.EXCEL_FILE_PATH):
            flash("Aucune donnée de consultation.", "warning")
            return redirect(url_for("index"))
        df = utils.pd.read_excel(utils.EXCEL_FILE_PATH, sheet_name=0)
        if pid:
            df_filtered = df[df["patient_id"].astype(str) == pid]
        elif pname:
            df_filtered = df[df["patient_name"].astype(str).str.contains(pname, case=False, na=False)]
        else:
            flash("Sélectionnez l'ID ou le nom du patient.", "warning")
            return redirect(url_for("index"))
        if df_filtered.empty:
            flash("Aucune consultation trouvée pour ce patient.", "info")
            return redirect(url_for("index"))
        pdf_path = os.path.join(utils.PDF_FOLDER, f"Historique_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf")
        utils.generate_history_pdf_file(pdf_path, df_filtered)
        return send_file(pdf_path, as_attachment=True)

    # ---------------------------------------------------------------------
    #  IMPORT EXCEL / BACKGROUND
    # ---------------------------------------------------------------------
    @app.route("/import_excel", methods=["POST"])
    def import_excel():
        if "excel_file" not in request.files or request.files["excel_file"].filename == "":
            return jsonify({"status": "warning", "message": "Aucun fichier sélectionné."})
        f = request.files["excel_file"]
        f.save(os.path.join(utils.EXCEL_FOLDER, utils.secure_filename(f.filename)))
        try:
            df = utils.pd.read_excel(f)
            df.columns = [c.lower() for c in df.columns]
            if "medications" in df.columns:
                utils.default_medications_options.extend(df["medications"].dropna().tolist())
            if "analyses" in df.columns:
                utils.default_analyses_options.extend(df["analyses"].dropna().tolist())
            if "radiologies" in df.columns:
                utils.default_radiologies_options.extend(df["radiologies"].dropna().tolist())
            utils.default_medications_options[:] = list(set(utils.default_medications_options))
            utils.default_analyses_options[:]    = list(set(utils.default_analyses_options))
            utils.default_radiologies_options[:] = list(set(utils.default_radiologies_options))
            cfg = _config()
            cfg.update({
                "medications_options": utils.default_medications_options,
                "analyses_options": utils.default_analyses_options,
                "radiologies_options": utils.default_radiologies_options,
            })
            utils.save_config(cfg)
            return jsonify({"status": "success", "message": "Import réussi."})
        except Exception as e:
            return jsonify({"status": "error", "message": f"Erreur : {e}"})

    @app.route("/import_background", methods=["POST"])
    def import_background():
        if "background_file" not in request.files or request.files["background_file"].filename == "":
            return jsonify({"status": "warning", "message": "Aucun fichier sélectionné."})
        f = request.files["background_file"]
        filename = utils.secure_filename(f.filename)
        path = os.path.join(utils.BACKGROUND_FOLDER, filename)
        f.save(path)
        ext = os.path.splitext(filename)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".pdf"):
            return jsonify({"status": "warning", "message": "Format non supporté."})
        utils.background_file = path
        cfg = _config(); cfg["background_file_path"] = path; utils.save_config(cfg)
        return jsonify({"status": "success", "message": f"Arrière plan importé : {path}"})

    # ---------------------------------------------------------------------
    #  COMMENTAIRE DE SUIVI PATIENT
    # ---------------------------------------------------------------------
    @app.route("/update_comment", methods=["POST"])
    def update_comment():
        pid = request.form.get("suivi_patient_id", "").strip()
        new_comment = request.form.get("new_doctor_comment", "").strip()
        if not pid:
            flash("Veuillez entrer l'ID du patient.", "warning")
            return redirect(url_for("index"))
        if os.path.exists(utils.EXCEL_FILE_PATH):
            df = utils.pd.read_excel(utils.EXCEL_FILE_PATH, sheet_name=0)
            df.loc[df["patient_id"].astype(str) == pid, "doctor_comment"] = new_comment
            df.to_excel(utils.EXCEL_FILE_PATH, index=False)
            flash("Commentaire mis à jour.", "success")
        else:
            flash("Fichier de données non trouvé.", "error")
        return redirect(url_for("index"))

    # ---------------------------------------------------------------------
    #  PARAMÈTRES APP
    # ---------------------------------------------------------------------
    from flask import session, request, render_template_string, redirect, url_for, flash, jsonify
    import theme  # votre module theme.py

    from flask import (
        current_app, session,
        request, jsonify, render_template_string, url_for
    )
    import theme, utils

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        cfg = utils.load_config()
        theme_names = list(theme.THEMES.keys())

        if request.method == "POST":
            # 1️⃣ Mise à jour des paramètres saisis
            cfg.update({
                "nom_clinique":         request.form.get("nom_clinique", ""),
                "cabinet":              request.form.get("cabinet", ""),
                "centre_medical":       request.form.get("centre_medecin", ""),
                "doctor_name":          request.form.get("nom_medecin", ""),
                "location":             request.form.get("lieu", ""),
                "theme":                request.form.get("theme", cfg.get("theme", theme.DEFAULT_THEME)),
                "background_file_path": request.form.get("arriere_plan", ""),
            })

            storage_path = request.form.get("storage_path", "").strip()
            if storage_path:
                cfg["storage_path"] = storage_path

            # Listes dynamiques
            cfg["medications_options"] = (
                request.form.get("liste_medicaments","").splitlines()
                if request.form.get("liste_medicaments","") else utils.default_medications_options
            )
            cfg["analyses_options"] = (
                request.form.get("liste_analyses","").splitlines()
                if request.form.get("liste_analyses","") else utils.default_analyses_options
            )
            cfg["radiologies_options"] = (
                request.form.get("liste_radiologies","").splitlines()
                if request.form.get("liste_radiologies","") else utils.default_radiologies_options
            )

            # 2️⃣ Sauvegarde et rechargement immédiat
            utils.save_config(cfg)
            session["theme"] = cfg["theme"]

            # Recharger la config dans Flask et mettre à jour l’arrière-plan
            utils.init_app(current_app)
            current_app.background_path = cfg.get("background_file_path", "")
            utils.background_file      = current_app.background_path

            # 3️⃣ Si AJAX JSON, renvoyer les nouvelles valeurs + vars CSS
            if request.accept_mimetypes.accept_json:
                return jsonify({
                    "nom_clinique":         cfg.get("nom_clinique"),
                    "cabinet":              cfg.get("cabinet"),
                    "centre_medical":       cfg.get("centre_medical"),
                    "doctor_name":          cfg.get("doctor_name"),
                    "location":             cfg.get("location"),
                    "storage_path":         cfg.get("storage_path", ""),
                    "background_file_path": cfg.get("background_file_path",""),
                    "theme":                cfg.get("theme"),
                    "medications_options":  cfg.get("medications_options"),
                    "analyses_options":     cfg.get("analyses_options"),
                    "radiologies_options":  cfg.get("radiologies_options"),
                    "theme_names":          theme_names,
                    "theme_vars":           theme.current_theme(),
                })
            return jsonify({"status": "success"})

        # GET : affichage de l’offcanvas de configuration
        return render_template_string(
            settings_template,
            config=cfg,
            theme_names=theme_names,
            theme_vars=theme.current_theme()
        )

    # ---------------------------------------------------------------------
    #  TÉLÉCHARGEMENT DE L'APPLI WINDOWS
    # ---------------------------------------------------------------------
    @app.route("/download_app")
    def download_app():
        file_path = os.path.join(utils.BASE_DIR, "EasyMedicalink.rar")
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        flash("Le fichier n'existe pas.", "error")
        return redirect(url_for("index"))


