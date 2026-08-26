from typing import Literal

Provider = Literal["neon", "redis", "supabase", "logfire"]

PROVIDER_NAMES: dict[Provider, str] = {
    "neon": "Neon",
    "redis": "Redis Cloud",
    "supabase": "Supabase",
    "logfire": "Logfire",
}
