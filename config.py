# ============================================================
#  CONFIG — Sourcing Luxe Bot
#  Modifie ce fichier selon tes besoins
# ============================================================

TELEGRAM_TOKEN = "8773112253:AAFuACN55hxcRmsPI3xYXj-6A2aGRh0so8k"   # @BotFather
CHAT_ID        = "1014790204" # /start dans le bot pour l'obtenir

# Intervalle de scan en minutes
SCAN_INTERVAL_MIN = 60

# ── Tailles recherchées ────────────────────────────────────
SIZES_MEN   = ["M", "L", "48", "42", "XL"]
SIZES_WOMEN = ["S", "M", "36", "38", "8", "10"]

# ── Matières autorisées (tout le reste est ignoré) ─────────
NOBLE_MATERIALS = [
    "laine", "wool", "cachemire", "cashmere", "soie", "silk",
    "lin", "linen", "cuir", "leather", "agneau", "lamb",
    "daim", "suède", "suede", "mohair", "alpaga", "alpaca",
    "angora", "tweed", "flanelle", "flannel", "gabardine",
    "velours", "velvet", "coton", "cotton", "100%",
]
FORBIDDEN_MATERIALS = [
    "polyester", "acrylique", "acrylic", "nylon", "viscose",
    "lycra", "elasthanne", "spandex", "polyamide", "modal",
    "synthétique", "synthetic",
]

# ── Marques Tier 1 — Maisons sartoriales (multiplicateur x3.5) ─
BRANDS_T1 = [
    "Brioni", "Kiton", "Cesare Attolini", "Caraceni",
    "Tommy Caraceni", "Domenico Caraceni", "Rubinacci",
    "Liverano Liverano", "Anderson & Sheppard", "Henry Poole",
    "Henry Maxwell", "Charvet", "Cifonelli", "Ambrosi Napoli",
    "Sartoria Renato Ciardi", "Camps de Lucas", "Sulka",
    "Di Nota", "Bouvard Bottier", "Daliet Grand", "Gravati",
    "John Lobb", "George Cleverley",
]

# ── Marques Tier 2 — Grand luxe (multiplicateur x2.8) ──────
BRANDS_T2 = [
    "Hermès", "Hermes", "Ermenegildo Zegna", "Zegna",
    "Brunello Cucinelli", "Loro Piana", "Berluti", "Scabal",
    "Canali", "Caruso", "Corneliani", "Montezemolo",
    "Bespoke", "Brano", "Cifonelli", "Arnys",
    "Francesco Smalto", "Ralph Lauren Purple Label",
    "Loewe", "Eric Bompard",
]

# ── Marques Tier 3 — Luxe accessible (multiplicateur x2.2) ─
BRANDS_T3 = [
    "Giorgio Armani", "Armani", "Yves Saint Laurent", "YSL",
    "Ralph Lauren", "Burberry", "Louis Vuitton", "Prada",
    "Bottega Veneta", "Celine", "Céline", "Dries Van Noten",
    "Marni", "Roberto Cavalli", "Caracollo", "Aspesi",
    "Berluti", "Miu Miu", "Dior", "Christian Dior",
    "Tom Ford", "Charvet", "Kiton",
]

ALL_BRANDS = list(dict.fromkeys(BRANDS_T1 + BRANDS_T2 + BRANDS_T3))

# Multiplicateur estimé de revente par tier
MULTIPLIER = {
    "T1": 3.5,
    "T2": 2.8,
    "T3": 2.2,
}

# ── Règles de marge minimum ────────────────────────────────
# Achat < 400€  → marge x3 minimum
# Achat 400-2000€ → marge x2 minimum
# Achat > 2000€  → marge x1.8 minimum

def get_min_multiplier(buy_price: float) -> float:
    if buy_price < 400:
        return 3.0
    elif buy_price <= 2000:
        return 2.0
    else:
        return 1.8

def get_tier(brand: str) -> str:
    b = brand.lower()
    for br in BRANDS_T1:
        if br.lower() in b or b in br.lower():
            return "T1"
    for br in BRANDS_T2:
        if br.lower() in b or b in br.lower():
            return "T2"
    for br in BRANDS_T3:
        if br.lower() in b or b in br.lower():
            return "T3"
    return "T3"

def estimated_sell_price(buy_price: float, tier: str) -> float:
    return round(buy_price * MULTIPLIER[tier])

def is_pepite(buy_price: float, tier: str) -> bool:
    sell = estimated_sell_price(buy_price, tier)
    ratio = sell / buy_price
    return ratio >= get_min_multiplier(buy_price)

def margin_pct(buy_price: float, tier: str) -> int:
    sell = estimated_sell_price(buy_price, tier)
    return round(((sell - buy_price) / buy_price) * 100)
