"""Room and room-type schemas."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.room import RoomStatus
from app.schemas.common import ORMModel


class RoomTypeBase(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    description: str | None = None
    base_price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    capacity: int = Field(2, ge=1, le=10)
    amenities: list[str] = Field(default_factory=list)


class RoomTypeCreate(RoomTypeBase):
    pass


class RoomTypeUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=60)
    description: str | None = None
    base_price: Decimal | None = Field(None, gt=0, max_digits=10, decimal_places=2)
    capacity: int | None = Field(None, ge=1, le=10)
    amenities: list[str] | None = None


class RoomTypeRead(ORMModel):
    id: int
    name: str
    description: str | None
    base_price: Decimal
    capacity: int
    amenities: list[str]


class RoomCreate(BaseModel):
    room_number: str = Field(min_length=1, max_length=10)
    room_type_id: int
    floor: int = Field(1, ge=0, le=100)
    status: RoomStatus = RoomStatus.AVAILABLE
    notes: str | None = None


class RoomUpdate(BaseModel):
    room_number: str | None = Field(None, min_length=1, max_length=10)
    room_type_id: int | None = None
    floor: int | None = Field(None, ge=0, le=100)
    status: RoomStatus | None = None
    notes: str | None = None


class RoomRead(ORMModel):
    id: int
    room_number: str
    floor: int
    status: RoomStatus
    notes: str | None
    room_type: RoomTypeRead


class RoomAvailabilityQuery(BaseModel):
    check_in_date: date
    check_out_date: date
    room_type_id: int | None = None
    capacity: int | None = Field(None, ge=1)

    @model_validator(mode="after")
    def _validate_range(self) -> "RoomAvailabilityQuery":
        if self.check_out_date <= self.check_in_date:
            raise ValueError("check_out_date must be after check_in_date")
        return self

    @property
    def nights(self) -> int:
        return (self.check_out_date - self.check_in_date).days


class AvailableRoom(ORMModel):
    id: int
    room_number: str
    floor: int
    status: RoomStatus
    room_type: RoomTypeRead
    nights: int = 0
    total_price: Decimal = Decimal("0.00")


class RoomStatusUpdate(BaseModel):
    """Body of `POST /rooms/{id}/status`.

    A body rather than a query parameter, so the change is described in the
    request rather than in the URL and every access log along the way.
    """

    status: RoomStatus
