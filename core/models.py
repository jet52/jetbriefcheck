"""Data models for the appellate brief compliance checker."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class BriefType(Enum):
    APPELLANT = "appellant"
    APPELLEE = "appellee"
    REPLY = "reply"
    CROSS_APPEAL = "cross_appeal"
    AMICUS = "amicus"
    UNKNOWN = "unknown"


class Severity(Enum):
    """Severity of a failed check, ordered by impact."""
    NOTE = "note"
    CORRECTION = "correction"
    REJECT = "reject"


class Recommendation(Enum):
    ACCEPT = "accept"
    CORRECTION_LETTER = "correction_letter"
    REJECT = "reject"


@dataclass
class CheckResult:
    check_id: str
    name: str
    rule: str
    passed: bool
    severity: Severity
    message: str
    details: Optional[str] = None
    applicable: bool = True  # False if this check doesn't apply to the brief type
    pages: Optional[list[int]] = None  # Page numbers with issues (if applicable)

    @property
    def failed(self) -> bool:
        return not self.passed and self.applicable


@dataclass
class PageInfo:
    """Extracted information about a single PDF page."""
    page_number: int  # 0-indexed
    width_inches: float
    height_inches: float
    left_margin_inches: float
    right_margin_inches: float
    top_margin_inches: float
    bottom_margin_inches: float
    fonts: list[dict] = field(default_factory=list)  # [{"name": ..., "size": ...}]
    line_spacing: Optional[float] = None  # approximate pts between baselines
    text: str = ""
    has_page_number_bottom: bool = False
    page_number_text: Optional[str] = None  # the printed page number if found


@dataclass
class BriefMetadata:
    """Aggregated metadata from the full PDF."""
    brief_type: BriefType = BriefType.UNKNOWN
    total_pages: int = 0
    body_pages: int = 0  # excluding addendum
    addendum_start_page: Optional[int] = None
    cover_text: str = ""
    full_text: str = ""
    pages: list[PageInfo] = field(default_factory=list)
    min_font_size: Optional[float] = None
    predominant_font: Optional[str] = None
    predominant_font_size: Optional[float] = None
    has_double_spacing: bool = True
    word_count: int = 0


@dataclass
class ComplianceReport:
    brief_type: BriefType
    recommendation: Recommendation
    results: list[CheckResult] = field(default_factory=list)
    metadata: Optional[BriefMetadata] = None
    claude_reasoning: str = ""
    report_id: str = ""
    case_number: str = ""       # e.g. "20990001"
    case_title: str = ""        # e.g. "Example v. Case et al."
    brief_label: str = ""       # e.g. "Amended Brief of Defendant-Appellant"
    pdf_filename: str = ""      # original PDF filename
    pymupdf_used: bool = True   # Whether PyMuPDF was used for mechanical checks

    @property
    def failed_checks(self) -> list[CheckResult]:
        return [r for r in self.results if r.failed]

    @property
    def passed_checks(self) -> list[CheckResult]:
        return [r for r in self.results if r.passed and r.applicable]

    @property
    def inapplicable_checks(self) -> list[CheckResult]:
        return [r for r in self.results if not r.applicable]

    @property
    def reject_failures(self) -> list[CheckResult]:
        return [r for r in self.failed_checks if r.severity == Severity.REJECT]

    @property
    def correction_failures(self) -> list[CheckResult]:
        return [r for r in self.failed_checks if r.severity == Severity.CORRECTION]

    @property
    def note_failures(self) -> list[CheckResult]:
        return [r for r in self.failed_checks if r.severity == Severity.NOTE]
