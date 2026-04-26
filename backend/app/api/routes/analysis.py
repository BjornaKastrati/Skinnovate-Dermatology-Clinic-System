"""Analysis routes: /api/analysis/ – image upload + AI inference."""

import os
from flask import Blueprint, request, current_app, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError

from app import db
from app.models.user import User
from app.models.patient import Patient
from app.models.skin_image import SkinImage
from app.models.ai_diagnosis import AIDiagnosis
from app.models.treatment import Treatment
from app.services.ai_service.predictor import predict
from app.utils.file_utils import allowed_image, save_upload, delete_file
from app.utils.response import success, error
from app.middleware.jwt_handlers import role_required
from app.models.treatment import Treatment

analysis_bp = Blueprint("analysis", __name__)


def _image_url(filename: str) -> str:
    """Build the public URL for a stored skin image."""
    return f"/api/analysis/image/{filename}"


@analysis_bp.post("/upload")
@jwt_required()
def upload_and_analyze():
    """Upload a skin image and run AI inference immediately."""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return error("User not found", 404)

    if user.role != "patient":
        return error("Only patients can upload skin images", 403)

    patient = Patient.query.filter_by(user_id=user_id).first()
    if not patient:
        return error("Patient profile not found", 404)

    if "image" not in request.files:
        return error("No image file provided")

    file = request.files["image"]
    if not file or not file.filename:
        return error("Empty file")

    if not allowed_image(file.filename):
        return error("Unsupported file type. Use JPG, PNG, or WebP")

    # Save file
    filename, filepath = save_upload(file, subfolder="skin_images")

    # Resolve absolute path for inference
    if not os.path.isabs(filepath):
        backend_root = os.path.abspath(os.path.join(current_app.root_path, ".."))
        filepath_abs = os.path.normpath(os.path.join(backend_root, filepath))
    else:
        filepath_abs = filepath

    skin_image = SkinImage(
        patient_id=patient.id,
        filename=filename,
        filepath=filepath,   # keep stored path as before
        description=request.form.get("description"),
        body_area=request.form.get("body_area"),
    )
    db.session.add(skin_image)
    db.session.flush()

    # AI inference
    model_path = current_app.config["AI_MODEL_PATH"]
    threshold = current_app.config["AI_CONFIDENCE_THRESHOLD"]
    result = predict(filepath_abs, model_path, threshold)

    if result.error:
        db.session.rollback()
        return error(f"AI inference failed: {result.error}", 500)

    diagnosis = AIDiagnosis(
        skin_image_id=skin_image.id,
        predicted_condition=result.predicted_condition,
        confidence_score=result.confidence_score,
        all_predictions=result.all_predictions,
        severity=result.severity,
        requires_consultation=result.requires_consultation,
    )
    db.session.add(diagnosis)

    # Loyalty points +5
    current_points = db.session.query(Patient.loyalty_points).filter_by(id=patient.id).scalar() or 0
    patient.loyalty_points = current_points + 5

    db.session.commit()

    image_data = skin_image.to_dict()
    image_data["image_url"] = _image_url(filename)

    db.session.refresh(patient)

    return success(
        {
            "image": image_data,
            "diagnosis": diagnosis.to_dict(),
            "loyalty_points": patient.loyalty_points,
        },
        "Analysis complete",
        201,
    )


@analysis_bp.get("/image/<filename>")
def serve_image(filename):
    """
    Serve uploaded image by filename.

    Tries:
    1. exact filepath stored in DB
    2. backend/uploads/skin_images/<filename>
    3. backend/app/uploads/skin_images/<filename> (legacy fallback)
    """
    skin_image = SkinImage.query.filter_by(filename=filename).first()
    if not skin_image:
        return error("Image not found", 404)

    backend_root = os.path.abspath(os.path.join(current_app.root_path, ".."))
    app_root = current_app.root_path

    candidates = []

    stored_path = skin_image.filepath
    if stored_path:
        if os.path.isabs(stored_path):
            candidates.append(stored_path)
        else:
            candidates.append(os.path.abspath(os.path.join(backend_root, stored_path)))
            candidates.append(os.path.abspath(os.path.join(app_root, stored_path)))

    upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads")
    candidates.append(os.path.abspath(os.path.join(backend_root, upload_folder, "skin_images", filename)))
    candidates.append(os.path.abspath(os.path.join(app_root, upload_folder, "skin_images", filename)))

    for path in candidates:
        if path and os.path.exists(path):
            return send_file(path)

    return error(
        {
            "message": "Image file not found on disk",
            "filename": filename,
            "stored_path": stored_path,
            "checked_paths": candidates,
        },
        404,
    )


@analysis_bp.get("/history")
@jwt_required()
def analysis_history():
    """Return all AI analyses for the current user.

    Patients see only their own images.
    For patients, analyses linked to treatments with status other than
    'active' are hidden from history/dashboard to keep the UI clean.
    Doctors/admins see the 50 most recent across all patients.
    """
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)

    if user.role == "patient":
        patient = Patient.query.filter_by(user_id=user_id).first()
        if not patient:
            return error("Patient profile not found", 404)

        images = (
            SkinImage.query
            .filter_by(patient_id=patient.id)
            .order_by(SkinImage.uploaded_at.desc())
            .all()
        )

        results = []
        for img in images:
            diagnosis = img.diagnosis

            # Hide analyses linked to completed/cancelled/paused treatments
            if diagnosis:
                linked_treatment = Treatment.query.filter_by(diagnosis_id=diagnosis.id).first()
                if linked_treatment and linked_treatment.status != "active":
                    continue

            entry = img.to_dict()
            entry["image_url"] = _image_url(img.filename)
            if diagnosis:
                entry["diagnosis"] = diagnosis.to_dict()
            results.append(entry)

        return success(results)

    else:
        images = (
            SkinImage.query
            .order_by(SkinImage.uploaded_at.desc())
            .limit(50)
            .all()
        )

        results = []
        for img in images:
            entry = img.to_dict()
            entry["image_url"] = _image_url(img.filename)

            patient = Patient.query.get(img.patient_id)
            if patient:
                patient_user = User.query.get(patient.user_id)
                if patient_user:
                    entry["patient_name"] = patient_user.full_name

            if img.diagnosis:
                entry["diagnosis"] = img.diagnosis.to_dict()

            results.append(entry)

        return success(results)


@analysis_bp.get("/<int:diagnosis_id>")
@jwt_required()
def get_diagnosis(diagnosis_id):
    """Return a single diagnosis with its linked image URL + patient info."""
    diag = AIDiagnosis.query.get_or_404(diagnosis_id)
    data = diag.to_dict()

    if diag.skin_image:
        img = diag.skin_image
        img_data = img.to_dict()
        img_data["image_url"] = _image_url(img.filename)

        # 🔥 ADD THIS BLOCK
        patient = Patient.query.get(img.patient_id)
        if patient:
            user = User.query.get(patient.user_id)
            if user:
                img_data["patient_name"] = user.full_name

        data["skin_image"] = img_data

    return success(data)


@analysis_bp.delete("/<int:skin_image_id>")
@jwt_required()
def delete_analysis(skin_image_id):
    """Delete one analysis from the patient's side.

    Patients may delete only their own analyses.
    Analyses linked to treatment plans cannot be deleted.
    """
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return error("User not found", 404)

    if user.role != "patient":
        return error("Only patients can delete analyses", 403)

    patient = Patient.query.filter_by(user_id=user_id).first()
    if not patient:
        return error("Patient profile not found", 404)

    skin_image = SkinImage.query.get_or_404(skin_image_id)

    if skin_image.patient_id != patient.id:
        return error("You can delete only your own analyses", 403)

    diagnosis = AIDiagnosis.query.filter_by(skin_image_id=skin_image.id).first()

    # Block patient deletion if linked to a treatment
    if diagnosis:
        linked_treatment = Treatment.query.filter_by(diagnosis_id=diagnosis.id).first()
        if linked_treatment:
            return error("This analysis is linked to a treatment plan and cannot be deleted.", 400)

    filepath = skin_image.filepath

    try:
        if diagnosis:
            db.session.delete(diagnosis)

        db.session.delete(skin_image)
        db.session.commit()

        if filepath:
            # Resolve stored relative path before deletion if needed
            if not os.path.isabs(filepath):
                backend_root = os.path.abspath(os.path.join(current_app.root_path, ".."))
                filepath = os.path.normpath(os.path.join(backend_root, filepath))
            delete_file(filepath)

        return success({"deleted_id": skin_image_id}, "Analysis deleted successfully")

    except IntegrityError as exc:
        db.session.rollback()
        current_app.logger.warning("Delete blocked for analysis %s due to linked records: %s", skin_image_id, exc)
        return error("This analysis is linked to a treatment plan and cannot be deleted.", 400)

    except Exception as exc:
        db.session.rollback()
        current_app.logger.error("Failed to delete analysis %s: %s", skin_image_id, exc)
        return error("Could not delete analysis", 500)


@analysis_bp.patch("/<int:diagnosis_id>/validate")
@jwt_required()
@role_required("dermatologist", "admin")
def validate_diagnosis(diagnosis_id):
    """Doctor confirms or overrides the AI diagnosis."""
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    diag = AIDiagnosis.query.get_or_404(diagnosis_id)
    diag.doctor_confirmed = data.get("confirmed", True)
    diag.doctor_diagnosis = data.get("doctor_diagnosis", diag.predicted_condition)
    diag.validated_by = user_id
    diag.validated_at = datetime.now(timezone.utc)

    db.session.commit()
    return success(diag.to_dict(), "Diagnosis validated")