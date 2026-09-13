"""
Fixed responses for query categories that must never reach the LLM
generation step. Keeping these as plain strings (not LLM-generated)
means the safety boundary can't be prompt-engineered away and doesn't
depend on the model behaving -- it's a hard architectural gate.
"""

ADVICE_SEEKING_RESPONSE = (
    "I can share factual, reference information about medicines -- what "
    "they're for, generic equivalents, and officially listed side effects "
    "or interactions. I'm not able to tell you whether you personally "
    "should take a medicine, what dose is right for you, or whether "
    "something explains your symptoms. That needs a doctor or pharmacist "
    "who knows your medical history.\n\n"
    "If you'd like, ask me about a specific medicine by name and I can "
    "tell you what it's officially registered for and its listed generic "
    "equivalents."
)

OUT_OF_SCOPE_RESPONSE = (
    "I'm a medicine information assistant for Pakistan -- I can look up "
    "what a registered drug is for, find its generic equivalents, and "
    "surface official side-effect or interaction information. That "
    "question is outside what I can help with here."
)

CLASSIFIER_ERROR_FALLBACK = (
    "I wasn't able to process that question just now. To be safe, I'd "
    "rather not guess -- could you rephrase it, or ask about a specific "
    "medicine by name? And as always, for anything about your personal "
    "health or treatment, please check with a doctor or pharmacist."
)

# Appended to every generated lookup answer, regardless of content.
SAFETY_FOOTER = (
    "\n\n---\nThis is reference information only, not medical advice. "
    "For guidance specific to you, please consult a doctor or pharmacist."
)
