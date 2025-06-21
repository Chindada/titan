from pydantic import BaseModel


class APISecret(BaseModel):
    api_key: str
    api_key_secret: str


class CASecret(BaseModel):
    person_id: str
    ca_path: str
    ca_password: str


class ShioajiAuth(BaseModel):
    api_secret: APISecret
    ca_secret: CASecret

    @property
    def api_key(self) -> str:
        return self.api_secret.api_key

    @property
    def api_key_secret(self) -> str:
        return self.api_secret.api_key_secret

    @property
    def person_id(self) -> str:
        return self.ca_secret.person_id

    @property
    def ca_path(self) -> str:
        return self.ca_secret.ca_path

    @property
    def ca_password(self) -> str:
        return self.ca_secret.ca_password
