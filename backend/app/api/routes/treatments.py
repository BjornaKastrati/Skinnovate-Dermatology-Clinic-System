"""Treatment plan routes: /api/treatments/"""

import os
from flask import Blueprint, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import date

from app import db
from app.models.user import User
from app.models.patient import Patient
from app.models.dermatologist import Dermatologist
from app.models.treatment import Treatment, TreatmentProgress
from app.models.skin_image import SkinImage
from app.models.ai_diagnosis import AIDiagnosis
from app.utils.file_utils import delete_file
from app.utils.response import success, error
from app.middleware.jwt_handlers import role_required
from app.models.prescription import Prescription

treatments_bp = Blueprint("treatments", __name__)


@treatments_bp.post("/")
@jwt_required()
@role_required("dermatologist")
def create_treatment():
    user_id = int(get_jwt_identity())
    doctor = Dermatologist.query.filter_by(user_id=user_id).first()
    data = request.get_json(silent=True) or {}

    if not doctor:
        return error("Dermatologist profile not found", 404)

    required = ["patient_id", "title", "start_date"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return error(f"Missing: {', '.join(missing)}")

    patient = Patient.query.get(data["patient_id"])
    if not patient:
        return error("Patient not found", 404)

    treatment_type = data.get("treatment_type") or "General"

    treatment = Treatment(
        patient_id=data["patient_id"],
        dermatologist_id=doctor.id,
        diagnosis_id=data.get("diagnosis_id"),
        title=data["title"],
        description=data.get("description"),
        treatment_type=data.get("treatment_type"),
        start_date=date.fromisoformat(data["start_date"]),
        end_date=date.fromisoformat(data["end_date"]) if data.get("end_date") else None,
    )
    db.session.add(treatment)

    prescription = Prescription(
        patient_id=data["patient_id"],
        dermatologist_id=doctor.id,
        appointment_id=data.get("appointment_id"),
        medications=[
            {
                "name": data["title"],
                "dosage": treatment_type,
                "frequency": "",
                "duration": "",
            }
        ],
        notes=data.get("description"),
    )
    db.session.add(prescription)

    db.session.commit()

    return success(
        {
            "treatment": treatment.to_dict(),
            "prescription": prescription.to_dict(),
        },
        "Treatment plan created and prescription added",
        201,
    )


@treatments_bp.get("/patient/<int:patient_id>")
@jwt_required()
def patient_treatments(patient_id):
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)

    if user.role == "patient":
        p = Patient.query.filter_by(user_id=user_id).first()
        if p.id != patient_id:
            return error("Forbidden", 403)

    treatments = Treatment.query.filter_by(patient_id=patient_id).order_by(Treatment.start_date.desc()).all()
    result = []
    for t in treatments:
        td = t.to_dict()
        td["progress_logs"] = [p.to_dict() for p in t.progress_logs]
        result.append(td)

    return success(result)


@treatments_bp.get("/my")
@jwt_required()
def my_treatments():
    user_id = int(get_jwt_identity())
    patient = Patient.query.filter_by(user_id=user_id).first()
    if not patient:
        return error("Patient profile not found", 404)

    treatments = Treatment.query.filter_by(patient_id=patient.id).order_by(Treatment.start_date.desc()).all()
    result = []
    for t in treatments:
        td = t.to_dict()
        td["progress_logs"] = [p.to_dict() for p in t.progress_logs]
        result.append(td)
    return success(result)


@treatments_bp.post("/<int:treatment_id>/progress")
@jwt_required()
def add_progress(treatment_id):
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    treatment = Treatment.query.get_or_404(treatment_id)
    log = TreatmentProgress(
        treatment_id=treatment_id,
        image_id=data.get("image_id"),
        notes=data.get("notes"),
        logged_by=user_id,
    )
    db.session.add(log)
    db.session.commit()
    return success(log.to_dict(), "Progress logged", 201)


@treatments_bp.patch("/<int:treatment_id>")
@jwt_required()
@role_required("dermatologist", "admin")
def update_treatment(treatment_id):
    data = request.get_json(silent=True) or {}
    t = Treatment.query.get_or_404(treatment_id)

    for field in ("title", "description", "status", "end_date"):
        if field in data:
            if field == "end_date" and data[field]:
                setattr(t, field, date.fromisoformat(data[field]))
            else:
                setattr(t, field, data[field])

    # If treatment is completed/cancelled, remove the linked prescription too
    if t.status in ("completed", "cancelled"):
        prescriptions = Prescription.query.filter_by(
            patient_id=t.patient_id,
            dermatologist_id=t.dermatologist_id,
        ).all()

        for rx in prescriptions:
            meds = rx.medications or []
            has_matching_med = any(
                med.get("name") == t.title
                for med in meds
                if isinstance(med, dict)
            )

            if has_matching_med:
                db.session.delete(rx)

    db.session.commit()
    return success(t.to_dict(), "Treatment updated")