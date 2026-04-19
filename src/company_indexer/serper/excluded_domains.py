"""Domains to exclude from Serper searches.

The website-search endpoint searches a KVK number to find a company's own
website. Business-registry aggregators list every KVK number and would
otherwise dominate results, so they're stripped via Google's ``-site:``
operator.

Expand this list as new aggregators surface. LinkedIn/Facebook are kept in
on purpose — they're sometimes the only web presence for small businesses,
and the extraction step can decide.
"""

EXCLUDED_DOMAINS: list[str] = [
    "kvk.nl",
    "company.info",
    "companyinfo.nl",
    "drimble.nl",
    "opencorporates.com",
    "openkvk.nl",
    "bedrijvenpagina.nl",
    "graydon.com",
    "dnb.com",
    "bedrijfinbeeld.nl",
    "creditsafe.com",
    "altares.nl",
    "transfirm.nl",
    "northdata.com",
    "oozo.nl",
    "cage.report",
    "bedrijven.com",
    "northdata.de",
    "tweakers.net",
    "europa.eu",
]


def build_query(base: str, excluded: list[str] | None = None) -> str:
    domains = EXCLUDED_DOMAINS if excluded is None else excluded
    return " ".join([base, *(f"-site:{d}" for d in domains)])
