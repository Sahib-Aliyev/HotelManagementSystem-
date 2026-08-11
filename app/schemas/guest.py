"""Guest schemas."""

from datetime import date

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.guest import DocumentType
from app.schemas.common import ORMModel


class GuestBase(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=5, max_length=30)
    email: EmailStr | None = None
    document_type: DocumentType = DocumentType.PASSPORT
    document_number: str = Field(min_length=3, max_length=50)
    nationality: str | None = Field(None, max_length=60)
    date_of_birth: date | None = None
    address: str | None = Field(None, max_length=255)
    notes: str | None = None

    @field_validator("document_number")
    @classmethod
    def _normalise_document(cls, v: str) -> str:
        # Stored upper-case and unspaced so lookups match however staff type it.
        return v.replace(" ", "").upper()

    @field_validator("date_of_birth")
    @classmethod
    def _not_in_future(cls, v: date | None) -> date | None:
        if v and v > date.today():
            raise ValueError("Date of birth cannot be in the future")
        return v


class GuestCreate(GuestBase):
    pass


class GuestUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=120)
    phone: str | None = Field(None, min_length=5, max_length=30)
    email: EmailStr | None = None
    document_type: DocumentType | None = None
    document_number: str | None = Field(None, min_length=3, max_length=50)
    nationality: str | None = Field(None, max_length=60)
    date_of_birth: date | None = None
    address: str | None = Field(None, max_length=255)
    notes: str | None = None


class GuestRead(ORMModel):
    id: int
    full_name: str
    phone: str
    email: str | None
    document_type: DocumentType
    document_number: str
    nationality: str | None
    date_of_birth: date | None
    address: str | None
    notes: str | None


class GuestSummary(ORMModel):
    """Trimmed guest payload for embedding inside reservation responses."""

    id: int
    full_name: str
    phone: str
    email: str | None
    nationality: str | None
