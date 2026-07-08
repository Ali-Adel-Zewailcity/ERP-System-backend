"""
Schemas package - Pydantic v2 request/response models.

Sub-modules will be added here as each API feature is implemented:
  schemas/auth.py
  schemas/inventory.py
  schemas/sales.py
  schemas/hr.py
"""

from app.models.hr import (
    EmployeeCreate,
    EmployeeUpdate,
    EmployeeResponse,
    EmployeeListResponse,
    AttachmentResponse,
    ActivityLogResponse,
    AttendanceCreate,
    AttendanceUpdate,
    AttendanceResponse,
    AttendanceListResponse,
)
