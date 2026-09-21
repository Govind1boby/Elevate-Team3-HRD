"""Pydantic data contracts and schemas for WorkWeek HCM integrations.
"""

from datetime import date
import re
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

# E.164 Phone format regex
E164_REGEX = re.compile(r"^\+?[1-9]\d{1,14}$")


class ContactInfo(BaseModel):
    home_address: str = Field(..., min_length=5, max_length=255, description="Residential street address")
    phone_number: str = Field(..., description="E.164 formatted telephone number")

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        cleaned = re.sub(r"[\s\-\(\)]", "", v)
        if not E164_REGEX.match(cleaned):
            raise ValueError(f"Phone number '{v}' is not valid E.164 format (e.g. +6591234567)")
        return v


class UpdateContactInfoRequest(BaseModel):
    home_address: Optional[str] = Field(None, min_length=5, max_length=255)
    phone_number: Optional[str] = Field(None, description="E.164 formatted telephone number")

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = re.sub(r"[\s\-\(\)]", "", v)
            if not E164_REGEX.match(cleaned):
                raise ValueError(f"Phone number '{v}' is not valid E.164 format (e.g. +6591234567)")
        return v

    @model_validator(mode="after")
    def check_at_least_one_field(self):
        if self.home_address is None and self.phone_number is None:
            raise ValueError("At least one of 'home_address' or 'phone_number' must be provided.")
        return self


class EmployeeProfile(BaseModel):
    employee_id: str = Field(..., description="Unique employee identifier (e.g. EMP-10492)")
    first_name: str
    last_name: str
    email: str
    department: str
    role: str
    manager_name: str
    manager_email: str
    hire_date: str
    work_location: str
    personal_contact: ContactInfo


class LeaveBalanceItem(BaseModel):
    category: str = Field(..., description="'Vacation' or 'Sick'")
    accrued: float
    used: float
    remaining: float


class LeaveBalancesResponse(BaseModel):
    employee_id: str
    as_of_date: str
    balances: List[LeaveBalanceItem]


class SubmitLeaveRequest(BaseModel):
    employee_id: str
    leave_type: str = Field(..., description="'Vacation' or 'Sick'")
    start_date: str = Field(..., description="YYYY-MM-DD")
    end_date: str = Field(..., description="YYYY-MM-DD")
    work_days: float = Field(..., gt=0, description="Total working days requested")

    @field_validator("leave_type")
    @classmethod
    def validate_leave_type(cls, v: str) -> str:
        normalized = v.strip().capitalize()
        if normalized not in ("Vacation", "Sick"):
            raise ValueError(f"Invalid leave_type: '{v}'. Must be 'Vacation' or 'Sick'.")
        return normalized

    @model_validator(mode="after")
    def validate_dates(self):
        try:
            start = date.fromisoformat(self.start_date)
            end = date.fromisoformat(self.end_date)
        except ValueError as e:
            raise ValueError(f"Dates must be in YYYY-MM-DD format: {e}")

        today = date.today()
        if start < today:
            raise ValueError(f"start_date {self.start_date} cannot be in the past (today: {today}).")
        if start > end:
            raise ValueError(f"start_date {self.start_date} must be <= end_date {self.end_date}.")
        return self


class SubmitLeaveResponse(BaseModel):
    request_id: str
    status: str
    employee_id: str
    leave_type: str
    start_date: str
    end_date: str
    work_days: float
    remaining_balance_after: float
