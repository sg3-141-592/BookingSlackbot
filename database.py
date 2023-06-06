from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    JSON,
    Integer,
    String,
    and_,
    create_engine,
    func,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import PendingRollbackError, IntegrityError, NoResultFound
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import SingletonThreadPool

import datetime
import os

import utilities

engine = create_engine(
    os.environ["DATABASE_STR"], poolclass=SingletonThreadPool, echo=False
)

Base = declarative_base()


class ResourceType(Base):
    __tablename__ = "resource_types"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    organisation_id = Column(String, index=True)
    description = Column(String, nullable=True)
    administrators = Column(JSON)
    __table_args__ = (
        UniqueConstraint("name", "organisation_id", name="uix_name_org_id"),
    )


class Environment(Base):
    __tablename__ = "environments"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    description = Column(String, nullable=True)
    resource_type = Column(Integer, ForeignKey("resource_types.id"), index=True)
    booking_type = Column(String)
    booking_settings = Column(JSON)
    maximum_users = Column(Integer)
    __table_args__ = (
        UniqueConstraint("name", "resource_type", name="uix_name_resource_type"),
    )


class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True)
    environment = Column(Integer, ForeignKey("environments.id"), index=True)
    user_id = Column(String)
    booking_key = Column(String, index=True)
    __table_args__ = (UniqueConstraint("environment", "booking_key", "user_id", name="uix_env_date"),)

# Used to record references to shares to update them later
class Share(Base):
    __tablename__ = "shares"
    id = Column(Integer, primary_key=True)
    environment = Column(Integer, ForeignKey("environments.id"), index=True)
    channel_id = Column(String)
    timestamp = Column(String)
    created = Column(
		DateTime(timezone=True),
		default=datetime.datetime.utcnow
	)

Base.metadata.create_all(engine)

# Create a session
Session = sessionmaker(bind=engine)
session = Session()


# Resource Types
def addResourceType(name: str, organisationId: str, description: str = None, administrators: list = []):
    try:
        newResourceType = ResourceType(
            name=name, organisation_id=organisationId, description=description, administrators=administrators
        )
        session.add(newResourceType)
        session.commit()
    except (PendingRollbackError, IntegrityError):
        session.rollback()
        raise

def getResourceType(resourceTypeId: int):
    try:
        resourceTypes = session.query(
            ResourceType.id, ResourceType.name, ResourceType.description, ResourceType.administrators
        ).filter(ResourceType.id == resourceTypeId).one()
        return resourceTypes
    except NoResultFound:
        session.rollback()
        raise

def getResourceTypes(organisationId: str):
    try:
        resourceTypes = session.query(
            ResourceType.id, ResourceType.name, ResourceType.description, ResourceType.administrators
        ).filter(ResourceType.organisation_id == organisationId).all()
        return resourceTypes
    except NoResultFound:
        return None


def modifyResourceType(resourceTypeId: int, name: str, description: str, administrators: list):
    session.query(ResourceType).filter(ResourceType.id == resourceTypeId).update({
        "name": name,
        "description": description,
        "administrators": administrators
    })
    session.commit()

def deleteResourceType(resourceTypeId: int):
    # Get all the environments for the resource type
    environments = list(session.query(Environment.id).where(Environment.resource_type == resourceTypeId))
    for environmentId, in environments:
        deleteEnvironment(environmentId)
    # Get current resource type object and delete it
    deleteResourceType = (
        session.query(ResourceType).filter(ResourceType.id == resourceTypeId).one()
    )
    session.delete(deleteResourceType)
    session.commit()

# Environments
# -----------------------------------


def getEnvironment(environmentId: int):
    try:
        return (
            session.query(
                Environment.id,
                Environment.name,
                Environment.description,
                ResourceType.id,
                Environment.booking_type,
                Environment.booking_settings,
                Environment.maximum_users,
            )
            .join(ResourceType)
            .filter(Environment.id == environmentId)
            .one()
        )
    except NoResultFound:
        return None


def addEnvironment(
    name: str,
    resourceTypeId: int,
    bookingType: str,
    bookingSettings: dict,
    maximumUsers: int,
    description: str = None,
):
    try:
        newEnvironment = Environment(
            name=name,
            description=description,
            resource_type=resourceTypeId,
            booking_type=bookingType,
            booking_settings=bookingSettings,
            maximum_users=maximumUsers,
        )
        session.add(newEnvironment)
        session.commit()
    except (PendingRollbackError, IntegrityError):
        session.rollback()
        raise


def modifyEnvironment(environmentId: int, name: str, description: str = None):
    session.query(Environment).filter(Environment.id == environmentId).update(
        {"name": name, "description": description}
    )
    session.commit()


def deleteEnvironment(environmentId: int):
    # Get all bookings for the environment and delete them
    del_environmentBookings = Booking.__table__.delete().where(
        Booking.environment == environmentId
    )
    session.execute(del_environmentBookings)

    deleteEnvironment = (
        session.query(Environment).filter(Environment.id == environmentId).one()
    )
    session.delete(deleteEnvironment)
    session.commit()

def getEnvironments(organisationId: str, resourceTypeId: int, timeZoneName: str) -> str:
    result = list(
        session.query(
            Environment.id,
            Environment.name,
            Environment.description,
            Environment.booking_type,
            Environment.booking_settings,
            Environment.maximum_users,
        )
        .join(ResourceType)
        .filter(
            and_(
                ResourceType.organisation_id == organisationId,
                Environment.resource_type == resourceTypeId,
            )
        )
    )
    # Filter out all environments that don't have valid dates
    # i.e. one time bookings that are in the past
    filtered_environments = filter(lambda x: utilities.getValidBookings(x[3], x[4], timeZoneName) != None, result)

    return list(filtered_environments)


# Bookings
# -----------------------------------


def addBooking(environmentId: int, bookingKey: str, userId: str):
    # For the requested environment try and add a booking
    try:
        newBooking = Booking(environment=environmentId, booking_key=bookingKey, user_id=userId)
        session.add(newBooking)
        session.commit()
    except (PendingRollbackError, IntegrityError):
        session.rollback()
        raise


def removeBooking(environmentId: int, bookingKey: str, userId: str):
    deleteBooking = (
        session.query(Booking)
        .filter(Booking.environment == environmentId, Booking.booking_key == bookingKey, Booking.user_id == userId)
        .one()
    )
    session.delete(deleteBooking)
    session.commit()

def getBookings(
    organisationId: str = None, environmentId=None, resourceTypeId: int = None, bookingKey: str = None, timeZoneName: str = None
) -> list:
    # Get information about the current environment
    environmentData = getEnvironment(environmentId)
    validBookingKeys = utilities.getValidBookings(environmentData[4], environmentData[5], timeZoneName)
    if bookingKey and environmentId:
        return list(
            session.query(Booking.environment, Booking.booking_key, Booking.user_id)
            .join(Environment)
            .where(
                and_(
                    Booking.booking_key == bookingKey,
                    Environment.id == environmentId
                )
            )
        )
    elif environmentId:
        return list(
            session.query(Booking.environment, Booking.booking_key, Booking.user_id)
            .join(Environment)
            .where(
                and_(
                    Booking.booking_key.in_(validBookingKeys),
                    Environment.id == environmentId
                )
            )
        )
    else:
        return list(
            session.query(Booking.environment, Booking.booking_key, Booking.user_id)
            .join(Environment)
            .where(
                and_(
                    Booking.booking_key.in_(validBookingKeys),
                    Environment.resource_type == resourceTypeId,
                )
            )
        )


# Shares
# -----------------------------------

def addShare(environmentId: int, channelId: str, timestamp: str):
    try:
        newShare = Share(
            environment=environmentId,
            channel_id=channelId,
            timestamp=timestamp
        )
        session.add(newShare)
        session.commit()
    except (PendingRollbackError, IntegrityError):
        session.rollback()
        raise

def getShares(environmentId: int):
    return list(
        session.query(Share.channel_id, Share.timestamp)
        .where(Share.environment == environmentId)
    )