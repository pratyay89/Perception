from enum import Enum


class UserType(str, Enum):
    student = "student"
    teacher = "teacher"
    admin = "admin"


class EvaluationStatus(str, Enum):
    pending = "pending"
    success = "success"
    failed = "failed"


class PaperStatus(str, Enum):
    draft = "draft"  # not published; only the teacher can see it
    scheduled = "scheduled"  # published, start date is in the future
    open = "open"  # students can submit answers
    closed = "closed"  # the teacher stopped accepting submissions
