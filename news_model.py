"""
Data models and schemas for News Items.
Provides Pydantic models for validation, serialization, and API schemas.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, HttpUrl


class NewsItemBase(BaseModel):
    """Base schema with common attributes for news items."""

    ticker: Optional[str] = Field(
        default=None,
        description="Standardized NSE/BSE ticker symbol (e.g. RELIANCE, TCS)",
        max_length=50,
    )
    title: str = Field(
        ...,
        description="Headline / title of the announcement or news item",
        min_length=1,
    )
    description: Optional[str] = Field(
        default=None,
        description="Short description or summary text",
    )
    source: str = Field(
        ...,
        description="Data source: 'bse', 'nse', 'sebi', 'company_ir'",
        max_length=50,
    )
    source_url: Optional[str] = Field(
        default=None,
        description="Original URL to the disclosure or filing document",
    )
    source_id: str = Field(
        ...,
        description="Unique announcement ID from the source exchange/portal",
        max_length=255,
    )
    category: Optional[str] = Field(
        default="general",
        description="Category: 'results', 'board_meeting', 'acquisition', 'dividend', 'agm_egm', 'regulatory', 'general'",
        max_length=100,
    )
    published_at: datetime = Field(
        ...,
        description="Timestamp when disclosure was published by exchange/source",
    )


class NewsItemCreate(NewsItemBase):
    """Schema used when inserting or scraping a new news item."""

    pass


class NewsItemResponse(NewsItemBase):
    """Schema returned by API endpoints."""

    id: UUID = Field(..., description="Unique database UUID")
    scraped_at: datetime = Field(
        ...,
        description="Timestamp when item was ingested into our system",
    )

    class Config:
        from_attributes = True


def categorize_announcement(title: str, description: Optional[str] = None) -> str:
    """
    Infers announcement category based on keywords in title and description.
    """
    text = f"{title} {description or ''}".lower()

    if any(k in text for k in ["financial result", "quarterly result", "audited result", "unaudited result", "q1", "q2", "q3", "q4"]):
        return "financial_results"
    if any(k in text for k in ["board meeting", "outcome of board meeting", "board to consider"]):
        return "board_meeting"
    if any(k in text for k in ["dividend", "interim dividend", "final dividend", "special dividend"]):
        return "dividend"
    if any(k in text for k in ["acquisition", "takeover", "merger", "amalgamation", "joint venture"]):
        return "acquisition_merger"
    if any(k in text for k in ["resignation", "appointment", "cessation", "key managerial"]):
        return "management_change"
    if any(k in text for k in ["bonus", "stock split", "sub-division", "rights issue"]):
        return "corporate_action"
    if any(k in text for k in ["order", "contract", "bagged", "won order", "commercial operation"]):
        return "order_contract"
    if any(k in text for k in ["circular", "regulatory", "penalty", "show cause", "sebi"]):
        return "regulatory"
    if any(k in text for k in ["agm", "egm", "annual general meeting", "extraordinary general meeting"]):
        return "shareholder_meeting"

    return "general"
