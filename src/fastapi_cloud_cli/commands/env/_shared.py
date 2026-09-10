from rich.text import Text

from fastapi_cloud_cli.api import EnvironmentVariable

ENV_VAR_VALUE_MAX_LENGTH = 40


def _find_environment_variable(
    environment_variables: list[EnvironmentVariable], name: str
) -> EnvironmentVariable | None:
    return next(
        (
            environment_variable
            for environment_variable in environment_variables
            if environment_variable.name == name
        ),
        None,
    )


def _format_env_var_value(env_var: EnvironmentVariable) -> Text:
    if env_var.value is None:
        placeholder = "[secret]" if env_var.is_secret else "-"

        return Text(placeholder, style="dim")

    value = env_var.value.replace("\r", "\\r").replace("\n", "\\n")

    if len(value) > ENV_VAR_VALUE_MAX_LENGTH:
        value = f"{value[: ENV_VAR_VALUE_MAX_LENGTH - 3]}..."

    return Text(value)
