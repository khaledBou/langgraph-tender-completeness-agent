"""Synthetic documents used to build the evaluation cases.

Everything here is invented. Company, people and amounts are fictional.
"""

FILLER_PARAGRAPH = (
    "This paragraph is part of the general terms of the consultation. It describes the "
    "obligations of the parties, the payment schedule, the penalties for late delivery and "
    "the insurance obligations of the contractor during the execution of the works. "
)


def dc1(signed: bool = True, extra: str = "") -> str:
    signature = "Signed in Nantes on 2 November 2026\nMarie Dupont, Managing Director" if signed else ""
    return f"""APPLICATION LETTER (DC1)

Contracting authority: City of Nantes, public works department
Procedure: Maintenance of municipal buildings, lot 2 (electrical works)

Candidate: Volt Services SAS, 12 rue des Forges, 44000 Nantes
SIRET: 812 345 678 00021

The candidate applies for lot 2 and declares that it is not subject to any exclusion from procurement procedures.
{extra}
{signature}
"""


def dc2(with_turnover: bool = True) -> str:
    turnover = """Turnover of the last three financial years:
2023: 2,350,000 EUR
2024: 2,710,000 EUR
2025: 3,020,000 EUR"""
    if not with_turnover:
        turnover = "Turnover of the last three financial years: to be completed"
    return f"""CANDIDATE DECLARATION (DC2)

Candidate: Volt Services SAS
Legal form: Simplified joint stock company
Share capital: 150,000 EUR

{turnover}

Average staff over the last three years: 24 people, including 15 qualified electricians.

Signed in Nantes on 2 November 2026
Marie Dupont, Managing Director
"""


def kbis(issued: str = "20 October 2026") -> str:
    return f"""COMPANY REGISTRATION EXTRACT
Registry of commerce and companies of Nantes

Company name: VOLT SERVICES
Legal form: SAS
Registration number: 812 345 678 R.C.S. Nantes
Registered office: 12 rue des Forges, 44000 Nantes
Activity: Electrical installation works (NAF 43.21A)
Managing director: Marie DUPONT

Extract issued on {issued}
"""


def insurance(
    period: str = "from 1 January 2026 to 31 December 2026", issued: str = "15 January 2026"
) -> str:
    return f"""INSURANCE CERTIFICATE

Insurer: Atlantique Assurances
Policyholder: Volt Services SAS, 12 rue des Forges, 44000 Nantes
Policy number: RC-2026-77412

We certify that the policyholder holds a professional liability insurance policy covering
electrical installation and maintenance works, for the period {period}.

Issued in Nantes on {issued}
"""


def insurance_cancelled() -> str:
    return """NOTICE OF CANCELLATION

Insurer: Atlantique Assurances
Policyholder: Volt Services SAS
Policy number: RC-2026-77412

We inform the policyholder that the professional liability insurance policy RC-2026-77412
was cancelled on 30 June 2026 for non payment of the premium. No cover applies after that date.

Issued in Nantes on 2 July 2026
"""


def generic_attestation() -> str:
    return """ATTESTATION

Atlantique Assurances certifies that Volt Services SAS is a client of the company
and that its account is up to date.

Issued in Nantes on 15 January 2026
"""


def references() -> str:
    return """SIMILAR REFERENCES (last five years)

1. Renovation of the electrical installation of the Malakoff school group, City of Nantes, 2024, 410,000 EUR.
2. Maintenance of electrical equipment of the Saint-Herblain sports complex, 2023 to 2025, 180,000 EUR per year.
3. Lighting upgrade of the Rezé municipal library, 2022, 95,000 EUR.
"""


def filler(characters: int) -> str:
    text = ""
    i = 1
    while len(text) < characters:
        text += f"Article {i}. {FILLER_PARAGRAPH}\n\n"
        i += 1
    return text
