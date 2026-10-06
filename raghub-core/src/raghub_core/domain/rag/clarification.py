import re
import unicodedata
from dataclasses import dataclass

from raghub_core.domain.rag.intent import IntentAction, IntentDecision

ADMISSIONS_PROFILE = "admissions"
_ALLOWED_MODES = {"off", "conservative", "proactive"}
_SLOT_ORDER = ("year", "major", "admission_round", "method", "program_type", "info_type")
_MAJOR_TERMS = (
    "cntt",
    "cong nghe thong tin",
    "ke toan",
    "ngon ngu anh",
    "vi mach",
    "ban dan",
)
_PROGRAM_ENGLISH_TERMS = (
    "tieng anh",
    "chuong trinh anh",
    "ctdt bang tieng anh",
)
_SCORE_TERMS = (
    "diem chuan",
    "diem san",
    "nguong",
    "co do khong",
    "do khong",
)


def normalize_query(text: str) -> str:
    text = text.casefold().replace("\u0111", "d")
    return "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )


def _tokens(normalized: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalized)


@dataclass(frozen=True)
class SlotProfile:
    name: str
    slots: tuple[str, ...]


ADMISSIONS_SLOT_PROFILE = SlotProfile(ADMISSIONS_PROFILE, _SLOT_ORDER)


class ClarificationPolicy:
    def __init__(self, *, confidence_threshold: float = 0.22) -> None:
        self.confidence_threshold = confidence_threshold

    def evaluate(
        self,
        question: str,
        *,
        domain_profile: str = ADMISSIONS_PROFILE,
        mode: str = "conservative",
        clarifying_turns: int = 0,
        max_clarifying_turns: int = 1,
        retrieval_confidence: float | None = None,
    ) -> IntentDecision:
        if domain_profile != ADMISSIONS_PROFILE:
            return IntentDecision(IntentAction.ANSWER_NOW, reason="unsupported_profile")
        if mode not in _ALLOWED_MODES:
            raise ValueError("mode must be one of: off, conservative, proactive")
        if mode == "off":
            return IntentDecision(IntentAction.ANSWER_NOW, reason="clarification_disabled")

        normalized = normalize_query(question)
        tokens = _tokens(normalized)
        if self._is_injection(normalized):
            return IntentDecision(
                IntentAction.REFUSE_OR_REDIRECT,
                reason="prompt_injection",
                message="Mình chỉ có thể trả lời dựa trên tài liệu được cung cấp.",
            )
        if self._is_out_of_scope(normalized):
            return IntentDecision(
                IntentAction.REFUSE_OR_REDIRECT,
                reason="out_of_scope",
                message="Câu hỏi này nằm ngoài phạm vi tài liệu hiện có.",
            )

        detected = self.detect_slots(question)
        if retrieval_confidence is not None and retrieval_confidence < self.confidence_threshold:
            return self._clarify_or_answer(
                ("info_type",),
                reason="low_retrieval_confidence",
                clarifying_turns=clarifying_turns,
                max_clarifying_turns=max_clarifying_turns,
            )

        missing = self._missing_slots(detected, tokens=tokens, mode=mode)
        if missing:
            return self._clarify_or_answer(
                missing,
                reason="missing_required_slot",
                clarifying_turns=clarifying_turns,
                max_clarifying_turns=max_clarifying_turns,
            )
        return IntentDecision(IntentAction.ANSWER_NOW, reason="sufficient_context")

    def detect_slots(self, question: str) -> dict[str, str]:
        normalized = normalize_query(question)
        slots: dict[str, str] = {}
        year = re.search(r"\b20\d{2}\b", normalized)
        if year:
            slots["year"] = year.group(0)
        if any(term in normalized for term in _MAJOR_TERMS):
            slots["major"] = "major"
        if any(term in normalized for term in ("dot 2", "dot hai", "bo sung")):
            slots["admission_round"] = "round"
        if any(term in normalized for term in ("pt1", "pt2", "pt3", "pt4", "pt5", "phuong thuc")):
            slots["method"] = "method"
        if any(term in normalized for term in _PROGRAM_ENGLISH_TERMS):
            slots["program_type"] = "english"
        elif any(term in normalized for term in ("chuong trinh chuan", "he chuan", "dai tra")):
            slots["program_type"] = "standard"
        info_type = self._info_type(normalized)
        if info_type:
            slots["info_type"] = info_type
        return slots

    def _missing_slots(
        self,
        slots: dict[str, str],
        *,
        tokens: list[str],
        mode: str,
    ) -> tuple[str, ...]:
        info_type = slots.get("info_type")
        missing: list[str] = []
        if not info_type:
            if mode == "proactive" and len(tokens) <= 4:
                return ("info_type",)
            return ()
        if info_type == "tuition":
            if "program_type" not in slots and "major" not in slots:
                missing.extend(["program_type", "major"])
        elif info_type == "score":
            if self._asks_personal_admission(tokens):
                for slot in ("major", "method"):
                    if slot not in slots:
                        missing.append(slot)
            else:
                for slot in ("major", "year"):
                    if slot not in slots:
                        missing.append(slot)
        elif info_type == "schedule":
            if "year" not in slots:
                missing.append("year")
        elif info_type == "method":
            if mode == "proactive" and "year" not in slots:
                missing.append("year")
        return tuple(dict.fromkeys(missing))

    def _clarify_or_answer(
        self,
        missing: tuple[str, ...],
        *,
        reason: str,
        clarifying_turns: int,
        max_clarifying_turns: int,
    ) -> IntentDecision:
        if clarifying_turns >= max_clarifying_turns:
            return IntentDecision(IntentAction.ANSWER_NOW, reason="clarification_limit_reached")
        suggestions = self._suggestions(missing)
        return IntentDecision(
            IntentAction.CLARIFY,
            missing_slots=missing,
            suggestions=suggestions,
            reason=reason,
            message=self._message(missing),
        )

    def _info_type(self, normalized: str) -> str | None:
        if any(term in normalized for term in ("hoc phi", "le phi", "phi bao nhieu")):
            return "tuition"
        if any(term in normalized for term in _SCORE_TERMS):
            return "score"
        if any(term in normalized for term in ("dang ky", "thoi gian", "cong bo", "han nop")):
            return "schedule"
        if any(term in normalized for term in ("phuong thuc", "pt1", "pt2", "pt3", "pt4", "pt5")):
            return "method"
        if "hoc bong" in normalized:
            return "scholarship"
        if "chi tieu" in normalized:
            return "quota"
        return None

    def _is_injection(self, normalized: str) -> bool:
        return any(
            term in normalized
            for term in (
                "bo qua tai lieu",
                "ignore previous",
                "ignore instructions",
                "noi toi do chac",
                "tra loi sai",
                "khong can can cu",
            )
        )

    def _is_out_of_scope(self, normalized: str) -> bool:
        return any(
            term in normalized
            for term in ("bitcoin", "thoi tiet", "banh mi", "lich thi hoc ky", "y khoa")
        )

    def _asks_personal_admission(self, tokens: list[str]) -> bool:
        joined = " ".join(tokens)
        return "toi co do khong" in joined or "em co do khong" in joined or "co do khong" in joined

    def _suggestions(self, missing: tuple[str, ...]) -> tuple[str, ...]:
        values: list[str] = []
        if "program_type" in missing:
            values.extend(["Chương trình chuẩn", "Chương trình tiếng Anh"])
        if "major" in missing:
            values.extend(["Công nghệ thông tin", "Kế toán", "Ngôn ngữ Anh"])
        if "year" in missing:
            values.append("Năm 2026")
        if "method" in missing:
            values.extend(["PT1", "PT2", "PT3", "PT4", "PT5"])
        if "info_type" in missing:
            values.extend(["Học phí", "Điểm chuẩn", "Phương thức tuyển sinh"])
        return tuple(dict.fromkeys(values))

    def _message(self, missing: tuple[str, ...]) -> str:
        labels = {
            "year": "năm tuyển sinh",
            "major": "ngành/chương trình",
            "admission_round": "đợt tuyển sinh",
            "method": "phương thức xét tuyển",
            "program_type": "chương trình chuẩn hay tiếng Anh",
            "info_type": "nội dung bạn muốn hỏi",
        }
        wanted = ", ".join(labels.get(slot, slot) for slot in missing)
        return f"Bạn vui lòng cho biết thêm {wanted} để mình trả lời đúng hơn."