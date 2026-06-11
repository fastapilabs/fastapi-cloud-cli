from pydantic import BaseModel

from fastapi_cloud_cli.utils.api import APIClient, DeploymentStatus


class Team(BaseModel):
    id: str
    slug: str
    name: str


class AppResponse(BaseModel):
    id: str
    slug: str
    directory: str | None


class CreateDeploymentResponse(BaseModel):
    id: str
    app_id: str
    slug: str
    status: DeploymentStatus
    dashboard_url: str
    url: str


def _get_teams(client: APIClient) -> list[Team]:
    response = client.get("/teams/")
    response.raise_for_status()

    data = response.json()["data"]

    return [Team.model_validate(team) for team in data]


def _update_app(client: APIClient, app_id: str, directory: str | None) -> AppResponse:
    response = client.patch(
        f"/apps/{app_id}",
        json={"directory": directory},
    )

    response.raise_for_status()

    return AppResponse.model_validate(response.json())


def _create_app(
    client: APIClient, team_id: str, app_name: str, directory: str | None
) -> AppResponse:
    response = client.post(
        "/apps/",
        json={"name": app_name, "team_id": team_id, "directory": directory},
    )

    response.raise_for_status()

    return AppResponse.model_validate(response.json())


def _create_deployment(client: APIClient, app_id: str) -> CreateDeploymentResponse:
    response = client.post(f"/apps/{app_id}/deployments/")
    response.raise_for_status()

    return CreateDeploymentResponse.model_validate(response.json())


def _get_app(client: APIClient, app_id: str) -> AppResponse | None:
    response = client.get(f"/apps/{app_id}")

    if response.status_code == 404:
        return None

    response.raise_for_status()

    data = response.json()

    return AppResponse.model_validate(data)


def _get_apps(client: APIClient, team_id: str) -> list[AppResponse]:
    response = client.get("/apps/", params={"team_id": team_id})
    response.raise_for_status()

    data = response.json()["data"]

    return [AppResponse.model_validate(app) for app in data]
