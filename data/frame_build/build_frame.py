#!/usr/bin/env python3
"""Build data/frame.csv for funnel.py.

Inputs (both in this folder):
  cmc_top1000_raw.txt  companiesmarketcap.com top ~1000 by market cap, fetched 2026-09-28
  supplement.txt       hand-written supplement of private / smaller multinationals

Aliases = cleaned parent name + names in brackets + BRAND_ALIASES below.
Same inputs -> same frame.csv.
"""
import csv, os, re, sys, unicodedata

CMC_SOURCE = "companiesmarketcap.com top 1000 by market cap (fetched 2026-09-28)"
SUP_SOURCE = "Supplement: curated private/smaller multinationals (Claude, 2026-09-28; review)"

COUNTRY = {"USA": "United States", "UK": "United Kingdom", "S. Korea": "South Korea",
           "S. Arabia": "Saudi Arabia"}

# Parents whose Singapore entities trade under other names. Replaces the default alias
# when the parent name itself would be wrong or ambiguous (marked with "!" first).
BRAND_ALIASES = {
    "Alphabet": "Alphabet;Google;YouTube;DeepMind",
    "Meta Platforms": "Meta Platforms;Facebook;WhatsApp;Instagram",
    "Microsoft": "Microsoft;LinkedIn;GitHub",
    "Amazon": "Amazon;Amazon Web Services;Twitch",
    "Apple": "Apple South Asia;Apple Singapore;Apple Asia",
    "Merck": "!MSD;Merck Sharp & Dohme;MSD International",
    "Merck KGaA": "!Merck;EMD;MilliporeSigma",
    "Johnson & Johnson": "Johnson & Johnson;Janssen",
    "Procter & Gamble": "Procter & Gamble;P&G",
    "General Electric": "!GE Aerospace;General Electric",
    "GE Vernova": "GE Vernova",
    "GE HealthCare Technologies": "!GE HealthCare;GE Healthcare",
    "Hewlett Packard Enterprise": "Hewlett Packard Enterprise;HPE;Aruba Networks",
    "HP": "!HP Inc;HP PPS;Hewlett-Packard",
    "Deere & Company": "!John Deere;Deere",
    "Walt Disney": "Walt Disney;Disney",
    "McDonald": "McDonald's;McDonalds",
    "Booking Holdings": "Booking.com;Agoda;Priceline",
    "Alibaba": "Alibaba;Lazada;Alibaba Cloud;AliExpress",
    "Tencent": "Tencent;WeChat",
    "Sea Limited": "!Shopee;Garena;SeaMoney;Sea Group;Monee",
    "DBS Group": "!DBS Bank;DBS Group;DBS Vickers;DBS Asia",
    "OCBC Bank": "!OCBC;Oversea-Chinese Banking;Bank of Singapore",
    "UOB": "!United Overseas Bank;UOB Asset;UOB Kay Hian;UOB Venture",
    "Singtel": "!Singapore Telecommunications;Singtel;NCS Pte;Trustwave",
    "ST Engineering": "!Singapore Technologies Engineering;ST Engineering",
    "Flex": "!Flextronics;Flex Ltd",
    "Mitsubishi UFJ Financial": "!MUFG;Mitsubishi UFJ",
    "Mitsubishi Corporation": "!Mitsubishi Corporation",
    "Mitsui & Co": "!Mitsui & Co",
    "Sumitomo Corporation": "!Sumitomo Corporation",
    "Sumitomo Mitsui Financial Group": "!SMBC;Sumitomo Mitsui Banking;Sumitomo Mitsui Finance",
    "Sumitomo Mitsui Trust Holdings": "!Sumitomo Mitsui Trust",
    "Sumitomo Electric Industries": "!Sumitomo Electric",
    "Toyota": "Toyota Motor;Toyota Motor Asia;Lexus;Toyota Material Handling",
    "Hyundai": "!Hyundai Motor;Hyundai Engineering",
    "HD Hyundai Heavy Industries": "!Hyundai Heavy Industries;HD Hyundai",
    "LG Electronics": "LG Electronics",
    "SK Group": "!SK Innovation;SK Energy;SK Telecom;SK Holdings",
    "Samsung": "!Samsung Electronics;Samsung Asia;Samsung C&T;Samsung SDS;Samsung Engineering",
    "Siemens": "!Siemens Pte;Siemens Industry;Siemens Mobility;Siemens Singapore",
    "Nestlé": "Nestle",
    "L'Oréal": "L'Oreal",
    "Hermès": "Hermes",
    "Société Générale": "Societe Generale",
    "Crédit Agricole": "Credit Agricole;CACIB",
    "Dassault Systèmes": "Dassault Systemes",
    "Kühne + Nagel": "Kuehne + Nagel;Kuehne Nagel",
    "Deutsche Börse": "Deutsche Boerse;Eurex;Clearstream",
    "Munich RE": "Munich Re;Munchener Ruck;Munich Reinsurance",
    "Hannover Rück": "Hannover Re;Hannover Rueck",
    "Ørsted": "Orsted",
    "Itaú Unibanco": "Itau",
    "Grupo México": "Grupo Mexico",
    "Compagnie Financière Richemont": "Richemont;Cartier",
    "Compagnie de Saint-Gobain": "Saint-Gobain",
    "Anheuser-Busch Inbev": "Anheuser-Busch;AB InBev",
    "Banco Bilbao Vizcaya Argentaria": "BBVA;Banco Bilbao Vizcaya",
    "Santander": "Banco Santander;Santander",
    "Royal Bank Of Canada": "Royal Bank of Canada;RBC",
    "Toronto Dominion Bank": "Toronto-Dominion;TD Securities",
    "Bank of Montreal": "Bank of Montreal;BMO",
    "Scotiabank": "Bank of Nova Scotia;Scotiabank",
    "CIBC": "Canadian Imperial Bank of Commerce;CIBC",
    "BNY Mellon": "Bank of New York Mellon;BNY Mellon",
    "ANZ Bank": "Australia and New Zealand Banking;ANZ",
    "Commonwealth Bank": "Commonwealth Bank of Australia",
    "National Australia Bank": "National Australia Bank",
    "Westpac Banking": "Westpac",
    "Bank of China": "!Bank of China Limited;Bank of China Singapore;BOC Aviation",
    "Bank of China (Hong Kong)": "!Bank of China (Hong Kong)",
    "China Construction Bank": "China Construction Bank;CCB",
    "ICBC": "Industrial and Commercial Bank of China;ICBC",
    "Agricultural Bank of China": "Agricultural Bank of China",
    "CM Bank": "!China Merchants Bank",
    "Industrial Bank": "!Industrial Bank Co",
    "Ping An Insurance": "Ping An",
    "Ping An Bank": "!Ping An Bank",
    "AIA": "!AIA Singapore;AIA Company;AIA Investment",
    "Prudential plc": "!Prudential Assurance;Eastspring;Prudential Singapore",
    "Prudential Financial": "!PGIM;Prudential Financial",
    "Manulife Financial": "Manulife",
    "Sun Life Financial": "Sun Life",
    "Tokio Marine": "Tokio Marine",
    "MS&AD Insurance": "Mitsui Sumitomo Insurance;Aioi Nissay Dowa;MS First Capital",
    "Sompo Holdings": "Sompo",
    "Dai-ichi Life Holdings": "Dai-ichi Life",
    "Chubb": "Chubb",
    "American International Group": "!AIG Asia;AIG Singapore;American International Group",
    "Marsh & McLennan Companies": "Marsh;Mercer;Oliver Wyman;Guy Carpenter",
    "Willis Towers Watson": "Willis Towers Watson;Towers Watson;Willis",
    "Arthur J. Gallagher & Co.": "Gallagher",
    "Aon": "Aon",
    "S&P Global": "S&P Global;Standard & Poor;Platts",
    "Moody's": "Moody's",
    "London Stock Exchange": "!London Stock Exchange;LSEG;Refinitiv",
    "RELX": "RELX;Elsevier;LexisNexis",
    "Thomson Reuters": "Thomson Reuters;Reuters",
    "Experian": "Experian",
    "Accenture": "Accenture",
    "IBM": "IBM;International Business Machines;Red Hat",
    "Oracle": "Oracle",
    "Salesforce": "Salesforce;Slack Technologies;Tableau;MuleSoft",
    "Adobe": "Adobe",
    "SAP": "SAP Asia;SAP Singapore;SAP Concur;Concur",
    "Cisco": "Cisco;Splunk",
    "Broadcom": "Broadcom;VMware",
    "Dell": "Dell",
    "Intel": "Intel",
    "NVIDIA": "NVIDIA",
    "AMD": "Advanced Micro Devices;AMD",
    "Micron Technology": "Micron",
    "QUALCOMM": "Qualcomm",
    "Texas Instruments": "Texas Instruments",
    "Applied Materials": "Applied Materials",
    "Lam Research": "Lam Research",
    "KLA": "KLA Corporation;KLA-Tencor",
    "ASML": "ASML",
    "TSMC": "Taiwan Semiconductor;TSMC",
    "Palo Alto Networks": "Palo Alto Networks",
    "CrowdStrike": "CrowdStrike",
    "Fortinet": "Fortinet",
    "ServiceNow": "ServiceNow",
    "Workday": "Workday",
    "Snowflake": "Snowflake",
    "Datadog": "Datadog",
    "Cloudflare": "Cloudflare",
    "Zoom": "Zoom Video",
    "Twilio": "Twilio",
    "Okta": "Okta",
    "MongoDB": "MongoDB",
    "Atlassian": "Atlassian",
    "Autodesk": "Autodesk",
    "Uber": "Uber",
    "Airbnb": "Airbnb",
    "Netflix": "Netflix",
    "Spotify": "Spotify",
    "PayPal": "PayPal",
    "Visa": "!Visa Worldwide;Visa International",
    "Mastercard": "Mastercard",
    "American Express": "American Express",
    "Adyen": "Adyen",
    "Block": "!Block Inc;Square;Afterpay",
    "Coinbase": "Coinbase",
    "Shell": "!Shell Eastern;Shell Singapore;Shell Energy;Shell International;Shell Chemicals",
    "BP": "!BP Singapore;BP Asia;Castrol",
    "Exxon Mobil": "ExxonMobil;Exxon Mobil;Esso",
    "Chevron": "Chevron",
    "TotalEnergies": "TotalEnergies",
    "Unilever": "Unilever",
    "Pepsico": "PepsiCo;Pepsi-Cola",
    "Coca-Cola": "Coca-Cola",
    "Coca-Cola European Partners": "!Coca-Cola European Partners;Coca-Cola Europacific",
    "Mondelez International": "Mondelez",
    "Kraft Heinz": "Kraft Heinz;Heinz",
    "Kimberly-Clark": "Kimberly-Clark",
    "Colgate-Palmolive": "Colgate-Palmolive",
    "Estee Lauder": "Estee Lauder",
    "Reckitt Benckiser": "Reckitt",
    "Haleon": "Haleon",
    "Kenvue": "Kenvue",
    "Diageo": "Diageo",
    "Heineken": "Heineken;Asia Pacific Breweries",
    "Danone": "Danone",
    "Abbott Laboratories": "Abbott",
    "Pfizer": "Pfizer",
    "Novartis": "Novartis;Sandoz",
    "Roche": "Roche",
    "AstraZeneca": "AstraZeneca",
    "GSK plc": "GlaxoSmithKline;GSK",
    "Sanofi": "Sanofi",
    "Bayer": "Bayer",
    "Eli Lilly": "Eli Lilly",
    "AbbVie": "AbbVie",
    "Amgen": "Amgen",
    "Takeda Pharmaceutical": "Takeda",
    "Medtronic": "Medtronic",
    "Boston Scientific": "Boston Scientific",
    "Becton Dickinson": "Becton Dickinson;BD",
    "Thermo Fisher Scientific": "Thermo Fisher",
    "Philips": "Philips",
    "Hitachi": "Hitachi",
    "Sony": "Sony",
    "Panasonic": "Panasonic",
    "Canon": "Canon",
    "Fujifilm": "Fujifilm;Fuji Xerox",
    "Fujitsu": "Fujitsu",
    "NEC Corp": "NEC Asia;NEC Corporation",
    "NTT": "NTT;Nippon Telegraph;NTT Data",
    "DHL Group": "DHL;Deutsche Post",
    "FedEx": "FedEx;Federal Express",
    "United Parcel Service": "UPS;United Parcel Service",
    "Maersk": "Maersk;Damco",
    "Honeywell": "Honeywell",
    "3M": "!3M Singapore;3M Asia;3M Technologies",
    "Emerson": "Emerson Electric;Emerson Process",
    "Schneider Electric": "Schneider Electric",
    "ABB": "ABB",
    "Johnson Controls": "Johnson Controls",
    "Caterpillar": "Caterpillar",
    "Rolls-Royce Holdings": "Rolls-Royce",
    "Airbus": "Airbus",
    "Boeing": "Boeing",
    "Standard Chartered": "Standard Chartered",
    "HSBC": "HSBC;Hongkong and Shanghai Banking",
    "Citigroup": "Citibank;Citigroup;Citicorp",
    "JPMorgan Chase": "JPMorgan;J.P. Morgan;JP Morgan Chase",
    "Goldman Sachs": "Goldman Sachs",
    "Morgan Stanley": "Morgan Stanley",
    "Bank of America": "Bank of America;BofA Securities;Merrill Lynch",
    "Wells Fargo": "Wells Fargo",
    "BlackRock": "BlackRock",
    "UBS": "UBS;Credit Suisse",
    "BNP Paribas": "BNP Paribas",
    "Deutsche Bank": "Deutsche Bank",
    "Barclays": "Barclays",
    "ING": "!ING Bank",
    "AXA": "AXA",
    "Allianz SE": "Allianz;PIMCO",
    "Zurich Insurance Group": "Zurich Insurance;Zurich International",
    "Swiss Re": "Swiss Re;Swiss Reinsurance",
    "Generali": "Generali",
    "Macquarie Group Limited": "Macquarie",
    "Blackstone Group": "Blackstone",
    "KKR & Co.": "KKR",
    "Brookfield Asset Management": "Brookfield Asset",
    "Brookfield Corporation": "!Brookfield",
    "Apollo Global Management": "Apollo Global",
    "Marriott International": "Marriott",
    "Hilton Worldwide": "Hilton",
    "Starbucks": "Starbucks",
    "Nike": "Nike",
    "Adidas": "Adidas",
    "LVMH": "LVMH;Louis Vuitton;Sephora;Moet Hennessy;DFS Venture",
    "Kering": "Kering;Gucci",
    "Inditex": "Inditex;Zara",
    "H&M": "H&M;Hennes & Mauritz",
    "Fast Retailing": "Fast Retailing;Uniqlo",
    "Target": "!Target Corporation",
    "Progressive": "!Progressive Corporation",
    "Orange": "!Orange Business;Orange Singapore",
    "Vale": "!Vale International;Vale Singapore",
    "Block": "!Block Inc;Square;Afterpay",
    "Eaton": "Eaton",
    "Linde": "Linde",
    "Air Liquide": "Air Liquide",
    "BASF": "BASF",
    "Glencore": "Glencore",
    "Rio Tinto": "Rio Tinto",
    "BHP Group": "BHP",
    "Anglo American": "Anglo American",
    "Vodafone": "Vodafone",
    "BT Group": "!BT Singapore;British Telecommunications;BT Global",
    "Telstra": "Telstra",
    "Lenovo": "Lenovo",
    "Xiaomi": "Xiaomi",
    "Baidu": "Baidu",
    "JD.com": "JD.com;JD Logistics",
    "Trip.com": "Trip.com;Ctrip",
    "Meituan": "Meituan;Keeta",
    "PDD Holdings": "PDD;Temu;Whaleco",
    "Coupang": "Coupang",
    "Expedia Group": "Expedia",
    "eBay": "eBay",
    "Infosys": "Infosys",
    "Tata Consultancy Services": "Tata Consultancy",
    "HCL Technologies": "HCL Technologies;HCL",
    "Recruit": "!Indeed;Glassdoor;Recruit Holdings",
    "Publicis Groupe": "Publicis",
    "Compass Group": "Compass Group",
    "Sysco": "Sysco",
    "Seven & i Holdings": "!Seven & i;7-Eleven Inc",
    "Rakuten": "Rakuten",
}


# Brand names that are also ordinary words or common names. Marked "=" in the frame:
# funnel.py accepts a match on them only when the rest of the entity name is neutral
# (e.g. "ORACLE CORPORATION SINGAPORE" passes, "ORACLE CONSULTANCY SERVICES" goes to review).
STRICT_WORDS = set("""apple oracle zoom amazon tesla flex grab canon dell intel square booking carnival
compass concur corning disco dover eternal fortis goodman hana hartford hermes hexagon indeed intact
investor leonardo manpower marsh mercer olympus principal quanta republic rocket scoot sika southern
strategy titan travelers vinci viking vistra waters williams willis zara cathay citizens coherent
genesys nium nike target visa orange delta shell progressive block merck keeta ventas humana intuit
sandoz continental emerson eaton cummins linde hilton medline everpure legrand wise mars puma kao red xero
stripe braze bain""".split())

BRAND_ALIASES.update({
    "International Holding Company": "!International Holding Company",
    "Southern Company": "!Southern Company",
    "Titan Company": "!Titan Company",
    "Eternal": "!Zomato;Blinkit",
    "Compass Group": "!Compass Group",
    "Republic Services": "!Republic Services",
    "Rocket Companies": "!Rocket Mortgage",
    "Viking Holdings": "!Viking Cruises",
    "Strategy": "!MicroStrategy",
    "Principal Financial Group": "!Principal Global Investors;Principal Asset Management",
    "Cathay Financial Holding": "!Cathay United Bank;Cathay Life Insurance",
    "Hana Financial Group": "!Hana Bank;KEB Hana",
    "Fortis": "!=Fortis",
    "Block": "!=Block;Afterpay",
    "Becton Dickinson": "!Becton Dickinson",
    "Nu Holdings": "!Nubank",
    "KB Financial Group": "!Kookmin Bank;KB Kookmin",
    "Sea Limited": "!Shopee;Garena;SeaMoney;Sea Group",
    "Quanta Services": "!Quanta Services",
    "Investor AB": "!Investor AB",
    "Intact Financial": "!Intact Financial",
    "Williams Companies": "!Williams Companies",
    "Dover Corporation": "!Dover Corporation",
    "The Travelers Companies": "!Travelers Companies",
    "Citizens Financial Group": "!Citizens Financial",
    "Carnival Corporation": "!Carnival Corporation;Carnival Cruise;Princess Cruises",
    "Disco Corp.": "!Disco Hi-Tec;Disco Corporation",
    "Waters Corporation": "!Waters Corporation;Waters Asia",
    "The Hartford": "!Hartford Financial",
    "Hexagon AB": "!Hexagon AB;Hexagon Metrology;Hexagon Geosystems;Leica Geosystems",
    "Vistra": "!Vistra Corp",
    "Apple": "!Apple South Asia;Apple Singapore;Apple Asia;Apple",
    "Booking Holdings": "!Booking.com;Agoda;Priceline",
    "Honeywell Aerospace": "!Honeywell Aerospace",
})


def mark_strict(aliases):
    out = []
    for a in aliases.split(";"):
        a = a.strip()
        if a and not a.startswith("=") and len(a.split()) == 1 and a.lower().strip(".") in STRICT_WORDS:
            a = "=" + a
        out.append(a)
    return ";".join(x for x in out if x)


def clean(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s.strip()


TRAIL = {"group", "holdings", "holding", "corporation", "corp", "company", "companies", "co",
         "inc", "limited", "ltd", "plc", "se", "ag", "sa", "nv", "n.v.", "ab", "pcl", "tbk",
         "international", "financial", "services", "lp", "&"}


def base_alias(name):
    s = re.sub(r"\(.*?\)", "", name)
    s = re.sub(r"^the ", "", clean(s), flags=re.I).rstrip(".").strip()
    toks = s.split()
    while len(toks) > 1 and toks[-1].lower().strip(".,") in TRAIL:
        toks.pop()
    return " ".join(toks)


def parent_key(name):
    return re.sub(r"\s*\(.*?\)", "", name).strip()


def aliases_for(name):
    key = parent_key(name)
    extra = BRAND_ALIASES.get(key) or BRAND_ALIASES.get(name, "")
    out = []
    if extra.startswith("!"):
        out = extra[1:].split(";")
    else:
        curated = [a for a in extra.split(";") if a]
        auto = [base_alias(name)] + [clean(p) for p in re.findall(r"\((.*?)\)", name)]
        # Auto-derived single words ("First", "Next", "Phoenix") are often ordinary words:
        # make them strict unless the same word is also curated in BRAND_ALIASES.
        cur_l = {c.lower() for c in curated}
        auto = ["=" + a if len(a.split()) == 1 and a.lower() not in cur_l else a for a in auto]
        out = auto + curated
    seen, res = set(), []
    for a in out:
        a = clean(a).strip()
        if a and a.lower().lstrip("=") not in seen:
            seen.add(a.lower().lstrip("=")); res.append(a)
    return ";".join(res)


SG_MNC_BASIS = "Singapore-HQ group with operations outside Singapore (curated; verify)"
SG_MNC_PENDING = "Pending: Singapore-HQ, overseas operations not yet checked - confirm at stage 6 (c1)"

SOURCES = {
    "cmc_top1000": "companiesmarketcap.com ranks 1-1000 by market cap (fetched 2026-09-28)",
    "cmc_1001_1500": "companiesmarketcap.com ranks 1001-1500 by market cap (fetched 2026-09-28)",
    "supplement": "Supplement: curated private/smaller multinationals (Claude, 2026-09-28; review)",
    "sgx_midcap": "Singapore-HQ listed, market cap US$0.3-10B, companiesmarketcap.com Singapore list (fetched 2026-09-28)",
    "ft_hg_apac": "FT/Statista High-Growth Companies Asia-Pacific 2026 (PARTIAL: names from public articles only)",
}

# Supplement companies that are scale-ups rather than giants.
SUPPLEMENT_MID = {"Airwallex", "Nium", "Thunes", "Xendit", "Ninja Van", "Klook", "Carousell",
                  "PropertyGuru", "Razer", "Braze", "Sprinklr", "Freshworks"}


def key_of(name):
    return re.sub(r"[^a-z0-9]", "", clean(parent_key(name)).lower())


# Global tier = Forbes Global 2000 if forbes_global2000.txt (one name per line) is present,
# otherwise market-cap ranks 1-1500 as a stand-in (similar size cut-off; listed companies only).
FORBES_FILE = "forbes_global2000.txt"
forbes = None
if os.path.exists(FORBES_FILE):
    forbes = {key_of(l) for l in open(FORBES_FILE, encoding="utf-8") if l.strip() and not l.startswith("#")}
TIER_BASIS = "Forbes Global 2000" if forbes is not None else "Proxy: market-cap top 1500 (Forbes list not available)"


def read_rows(path, has_source=False):
    for line in open(path, encoding="utf-8"):
        if line.startswith("#") or "|" not in line:
            continue
        yield [x.strip() for x in line.rstrip("\n").split("|")]


rows, index = [], {}


def add(name, country, src, aliases, segment, mnc_basis):
    k = key_of(name)
    if k in index:                       # already in the frame: record the extra source
        r = index[k]
        if SOURCES[src] not in r["frame_source"]:
            r["frame_source"] += " + " + SOURCES[src]
        if segment == "mid" and src in ("sgx_midcap", "ft_hg_apac"):
            r["listed_in_midsize_source"] = "y"
        return
    r = {"parent_name": parent_key(name), "aliases": mark_strict(aliases), "hq_country": country,
         "frame_source": SOURCES[src], "mnc_basis": mnc_basis,
         "global_tier": "", "size_segment": segment,
         "listed_in_midsize_source": "y" if src in ("sgx_midcap", "ft_hg_apac") else ""}
    rows.append(r); index[k] = r


for src, path in [("cmc_top1000", "cmc_top1000_raw.txt"), ("cmc_1001_1500", "cmc_1001_1500_raw.txt")]:
    for name, country in (x[:2] for x in read_rows(path)):
        country = COUNTRY.get(country, country)
        add(name, country, src, aliases_for(name), "large",
            SG_MNC_BASIS if country == "Singapore" else "")

for parts in read_rows("supplement.txt"):
    name, country, al = parts[0], parts[1], (parts[2] if len(parts) > 2 else "")
    seg = "mid" if parent_key(name) in SUPPLEMENT_MID else "large"
    add(name, country, "supplement", al or base_alias(name), seg,
        SG_MNC_BASIS if country == "Singapore" else "")

for f in ["midsize_sources.txt", "ft_high_growth_apac_full.txt"]:
    if not os.path.exists(f):
        continue
    for parts in read_rows(f):
        name, country, src = parts[0], parts[1], parts[2]
        al = parts[3] if len(parts) > 3 and parts[3] else base_alias(name)
        add(name, country, src, al, "mid", SG_MNC_PENDING if country == "Singapore" else "")

# global tier + final segment: a global-tier company is always "large"
proxy = {key_of(n) for p in ["cmc_top1000_raw.txt", "cmc_1001_1500_raw.txt"] for n, *_ in read_rows(p)}
for r in rows:
    k = key_of(r["parent_name"])
    r["global_tier"] = "y" if k in (forbes if forbes is not None else proxy) else "n"
    if r["global_tier"] == "y":
        r["size_segment"] = "large"
    r["global_tier_basis"] = TIER_BASIS

out = sys.argv[1] if len(sys.argv) > 1 else "frame.csv"
cols = ["parent_name", "aliases", "hq_country", "frame_source", "mnc_basis", "global_tier",
        "global_tier_basis", "size_segment", "listed_in_midsize_source"]
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader(); w.writerows(rows)
from collections import Counter
print(f"{len(rows)} parents -> {out}")
print(" global_tier:", dict(Counter(r["global_tier"] for r in rows)),
      " size_segment:", dict(Counter(r["size_segment"] for r in rows)))
