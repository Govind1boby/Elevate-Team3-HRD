"""WorkWeek HCM Domain Toolkit & Adapter.
Enforces deterministic parameter validations, balance limits, temporal constraints,
and Anti-IDOR checks for employee profile and leave operations (SDD Section 5.1.2 - 5.1.5).
"""

from datetime import date
import uuid
from typing import Any, Dict, Optional
from src.toolkits.base import BaseTool, ExecutionContext, ToolExecutionError
from src.toolkits.workweek.models import (
    ContactInfo,
    EmployeeProfile,
    LeaveBalanceItem,
    LeaveBalancesResponse,
    SubmitLeaveRequest,
    SubmitLeaveResponse,
    UpdateContactInfoRequest,
)

# Seed database with baseline employee EMP-10492 (Alexander Tan) per SDD specifications and companion test personas
EMPLOYEE_STORE: Dict[str, Dict[str, Any]] = {
    "EMP-10492": {
        "employee_id": "EMP-10492",
        "first_name": "Alexander",
        "last_name": "Tan",
        "email": "alexander.tan@altostrat.com",
        "department": "Engineering",
        "role": "Senior Staff Software Engineer",
        "manager_name": "David Tan",
        "manager_email": "david.tan@altostrat.com",
        "hire_date": "2021-04-15",
        "work_location": "Remote - Singapore",
        "personal_contact": {
            "home_address": "12 Marina Boulevard, #18-02, Singapore 018982",
            "phone_number": "+65 9123 4567"
        },
        "balances": {
            "Vacation": {"accrued": 20.0, "used": 6.0, "remaining": 14.0},
            "Sick": {"accrued": 14.0, "used": 0.0, "remaining": 14.0}
        },
        "submitted_leaves": []
    },
    "EMP-10888": {
        "employee_id": "EMP-10888",
        "first_name": "David",
        "last_name": "Tan",
        "email": "david.tan@altostrat.com",
        "department": "Engineering",
        "role": "Director of Engineering (Manager)",
        "manager_name": "VP Engineering",
        "manager_email": "vp-eng@altostrat.com",
        "hire_date": "2019-01-10",
        "work_location": "Hybrid - Singapore Office",
        "personal_contact": {
            "home_address": "88 Orchard Boulevard, Singapore 248648",
            "phone_number": "+65 9876 5432"
        },
        "balances": {
            "Vacation": {"accrued": 25.0, "used": 7.0, "remaining": 18.0},
            "Sick": {"accrued": 14.0, "used": 2.0, "remaining": 12.0}
        },
        "submitted_leaves": []
    },
    "EMP-20341": {
        "employee_id": "EMP-20341",
        "first_name": "Sarah",
        "last_name": "Lim",
        "email": "sarah.lim@altostrat.com",
        "department": "Workplace Operations",
        "role": "Facilities & Workplace Coordinator",
        "manager_name": "Head of Real Estate",
        "manager_email": "facilities-lead@altostrat.com",
        "hire_date": "2022-08-01",
        "work_location": "Onsite - Singapore Office",
        "personal_contact": {
            "home_address": "5 Tanjong Pagar Plaza, Singapore 081005",
            "phone_number": "+65 8123 9999"
        },
        "balances": {
            "Vacation": {"accrued": 18.0, "used": 8.0, "remaining": 10.0},
            "Sick": {"accrued": 14.0, "used": 1.0, "remaining": 13.0}
        },
        "submitted_leaves": []
    },
    "EMP-99999": {
        "employee_id": "EMP-99999",
        "first_name": "Former",
        "last_name": "Colleague",
        "email": "former.colleague@altostrat.com",
        "department": "Operations",
        "role": "Former Employee (Terminated)",
        "manager_name": "HR Operations",
        "manager_email": "hr-operations@altostrat.com",
        "hire_date": "2020-03-01",
        "work_location": "Offboarded",
        "status": "TERMINATED",
        "personal_contact": {
            "home_address": "N/A",
            "phone_number": "+65 0000 0000"
        },
        "balances": {
            "Vacation": {"accrued": 0.0, "used": 0.0, "remaining": 0.0},
            "Sick": {"accrued": 0.0, "used": 0.0, "remaining": 0.0}
        },
        "submitted_leaves": []
    },
    "EMP-30101": {
        "employee_id": "EMP-30101",
        "first_name": "Govindu",
        "last_name": "Kolluri",
        "email": "govindu.kolluri@altostrat.com",
        "department": "Solutions Architecture",
        "role": "Principal Cloud Solutions Architect",
        "manager_name": "David Tan",
        "manager_email": "david.tan@altostrat.com",
        "hire_date": "2020-11-01",
        "work_location": "Remote - Singapore",
        "personal_contact": {
            "home_address": "21 Marina Way, #24-05, Singapore 018978",
            "phone_number": "+65 9111 2233"
        },
        "balances": {
            "Vacation": {"accrued": 22.0, "used": 6.0, "remaining": 16.0},
            "Sick": {"accrued": 14.0, "used": 0.0, "remaining": 14.0}
        },
        "submitted_leaves": []
    },
    "EMP-30102": {
        "employee_id": "EMP-30102",
        "first_name": "Ananth",
        "last_name": "K",
        "email": "ananth.k@altostrat.com",
        "department": "AI & Data Platforms",
        "role": "Lead Machine Learning Engineer",
        "manager_name": "David Tan",
        "manager_email": "david.tan@altostrat.com",
        "hire_date": "2021-02-15",
        "work_location": "Hybrid - Singapore Office",
        "personal_contact": {
            "home_address": "50 Collyer Quay, #12-01, Singapore 049321",
            "phone_number": "+65 9222 3344"
        },
        "balances": {
            "Vacation": {"accrued": 20.0, "used": 2.0, "remaining": 18.0},
            "Sick": {"accrued": 14.0, "used": 0.0, "remaining": 14.0}
        },
        "submitted_leaves": []
    },
    "EMP-30103": {
        "employee_id": "EMP-30103",
        "first_name": "Ankit",
        "last_name": "Gupta",
        "email": "ankit.gupta@altostrat.com",
        "department": "Cloud Reliability",
        "role": "Senior Site Reliability Engineer (SRE)",
        "manager_name": "David Tan",
        "manager_email": "david.tan@altostrat.com",
        "hire_date": "2021-07-20",
        "work_location": "Remote - Singapore",
        "personal_contact": {
            "home_address": "18 Robinson Road, #09-02, Singapore 048547",
            "phone_number": "+65 9333 4455"
        },
        "balances": {
            "Vacation": {"accrued": 20.0, "used": 5.0, "remaining": 15.0},
            "Sick": {"accrued": 14.0, "used": 2.0, "remaining": 12.0}
        },
        "submitted_leaves": []
    },
    "EMP-30104": {
        "employee_id": "EMP-30104",
        "first_name": "Harsha",
        "last_name": "Heda",
        "email": "harsha.heda@altostrat.com",
        "department": "Product Management",
        "role": "Staff Product Manager (HCM & Core HR)",
        "manager_name": "Priya Sharma",
        "manager_email": "priya.sharma@altostrat.com",
        "hire_date": "2020-05-18",
        "work_location": "Hybrid - Singapore Office",
        "personal_contact": {
            "home_address": "7 Wallich Street, #30-01, Singapore 078884",
            "phone_number": "+65 9444 5566"
        },
        "balances": {
            "Vacation": {"accrued": 24.0, "used": 5.0, "remaining": 19.0},
            "Sick": {"accrued": 14.0, "used": 0.0, "remaining": 14.0}
        },
        "submitted_leaves": []
    },
    "EMP-30105": {
        "employee_id": "EMP-30105",
        "first_name": "Jomcy",
        "last_name": "Pappachen",
        "email": "jomcy.pappachen@altostrat.com",
        "department": "Cyber Security & Governance",
        "role": "Senior Information Security Analyst",
        "manager_name": "Marcus Vance",
        "manager_email": "marcus.vance@altostrat.com",
        "hire_date": "2022-01-10",
        "work_location": "Onsite - Singapore Office",
        "personal_contact": {
            "home_address": "30 Raffles Place, #15-03, Singapore 048622",
            "phone_number": "+65 9555 6677"
        },
        "balances": {
            "Vacation": {"accrued": 18.0, "used": 6.0, "remaining": 12.0},
            "Sick": {"accrued": 14.0, "used": 1.0, "remaining": 13.0}
        },
        "submitted_leaves": []
    },
    "EMP-30106": {
        "employee_id": "EMP-30106",
        "first_name": "Missie",
        "last_name": "Singh",
        "email": "missie.singh@altostrat.com",
        "department": "Engineering Operations",
        "role": "Senior Technical Program Manager (TPM)",
        "manager_name": "David Tan",
        "manager_email": "david.tan@altostrat.com",
        "hire_date": "2021-09-01",
        "work_location": "Hybrid - Singapore Office",
        "personal_contact": {
            "home_address": "10 Bayfront Avenue, #08-04, Singapore 018956",
            "phone_number": "+65 9666 7788"
        },
        "balances": {
            "Vacation": {"accrued": 21.0, "used": 4.0, "remaining": 17.0},
            "Sick": {"accrued": 14.0, "used": 0.0, "remaining": 14.0}
        },
        "submitted_leaves": []
    },
    "EMP-30107": {
        "employee_id": "EMP-30107",
        "first_name": "Nithan",
        "last_name": "Rodrigues",
        "email": "nithan.rodrigues@altostrat.com",
        "department": "Enterprise Integrations",
        "role": "Full Stack Software Engineer II",
        "manager_name": "David Tan",
        "manager_email": "david.tan@altostrat.com",
        "hire_date": "2023-03-15",
        "work_location": "Remote - Singapore",
        "personal_contact": {
            "home_address": "8 Marina View, #14-06, Singapore 018960",
            "phone_number": "+65 9777 8899"
        },
        "balances": {
            "Vacation": {"accrued": 18.0, "used": 4.0, "remaining": 14.0},
            "Sick": {"accrued": 14.0, "used": 3.0, "remaining": 11.0}
        },
        "submitted_leaves": []
    }
}


class WorkWeekGetEmployeeProfileTool(BaseTool):
    name = "workweek_get_employee_profile"
    description = (
        "Fetches verified employee profile data from WorkWeek HCM including role, department, "
        "manager hierarchy, work location, and personal contact details."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "employee_id": {
                "type": "string",
                "description": "Employee identifier (e.g. EMP-10492). Must match authenticated caller."
            }
        },
        "required": ["employee_id"]
    }

    async def execute(self, context: ExecutionContext, **kwargs) -> Dict[str, Any]:
        target_id = kwargs.get("employee_id")
        verified_id = self.enforce_anti_idor(context, target_id)

        record = EMPLOYEE_STORE.get(verified_id)
        if not record:
            raise ToolExecutionError(f"Employee record not found for {verified_id}")

        profile = EmployeeProfile(
            employee_id=record["employee_id"],
            first_name=record["first_name"],
            last_name=record["last_name"],
            email=record["email"],
            department=record["department"],
            role=record["role"],
            manager_name=record["manager_name"],
            manager_email=record["manager_email"],
            hire_date=record["hire_date"],
            work_location=record["work_location"],
            personal_contact=ContactInfo(**record["personal_contact"])
        )
        return profile.model_dump()


class WorkWeekUpdateContactInfoTool(BaseTool):
    name = "workweek_update_contact_info"
    description = (
        "Updates employee personal home address and/or mobile phone number in WorkWeek HCM. "
        "Strictly disallows modifying legal name, job title, role, salary, or manager."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "home_address": {
                "type": "string",
                "description": "Updated residential street address (min 5 characters)."
            },
            "phone_number": {
                "type": "string",
                "description": "Updated mobile phone number in E.164 international format (e.g. +6591234567)."
            }
        }
    }

    async def execute(self, context: ExecutionContext, **kwargs) -> Dict[str, Any]:
        # Anti-IDOR: strictly scoped to context.caller_id
        verified_id = context.caller_id

        # Validate with Pydantic model
        req = UpdateContactInfoRequest(**kwargs)

        record = EMPLOYEE_STORE.get(verified_id)
        if not record:
            raise ToolExecutionError(f"Employee record not found for {verified_id}")

        if req.home_address:
            record["personal_contact"]["home_address"] = req.home_address
        if req.phone_number:
            record["personal_contact"]["phone_number"] = req.phone_number

        return {
            "status": "SUCCESS",
            "employee_id": verified_id,
            "message": "Personal contact information updated successfully.",
            "updated_contact": record["personal_contact"]
        }


class WorkWeekGetLeaveBalancesTool(BaseTool):
    name = "workweek_get_leave_balances"
    description = (
        "Retrieves accrued, used, and remaining PTO and sick leave balance ledgers from WorkWeek HCM."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "employee_id": {
                "type": "string",
                "description": "Employee identifier (e.g. EMP-10492). Must match authenticated caller."
            }
        },
        "required": ["employee_id"]
    }

    async def execute(self, context: ExecutionContext, **kwargs) -> Dict[str, Any]:
        target_id = kwargs.get("employee_id")
        verified_id = self.enforce_anti_idor(context, target_id)

        record = EMPLOYEE_STORE.get(verified_id)
        if not record:
            raise ToolExecutionError(f"Employee record not found for {verified_id}")

        balances_list = []
        for cat, val in record["balances"].items():
            balances_list.append(LeaveBalanceItem(
                category=cat,
                accrued=val["accrued"],
                used=val["used"],
                remaining=val["remaining"]
            ))

        resp = LeaveBalancesResponse(
            employee_id=verified_id,
            as_of_date=date.today().isoformat(),
            balances=balances_list
        )
        return resp.model_dump()


class WorkWeekSubmitLeaveRequestTool(BaseTool):
    name = "workweek_submit_leave_request"
    description = (
        "Submits a vacation or sick time-off request in WorkWeek HCM after executing temporal "
        "and balance limit verifications."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "employee_id": {
                "type": "string",
                "description": "Employee identifier (e.g. EMP-10492). Must match authenticated caller."
            },
            "leave_type": {
                "type": "string",
                "enum": ["Vacation", "Sick"],
                "description": "Type of leave requested ('Vacation' or 'Sick')."
            },
            "start_date": {
                "type": "string",
                "description": "Leave start date in YYYY-MM-DD format (must be >= today)."
            },
            "end_date": {
                "type": "string",
                "description": "Leave end date in YYYY-MM-DD format (must be >= start_date)."
            },
            "work_days": {
                "type": "number",
                "description": "Number of work days requested (must be <= remaining balance)."
            }
        },
        "required": ["employee_id", "leave_type", "start_date", "end_date", "work_days"]
    }

    async def execute(self, context: ExecutionContext, **kwargs) -> Dict[str, Any]:
        target_id = kwargs.get("employee_id")
        verified_id = self.enforce_anti_idor(context, target_id)
        kwargs["employee_id"] = verified_id

        # Validate with Pydantic model
        req = SubmitLeaveRequest(**kwargs)

        record = EMPLOYEE_STORE.get(verified_id)
        if not record:
            raise ToolExecutionError(f"Employee record not found for {verified_id}")

        category_balances = record["balances"].get(req.leave_type)
        if not category_balances:
            raise ToolExecutionError(f"Unknown leave category '{req.leave_type}'.")

        remaining = category_balances["remaining"]
        if req.work_days > remaining:
            raise ToolExecutionError(
                f"Insufficient leave balance: Requested {req.work_days} work days of {req.leave_type} leave, "
                f"but only {remaining} days are remaining."
            )

        # Execute transaction
        category_balances["remaining"] -= req.work_days
        category_balances["used"] += req.work_days

        request_id = f"LV-{uuid.uuid4().hex[:5].upper()}"
        submission_record = {
            "request_id": request_id,
            "status": "SUBMITTED",
            "leave_type": req.leave_type,
            "start_date": req.start_date,
            "end_date": req.end_date,
            "work_days": req.work_days,
            "submitted_at": date.today().isoformat()
        }
        record["submitted_leaves"].append(submission_record)

        resp = SubmitLeaveResponse(
            request_id=request_id,
            status="SUBMITTED",
            employee_id=verified_id,
            leave_type=req.leave_type,
            start_date=req.start_date,
            end_date=req.end_date,
            work_days=req.work_days,
            remaining_balance_after=category_balances["remaining"]
        )
        return resp.model_dump()
