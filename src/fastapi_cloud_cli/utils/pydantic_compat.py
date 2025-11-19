from typing import Any, Dict, Type, TypeVar

from pydantic import BaseModel
from pydantic.version import VERSION as PYDANTIC_VERSION

PYDANTIC_VERSION_MINOR_TUPLE = tuple(int(x) for x in PYDANTIC_VERSION.split(".")[:2])
PYDANTIC_V2 = PYDANTIC_VERSION_MINOR_TUPLE[0] == 2


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
