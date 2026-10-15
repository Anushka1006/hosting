import os
import re
import pandas as pd

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


# ============================================================
# BASE DIRECTORY
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

OUTPUT_DIR = os.path.join(
    BASE_DIR,
    "output"
)

OUTPUT_FILE = os.path.join(
    OUTPUT_DIR,
    "technology_summary_clean.xlsx"
)


# ============================================================
# RUN MODE
# ============================================================
#
# RESUME
#   - Recommended
#   - Existing completed companies are skipped
#   - Only remaining companies are processed
#
# TEST
#   - Only TEST_COMPANIES are processed
#   - Useful for testing changes
#   - Existing rows for those companies are replaced
#
# FULL
#   - All companies are processed
#   - Existing output is rebuilt
#
# ============================================================

RUN_MODE = "RESUME"


# ============================================================
# TEST COMPANIES
# ============================================================

TEST_COMPANIES = [
    # "Onesource Specialty Pharma",
    # "eClerx Services",
    # "Sammaan Capital",
    # "Travel Food Services",
    # "JSW Cement",
    # "Ola Electric Mobility",
    # "Cohance Lifesciences",
    # "PG Electroplast",
    # "Zen Technologies",
    # "Amara Raja Energy & Mobility",
    # "Minda Corporation",
    # "Zydus Wellness",
    # "KFin Technologies",
    # "DCM Shriram Consolidated",
    # "Godawari Power & Ispat",
    # "Jammu & Kashmir Bank",
    # "Syngene International",
    # "Paradeep Phosphates",
    # "Kansai Nerolac Paints",
    # "BEML",
    # "Concord Biotech",
    # "Tata Chemicals",
    # "KPIT Technologies",
    # "Kirloskar Oil Engines",
    # "Netweb Technologies",
    # "Aegis Vopak Terminals",
    # "ZF Commercial",
    # "Garden Reach Shipbuilders",
    # "Neuland Laboratories",
    # "Cholamandalam Financial Holdings",
    # "Aditya Birla Sun Life AMC",
    # "IIFL Finance",
    # "ACME Solar Holdings",
    # "Central Bank of India",
    # "Syrma SGS",
    # "Apollo Tyres",
    # "Bandhan Bank",
    # "Redington",
    # "Piramal Pharma",
    # "TVS Holdings",
    # "Craftsman Automation",
    # "Schneider Electric Infra",
    # "LIC Housing Finance",
    # "Angel One",
    # "AWL Agri Business",
    # "Kaynes Technology India",
    # "Sona BLW Precision Forgings",
    # "GlaxoSmithKline Pharmaceuticals",
    # "IPCA Laboratories",
    # "Anthem Biosciences",
    # "Piramal Finance",
    # "360 One WAM",
    # "Tata Communications",
    # "UPL",
    # "Authum Inv & Infr",
    # "Thermax",
    # "Aegis Logistics",
    # "Premier Energies",
    # "Gland Pharma",
    # "Mphasis",
    # "Balkrishna Industries",
    # "Rail Vikas Nigam",
    # "Supreme Industries",
    # "Petronet LNG",
    # "Ajanta Pharma",
    # "Endurance Technologies",
    # "Navin Fluorine International",
    # "Poonawalla Fincorp",
    # "Voltas",
    # "Astral",
    # "JK Cement",
    # "Marico",
    # "Aditya Birla Capital",
    # "One 97 Communications",
    # "GE Vernova T&D",
    # "Tata Consumer Products",
    # "GMR Airports",
    # "Indian Hotels Company",
    # "Lloyds Metals & Energy",
    # "Mazagon Dock Shipbuilders",
    # "Ashok Leyland",
    # "Indus Towers",
    # "Ambuja Cements",
    # "Oracle Financial Services Software",
    # "Laurus Labs",
    # "Lupin",
    # "JSW Energy",
    # "Dr Reddys Laboratories",
    # "Bharat Forge",
    # "Mankind Pharma",
    # "Max Healthcare Institute",
    # "Nykaa",
    # "Meesho",
    # "IDBI Bank",
    # "Godrej Consumer Products",
    # "3M India Ltd.",
    # "ABB India Ltd.",
    # "ACC Ltd.",
    # "ACME Solar Holdings Ltd.",
    # "AIA Engineering Ltd.",
    # "APL Apollo Tubes Ltd.",
    # "AU Small Finance Bank Ltd.",
    # "AWL Agri Business Ltd.",
    # "Aarti Industries Ltd.",
    # "Aavas Financiers Ltd.",
    # "Abbott India Ltd.",
    # "Acutaas Chemicals Ltd.",
    # "Adani Enterprises Ltd.",
    # "Adani Green Energy Ltd.",
    # "Adani Power Ltd.",
    # "Aditya Birla Capital Ltd.",
    # "Aditya Birla Sun Life AMC Ltd.",
    # "Aegis Logistics Ltd.",
    # "Aegis Vopak Terminals Ltd.",
    # "Afcons Infrastructure Ltd.",
    # "Affle 3i Ltd.",
    # "Alkem Laboratories Ltd.",
    # "Amber Enterprises India Ltd.",
    # "Ambuja Cements Ltd.",
    # "Anand Rathi Wealth Ltd.",
    # "Anthem Biosciences Ltd.",
    # "Anupam Rasayan India Ltd.",
    # "Apar Industries Ltd.",
    # "Apollo Hospitals Enterprise Ltd.",
    # "Apollo Tyres Ltd.",
    # "Aptus Value Housing Finance India Ltd.",
    # "Asahi India Glass Ltd.",
    # "Ashok Leyland Ltd.",
    # "Asian Paints Ltd.",
    # "Aster DM Quality Care Ltd.",
    # "Astral Ltd.",
    # "Atul Ltd.",
    # "Aurobindo Pharma Ltd.",
    # "Axis Bank Ltd.",
    # "BEML Ltd.",
    # "BLS International Services Ltd.",
    # "BSE Ltd.",
    # "Bajaj Auto Ltd.",
    # "Bajaj Finserv Ltd.",
    # "Bajaj Housing Finance Ltd.",
    # "Balkrishna Industries Ltd.",
    # "Balrampur Chini Mills Ltd.",
    # "Bank of Baroda",
    # "Bank of India",
    # "Bank of Maharashtra",
    # "Bata India Ltd.",
    # "Bayer Cropscience Ltd.",
    # "Belrise Industries Ltd.",
    # "Berger Paints India Ltd.",
    # "Bharat Electronics Ltd.",
    # "Bharat Forge Ltd.",
    # "Bharat Heavy Electricals Ltd.",
    # "Bharti Airtel Ltd.",
    # "Bikaji Foods International Ltd.",
    # "Biocon Ltd.",
    # "Blue Dart Express Ltd.",
    # "Blue Jet Healthcare Ltd.",
    # "Blue Star Ltd.",
    # "Bosch Ltd.",
    # "Brainbees Solutions Ltd.",
    # "Brigade Enterprises Ltd.",
    # "Britannia Industries Ltd.",
    # "CCL Products (I) Ltd.",
    # "CESC Ltd.",
    # "CRISIL Ltd.",
    # "Can Fin Homes Ltd.",
    # "Canara Bank",
    # "Caplin Point Laboratories Ltd.",
    # "Capri Global Capital Ltd.",
    # "Carborundum Universal Ltd.",
    # "Cartrade Tech Ltd.",
    # "Castrol India Ltd.",
    # "Ceat Ltd.",
    # "Chalet Hotels Ltd.",
    # "Choice International Ltd.",
    # "Cipla Ltd.",
    # "City Union Bank Ltd.",
    # "Clean Science and Technology Ltd.",
    # "Coal India Ltd.",
    # "Coforge Ltd.",
    # "Cohance Lifesciences Ltd.",
    # "Coromandel International Ltd.",
    # "Craftsman Automation Ltd.",
    # "CreditAccess Grameen Ltd.",
    # "Crompton Greaves Consumer Electricals Ltd.",
    # "Cummins India Ltd.",
    # "Cyient Ltd.",
    # "DCM Shriram Ltd.",
    # "DLF Ltd.",
    # "DOMS Industries Ltd.",
    # "Dabur India Ltd.",
    # "Data Patterns (India) Ltd.",
    # "Deepak Nitrite Ltd.",
    # "Delhivery Ltd.",
    # "Devyani International Ltd.",
    # "Divi's Laboratories Ltd.",
    # "Dixon Technologies (India) Ltd.",
    # "Dr. Lal Path Labs Ltd.",
    # "Dr. Reddy's Laboratories Ltd.",
    # "E.I.D. Parry (India) Ltd.",
    # "EIH Ltd.",
    # "Eicher Motors Ltd.",
    # "Elecon Engineering Co. Ltd.",
    # "Elgi Equipments Ltd.",
    # "Emami Ltd.",
    # "Emcure Pharmaceuticals Ltd.",
    # "Emmvee Photovoltaic Power Ltd.",
    # "Endurance Technologies Ltd.",
    # "Engineers India Ltd.",
    "Eris Lifesciences Ltd.",
    "Escorts Kubota Ltd.",
    "Eternal Ltd.",
    "Exide Industries Ltd.",
    "Federal Bank Ltd.",
    "Finolex Cables Ltd.",
    "Firstsource Solutions Ltd.",
    "Five-Star Business Finance Ltd.",
    "Force Motors Ltd.",
    "Fortis Healthcare Ltd.",
    "GAIL (India) Ltd.",
    "GE Vernova T&D India Ltd.",
    "Gabriel India Ltd.",
    "Gallantt Ispat Ltd.",
    "General Insurance Corporation of India",
    "Gillette India Ltd.",
    "Gland Pharma Ltd.",
    "Glenmark Pharmaceuticals Ltd.",
    "Global Health Ltd.",
    "Godawari Power & Ispat Ltd.",
    "Godfrey Phillips India Ltd.",
    "Godrej Consumer Products Ltd.",
    "Godrej Industries Ltd.",
    "Godrej Properties Ltd.",
    "Granules India Ltd.",
    "Graphite India Ltd.",
    "Grasim Industries Ltd.",
    "Gravita India Ltd.",
    "HBL Engineering Ltd.",
    "HCL Technologies Ltd.",
    "HDFC Bank Ltd.",
    "HFCL Ltd.",
    "Havells India Ltd.",
    "Hero MotoCorp Ltd.",
    "Hexaware Technologies Ltd.",
    "Hindalco Industries Ltd.",
    "Hindustan Aeronautics Ltd.",
    "Hindustan Copper Ltd.",
    "Hindustan Unilever Ltd.",
    "Hindustan Zinc Ltd.",
    "Hitachi Energy India Ltd.",
    "Honasa Consumer Ltd.",
    "Honeywell Automation India Ltd.",
    "Hyundai Motor India Ltd.",
    "ICICI Bank Ltd.",
    "IDBI Bank Ltd.",
    "IFCI Ltd.",
    "IIFL Finance Ltd.",
    "IRB Infrastructure Developers Ltd.",
    "IRCON International Ltd.",
    "ITC Hotels Ltd.",
    "ITC Ltd.",
    "ITI Ltd.",
    "India Cements Ltd.",
    "Indiamart Intermesh Ltd.",
    "Indian Bank",
    "Indian Hotels Co. Ltd.",
    "Indian Oil Corporation Ltd.",
    "Indian Overseas Bank",
    "Indraprastha Gas Ltd.",
    "IndusInd Bank Ltd.",
    "Info Edge (India) Ltd.",
    "Intellect Design Arena Ltd.",
    "InterGlobe Aviation Ltd.",
    "Ipca Laboratories Ltd.",
    "JBM Auto Ltd.",
    "JK Tyre & Industries Ltd.",
    "JM Financial Ltd.",
    "JSW Energy Ltd.",
    "JSW Infrastructure Ltd.",
    "JSW Steel Ltd.",
    "Jammu & Kashmir Bank Ltd.",
    "Jindal Saw Ltd.",
    "Jindal Stainless Ltd.",
    "Jubilant Foodworks Ltd.",
    "Jubilant Pharmova Ltd.",
    "Jyoti CNC Automation Ltd.",
    "KEI Industries Ltd.",
    "KPIT Technologies Ltd.",
    "Kajaria Ceramics Ltd.",
    "Kalpataru Projects International Ltd.",
    "Karur Vysya Bank Ltd.",
    "Kaynes Technology India Ltd.",
    "Kec International Ltd.",
    "Kirloskar Oil Eng Ltd.",
    "Kotak Mahindra Bank Ltd.",
    "LG Electronics India Ltd.",
    "LIC Housing Finance Ltd.",
    "LT Foods Ltd.",
    "LTM Ltd.",
    "Larsen & Toubro Ltd.",
    "Latent View Analytics Ltd.",
    "Lemon Tree Hotels Ltd.",
    "Lenskart Solutions Ltd.",
    "Life Insurance Corporation of India",
    "Lloyds Metals And Energy Ltd.",
    "Lodha Developers Ltd.",
    "Lupin Ltd.",
    "MMTC Ltd.",
    "MRF Ltd.",
    "Mahanagar Gas Ltd.",
    "Mahindra & Mahindra Ltd.",
    "Manappuram Finance Ltd.",
    "Mankind Pharma Ltd.",
    "Marico Ltd.",
    "Maruti Suzuki India Ltd.",
    "Meesho Ltd.",
    "Minda Corporation Ltd.",
    "Motherson Sumi Wiring India Ltd.",
    "MphasiS Ltd.",
    "Muthoot Finance Ltd.",
    "NATCO Pharma Ltd.",
    "NBCC (India) Ltd.",
    "NCC Ltd.",
    "NHPC Ltd.",
    "NMDC Ltd.",
    "NMDC Steel Ltd.",
    "NTPC Green Energy Ltd.",
    "NTPC Ltd.",
    "Narayana Hrudayalaya Ltd.",
    "National Aluminium Co. Ltd."
]


# ============================================================
# CONSTANTS
# ============================================================

MISSING_VALUE = "Not Available in collected data"


TECHNOLOGY_PARAMETERS = [
    "Current Technology Adoption",
    "Digital Transformation",
    "R&D",
    "Emerging Technologies",
    "Technology Partnerships",
    "Technology Investments",
    "Cloud Adoption",
    "Automation",
    "Cybersecurity",
    "Future Technology Roadmaps",
    "Technology Pain Areas",
]


# ============================================================
# TECHNOLOGY ALIASES
# ============================================================

TECHNOLOGY_ALIASES = {

    # AI
    "artificial intelligence": "AI",
    "artificial-intelligence": "AI",
    " ai ": "AI",
    "ai ": "AI",
    "genai": "Generative AI",
    "generative ai": "Generative AI",
    "generative artificial intelligence": "Generative AI",
    "machine learning": "Machine Learning",
    "machine-learning": "Machine Learning",
    "deep learning": "Deep Learning",

    # Analytics
    "advanced analytics": "Advanced Analytics",
    "data analytics": "Data Analytics",
    "predictive analytics": "Predictive Analytics",
    "business analytics": "Business Analytics",
    "data science": "Data Science",
    "data engineering": "Data Engineering",
    "big data": "Big Data",

    # Cloud
    "cloud computing": "Cloud Computing",
    "cloud platform": "Cloud Platform",
    "cloud platforms": "Cloud Platforms",
    "cloud infrastructure": "Cloud Infrastructure",
    "cloud-native": "Cloud-Native",
    "cloud native": "Cloud-Native",
    "hybrid cloud": "Hybrid Cloud",
    "public cloud": "Public Cloud",
    "private cloud": "Private Cloud",
    "multi-cloud": "Multi-Cloud",
    "multicloud": "Multi-Cloud",

    # Providers
    "amazon web services": "AWS",
    "aws": "AWS",
    "microsoft azure": "Microsoft Azure",
    "azure": "Microsoft Azure",
    "google cloud": "Google Cloud",
    "google cloud platform": "Google Cloud",
    "gcp": "Google Cloud",
    "oracle cloud": "Oracle Cloud",
    "salesforce": "Salesforce",

    # Enterprise
    "sap": "SAP",
    "sap s/4hana": "SAP S/4HANA",
    "s/4hana": "SAP S/4HANA",
    "erp": "ERP",
    "enterprise resource planning": "ERP",
    "crm": "CRM",
    "customer relationship management": "CRM",
    "enterprise applications": "Enterprise Applications",
    "enterprise software": "Enterprise Software",

    # Automation
    "robotic process automation": "RPA",
    "robotic process automations": "RPA",
    "rpa": "RPA",
    "intelligent automation": "Intelligent Automation",
    "workflow automation": "Workflow Automation",
    "process automation": "Process Automation",
    "business process automation": "Business Process Automation",
    "industrial automation": "Industrial Automation",
    "automated testing": "Automated Testing",
    "automation": "Automation",
    "robotics": "Robotics",
    "robotic automation": "Robotics",

    # IoT / advanced tech
    "internet of things": "IoT",
    "iot": "IoT",
    "industry 4.0": "Industry 4.0",
    "digital twin": "Digital Twin",
    "digital twins": "Digital Twins",
    "edge computing": "Edge Computing",
    "blockchain": "Blockchain",
    "computer vision": "Computer Vision",
    "augmented reality": "AR",
    "virtual reality": "VR",
    "ar/vr": "AR/VR",

    # Security
    "cybersecurity": "Cybersecurity",
    "cyber security": "Cybersecurity",
    "information security": "Information Security",
    "information-security": "Information Security",
    "identity and access management": "IAM",
    "identity access management": "IAM",
    "iam": "IAM",
    "privileged access management": "PAM",
    "pam": "PAM",
    "security information and event management": "SIEM",
    "siem": "SIEM",
    "security operations center": "Security Operations",
    "security operations centre": "Security Operations",
    "security operations": "Security Operations",
    "threat detection": "Threat Detection",
    "endpoint security": "Endpoint Security",
    "network security": "Network Security",
    "vulnerability management": "Vulnerability Management",

    # Data
    "data lake": "Data Lake",
    "data lakes": "Data Lakes",
    "data warehouse": "Data Warehouse",
    "data warehouses": "Data Warehouses",
    "database": "Database",
    "databases": "Databases",

    # Platforms
    "digital platform": "Digital Platform",
    "digital platforms": "Digital Platforms",
    "digital portal": "Digital Portal",
    "digital portals": "Digital Portals",
    "mobile application": "Mobile Application",
    "mobile applications": "Mobile Applications",
    "mobile app": "Mobile Application",
    "mobile apps": "Mobile Applications",

    # SaaS
    "software as a service": "SaaS",
    "saas": "SaaS",
    "platform as a service": "PaaS",
    "paas": "PaaS",
    "infrastructure as a service": "IaaS",
    "iaas": "IaaS",
}


# ============================================================
# PARAMETER KEYWORDS
# ============================================================

PARAMETER_KEYWORDS = {

    "Current Technology Adoption": [
        "implemented",
        "deployed",
        "adopted",
        "uses",
        "using",
        "currently uses",
        "technology",
        "platform",
        "system",
        "software",
        "application",
        "digital",
        "ai",
        "analytics",
        "cloud",
        "automation",
        "erp",
        "sap",
        "cybersecurity",
    ],

    "Digital Transformation": [
        "digital transformation",
        "digitalisation",
        "digitalization",
        "digitisation",
        "digitization",
        "digital journey",
        "digital initiative",
        "digital initiatives",
        "digital platform",
        "digital platforms",
        "modernisation",
        "modernization",
        "legacy modernization",
        "process transformation",
        "business transformation",
        "technology transformation",
    ],

    "R&D": [
        "research and development",
        "research & development",
        "r&d",
        "research",
        "development",
        "innovation",
        "laboratory",
        "laboratories",
        "patent",
        "patents",
        "intellectual property",
        "product development",
        "technology development",
        "engineering",
    ],

    "Emerging Technologies": [
        "artificial intelligence",
        "generative ai",
        "genai",
        "machine learning",
        "deep learning",
        "robotics",
        "robotic",
        "internet of things",
        "iot",
        "blockchain",
        "digital twin",
        "edge computing",
        "computer vision",
        "industry 4.0",
        "advanced analytics",
        "predictive analytics",
    ],

    "Technology Partnerships": [
        "technology partner",
        "technology partnership",
        "strategic partner",
        "strategic partnership",
        "technology alliance",
        "collaboration",
        "collaborated",
        "in partnership with",
        "partnered with",
        "cloud provider",
        "software provider",
        "technology provider",
        "vendor",
        "vendors",
        "startup",
        "university",
        "research institution",
    ],

    "Technology Investments": [
        "technology investment",
        "technology investments",
        "digital investment",
        "digital investments",
        "technology spending",
        "technology expenditure",
        "it investment",
        "it investments",
        "it spending",
        "capital expenditure",
        "capex",
        "infrastructure investment",
        "software investment",
        "cybersecurity investment",
    ],

    "Cloud Adoption": [
        "cloud",
        "cloud computing",
        "cloud platform",
        "cloud platforms",
        "cloud infrastructure",
        "cloud migration",
        "cloud-based",
        "cloud native",
        "cloud-native",
        "hybrid cloud",
        "public cloud",
        "private cloud",
        "multi-cloud",
        "saas",
        "paas",
        "iaas",
        "aws",
        "azure",
        "google cloud",
    ],

    "Automation": [
        "automation",
        "automated",
        "automating",
        "robotic process automation",
        "rpa",
        "robotics",
        "workflow automation",
        "process automation",
        "intelligent automation",
        "industrial automation",
        "automated testing",
    ],

    "Cybersecurity": [
        "cybersecurity",
        "cyber security",
        "information security",
        "security operations",
        "security monitoring",
        "threat detection",
        "cyber risk",
        "cyber-risk",
        "identity management",
        "identity and access",
        "iam",
        "pam",
        "siem",
        "encryption",
        "firewall",
        "vulnerability",
        "security controls",
        "security framework",
    ],

    "Future Technology Roadmaps": [
        "future technology",
        "technology roadmap",
        "technology roadmaps",
        "digital roadmap",
        "future plans",
        "planned",
        "planning",
        "will implement",
        "will deploy",
        "to be implemented",
        "to be deployed",
        "future initiative",
        "upcoming",
        "roadmap",
        "next phase",
        "strategic technology",
    ],

    "Technology Pain Areas": [
        "technology challenge",
        "technology challenges",
        "technology risk",
        "technology risks",
        "technology gap",
        "technology gaps",
        "legacy system",
        "legacy systems",
        "cybersecurity risk",
        "cyber risk",
        "data challenge",
        "data challenges",
        "infrastructure limitation",
        "technology limitation",
        "technology limitations",
        "integration challenge",
        "integration challenges",
        "technology talent",
        "skill gap",
        "skills gap",
        "implementation challenge",
        "technology cost",
        "scalability",
    ],
}


# ============================================================
# NOISE PATTERNS
# ============================================================

NOISE_PATTERNS = [
    r"\bcontents\b",
    r"\btable of contents\b",
    r"\bpage\s*\d+\b",
    r"\bsource\s*:",
    r"\bannual report\b",
    r"\bfinancial statements?\b",
    r"\bindependent auditor",
    r"\bstatutory auditor",
    r"\bauditor's report",
    r"\bauditors report",
    r"\bprofit and loss account\b",
    r"\bbalance sheet\b",
    r"\bcash flow statement\b",
    r"\boperating revenue\b",
    r"\bother income\b",
    r"\bearnings per share\b",
    r"\bprofit before tax\b",
    r"\bprofit after tax\b",
    r"\btotal assets\b",
    r"\btotal liabilities\b",
    r"\bshare capital\b",
    r"\bcorporate social responsibility\b",
    r"\bcsr expenditure\b",
    r"\bmaterial issue\b",
    r"\bshareholders\b",
    r"\bboard of directors\b",
    r"\bremuneration\b",
    r"\bregistered office\b",
    r"\bnotice of annual general meeting\b",
]


# ============================================================
# FINANCIAL NOISE
# ============================================================

FINANCIAL_PATTERNS = [
    "operating revenue",
    "revenue from operations",
    "total revenue",
    "profit before tax",
    "profit after tax",
    "net profit",
    "ebitda",
    "earnings per share",
    "basic eps",
    "diluted eps",
    "total assets",
    "total liabilities",
    "trade receivables",
    "trade payables",
    "cash and cash equivalents",
    "financial instruments",
    "fair value",
    "deferred tax",
    "income tax",
    "tax expense",
    "auditor",
    "audit fee",
    "statutory audit",
    "share capital",
    "reserves and surplus",
    "dividend",
]


# ============================================================
# COMPANY NORMALIZATION
# ============================================================

def normalize_company_name(name):

    if pd.isna(name):
        return ""

    name = str(name).strip()

    name = re.sub(
        r"\s+",
        " ",
        name,
    )

    name = name.lower()

    name = re.sub(
        r"\.pdf$",
        "",
        name,
        flags=re.I,
    )

    suffixes = [
        " limited",
        " ltd",
        " ltd.",
        " private limited",
        " pvt limited",
        " pvt ltd",
        " pvt. ltd.",
        " plc",
        " incorporated",
        " inc.",
        " inc",
        " corporation",
        " corp.",
        " corp",
        " llp",
    ]

    changed = True

    while changed:

        changed = False

        for suffix in suffixes:

            if name.endswith(suffix):

                name = name[
                    :-len(suffix)
                ].strip()

                changed = True

    name = re.sub(
        r"[^a-z0-9]+",
        " ",
        name,
    )

    name = re.sub(
        r"\s+",
        " ",
        name,
    ).strip()

    return name


# ============================================================
# DISPLAY COMPANY NAME
# ============================================================

def clean_company_display_name(name):

    if pd.isna(name):
        return ""

    name = str(name).strip()

    name = re.sub(
        r"\.pdf$",
        "",
        name,
        flags=re.I,
    )

    name = re.sub(
        r"\s+annual\s+report.*$",
        "",
        name,
        flags=re.I,
    )

    name = re.sub(
        r"\s+annual.*$",
        "",
        name,
        flags=re.I,
    )

    return name.strip()


# ============================================================
# FIND INPUT FILE
# ============================================================

def find_input_file():

    target_name = "technology_analysis_filled.xlsx"

    possible_locations = [
        os.path.join(
            BASE_DIR,
            target_name,
        ),
        os.path.join(
            BASE_DIR,
            "raw_data",
            target_name,
        ),
        os.path.join(
            BASE_DIR,
            "data",
            target_name,
        ),
    ]

    for path in possible_locations:

        if os.path.exists(path):
            return path

    for root, dirs, files in os.walk(BASE_DIR):

        for file in files:

            if file.lower() == target_name.lower():

                return os.path.join(
                    root,
                    file,
                )

    candidates = []

    for root, dirs, files in os.walk(BASE_DIR):

        for file in files:

            if file.lower().endswith(
                (".xlsx", ".xls")
            ):

                if "technology" in file.lower():

                    candidates.append(
                        os.path.join(
                            root,
                            file,
                        )
                    )

    if candidates:
        return candidates[0]

    return None


# ============================================================
# REMOVE SOURCE METADATA
# ============================================================

def remove_source_metadata(text):

    if not text:
        return ""

    text = str(text)

    text = re.sub(
        r"https?://\S+",
        " ",
        text,
        flags=re.I,
    )

    text = re.sub(
        r"www\.\S+",
        " ",
        text,
        flags=re.I,
    )

    text = re.sub(
        r"\b[\w .()&'’\-]+\.pdf\b",
        " ",
        text,
        flags=re.I,
    )

    text = re.sub(
        r"(?i)\bsource\s*:\s*[^|;\n]+",
        " ",
        text,
    )

    text = re.sub(
        r"(?i)\bpage\s*[:#\-]?\s*\d+\b",
        " ",
        text,
    )

    text = re.sub(
        r"(?i)\brag\s+evidence\s*:",
        " ",
        text,
    )

    text = re.sub(
        r"(?i)\boriginal\s+evidence\s*:",
        " ",
        text,
    )

    text = re.sub(
        r"[A-Za-z]:\\[^ ]+",
        " ",
        text,
    )

    return text


# ============================================================
# DEEP CLEAN
# ============================================================

def deep_clean_evidence(text):

    if not text:
        return ""

    text = remove_source_metadata(text)

    text = re.sub(
        r"[\r\n]+",
        ". ",
        text,
    )

    text = re.sub(
        r"[|]+",
        " ",
        text,
    )

    text = re.sub(
        r"\.{2,}",
        ".",
        text,
    )

    headings = [
        "table of contents",
        "contents",
        "annual report",
        "corporate overview",
        "financial statements",
        "independent auditors report",
        "independent auditor's report",
        "statutory auditors report",
        "board of directors",
        "management discussion and analysis",
        "directors report",
    ]

    for heading in headings:

        text = re.sub(
            re.escape(heading),
            " ",
            text,
            flags=re.I,
        )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# SPLIT SENTENCES
# ============================================================

def split_sentences(text):

    if not text:
        return []

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    sentences = re.split(
        r"(?<=[.!?])\s+(?=[A-Z0-9])",
        text,
    )

    cleaned = []

    for sentence in sentences:

        sentence = sentence.strip()

        if len(sentence) < 20:
            continue

        cleaned.append(sentence)

    return cleaned


# ============================================================
# NOISE CHECK
# ============================================================

def is_noise_sentence(sentence):

    if not sentence:
        return True

    low = sentence.lower()

    if len(sentence.split()) < 5:
        return True

    numbers = re.findall(
        r"\b\d+(?:\.\d+)?\b",
        sentence,
    )

    words = sentence.split()

    if words:

        if len(numbers) / len(words) > 0.30:
            return True

    financial_hits = 0

    for pattern in FINANCIAL_PATTERNS:

        if pattern in low:
            financial_hits += 1

    if financial_hits >= 2:
        return True

    for pattern in NOISE_PATTERNS:

        if re.search(
            pattern,
            low,
            flags=re.I,
        ):

            if (
                "cyber" not in low
                and "security" not in low
            ):
                return True

    if sentence.count("|") >= 2:
        return True

    letters = re.findall(
        r"[A-Za-z]",
        sentence,
    )

    uppercase = re.findall(
        r"[A-Z]",
        sentence,
    )

    if len(letters) > 20:

        if len(uppercase) / len(letters) > 0.75:
            return True

    return False


# ============================================================
# CLEAN SENTENCE
# ============================================================

def clean_sentence(sentence):

    sentence = deep_clean_evidence(sentence)

    if not sentence:
        return ""

    sentence = re.sub(
        r"(?i)^(technology|digital|it|r&d)\s*:\s*",
        "",
        sentence,
    )

    sentence = re.sub(
        r"\s+",
        " ",
        sentence,
    ).strip()

    return sentence


# ============================================================
# EXTRACT TECHNOLOGIES
# ============================================================

def extract_technologies(text):

    if not text:
        return []

    low = " " + text.lower() + " "

    found = []

    aliases = sorted(
        TECHNOLOGY_ALIASES.items(),
        key=lambda x: len(x[0]),
        reverse=True,
    )

    for search_term, display_name in aliases:

        if len(search_term.strip()) <= 3:

            pattern = (
                r"(?<![a-z0-9])"
                + re.escape(search_term.strip())
                + r"(?![a-z0-9])"
            )

        else:

            pattern = (
                r"(?<!\w)"
                + re.escape(search_term.strip())
                + r"(?!\w)"
            )

        if re.search(
            pattern,
            low,
            flags=re.I,
        ):

            if display_name not in found:
                found.append(display_name)

    return found


# ============================================================
# SCORE SENTENCE
# ============================================================

def score_sentence(sentence, parameter):

    if not sentence:
        return 0

    low = sentence.lower()

    score = 0

    keywords = PARAMETER_KEYWORDS.get(
        parameter,
        [],
    )

    for keyword in keywords:

        if keyword.lower() in low:

            if len(keyword.split()) >= 2:
                score += 5
            else:
                score += 2

    technologies = extract_technologies(sentence)

    score += min(
        len(technologies) * 3,
        15,
    )

    action_words = [
        "implemented",
        "deployed",
        "adopted",
        "uses",
        "using",
        "used",
        "developed",
        "launched",
        "integrated",
        "migrated",
        "automated",
        "enabled",
        "invested",
        "partnered",
        "collaborated",
        "planning",
        "planned",
    ]

    for word in action_words:

        if re.search(
            r"\b"
            + re.escape(word)
            + r"\b",
            low,
        ):

            score += 2

    for pattern in FINANCIAL_PATTERNS:

        if pattern in low:
            score -= 5

    number_count = len(
        re.findall(
            r"\b\d+(?:\.\d+)?\b",
            sentence,
        )
    )

    if number_count >= 5:
        score -= 5

    return score


# ============================================================
# EXTRACT PURPOSE
# ============================================================

def extract_purpose(sentence):

    if not sentence:
        return ""

    low = sentence.lower()

    patterns = [
        r"\bused\s+for\s+(.+)",
        r"\bused\s+to\s+(.+)",
        r"\butilised\s+for\s+(.+)",
        r"\butilized\s+for\s+(.+)",
        r"\bto\s+support\s+(.+)",
        r"\bto\s+enable\s+(.+)",
        r"\bto\s+improve\s+(.+)",
        r"\bto\s+enhance\s+(.+)",
        r"\bto\s+automate\s+(.+)",
        r"\bto\s+provide\s+(.+)",
        r"\bfor\s+improving\s+(.+)",
        r"\bfor\s+supporting\s+(.+)",
        r"\bfor\s+enhancing\s+(.+)",
        r"\bsupporting\s+(.+)",
        r"\benabling\s+(.+)",
        r"\bhelping\s+(.+)",
        r"\bhelps\s+(.+)",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            low,
            flags=re.I,
        )

        if match:

            purpose = match.group(1).strip()

            purpose = re.split(
                r"[.;]",
                purpose,
            )[0]

            purpose = re.sub(
                r"\s+",
                " ",
                purpose,
            ).strip()

            words = purpose.split()

            if 3 <= len(words) <= 20:
                return purpose

    return ""


# ============================================================
# GET RELEVANT SENTENCES
# ============================================================

def get_relevant_sentences(
    evidence,
    parameter,
    max_sentences=8,
):

    if not evidence:
        return []

    evidence = deep_clean_evidence(evidence)

    sentences = split_sentences(evidence)

    scored = []

    for sentence in sentences:

        sentence = clean_sentence(sentence)

        if not sentence:
            continue

        if is_noise_sentence(sentence):
            continue

        score = score_sentence(
            sentence,
            parameter,
        )

        if score > 0:

            scored.append(
                (
                    score,
                    sentence,
                )
            )

    scored.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    selected = []

    seen = set()

    for score, sentence in scored:

        normalized = re.sub(
            r"[^a-z0-9]",
            "",
            sentence.lower(),
        )

        if normalized in seen:
            continue

        seen.add(normalized)

        selected.append(sentence)

        if len(selected) >= max_sentences:
            break

    return selected


# ============================================================
# EXTRACT TECHNOLOGIES FROM SENTENCES
# ============================================================

def extract_technologies_from_sentences(sentences):

    technologies = []

    for sentence in sentences:

        techs = extract_technologies(sentence)

        for tech in techs:

            if tech not in technologies:
                technologies.append(tech)

    return technologies


# ============================================================
# FILTER TECHNOLOGIES
# ============================================================

def filter_technologies(
    technologies,
    parameter,
):

    if not technologies:
        return []

    parameter_groups = {

        "Cloud Adoption": {
            "Cloud Computing",
            "Cloud Platform",
            "Cloud Platforms",
            "Cloud Infrastructure",
            "Cloud-Native",
            "Hybrid Cloud",
            "Public Cloud",
            "Private Cloud",
            "Multi-Cloud",
            "AWS",
            "Microsoft Azure",
            "Google Cloud",
            "Oracle Cloud",
            "SaaS",
            "PaaS",
            "IaaS",
        },

        "Automation": {
            "RPA",
            "Intelligent Automation",
            "Workflow Automation",
            "Process Automation",
            "Business Process Automation",
            "Industrial Automation",
            "Automated Testing",
            "Automation",
            "Robotics",
        },

        "Cybersecurity": {
            "Cybersecurity",
            "Information Security",
            "IAM",
            "PAM",
            "SIEM",
            "Security Operations",
            "Threat Detection",
            "Endpoint Security",
            "Network Security",
            "Vulnerability Management",
        },

        "Emerging Technologies": {
            "AI",
            "Generative AI",
            "Machine Learning",
            "Deep Learning",
            "IoT",
            "Robotics",
            "Digital Twin",
            "Digital Twins",
            "Edge Computing",
            "Blockchain",
            "Computer Vision",
            "AR",
            "VR",
            "AR/VR",
            "Industry 4.0",
            "Advanced Analytics",
            "Predictive Analytics",
        },
    }

    if parameter in parameter_groups:

        allowed = parameter_groups[parameter]

        filtered = [
            tech
            for tech in technologies
            if tech in allowed
        ]

        if filtered:
            return filtered

    generic = {
        "Software",
        "Database",
        "Databases",
        "Automation",
        "Microsoft",
    }

    return [
        tech
        for tech in technologies
        if tech not in generic
    ]


# ============================================================
# TRIM SENTENCE
# ============================================================

def trim_sentence(
    sentence,
    max_chars=280,
):

    if not sentence:
        return ""

    sentence = sentence.strip()

    if len(sentence) <= max_chars:
        return sentence

    shortened = sentence[:max_chars]

    shortened = shortened.rsplit(
        " ",
        1,
    )[0]

    return shortened + "..."


# ============================================================
# R&D FALLBACK
# ============================================================

def extract_rd_fallback(evidence):

    if not evidence:
        return []

    sentences = split_sentences(
        deep_clean_evidence(evidence)
    )

    results = []

    rd_words = [
        "research",
        "development",
        "innovation",
        "laboratory",
        "laboratories",
        "patent",
        "patents",
        "intellectual property",
        "product development",
        "technology development",
        "engineering",
    ]

    for sentence in sentences:

        if is_noise_sentence(sentence):
            continue

        low = sentence.lower()

        hits = sum(
            1
            for word in rd_words
            if word in low
        )

        if hits >= 1:
            results.append(sentence)

    return results


# ============================================================
# ORGANIZATION EXTRACTION
# ============================================================

def extract_organizations(sentences):

    organizations = []

    patterns = [
        r"\b[A-Z][A-Za-z&.\- ]{2,40}"
        r"\b(?:Technologies|Technology|"
        r"Systems|Solutions|Cloud|"
        r"Software|Labs|Laboratories|"
        r"University|Institute|"
        r"Corporation|Limited|Ltd)\b",
    ]

    for sentence in sentences:

        for pattern in patterns:

            matches = re.findall(
                pattern,
                sentence,
            )

            for match in matches:

                match = match.strip()

                if len(match.split()) <= 8:

                    if match not in organizations:
                        organizations.append(match)

    return organizations[:5]


# ============================================================
# BUILD PARAMETER SUMMARY
# ============================================================

def build_parameter_summary(
    evidence,
    parameter,
):

    if not evidence:
        return MISSING_VALUE

    sentences = get_relevant_sentences(
        evidence,
        parameter,
        max_sentences=10,
    )

    if not sentences:
        return MISSING_VALUE

    technologies = (
        extract_technologies_from_sentences(
            sentences
        )
    )

    technologies = filter_technologies(
        technologies,
        parameter,
    )

    technologies = technologies[:6]

    tech_text = ", ".join(technologies)

    purposes = []

    for sentence in sentences:

        purpose = extract_purpose(sentence)

        if purpose and purpose not in purposes:
            purposes.append(purpose)

    purposes = purposes[:2]

    # --------------------------------------------------------
    # Current Technology Adoption
    # --------------------------------------------------------

    if parameter == "Current Technology Adoption":

        if tech_text and purposes:

            return (
                f"Adopted technologies include "
                f"{tech_text}, supporting "
                f"{'; '.join(purposes)}."
            )

        if tech_text:

            return (
                f"The company uses "
                f"{tech_text} across its "
                f"operations."
            )

        return (
            "Technology adoption is indicated "
            "in the collected evidence, but "
            "specific technologies could not "
            "be reliably identified."
        )

    # --------------------------------------------------------
    # Digital Transformation
    # --------------------------------------------------------

    if parameter == "Digital Transformation":

        if tech_text and purposes:

            return (
                f"Digital transformation includes "
                f"{tech_text}, supporting "
                f"{'; '.join(purposes)}."
            )

        if tech_text:

            return (
                f"Digital transformation initiatives "
                f"include {tech_text}."
            )

        return (
            "Digital transformation initiatives "
            "are indicated in the collected evidence, "
            "but specific technologies could not "
            "be reliably identified."
        )

    # --------------------------------------------------------
    # R&D
    # --------------------------------------------------------

    if parameter == "R&D":

        if tech_text:

            return (
                f"Technology-related R&D includes "
                f"{tech_text}."
            )

        rd_sentences = extract_rd_fallback(evidence)

        if rd_sentences:

            concise = []

            for sentence in rd_sentences[:2]:

                sentence = trim_sentence(
                    sentence,
                    240,
                )

                concise.append(sentence)

            return (
                "Technology-related R&D focuses on "
                + " ".join(concise)
            )

        return MISSING_VALUE

    # --------------------------------------------------------
    # Emerging Technologies
    # --------------------------------------------------------

    if parameter == "Emerging Technologies":

        if tech_text:

            return (
                f"Emerging technologies identified "
                f"include {tech_text}."
            )

        return MISSING_VALUE

    # --------------------------------------------------------
    # Technology Partnerships
    # --------------------------------------------------------

    if parameter == "Technology Partnerships":

        organizations = extract_organizations(
            sentences
        )

        if tech_text:

            if organizations:

                return (
                    f"Technology partnerships involve "
                    f"{tech_text}, with external "
                    f"technology providers or "
                    f"collaborators including "
                    f"{', '.join(organizations[:3])}."
                )

            return (
                f"Technology partnerships and "
                f"collaborations involve "
                f"{tech_text}."
            )

        if organizations:

            return (
                "Technology collaborations include "
                + ", ".join(organizations[:3])
                + "."
            )

        return MISSING_VALUE

    # --------------------------------------------------------
    # Technology Investments
    # --------------------------------------------------------

    if parameter == "Technology Investments":

        if tech_text:

            return (
                f"Technology investment areas "
                f"include {tech_text}."
            )

        investment_sentences = []

        for sentence in sentences:

            low = sentence.lower()

            if any(
                word in low
                for word in [
                    "invest",
                    "investment",
                    "spending",
                    "expenditure",
                    "capex",
                ]
            ):

                investment_sentences.append(
                    sentence
                )

        if investment_sentences:

            return (
                "Technology investments focus on "
                + trim_sentence(
                    investment_sentences[0],
                    250,
                )
            )

        return MISSING_VALUE

    # --------------------------------------------------------
    # Cloud Adoption
    # --------------------------------------------------------

    if parameter == "Cloud Adoption":

        if tech_text:

            return (
                f"Cloud adoption includes "
                f"{tech_text}."
            )

        cloud_sentences = [
            s
            for s in sentences
            if "cloud" in s.lower()
        ]

        if cloud_sentences:

            return (
                "The company has cloud-related "
                "adoption or implementation "
                "indicated in the collected evidence."
            )

        return MISSING_VALUE

    # --------------------------------------------------------
    # Automation
    # --------------------------------------------------------

    if parameter == "Automation":

        if tech_text:

            return (
                f"Automation capabilities include "
                f"{tech_text}."
            )

        automation_sentences = [
            s
            for s in sentences
            if (
                "automat" in s.lower()
                or "rpa" in s.lower()
                or "robotic" in s.lower()
            )
        ]

        if automation_sentences:

            return (
                "The company uses automation "
                "in selected business or "
                "operational processes."
            )

        return MISSING_VALUE

    # --------------------------------------------------------
    # Cybersecurity
    # --------------------------------------------------------

    if parameter == "Cybersecurity":

        if tech_text:

            return (
                f"Cybersecurity capabilities include "
                f"{tech_text}."
            )

        security_sentences = [
            s
            for s in sentences
            if (
                "security" in s.lower()
                or "cyber" in s.lower()
            )
        ]

        if security_sentences:

            return (
                "Cybersecurity controls and "
                "information-security measures "
                "are indicated in the collected evidence."
            )

        return MISSING_VALUE

    # --------------------------------------------------------
    # Future Roadmaps
    # --------------------------------------------------------

    if parameter == "Future Technology Roadmaps":

        if tech_text:

            return (
                f"Future technology plans reference "
                f"{tech_text}."
            )

        future_sentences = [
            s
            for s in sentences
            if any(
                word in s.lower()
                for word in [
                    "planned",
                    "planning",
                    "future",
                    "roadmap",
                    "upcoming",
                    "will implement",
                    "will deploy",
                ]
            )
        ]

        if future_sentences:

            return (
                "Future technology initiatives "
                "include planned digital and "
                "technology improvements."
            )

        return MISSING_VALUE

    # --------------------------------------------------------
    # Technology Pain Areas
    # --------------------------------------------------------

    if parameter == "Technology Pain Areas":

        pain_sentences = []

        pain_words = [
            "challenge",
            "risk",
            "gap",
            "limitation",
            "legacy",
            "difficulty",
            "constraint",
            "shortage",
            "skill gap",
            "scalability",
            "integration",
        ]

        for sentence in sentences:

            low = sentence.lower()

            if any(
                word in low
                for word in pain_words
            ):

                pain_sentences.append(sentence)

        if pain_sentences:

            if tech_text:

                return (
                    f"Technology-related concerns "
                    f"include challenges associated "
                    f"with {tech_text}."
                )

            return (
                "Technology-related challenges "
                "identified in the collected evidence "
                "include "
                + trim_sentence(
                    pain_sentences[0],
                    260,
                )
            )

        return MISSING_VALUE

    if tech_text:

        return (
            f"Technology-related activities "
            f"include {tech_text}."
        )

    return MISSING_VALUE


# ============================================================
# DETECT COMPANY COLUMN
# ============================================================

def detect_company_column(df):

    candidates = [
        "Company",
        "Company Name",
        "company",
        "company_name",
        "CompanyName",
        "Name",
    ]

    for column in candidates:

        if column in df.columns:
            return column

    for column in df.columns:

        low = str(column).lower()

        if (
            "company" in low
            or low == "name"
        ):

            return column

    return None


# ============================================================
# DETECT EVIDENCE COLUMN
# ============================================================

def detect_evidence_column(df):

    candidates = [
        "Evidence",
        "RAG Evidence",
        "Original Evidence",
        "Evidence Text",
        "Text",
        "Content",
    ]

    for column in candidates:

        if column in df.columns:
            return column

    return None


# ============================================================
# DETECT PARAMETER COLUMN
# ============================================================

def detect_parameter_column(df):

    candidates = [
        "Parameter",
        "Technology Parameter",
        "parameter",
        "technology_parameter",
    ]

    for column in candidates:

        if column in df.columns:
            return column

    return None


# ============================================================
# LOAD INPUT
# ============================================================

def load_input_file(input_file):

    print()
    print("Loading input Excel...")

    excel = pd.ExcelFile(input_file)

    print(
        "Sheets found:",
        excel.sheet_names,
    )

    for sheet in excel.sheet_names:

        if sheet.lower() in [
            "original evidence",
            "evidence",
            "rag evidence",
            "technology detail",
        ]:

            try:

                temp = pd.read_excel(
                    input_file,
                    sheet_name=sheet,
                )

                company_col = detect_company_column(temp)
                evidence_col = detect_evidence_column(temp)
                parameter_col = detect_parameter_column(temp)

                if (
                    company_col
                    and evidence_col
                    and parameter_col
                ):

                    print(
                        f"Using long-format sheet: {sheet}"
                    )

                    return (
                        "long",
                        temp,
                    )

            except Exception:
                pass

    for sheet in excel.sheet_names:

        try:

            temp = pd.read_excel(
                input_file,
                sheet_name=sheet,
            )

            company_col = detect_company_column(temp)
            evidence_col = detect_evidence_column(temp)
            parameter_col = detect_parameter_column(temp)

            if (
                company_col
                and evidence_col
                and parameter_col
            ):

                print(
                    f"Using detected long-format sheet: {sheet}"
                )

                return (
                    "long",
                    temp,
                )

        except Exception:
            continue

    for sheet in excel.sheet_names:

        try:

            temp = pd.read_excel(
                input_file,
                sheet_name=sheet,
            )

            company_col = detect_company_column(temp)

            parameter_count = sum(
                1
                for parameter in TECHNOLOGY_PARAMETERS
                if parameter in temp.columns
            )

            if (
                company_col
                and parameter_count >= 3
            ):

                print(
                    f"Using wide-format sheet: {sheet}"
                )

                return (
                    "wide",
                    temp,
                )

        except Exception:
            continue

    raise ValueError(
        "Could not find a valid technology "
        "evidence sheet in the Excel file."
    )


# ============================================================
# PREPARE LONG DATA
# ============================================================

def prepare_long_data(df):

    company_col = detect_company_column(df)
    parameter_col = detect_parameter_column(df)
    evidence_col = detect_evidence_column(df)

    if not all([
        company_col,
        parameter_col,
        evidence_col,
    ]):

        raise ValueError(
            "Long format must contain "
            "Company, Parameter and Evidence columns."
        )

    records = []

    for _, row in df.iterrows():

        company = clean_company_display_name(
            row[company_col]
        )

        parameter = str(
            row[parameter_col]
        ).strip()

        evidence = row[evidence_col]

        if not company:
            continue

        if parameter not in TECHNOLOGY_PARAMETERS:
            continue

        if pd.isna(evidence):
            evidence = ""

        evidence = str(evidence).strip()

        records.append({
            "Company": company,
            "Company Key": normalize_company_name(company),
            "Parameter": parameter,
            "Evidence": evidence,
        })

    return pd.DataFrame(records)


# ============================================================
# WIDE TO LONG
# ============================================================

def wide_to_long(df):

    company_col = detect_company_column(df)

    if not company_col:

        raise ValueError(
            "Could not detect company column."
        )

    records = []

    for _, row in df.iterrows():

        company = clean_company_display_name(
            row[company_col]
        )

        if not company:
            continue

        company_key = normalize_company_name(company)

        for parameter in TECHNOLOGY_PARAMETERS:

            if parameter not in df.columns:
                continue

            value = row[parameter]

            if pd.isna(value):
                value = ""

            value = str(value).strip()

            records.append({
                "Company": company,
                "Company Key": company_key,
                "Parameter": parameter,
                "Evidence": value,
            })

    return pd.DataFrame(records)


# ============================================================
# COMBINE DUPLICATES
# ============================================================

def combine_duplicate_companies(long_df):

    if long_df.empty:
        return long_df

    grouped = []

    for company_key, group in long_df.groupby(
        "Company Key"
    ):

        names = [
            str(x).strip()
            for x in group["Company"]
            if str(x).strip()
        ]

        if not names:
            continue

        display_name = sorted(
            names,
            key=lambda x: (
                len(x),
                x.lower().endswith(
                    (" ltd", " limited")
                ),
            ),
        )[0]

        for parameter in TECHNOLOGY_PARAMETERS:

            parameter_rows = group[
                group["Parameter"] == parameter
            ]

            evidence_parts = []

            for value in parameter_rows["Evidence"]:

                if pd.isna(value):
                    continue

                value = str(value).strip()

                if value:
                    evidence_parts.append(value)

            evidence = "\n".join(
                evidence_parts
            )

            grouped.append({
                "Company": display_name,
                "Company Key": company_key,
                "Parameter": parameter,
                "Evidence": evidence,
            })

    return pd.DataFrame(grouped)


# ============================================================
# USEFUL SUMMARY CHECK
# ============================================================

def company_has_useful_summary(row):

    if row is None:
        return False

    useful_count = 0

    for parameter in TECHNOLOGY_PARAMETERS:

        value = row.get(
            parameter,
            MISSING_VALUE,
        )

        if pd.isna(value):
            continue

        value = str(value).strip()

        if (
            value
            and value != MISSING_VALUE
        ):

            useful_count += 1

    return useful_count > 0


# ============================================================
# LOAD EXISTING OUTPUT
# ============================================================

def load_existing_output():

    empty_summary = pd.DataFrame(
        columns=[
            "Company",
            *TECHNOLOGY_PARAMETERS,
        ]
    )

    empty_detail = pd.DataFrame(
        columns=[
            "Company",
            "Parameter",
            "Identified Technologies",
            "Relevant Evidence",
        ]
    )

    empty_original = pd.DataFrame(
        columns=[
            "Company",
            "Company Key",
            "Parameter",
            "Evidence",
        ]
    )

    if not os.path.exists(OUTPUT_FILE):

        print()
        print(
            "No previous output file found."
        )

        return (
            empty_summary,
            empty_detail,
            empty_original,
        )

    print()
    print(
        "Existing output found:"
    )

    print(
        OUTPUT_FILE
    )

    try:

        excel = pd.ExcelFile(
            OUTPUT_FILE
        )

        print(
            "Existing sheets:",
            excel.sheet_names,
        )

        if "Technology Summary" in excel.sheet_names:

            summary_df = pd.read_excel(
                OUTPUT_FILE,
                sheet_name="Technology Summary",
            )

        else:

            summary_df = empty_summary

        if "Technology Detail" in excel.sheet_names:

            detail_df = pd.read_excel(
                OUTPUT_FILE,
                sheet_name="Technology Detail",
            )

        else:

            detail_df = empty_detail

        if "Original Evidence" in excel.sheet_names:

            original_df = pd.read_excel(
                OUTPUT_FILE,
                sheet_name="Original Evidence",
            )

        else:

            original_df = empty_original

        return (
            summary_df,
            detail_df,
            original_df,
        )

    except Exception as e:

        print()
        print(
            "WARNING: Could not read existing output."
        )

        print(e)

        print(
            "Starting with empty output."
        )

        return (
            empty_summary,
            empty_detail,
            empty_original,
        )


# ============================================================
# GET COMPLETED COMPANIES
# ============================================================

def get_completed_company_keys(summary_df):

    completed = set()

    if summary_df is None or summary_df.empty:
        return completed

    company_col = detect_company_column(
        summary_df
    )

    if not company_col:
        return completed

    for _, row in summary_df.iterrows():

        company = row.get(
            company_col,
            "",
        )

        if pd.isna(company):
            continue

        company = clean_company_display_name(
            company
        )

        if not company:
            continue

        if company_has_useful_summary(row):

            completed.add(
                normalize_company_name(
                    company
                )
            )

    return completed


# ============================================================
# FILTER COMPANIES ACCORDING TO MODE
# ============================================================

def select_companies_to_process(
    long_df,
    existing_summary,
):

    if long_df.empty:
        return long_df

    all_keys = set(
        long_df["Company Key"].dropna()
    )

    print()
    print(
        "Total companies available in input:",
        len(all_keys),
    )

    # --------------------------------------------------------
    # FULL
    # --------------------------------------------------------

    if RUN_MODE.upper() == "FULL":

        print()
        print(
            "RUN MODE = FULL"
        )

        print(
            "All companies will be processed."
        )

        return long_df

    # --------------------------------------------------------
    # TEST
    # --------------------------------------------------------

    if RUN_MODE.upper() == "TEST":

        print()
        print(
            "RUN MODE = TEST"
        )

        test_keys = {
            normalize_company_name(x)
            for x in TEST_COMPANIES
        }

        selected_keys = (
            all_keys.intersection(test_keys)
        )

        print(
            "Test companies requested:",
            len(test_keys),
        )

        print(
            "Test companies found in input:",
            len(selected_keys),
        )

        missing_test = (
            test_keys - all_keys
        )

        if missing_test:

            print()
            print(
                "Test companies not found "
                "in input:"
            )

            for key in sorted(missing_test):
                print(
                    "  -",
                    key,
                )

        return long_df[
            long_df["Company Key"].isin(
                selected_keys
            )
        ].copy()

    # --------------------------------------------------------
    # RESUME
    # --------------------------------------------------------

    if RUN_MODE.upper() != "RESUME":

        raise ValueError(
            "Invalid RUN_MODE. Use "
            "'RESUME', 'TEST', or 'FULL'."
        )

    print()
    print(
        "RUN MODE = RESUME"
    )

    completed_keys = (
        get_completed_company_keys(
            existing_summary
        )
    )

    print(
        "Already completed companies:",
        len(completed_keys),
    )

    remaining_keys = (
        all_keys - completed_keys
    )

    print(
        "Remaining companies:",
        len(remaining_keys),
    )

    skipped_count = (
        len(all_keys.intersection(completed_keys))
    )

    print(
        "Companies that will be skipped:",
        skipped_count,
    )

    selected = long_df[
        long_df["Company Key"].isin(
            remaining_keys
        )
    ].copy()

    return selected


# ============================================================
# BUILD SUMMARY TABLE
# ============================================================

def build_summary_table(long_df):

    rows = []

    if long_df.empty:
        return pd.DataFrame(
            columns=[
                "Company",
                *TECHNOLOGY_PARAMETERS,
            ]
        )

    companies = (
        long_df[
            [
                "Company",
                "Company Key",
            ]
        ]
        .drop_duplicates()
        .sort_values("Company")
    )

    total = len(companies)

    for position, (_, company_row) in enumerate(
        companies.iterrows(),
        start=1,
    ):

        company = company_row["Company"]

        company_key = company_row[
            "Company Key"
        ]

        result = {
            "Company": company
        }

        company_data = long_df[
            long_df["Company Key"]
            == company_key
        ]

        for parameter in TECHNOLOGY_PARAMETERS:

            parameter_rows = company_data[
                company_data["Parameter"]
                == parameter
            ]

            evidence_parts = []

            for value in parameter_rows[
                "Evidence"
            ]:

                if pd.isna(value):
                    continue

                value = str(value).strip()

                if value:
                    evidence_parts.append(value)

            evidence = "\n".join(
                evidence_parts
            )

            summary = build_parameter_summary(
                evidence,
                parameter,
            )

            result[parameter] = summary

        rows.append(result)

        print(
            f"[{position}/{total}] Processed: "
            f"{company}"
        )

    return pd.DataFrame(rows)


# ============================================================
# BUILD DETAIL TABLE
# ============================================================

def build_detail_table(long_df):

    rows = []

    if long_df.empty:
        return pd.DataFrame(
            columns=[
                "Company",
                "Parameter",
                "Identified Technologies",
                "Relevant Evidence",
            ]
        )

    for _, row in long_df.iterrows():

        evidence = row["Evidence"]

        parameter = row["Parameter"]

        if not evidence:
            continue

        sentences = get_relevant_sentences(
            evidence,
            parameter,
            max_sentences=10,
        )

        technologies = (
            extract_technologies_from_sentences(
                sentences
            )
        )

        technologies = filter_technologies(
            technologies,
            parameter,
        )

        rows.append({
            "Company": row["Company"],
            "Parameter": parameter,
            "Identified Technologies": ", ".join(
                technologies[:10]
            ),
            "Relevant Evidence": " ".join(
                sentences[:5]
            ),
        })

    return pd.DataFrame(rows)


# ============================================================
# BUILD ORIGINAL EVIDENCE
# ============================================================

def build_original_evidence(long_df):

    if long_df.empty:

        return pd.DataFrame(
            columns=[
                "Company",
                "Company Key",
                "Parameter",
                "Evidence",
            ]
        )

    return long_df.copy()


# ============================================================
# REMOVE DUPLICATES FROM OUTPUT TABLES
# ============================================================

def deduplicate_summary(summary_df):

    if summary_df.empty:
        return summary_df

    company_col = detect_company_column(
        summary_df
    )

    if not company_col:
        return summary_df

    summary_df = summary_df.copy()

    summary_df["_Company Key"] = (
        summary_df[company_col]
        .apply(normalize_company_name)
    )

    # Keep last because new data should
    # replace old data in TEST/FULL.
    summary_df = summary_df.drop_duplicates(
        subset=["_Company Key"],
        keep="last",
    )

    summary_df = summary_df.drop(
        columns=["_Company Key"]
    )

    return summary_df


def deduplicate_detail(detail_df):

    if detail_df.empty:
        return detail_df

    required = [
        "Company",
        "Parameter",
    ]

    if not all(
        column in detail_df.columns
        for column in required
    ):
        return detail_df

    result = detail_df.copy()

    result["_Company Key"] = (
        result["Company"]
        .apply(normalize_company_name)
    )

    result = result.drop_duplicates(
        subset=[
            "_Company Key",
            "Parameter",
        ],
        keep="last",
    )

    result = result.drop(
        columns=["_Company Key"]
    )

    return result


def deduplicate_original(original_df):

    if original_df.empty:
        return original_df

    required = [
        "Company",
        "Parameter",
    ]

    if not all(
        column in original_df.columns
        for column in required
    ):
        return original_df

    result = original_df.copy()

    if "Company Key" not in result.columns:

        result["Company Key"] = (
            result["Company"]
            .apply(normalize_company_name)
        )

    result = result.drop_duplicates(
        subset=[
            "Company Key",
            "Parameter",
        ],
        keep="last",
    )

    return result


# ============================================================
# MERGE EXISTING + NEW
# ============================================================

def merge_outputs(
    existing_summary,
    existing_detail,
    existing_original,
    new_summary,
    new_detail,
    new_original,
):

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    if existing_summary.empty:

        combined_summary = new_summary.copy()

    elif new_summary.empty:

        combined_summary = existing_summary.copy()

    else:

        # New rows come after old rows.
        # deduplicate_summary keeps the new row.
        combined_summary = pd.concat(
            [
                existing_summary,
                new_summary,
            ],
            ignore_index=True,
        )

    combined_summary = deduplicate_summary(
        combined_summary
    )

    # --------------------------------------------------------
    # DETAIL
    # --------------------------------------------------------

    if existing_detail.empty:

        combined_detail = new_detail.copy()

    elif new_detail.empty:

        combined_detail = existing_detail.copy()

    else:

        combined_detail = pd.concat(
            [
                existing_detail,
                new_detail,
            ],
            ignore_index=True,
        )

    combined_detail = deduplicate_detail(
        combined_detail
    )

    # --------------------------------------------------------
    # ORIGINAL EVIDENCE
    # --------------------------------------------------------

    if existing_original.empty:

        combined_original = new_original.copy()

    elif new_original.empty:

        combined_original = existing_original.copy()

    else:

        combined_original = pd.concat(
            [
                existing_original,
                new_original,
            ],
            ignore_index=True,
        )

    combined_original = deduplicate_original(
        combined_original
    )

    return (
        combined_summary,
        combined_detail,
        combined_original,
    )


# ============================================================
# FORMAT EXCEL
# ============================================================

def format_excel(output_file):

    wb = load_workbook(output_file)

    header_fill = PatternFill(
        "solid",
        fgColor="1F4E78",
    )

    header_font = Font(
        color="FFFFFF",
        bold=True,
    )

    thin = Side(
        style="thin",
        color="D9E2F3",
    )

    border = Border(
        bottom=thin,
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    if "Technology Summary" in wb.sheetnames:

        ws = wb["Technology Summary"]

        ws.freeze_panes = "B2"

        ws.auto_filter.ref = ws.dimensions

        for cell in ws[1]:

            cell.fill = header_fill
            cell.font = header_font

            cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
                wrap_text=True,
            )

        for row in ws.iter_rows(min_row=2):

            for cell in row:

                cell.alignment = Alignment(
                    vertical="top",
                    wrap_text=True,
                )

                cell.border = border

        ws.column_dimensions["A"].width = 32

        for column in range(
            2,
            ws.max_column + 1,
        ):

            ws.column_dimensions[
                get_column_letter(column)
            ].width = 55

        ws.row_dimensions[1].height = 45

    # --------------------------------------------------------
    # DETAIL
    # --------------------------------------------------------

    if "Technology Detail" in wb.sheetnames:

        ws = wb["Technology Detail"]

        ws.freeze_panes = "A2"

        ws.auto_filter.ref = ws.dimensions

        for cell in ws[1]:

            cell.fill = header_fill
            cell.font = header_font

            cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
                wrap_text=True,
            )

        widths = {
            "A": 32,
            "B": 32,
            "C": 40,
            "D": 100,
        }

        for column, width in widths.items():

            ws.column_dimensions[
                column
            ].width = width

        for row in ws.iter_rows(min_row=2):

            for cell in row:

                cell.alignment = Alignment(
                    vertical="top",
                    wrap_text=True,
                )

    # --------------------------------------------------------
    # ORIGINAL EVIDENCE
    # --------------------------------------------------------

    if "Original Evidence" in wb.sheetnames:

        ws = wb["Original Evidence"]

        ws.freeze_panes = "A2"

        ws.auto_filter.ref = ws.dimensions

        for cell in ws[1]:

            cell.fill = header_fill
            cell.font = header_font

            cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
                wrap_text=True,
            )

        widths = {
            "A": 32,
            "B": 40,
            "C": 32,
            "D": 120,
        }

        for column, width in widths.items():

            if column in ws.column_dimensions:

                ws.column_dimensions[
                    column
                ].width = width

        for row in ws.iter_rows(min_row=2):

            for cell in row:

                cell.alignment = Alignment(
                    vertical="top",
                    wrap_text=True,
                )

    wb.save(output_file)


# ============================================================
# VALIDATE SUMMARY
# ============================================================

def validate_summary(summary_df):

    forbidden_patterns = [
        r"\bsource\s*:",
        r"\bpage\s*[:#\-]?\s*\d+\b",
        r"\.pdf\b",
        r"\brag\s+evidence\b",
        r"\boriginal\s+evidence\b",
        r"https?://",
    ]

    problems = []

    for _, row in summary_df.iterrows():

        company = row["Company"]

        for parameter in TECHNOLOGY_PARAMETERS:

            value = str(
                row.get(
                    parameter,
                    "",
                )
            )

            for pattern in forbidden_patterns:

                if re.search(
                    pattern,
                    value,
                    flags=re.I,
                ):

                    problems.append(
                        (
                            company,
                            parameter,
                            value[:200],
                        )
                    )

    if problems:

        print()
        print(
            "WARNING: Metadata found "
            "inside summary."
        )

        for problem in problems[:10]:

            print(problem)

        return False

    print()
    print(
        "Validation passed: "
        "no source/page/PDF metadata "
        "found in summary."
    )

    return True


# ============================================================
# SAVE OUTPUT
# ============================================================

def save_output(
    summary_df,
    detail_df,
    original_df,
):

    print()
    print(
        "Writing Excel..."
    )

    with pd.ExcelWriter(
        OUTPUT_FILE,
        engine="openpyxl",
    ) as writer:

        summary_df.to_excel(
            writer,
            sheet_name="Technology Summary",
            index=False,
        )

        detail_df.to_excel(
            writer,
            sheet_name="Technology Detail",
            index=False,
        )

        original_df.to_excel(
            writer,
            sheet_name="Original Evidence",
            index=False,
        )

    print(
        "Formatting Excel..."
    )

    format_excel(
        OUTPUT_FILE
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 75)
    print(
        "TECHNOLOGY INTELLIGENCE SUMMARIZER - RESUMABLE V9"
    )
    print("=" * 75)

    print()
    print(
        "Project folder:"
    )

    print(BASE_DIR)

    print()
    print(
        "RUN MODE:",
        RUN_MODE,
    )

    if RUN_MODE.upper() == "RESUME":

        print()
        print(
            "RESUME MODE:"
        )

        print(
            "Already completed companies will be skipped."
        )

        print(
            "Only remaining companies will be processed."
        )

    elif RUN_MODE.upper() == "TEST":

        print()
        print(
            "TEST MODE:"
        )

        print(
            "Only TEST_COMPANIES will be processed."
        )

    elif RUN_MODE.upper() == "FULL":

        print()
        print(
            "FULL MODE:"
        )

        print(
            "All companies will be processed."
        )

    else:

        raise ValueError(
            "RUN_MODE must be "
            "'RESUME', 'TEST', or 'FULL'."
        )

    # ========================================================
    # FIND INPUT
    # ========================================================

    input_file = find_input_file()

    if not input_file:

        print()
        print(
            "ERROR:"
        )

        print(
            "technology_analysis_filled.xlsx "
            "could not be found."
        )

        return

    print()
    print(
        "Input Excel:"
    )

    print(input_file)

    # ========================================================
    # CREATE OUTPUT DIRECTORY
    # ========================================================

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True,
    )

    # ========================================================
    # LOAD INPUT
    # ========================================================

    format_type, data = load_input_file(
        input_file
    )

    print()
    print(
        "Input format:",
        format_type,
    )

    print(
        "Input rows:",
        len(data),
    )

    # ========================================================
    # CONVERT TO LONG
    # ========================================================

    if format_type == "long":

        long_df = prepare_long_data(
            data
        )

    else:

        long_df = wide_to_long(
            data
        )

    print(
        "Converted rows:",
        len(long_df),
    )

    # ========================================================
    # COMBINE DUPLICATES
    # ========================================================

    print()
    print(
        "Combining duplicate company names..."
    )

    long_df = combine_duplicate_companies(
        long_df
    )

    print(
        "Normalized rows:",
        len(long_df),
    )

    total_input_companies = (
        long_df["Company Key"]
        .nunique()
    )

    print(
        "Unique companies in input:",
        total_input_companies,
    )

    # ========================================================
    # LOAD EXISTING OUTPUT
    # ========================================================

    (
        existing_summary,
        existing_detail,
        existing_original,
    ) = load_existing_output()

    print()
    print(
        "Existing summary rows:",
        len(existing_summary),
    )

    print(
        "Existing detail rows:",
        len(existing_detail),
    )

    print(
        "Existing evidence rows:",
        len(existing_original),
    )

    # ========================================================
    # SELECT COMPANIES
    # ========================================================

    process_df = select_companies_to_process(
        long_df,
        existing_summary,
    )

    companies_to_process = (
        process_df["Company Key"]
        .nunique()
        if not process_df.empty
        else 0
    )

    print()
    print("=" * 75)

    print(
        "PROCESSING PLAN"
    )

    print("=" * 75)

    print()
    print(
        "Total companies in input:",
        total_input_companies,
    )

    print(
        "Companies to process:",
        companies_to_process,
    )

    if RUN_MODE.upper() == "RESUME":

        completed_count = (
            total_input_companies
            - companies_to_process
        )

        print(
            "Companies skipped:",
            completed_count,
        )

    print()

    # ========================================================
    # NOTHING TO PROCESS
    # ========================================================

    if process_df.empty:

        print(
            "No new companies need processing."
        )

        print()

        print(
            "Your existing output is already "
            "up to date."
        )

        print()
        print(
            "Output file:"
        )

        print(
            OUTPUT_FILE
        )

        return

    # ========================================================
    # BUILD NEW SUMMARY
    # ========================================================

    print()
    print("=" * 75)
    print(
        "CREATING NEW TECHNOLOGY SUMMARIES"
    )
    print("=" * 75)

    new_summary_df = build_summary_table(
        process_df
    )

    print()
    print(
        "New summary rows:",
        len(new_summary_df),
    )

    # ========================================================
    # BUILD NEW DETAIL
    # ========================================================

    print()
    print(
        "Creating new technology detail..."
    )

    new_detail_df = build_detail_table(
        process_df
    )

    print(
        "New detail rows:",
        len(new_detail_df),
    )

    # ========================================================
    # BUILD NEW EVIDENCE
    # ========================================================

    print()
    print(
        "Creating new original evidence..."
    )

    new_original_df = (
        build_original_evidence(
            process_df
        )
    )

    print(
        "New evidence rows:",
        len(new_original_df),
    )

    # ========================================================
    # MERGE
    # ========================================================

    print()
    print(
        "Merging existing and newly processed data..."
    )

    (
        final_summary_df,
        final_detail_df,
        final_original_df,
    ) = merge_outputs(
        existing_summary,
        existing_detail,
        existing_original,
        new_summary_df,
        new_detail_df,
        new_original_df,
    )

    # ========================================================
    # SORT
    # ========================================================

    if not final_summary_df.empty:

        final_summary_df = (
            final_summary_df
            .sort_values(
                "Company",
                key=lambda x: x.astype(str).str.lower(),
            )
            .reset_index(drop=True)
        )

    if not final_detail_df.empty:

        final_detail_df = (
            final_detail_df
            .sort_values(
                ["Company", "Parameter"],
                key=lambda x: x.astype(str).str.lower(),
            )
            .reset_index(drop=True)
        )

    if not final_original_df.empty:

        final_original_df = (
            final_original_df
            .sort_values(
                ["Company", "Parameter"],
                key=lambda x: x.astype(str).str.lower(),
            )
            .reset_index(drop=True)
        )

    # ========================================================
    # SAVE
    # ========================================================

    save_output(
        final_summary_df,
        final_detail_df,
        final_original_df,
    )

    # ========================================================
    # VALIDATE
    # ========================================================

    validate_summary(
        final_summary_df
    )

    # ========================================================
    # FINAL COUNTS
    # ========================================================

    final_company_count = (
        final_summary_df["Company"]
        .apply(normalize_company_name)
        .nunique()
        if not final_summary_df.empty
        else 0
    )

    print()
    print("=" * 75)
    print(
        "COMPLETED SUCCESSFULLY"
    )
    print("=" * 75)

    print()

    print(
        "Companies processed this run:",
        companies_to_process,
    )

    print(
        "Total companies now in output:",
        final_company_count,
    )

    print(
        "Total input companies:",
        total_input_companies,
    )

    remaining_after_run = (
        total_input_companies
        - final_company_count
    )

    if remaining_after_run < 0:
        remaining_after_run = 0

    print(
        "Companies still remaining:",
        remaining_after_run,
    )

    print()

    print(
        "Output file:"
    )

    print(
        OUTPUT_FILE
    )

    print()

    print(
        "Sheets:"
    )

    print(
        "  1. Technology Summary"
    )

    print(
        "  2. Technology Detail"
    )

    print(
        "  3. Original Evidence"
    )

    print()

    if RUN_MODE.upper() == "RESUME":

        print(
            "RESUME INFORMATION:"
        )

        print(
            "You can run this script again."
        )

        print(
            "Previously completed companies "
            "will be skipped automatically."
        )

        print(
            "Only remaining companies will be processed."
        )

    print()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()