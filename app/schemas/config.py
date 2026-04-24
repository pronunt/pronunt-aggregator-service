from pydantic import BaseModel

from app.schemas.pull_request import ServiceCriticality


class ConfigServiceResponse(BaseModel):
    id: str
    service_name: str
    repository_full_name: str
    display_name: str
    description: str | None = None
    criticality: ServiceCriticality
    owners: list[str]
    tags: list[str]


class ConfigImpactResponse(BaseModel):
    service_name: str
    direct_dependencies: list[str]
    downstream_services: list[str]
