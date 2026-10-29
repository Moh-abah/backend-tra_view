# app/schemas/user.py
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    username: str
    full_name: Optional[str] = None

class UserCreate(UserBase):
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None

class UserInDB(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    is_verified: bool
    is_superuser: bool
    created_at: datetime
    updated_at: Optional[datetime]
    last_login: Optional[datetime]

class UserResponse(UserInDB):
    pass

class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: Optional[str] = None

class TokenData(BaseModel):
    username: Optional[str] = None
    user_id: Optional[int] = None
    permissions: List[str] = []


class RefreshRequest(BaseModel):
    """Body for POST /users/refresh."""

    refresh_token: str


class ChangePasswordRequest(BaseModel):
    """Body for POST /users/me/change-password."""

    old_password: str
    new_password: str = Field(min_length=8)


class PasswordResetRequest(BaseModel):
    """Body for POST /users/request-password-reset."""

    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Body for POST /users/reset-password."""

    token: str
    new_password: str = Field(min_length=8)


class MessageResponse(BaseModel):
    """Generic message payload."""

    message: str

# app/schemas/settings.py
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

class StrategyBase(BaseModel):
    name: str
    description: Optional[str] = None
    strategy_config: Dict[str, Any]
    category: str = "custom"
    tags: List[str] = Field(default_factory=list)
    is_public: bool = False
    is_default: bool = False

class StrategyCreate(StrategyBase):
    pass

class StrategyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    strategy_config: Optional[Dict[str, Any]] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    is_public: Optional[bool] = None
    is_default: Optional[bool] = None
    backtest_results: Optional[Dict[str, Any]] = None
    performance_score: Optional[float] = None

class StrategyResponse(StrategyBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class IndicatorBase(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    indicator_code: str
    indicator_type: str = "custom"
    parameters: Dict[str, Any] = Field(default_factory=dict)
    category: str = "custom"
    is_public: bool = False
    is_active: bool = True

class IndicatorCreate(IndicatorBase):
    pass

class IndicatorUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    indicator_code: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    category: Optional[str] = None
    is_public: Optional[bool] = None
    is_active: Optional[bool] = None

class IndicatorResponse(IndicatorBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class WatchlistBase(BaseModel):
    name: str
    description: Optional[str] = None
    symbols: List[str] = Field(default_factory=list)
    market: str = "crypto"
    is_default: bool = False
    color: str = "#3B82F6"

class WatchlistCreate(WatchlistBase):
    pass

class WatchlistUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    symbols: Optional[List[str]] = None
    market: Optional[str] = None
    is_default: Optional[bool] = None
    color: Optional[str] = None

class WatchlistResponse(WatchlistBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class FilterSettingsBase(BaseModel):
    name: str
    description: Optional[str] = None
    filter_criteria: Dict[str, Any]
    market: str = "crypto"
    is_default: bool = False

class FilterSettingsCreate(FilterSettingsBase):
    pass

class FilterSettingsUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    filter_criteria: Optional[Dict[str, Any]] = None
    market: Optional[str] = None
    is_default: Optional[bool] = None
    last_results: Optional[Dict[str, Any]] = None

class FilterSettingsResponse(FilterSettingsBase):
    id: int
    user_id: int
    last_run: Optional[datetime]
    last_results: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class PortfolioBase(BaseModel):
    name: str
    description: Optional[str] = None
    initial_capital: float = 10000.0
    currency: str = "USD"
    risk_level: str = "medium"
    strategy_allocation: Dict[str, float] = Field(default_factory=dict)

class PortfolioCreate(PortfolioBase):
    pass

class PortfolioUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    current_capital: Optional[float] = None
    risk_level: Optional[str] = None
    strategy_allocation: Optional[Dict[str, float]] = None

class PortfolioResponse(PortfolioBase):
    id: int
    user_id: int
    current_capital: float
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class APIKeyBase(BaseModel):
    name: str
    exchange: str
    permissions: List[str] = ["read"]

class APIKeyCreate(APIKeyBase):
    api_key: str
    api_secret: str

class APIKeyResponse(APIKeyBase):
    id: int
    user_id: int
    is_active: bool
    last_used: Optional[datetime]
    created_at: datetime
    
    class Config:
        from_attributes = True