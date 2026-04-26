"""Appointment routes: /api/appointments/"""

from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timezone
from sqlalchemy import or_

from app import db
from app.models.user import User
from app.models.patient import Patient
from app.models.dermatologist import Dermatologist
from app.models.appointment import Appointment
from app.utils.response import success, error
from app.middleware.jwt_handlers import role_required

appointments_bp = Blueprint("appointments", __name__)


def _get_patient(user_id):
    return Patient.query.filter_by(user_id=user_id).first()


def _get_doctor(user_id):
    return Dermatologist.query.filter_by(user_id=user_id).first()


def _parse_iso_datetime(value: str):
    """
    Parse ISO 8601 datetime safely.
    Handles trailing 'Z' by converting it to '+00:00'.
    Returns a datetime object.
    """
    if not value:
        raise ValueError("Missing datetime value")

    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    return datetime.fromisoformat(normalized)


def _to_utc_aware(dt: datetime) -> datetime:
    """
    Ensure datetime is timezone-aware in UTC.
    - If naive, assume UTC.
    - If aware, convert to UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@appointments_bp.post("/")
@jwt_required()
def book_appointment():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    data = request.get_json(silent=True) or {}

    patient = _get_patient(user_id) if user.role == "patient" else None
    if user.role == "patient" and not patient:
        return error("Patient profile not found", 404)

    if not data.get("scheduled_at"):
        return error("scheduled_at is required")

    try:
        scheduled = _parse_iso_datetime(data["scheduled_at"])
        scheduled_utc = _to_utc_aware(scheduled)
    except ValueError:
        return error("Invalid date format. Use ISO 8601")

    now_utc = datetime.now(timezone.utc)

    if scheduled_utc <= now_utc:
        return error("Appointment must be in the future")

    appt = Appointment(
        patient_id=patient.id if patient else data.get("patient_id"),
        dermatologist_id=data.get("dermatologist_id"),
        scheduled_at=scheduled_utc,
        appointment_type=data.get("appointment_type", "in_person"),
        reason=data.get("reason"),
        is_emergency=data.get("is_emergency", False),
        status="requested" if not data.get("dermatologist_id") else "scheduled",
    )
    db.session.add(appt)
    db.session.commit()
    return success(appt.to_dict(), "Appointment booked", 201)


@appointments_bp.get("/")
@jwt_required()
def list_appointments():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)

    if user.role == "patient":
        patient = _get_patient(user_id)
        query = Appointment.query.filter_by(patient_id=patient.id)
    elif user.role == "dermatologist":
        doctor = _get_doctor(user_id)
        query = Appointment.query.filter(
            or_(
                Appointment.dermatologist_id == doctor.id,
                Appointment.dermatologist_id.is_(None)
            )
        )
    else:
        query = Appointment.query

    status = request.args.get("status")
    if status:
        query = query.filter_by(status=status)

    appts = query.order_by(Appointment.scheduled_at.asc()).all()

    result = []
    for a in appts:
        data = a.to_dict()

        if a.patient and a.patient.user:
            data["patient_name"] = a.patient.user.full_name

        if a.dermatologist and a.dermatologist.user:
            data["dermatologist_name"] = a.dermatologist.user.full_name

        result.append(data)

    return success(result)


@appointments_bp.get("/<int:appt_id>")
@jwt_required()
def get_appointment(appt_id):
    appt = Appointment.query.get_or_404(appt_id)
    data = appt.to_dict()
    if appt.dermatologist and appt.dermatologist.user:
        data["dermatologist_name"] = appt.dermatologist.user.full_name
    if appt.patient and appt.patient.user:
        data["patient_name"] = appt.patient.user.full_name
    return success(data)


@appointments_bp.patch("/<int:appt_id>")
@jwt_required()
def update_appointment(appt_id):
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    appt = Appointment.query.get_or_404(appt_id)
    data = request.get_json(silent=True) or {}

    if user.role == "patient":
        patient = _get_patient(user_id)
        if appt.patient_id != patient.id:
            return error("Forbidden", 403)

        allowed = {"scheduled_at", "reason", "status"}

        if "status" in data and data["status"] not in ("cancelled",):
            return error("Patients can only cancel appointments")

    else:
        allowed = {"status", "notes", "dermatologist_id", "scheduled_at"}

        if user.role == "dermatologist":
            doctor = _get_doctor(user_id)

            # Accept requested appointment:
            # assign it to this doctor and move it to scheduled.
            if data.get("status") == "scheduled" and appt.status == "requested":
                appt.dermatologist_id = doctor.id

            # Safety: if an unassigned appointment is started directly, assign it too.
            if data.get("status") == "in_progress" and appt.dermatologist_id is None:
                appt.dermatologist_id = doctor.id

    for key in allowed:
        if key in data:
            if key == "scheduled_at":
                try:
                    parsed = _parse_iso_datetime(data[key])
                    setattr(appt, key, _to_utc_aware(parsed))
                except ValueError:
                    return error("Invalid date format")
            else:
                setattr(appt, key, data[key])

    db.session.commit()
    return success(appt.to_dict(), "Appointment updated")


@appointments_bp.get("/doctors/available")
@jwt_required()
def available_doctors():
    doctors = Dermatologist.query.filter_by(is_available=True).all()
    result = []
    for d in doctors:
        info = d.to_dict()
        if d.user:
            info["full_name"] = d.user.full_name
            info["email"] = d.user.email
        result.append(info)
    return success(result)