from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mqtt_host: str = "mqtt-broker"
    mqtt_port: int = 1883
    mqtt_user: str = "testuser"
    mqtt_password: str = "testpass"
    sim_interval_ms: int = 10_000
    sim_asset_path: str = "aeronorth/windfarm_north/sector_a/turbine_03"
