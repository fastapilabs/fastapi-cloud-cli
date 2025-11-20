from typing import Any, Dict, Generic, Type, TypeVar

from pydantic import BaseModel
from pydantic.version import VERSION as PYDANTIC_VERSION

PYDANTIC_VERSION_MINOR_TUPLE = tuple(int(x) for x in PYDANTIC_VERSION.split(".")[:2])
PYDANTIC_V2 = PYDANTIC_VERSION_MINOR_TUPLE[0] == 2


T = TypeVar("T")
Model = TypeVar("Model", bound=BaseModel)


def model_validate(model_class: Type[Model], data: Dict[Any, Any]) -> Model:
    if PYDANTIC_V2:
        return model_class.model_validate(data)  # type: ignore[no-any-return, unused-ignore, attr-defined]
    else:
        return model_class.parse_obj(data)  # type: ignore[no-any-return, unused-ignore, attr-defined]


def model_validate_json(model_class: Type[Model], data: str) -> Model:
    if PYDANTIC_V2:
        return model_class.model_validate_json(data)  # type: ignore[no-any-return, unused-ignore, attr-defined]
    else:
        return model_class.parse_raw(data)  # type: ignore[no-any-return, unused-ignore, attr-defined]


def model_dump(obj: BaseModel, **kwargs: Any) -> Dict[Any, Any]:
    if PYDANTIC_V2:
        return obj.model_dump(**kwargs)  # type: ignore[no-any-return, unused-ignore, attr-defined]
    else:
        return obj.dict(**kwargs)  # type: ignore[no-any-return, unused-ignore, attr-defined]


def model_dump_json(obj: BaseModel) -> str:
    if PYDANTIC_V2:
        return obj.model_dump_json()  # type: ignore[no-any-return, unused-ignore, attr-defined]
    else:
        # Use compact separators to match Pydantic v2's output format
        return obj.json(separators=(",", ":"))  # type: ignore[no-any-return, unused-ignore, attr-defined]


class TypeAdapter(Generic[T]):
    def __init__(self, type_: Type[T]) -> None:
        self.type_ = type_

        if PYDANTIC_V2:
            from pydantic import (  # type: ignore[attr-defined, unused-ignore]
                TypeAdapter as PydanticTypeAdapter,
            )

            self._adapter = PydanticTypeAdapter(type_)
        else:
            self._adapter = None  # type: ignore[assignment, unused-ignore]

    def validate_python(self, value: Any) -> T:
        """Validate a Python object against the type."""
        if PYDANTIC_V2:
            return self._adapter.validate_python(value)  # type: ignore[no-any-return, union-attr, unused-ignore]
        else:
            from pydantic import parse_obj_as

            return parse_obj_as(self.type_, value)  # type: ignore[no-any-return, unused-ignore]

    def validate_json(self, value: str) -> T:
        """Validate a JSON string against the type."""
        if PYDANTIC_V2:
            return self._adapter.validate_json(value)  # type: ignore[no-any-return, union-attr, unused-ignore]
        else:
            from pydantic import parse_raw_as

            return parse_raw_as(self.type_, value)  # type: ignore[no-any-return, unused-ignore, operator]
