import json
import os
import tempfile
from typing import Annotated, Literal, Optional

from fastapi import FastAPI, HTTPException, Path, Query
from pydantic import BaseModel, Field, ValidationError, computed_field, field_validator

app = FastAPI(title="Patient Management API")

FILE = "patients.json"
NOT_STORED = {"id", "bmi", "verdict"}  # id is the dict key; bmi/verdict are computed


class Patient(BaseModel):
    id: Annotated[str, Field(..., pattern=r"^P\d{3,}$", description="ID of the patient", examples=["P001"])]
    name: Annotated[str, Field(..., min_length=1, description="Name of the patient")]
    city: Annotated[str, Field(..., min_length=1, description="City of the patient")]
    age: Annotated[int, Field(..., gt=0, lt=120, description="Age of the patient")]
    gender: Annotated[Literal["male", "female", "others"], Field(..., description="Gender of the patient")]
    height: Annotated[float, Field(..., gt=0, description="Height of the patient in metres")]
    weight: Annotated[float, Field(..., gt=0, description="Weight of the patient in kg")]

    @field_validator("name", "city")
    @classmethod
    def clean_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v.title()

    @computed_field
    @property
    def bmi(self) -> float:
        return round(self.weight / (self.height ** 2), 2)

    @computed_field
    @property
    def verdict(self) -> str:
        if self.bmi < 18.5:
            return "underweight"
        elif self.bmi < 25:
            return "normal"
        elif self.bmi < 30:
            return "overweight"
        return "obese"


class PatientUpdate(BaseModel):
    name: Annotated[Optional[str], Field(default=None, min_length=1)]
    city: Annotated[Optional[str], Field(default=None, min_length=1)]
    age: Annotated[Optional[int], Field(default=None, gt=0, lt=120)]
    gender: Annotated[Optional[Literal["male", "female", "others"]], Field(default=None)]
    height: Annotated[Optional[float], Field(default=None, gt=0)]
    weight: Annotated[Optional[float], Field(default=None, gt=0)]


def load_data() -> dict:
    if not os.path.exists(FILE):
        return {}
    with open(FILE, "r") as f:
        return json.load(f)


def save_data(data: dict) -> None:
    # write to a temp file, then swap, so a crash can't corrupt patients.json
    fd, tmp = tempfile.mkstemp(dir=".", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=4)
    os.replace(tmp, FILE)


def to_patient(pid: str, record: dict) -> Patient:
    return Patient(id=pid, **record)


@app.get("/")
def hello():
    return {"message": "Patient management system API"}


@app.get("/about")
def about():
    return {"message": "A fully functional API to manage patient records"}


@app.post("/patients", status_code=201)
def create_patient(patient: Patient):
    data = load_data()
    if patient.id in data:
        raise HTTPException(status_code=400, detail="Patient already exists")
    data[patient.id] = patient.model_dump(exclude=NOT_STORED)
    save_data(data)
    return {"message": "Patient created successfully", "patient": patient}


@app.get("/patients")
def list_patients(
    sort_by: Optional[Literal["height", "weight", "bmi", "age"]] = Query(None, description="Field to sort on"),
    order: Literal["asc", "desc"] = Query("asc", description="Sorting order"),
):
    patients = [to_patient(pid, rec) for pid, rec in load_data().items()]
    if sort_by:
        patients.sort(key=lambda p: getattr(p, sort_by), reverse=(order == "desc"))
    return patients


@app.get("/patients/{patient_id}")
def view_patient(patient_id: str = Path(..., description="ID of the patient", examples=["P001"])):
    data = load_data()
    if patient_id not in data:
        raise HTTPException(status_code=404, detail="Patient not found")
    return to_patient(patient_id, data[patient_id])


@app.put("/patients/{patient_id}")
def update_patient(patient_id: str, update: PatientUpdate):
    data = load_data()
    if patient_id not in data:
        raise HTTPException(status_code=404, detail="Patient not found")

    # exclude_none stops an explicit null from overwriting a stored value
    changes = update.model_dump(exclude_unset=True, exclude_none=True)
    merged = {**data[patient_id], **changes}

    try:
        patient = to_patient(patient_id, merged)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=json.loads(e.json(include_url=False, include_context=False)))

    data[patient_id] = patient.model_dump(exclude=NOT_STORED)
    save_data(data)
    return {"message": "Patient updated", "patient": patient}


@app.delete("/patients/{patient_id}")
def delete_patient(patient_id: str):
    data = load_data()
    if patient_id not in data:
        raise HTTPException(status_code=404, detail="Patient not found")
    del data[patient_id]
    save_data(data)
    return {"message": "Patient deleted"}






