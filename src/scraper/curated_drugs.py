"""
Curated list of common generic medicine names for targeted scraping.

Scope decision: rather than brute-force enumerating DRAP's full
~130,000 registration-number space (estimated ~38 hours at a polite
rate), this targets commonly prescribed/OTC generics by name via the
search endpoint. This trades exhaustive coverage for fast, demo-quality
breadth across major therapeutic classes -- documented as a deliberate
scope decision, not a hidden shortcut.
"""

COMMON_GENERICS = [
    # Analgesics / antipyretics / NSAIDs
    "paracetamol", "ibuprofen", "aspirin", "diclofenac", "naproxen",
    "mefenamic acid", "ketoprofen", "tramadol", "piroxicam",

    # Antibiotics
    "amoxicillin", "azithromycin", "ciprofloxacin", "metronidazole",
    "doxycycline", "erythromycin", "clarithromycin", "levofloxacin",
    "moxifloxacin", "cefixime", "ceftriaxone", "cephradine",
    "clindamycin", "co-amoxiclav",

    # Diabetes
    "metformin", "glimepiride", "gliclazide", "pioglitazone",
    "insulin glargine", "insulin regular",

    # Cardiovascular
    "atorvastatin", "simvastatin", "rosuvastatin", "amlodipine",
    "losartan", "telmisartan", "valsartan", "enalapril", "atenolol",
    "bisoprolol", "carvedilol", "furosemide", "hydrochlorothiazide",
    "spironolactone", "clopidogrel", "warfarin", "digoxin",
    "isosorbide", "nifedipine",

    # GI
    "omeprazole", "pantoprazole", "esomeprazole", "ranitidine",
    "domperidone", "metoclopramide", "ondansetron", "loperamide",

    # Respiratory / allergy
    "cetirizine", "loratadine", "chlorpheniramine", "salbutamol",
    "montelukast", "budesonide", "dextromethorphan",

    # Steroids / anti-inflammatory
    "prednisolone", "dexamethasone",

    # Mental health
  "diazepam", "alprazolam", "sertraline", "fluoxetine",
    "amitriptyline",

    # Thyroid / hormones
    "levothyroxine",

    # Supplements commonly registered as drugs
    "folic acid", "ferrous sulfate", "calcium carbonate",

    # Other common
    "tranexamic acid", "allopurinol", "colchicine", "methotrexate",
    "fluconazole", "gentamicin",
]
