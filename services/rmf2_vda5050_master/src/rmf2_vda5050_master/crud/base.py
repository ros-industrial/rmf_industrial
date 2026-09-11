from typing import Any, Generic, TypeVar

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy.orm import Session

ModelType = TypeVar("ModelType", bound=Any)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """Base class for the database CRUD capability."""

    def __init__(self, model: type[ModelType]):
        """
        Make CRUD object with methods to Create, Read, Update, Delete (CRUD).

        Referenced from
        <https://github.com/tiangolo/full-stack-fastapi-postgresql/blob/
        master/src/backend/app/app/crud/base.py>

        :param model: A SQLAlchemy model class
        :param schema: A Pydantic model (schema) class
        """
        self.model = model

    def get(self, db: Session, id: Any) -> ModelType | None:
        """
        Get an object based on the ID.

        :param db: The database connection.
        :param id: The ID of the object.
        :returns: The database object.
        """
        return db.query(self.model).filter(self.model.id == id).first()

    def get_from_attr(self, db: Session, attr: str, value: Any) -> ModelType:
        """
        Get an Object via when its attribute matches the specified value.

        :param db: The database connection
        :param str attr: The attribute name
        :param value: the value of the attribute to be matched
        :returns: The database object.
        """
        if not hasattr(self.model, attr):
            raise AttributeError(
                f"Attribute {attr} does not exist in {type(self.model)}"
            )

        return db.query(self.model).filter(getattr(self.model, attr) == value).first()

    def get_multi(
        self, db: Session, *, skip: int = 0, limit: int = 100
    ) -> list[ModelType]:
        """
        Get multiple objects.

        :param db: The database connection.
        :param int skip: Number of rows to skip.
        :param int limit: Limit of rows to return.
        :returns: The database objects.
        """
        return db.query(self.model).offset(skip).limit(limit).all()

    def get_multi_from_attr(
        self, db: Session, filters: dict[str, Any], *, skip: int = 0, limit: int = 100
    ) -> list[ModelType]:
        """
        Get multiple Objects when its attribute matches the specified value.

        :param db: The database connection
        :param filter: The attribute name and
            the value of the attribute to be matched
        :param int skip: Number of rows to skip.
        :param int limit: Limit of rows to return.
        :returns: The database objects.
        """
        db_query = db.query(self.model)
        for attr, value in filters.items():
            if not hasattr(self.model, attr):
                raise AttributeError(
                    f"Attribute {attr} does not exist in {type(self.model)}"
                )
            db_query = db_query.filter(getattr(self.model, attr) == value)
        return db_query.offset(skip).limit(limit).all()

    def create(self, db: Session, *, obj_in: CreateSchemaType) -> ModelType:
        """
        Create an object.

        :param db: The database connection.
        :param obj_in: The object creation request.
        :returns: The database object created.
        """
        obj_in_data = obj_in if isinstance(obj_in, dict) else jsonable_encoder(obj_in)
        db_obj = self.model(**obj_in_data)  # type: ignore
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(
        self,
        db: Session,
        *,
        db_obj: ModelType,
        obj_in: UpdateSchemaType | dict[str, Any],
    ) -> ModelType:
        """
        Update an object.

        :param db: The database connection.
        :param db_obj: The database object to update.
        :param obj_in: The object update request.
        :returns: The database object updated.
        """
        update_data = (
            obj_in if isinstance(obj_in, dict) else obj_in.dict(exclude_unset=True)
        )
        for field in update_data:
            setattr(db_obj, field, update_data[field])
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def remove(self, db: Session, *, db_obj: ModelType) -> bool:
        """
        Remove an object.

        :param db: The database connection.
        :param id: The ID of the object.
        :returns: The database object removed.
        """
        db.delete(db_obj)
        db.commit()
        return True
