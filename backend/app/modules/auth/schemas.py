from pydantic import BaseModel, EmailStr, Field


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    turnstile_token: str = Field(default="", max_length=2048)


class EmailRequest(BaseModel):
    email: EmailStr
    turnstile_token: str = Field(default="", max_length=2048)


class PasswordResetRequest(BaseModel):
    token: str = Field(min_length=40)
    new_password: str = Field(min_length=8, max_length=128)
    turnstile_token: str = Field(default="", max_length=2048)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    message: str


class CurrentUserResponse(BaseModel):
    id: str
    email: EmailStr
    email_verified: bool


class AuthSecurityConfigResponse(BaseModel):
    turnstile_enabled: bool
    turnstile_site_key: str
