import yaml
from pydantic import BaseModel

from config.auth import ShioajiAuth


class Config(BaseModel):
    shioaji_auth: ShioajiAuth

    @classmethod
    def from_yaml(cls, file_path: str) -> "Config":
        with open(file_path, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
        return cls(**data)
