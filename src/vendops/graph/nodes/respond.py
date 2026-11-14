from typing import Any

from vendops.contracts.enums import ActionType, LanguageCode
from vendops.contracts.state import VendOpsState
from vendops.graph.llm import BaseLLMAdapter


def compose_grounded_reply_deterministic(
    invoice_id: str,
    action: ActionType,
    amount: float,
    rationale: str,
    language: str,
) -> str:
    """Deterministically compose grounded vendor responses matching language style."""
    match language:
        case LanguageCode.HINGLISH.value:
            match action:
                case ActionType.RELEASE_PAYMENT:
                    return (
                        f"Namaste! Aapke invoice {invoice_id} ka verification poora ho gaya hai. "
                        f"3-way match successfully verify ho chuka hai aur ${amount:,.2f} ka payment "
                        f"release kar diya gaya hai. Kripya 2-3 business days me bank account check karein. Dhanyawad!"
                    )
                case ActionType.PARTIAL_PAYMENT:
                    return (
                        f"Namaste! Aapke invoice {invoice_id} ke verification ke baad partial payment "
                        f"of ${amount:,.2f} release kar diya gaya hai. {rationale} "
                        f"Kripya baaki amount ke liye credit note issue karein ya details check karein. Dhanyawad!"
                    )
                case ActionType.CREDIT_NOTE:
                    return (
                        f"Namaste! Invoice {invoice_id} me price/qty discrepancy mili hai. "
                        f"${amount:,.2f} ka credit note issue karne ka request approve hua hai. Dhanyawad!"
                    )
                case ActionType.REPLACEMENT:
                    return (
                        f"Namaste! Invoice {invoice_id} ke items receiving pe reject ho gaye the. "
                        f"Aap se request hai ki replacement delivery dispatch karein taaki payment process ho sake. Dhanyawad!"
                    )
                case ActionType.REJECT:
                    return (
                        f"Namaste! Aapka invoice {invoice_id} dispute reject kar diya gaya hai. "
                        f"Karan: {rationale}. Agar koi sawal ho toh contact karein. Dhanyawad!"
                    )
                case ActionType.ESCALATE:
                    return (
                        f"Namaste! Invoice {invoice_id} ki details verify karne ke liye case internal team "
                        f"ko escalate kar diya gaya hai. Hamari team jald hi aapse contact karegi. Dhanyawad!"
                    )

        case LanguageCode.HINDI.value:
            match action:
                case ActionType.RELEASE_PAYMENT:
                    return (
                        f"नमस्ते! आपके इनवॉइस {invoice_id} का सत्यापन पूर्ण हो गया है। "
                        f"पूर्ण 3-वे मिलान के बाद ${amount:,.2f} का भुगतान जारी कर दिया गया है। धन्यवाद!"
                    )
                case ActionType.PARTIAL_PAYMENT:
                    return (
                        f"नमस्ते! आपके इनवॉइस {invoice_id} के लिए ${amount:,.2f} का आंशिक भुगतान स्वीकृत किया गया है। "
                        f"{rationale} धन्यवाद!"
                    )
                case _:
                    return (
                        f"नमस्ते! आपके इनवॉइस {invoice_id} पर {action.value} की कार्रवाई की गई है। "
                        f"विवरण: {rationale}। धन्यवाद!"
                    )

        case _:
            # Standard English response
            match action:
                case ActionType.RELEASE_PAYMENT:
                    return (
                        f"Dear Vendor, your inquiry regarding invoice {invoice_id} has been reviewed. "
                        f"The 3-way match has been verified successfully, and payment of ${amount:,.2f} "
                        f"has been released. Please allow 2-3 business days for fund settlement."
                    )
                case ActionType.PARTIAL_PAYMENT:
                    return (
                        f"Dear Vendor, partial payment of ${amount:,.2f} has been authorized for invoice "
                        f"{invoice_id}. Rationale: {rationale}."
                    )
                case ActionType.REJECT:
                    return (
                        f"Dear Vendor, your dispute for invoice {invoice_id} has been rejected. "
                        f"Reason: {rationale}."
                    )
                case ActionType.ESCALATE:
                    return (
                        f"Dear Vendor, invoice {invoice_id} requires additional review and has been "
                        f"escalated to our finance and procurement team. We will follow up shortly."
                    )
                case _:
                    return (
                        f"Dear Vendor, resolution action {action.value} has been recorded for invoice "
                        f"{invoice_id} for amount ${amount:,.2f}. Rationale: {rationale}."
                    )

    return f"Response for {invoice_id}: {action.value} - ${amount:,.2f}."


def respond_node(
    state: VendOpsState, llm: BaseLLMAdapter | None = None
) -> dict[str, Any]:
    """Response node: compose grounded vendor reply matching the input language style."""
    proposal = state.get("proposal")
    match_res = state.get("match_result")
    lang = state.get("language_detected", LanguageCode.ENGLISH.value)

    invoice_id = "INV-20240456"
    if match_res and match_res.invoice_id:
        invoice_id = match_res.invoice_id
    elif state.get("provenance_ids"):
        invs = [i for i in state["provenance_ids"] if i.startswith("INV-")]
        if invs:
            invoice_id = invs[0]

    action = proposal.action if proposal else ActionType.ESCALATE
    amount = proposal.amount if proposal else 0.0
    rationale = proposal.rationale if proposal else "Under review"

    if llm is not None:
        try:
            prompt = (
                f"Compose a grounded vendor response matching the language style '{lang}'.\n"
                f"Invoice ID: {invoice_id}\n"
                f"Action: {action.value}\n"
                f"Amount: {amount}\n"
                f"Rationale: {rationale}\n"
                f"Rule: Ground your response strictly on the factual details provided above."
            )
            reply = llm.generate(prompt)
            return {"response": reply}
        except (ValueError, RuntimeError, TypeError):
            reply = compose_grounded_reply_deterministic(
                invoice_id=invoice_id,
                action=action,
                amount=amount,
                rationale=rationale,
                language=lang,
            )
            return {"response": reply}

    reply = compose_grounded_reply_deterministic(
        invoice_id=invoice_id,
        action=action,
        amount=amount,
        rationale=rationale,
        language=lang,
    )
    return {"response": reply}
