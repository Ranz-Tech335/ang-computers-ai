from flask import Flask, render_template, request, jsonify
import json
import re

app = Flask(__name__)

BUSINESS = {
    "name": "AnG Computers",
    "location": "E Tower Building, Level 3, Shop C10",
    "phone": "0702 508 957 / 0771 463 343",
    "services": [
        "Laptop sales",
        "Desktop sales",
        "Laptop repairs",
        "Windows installation",
        "Software installation",
        "Computer accessories",
        "Laptop swaps and top-up"
    ]
}

with open("products.json", "r", encoding="utf-8") as f:
    PRODUCTS = json.load(f)


# ============================================================
# MEMORY
# ============================================================

CHAT_MEMORY = {}


def get_memory():
    session_id = "website_user"

    if session_id not in CHAT_MEMORY:
        CHAT_MEMORY[session_id] = {
            "min_budget": None,
            "max_budget": None,
            "brand": None,
            "purpose": None,
            "ram": None,
            "storage": None
        }

    return CHAT_MEMORY[session_id]


def reset_memory():
    CHAT_MEMORY["website_user"] = {
        "min_budget": None,
        "max_budget": None,
        "brand": None,
        "purpose": None,
        "ram": None,
        "storage": None
    }


# ============================================================
# MONEY
# ============================================================

def money(amount):
    return f"UGX {amount:,.0f}"


def parse_amount(number, unit):
    value = float(number)

    if unit.lower() in ["m", "million"]:
        return int(value * 1_000_000)

    if unit.lower() == "k":
        return int(value * 1_000)

    return int(value)


def extract_money_values(message):
    """
    Understands:
    1m
    1 million
    1.5m
    500k
    UGX 500000
    1000000
    """

    text = message.lower().replace(",", "")
    values = []

    # 1m / 1.5m / 2 million / 2.5 million
    for match in re.finditer(
        r"(?<![\d.])(\d+(?:\.\d+)?)\s*(m|million|k)\b",
        text
    ):
        values.append(
            parse_amount(match.group(1), match.group(2))
        )

    # UGX 500000 / 500000 UGX
    for match in re.finditer(
        r"ugx\s*(\d{4,})\b",
        text
    ):
        values.append(int(match.group(1)))

    for match in re.finditer(
        r"\b(\d{5,})\s*ugx\b",
        text
    ):
        values.append(int(match.group(1)))

    # Plain large numbers such as 1000000
    if not values:
        for match in re.finditer(r"\b\d{5,}\b", text):
            values.append(int(match.group(0)))

    return values


def extract_budget_range(message):
    text = message.lower()

    values = extract_money_values(text)

    if not values:
        return None, None, None

    # --------------------------------------------------------
    # BETWEEN / RANGE
    # --------------------------------------------------------

    if any(x in text for x in [
        "between",
        "from"
    ]) and len(values) >= 2:
        low = min(values)
        high = max(values)

        return low, high, "range"

    if any(x in text for x in [
        "to"
    ]) and len(values) >= 2:
        low = min(values)
        high = max(values)

        return low, high, "range"

    # --------------------------------------------------------
    # BELOW / UNDER / MAXIMUM
    # --------------------------------------------------------

    if any(x in text for x in [
        "below",
        "under",
        "less than",
        "maximum",
        "max",
        "up to",
        "not more than"
    ]):
        return None, values[0], "maximum"

    # --------------------------------------------------------
    # OVER / ABOVE / MINIMUM
    # --------------------------------------------------------

    if any(x in text for x in [
        "over",
        "above",
        "more than",
        "minimum",
        "starting from"
    ]):
        return values[0], None, "minimum"

    # --------------------------------------------------------
    # AROUND
    # --------------------------------------------------------

    if any(x in text for x in [
        "around",
        "about",
        "roughly",
        "close to"
    ]):
        return values[0], values[0], "around"

    # --------------------------------------------------------
    # NORMAL BUDGET
    # --------------------------------------------------------

    return None, values[0], "maximum"


# ============================================================
# DETECTORS
# ============================================================

def detect_brand(message):
    text = message.lower()

    for brand in [
        "hp",
        "dell",
        "lenovo",
        "acer",
        "asus",
        "apple",
        "macbook"
    ]:
        if re.search(r"\b" + re.escape(brand) + r"\b", text):
            return brand

    return None


def detect_purpose(message):
    text = message.lower()

    if any(x in text for x in [
        "programming",
        "coding",
        "developer",
        "software development",
        "python",
        "web development",
        "programmer"
    ]):
        return "programming"

    if any(x in text for x in [
        "gaming",
        "games",
        "gamer"
    ]):
        return "gaming"

    if any(x in text for x in [
        "design",
        "graphic",
        "graphics",
        "photoshop",
        "video editing",
        "editing"
    ]):
        return "design"

    if any(x in text for x in [
        "business",
        "office",
        "work",
        "accounting",
        "quickbooks"
    ]):
        return "business"

    if any(x in text for x in [
        "student",
        "school",
        "university",
        "campus",
        "studying"
    ]):
        return "student"

    return None


def detect_ram(message):
    match = re.search(
        r"(\d+)\s*gb\s*ram",
        message.lower()
    )

    return int(match.group(1)) if match else None


def detect_storage(message):
    match = re.search(
        r"(\d+)\s*(gb|tb)\s*(?:ssd|storage|hard)",
        message.lower()
    )

    if not match:
        return None

    value = int(match.group(1))

    if match.group(2) == "tb":
        value *= 1000

    return value


def product_ram(product):
    match = re.search(
        r"(\d+)\s*gb",
        product.get("ram", "").lower()
    )

    return int(match.group(1)) if match else 0


def product_storage(product):
    match = re.search(
        r"(\d+)\s*(gb|tb)",
        product.get("storage", "").lower()
    )

    if not match:
        return 0

    value = int(match.group(1))

    if match.group(2) == "tb":
        value *= 1000

    return value


def cpu_score(product):
    """
    Give a technical CPU score.

    Newer CPU generations get a bonus when the generation
    is explicitly present in the catalogue. When generation
    information is missing, fall back to the CPU family.
    """

    cpu = product.get("cpu", "").lower()

    score = 0

    # CPU family
    if "i9" in cpu:
        score = 50
    elif "i7" in cpu:
        score = 40
    elif "i5" in cpu:
        score = 30
    elif "i3" in cpu:
        score = 20
    elif "ryzen 9" in cpu:
        score = 50
    elif "ryzen 7" in cpu:
        score = 40
    elif "ryzen 5" in cpu:
        score = 30
    elif "ryzen 3" in cpu:
        score = 20
    elif "celeron" in cpu:
        score = 5
    elif "pentium" in cpu:
        score = 4
    elif "atom" in cpu:
        score = 2

    # Generation bonus when explicitly written.
    generation_match = re.search(
        r"(?:i[3579][ -]?)(?:-?)(\\d{1,2})(?:th|nd|rd|st)?\\b",
        cpu
    )

    if generation_match:
        generation = int(generation_match.group(1))
        score += generation

    # Explicit Ryzen generation, e.g. 3250U.
    ryzen_match = re.search(
        r"ryzen [3579][ -]?(\\d{4})",
        cpu
    )

    if ryzen_match:
        model = int(ryzen_match.group(1))
        score += model // 1000

    return score


# ============================================================
# INTENT
# ============================================================

def detect_intent(message):
    text = message.lower().strip()

    # Catalogue questions should always be handled before
    # purpose-specific recommendation logic.
    if any(x in text for x in [
        "which one is cheapest",
        "what is the cheapest",
        "cheapest laptop",
        "cheapest one",
        "cheapest"
    ]):
        return "catalogue"

    if any(x in text for x in [
        "what laptops do you have",
        "what laptops are available",
        "what do you have in stock",
        "what do you have",
        "show me your laptops",
        "show me the laptops",
        "list the laptops",
        "which laptops do you have",
        "available laptops"
    ]):
        return "catalogue"


    text = message.lower().strip()

    if text == "programming":
        return "programming"

    if text == "hp":
        return "brand"

    if text == "dell":
        return "brand"

    if text == "budget":
        return "budget_question"

    if text in [
        "hi",
        "hello",
        "hey",
        "good morning",
        "good afternoon",
        "good evening"
    ]:
        return "greeting"

    if any(x in text for x in [
        "are you good",
        "how are you",
        "how are u",
        "what's up",
        "whats up",
        "you good",
        "how is it going",
        "thanks",
        "thank you"
    ]):
        return "casual"

    if any(x in text for x in [
        "where are you",
        "where is your shop",
        "location",
        "address",
        "where can i find you",
        "shop located"
    ]):
        return "location"

    if any(x in text for x in [
        "contact",
        "phone number",
        "call you",
        "whatsapp number"
    ]):
        return "contact"

    if any(x in text for x in [
        "delivery",
        "deliver",
        "shipping",
        "send it",
        "can you bring"
    ]):
        return "delivery"

    if any(x in text for x in [
        "services",
        "what do you offer",
        "repair",
        "repairs",
        "windows installation",
        "software installation",
        "accessories",
        "swap",
        "top up",
        "desktop"
    ]):
        return "services"

    if any(x in text for x in [
        "compare",
        "comparison",
        "which is better",
        "better between",
        "difference between"
    ]):
        return "comparison"

    if any(x in text for x in [
        "laptop",
        "laptops",
        "computer",
        "notebook",
        "machine",
        "device",
        "show me",
        "available"
    ]):
        return "product"

    if extract_money_values(text):
        return "product"

    if detect_purpose(text):
        return "product"

    if detect_brand(text):
        return "product"

    if detect_ram(text):
        return "product"

    if detect_storage(text):
        return "product"

    return "unknown"


# ============================================================
# UPDATE MEMORY
# ============================================================

def update_memory(message):
    memory = get_memory()

    text = message.lower().strip()

    # Detect what this message contains.
    brand = detect_brand(text)
    purpose = detect_purpose(text)
    ram = detect_ram(text)
    storage = detect_storage(text)
    low, high, budget_type = extract_budget_range(text)

    # ---------------------------------------------------------
    # NEW REQUEST DETECTION
    #
    # A new purpose + new budget without a brand usually means
    # the customer has started a fresh buying request.
    # Don't let an old brand preference hijack it.
    # ---------------------------------------------------------

    has_new_budget = low is not None or high is not None
    has_new_purpose = purpose is not None

    if has_new_budget and has_new_purpose and not brand:
        memory["brand"] = None

    # ---------------------------------------------------------
    # BRAND
    # ---------------------------------------------------------

    if brand:
        memory["brand"] = brand

    # ---------------------------------------------------------
    # PURPOSE
    # ---------------------------------------------------------

    if purpose:
        memory["purpose"] = purpose

    # ---------------------------------------------------------
    # RAM
    # ---------------------------------------------------------

    if ram:
        memory["ram"] = ram

    # ---------------------------------------------------------
    # STORAGE
    # ---------------------------------------------------------

    if storage:
        memory["storage"] = storage

    # ---------------------------------------------------------
    # BUDGET
    # ---------------------------------------------------------

    if has_new_budget:
        memory["min_budget"] = low
        memory["max_budget"] = high
        memory["budget_type"] = budget_type

    return memory


# ============================================================
# RECOMMEND PRODUCTS
# ============================================================


def recommendation_level(product, purpose):
    """
    Classify a laptop for the customer's intended use.

    Returns:
        recommended
        acceptable
        not_recommended
    """
    if not purpose:
        return "acceptable"

    cpu = product.get("cpu", "").lower()
    ram = product_ram(product)
    storage_text = product.get("storage", "").lower()
    storage = product_storage(product)

    weak_cpu = any(x in cpu for x in [
        "celeron", "pentium", "atom"
    ])

    strong_cpu = any(x in cpu for x in [
        "i5", "i7", "i9",
        "ryzen 5", "ryzen 7", "ryzen 9"
    ])

    has_ssd = "ssd" in storage_text

    # ---------------------------------------------------------
    # PROGRAMMING
    # ---------------------------------------------------------
    if purpose == "programming":
        if weak_cpu or ram < 8:
            return "not_recommended"

        if strong_cpu and ram >= 8 and has_ssd:
            return "recommended"

        return "acceptable"

    # ---------------------------------------------------------
    # DESIGN / VIDEO / GRAPHICS
    # ---------------------------------------------------------
    if purpose in ["design", "graphics", "video", "editing"]:
        if weak_cpu or ram < 8:
            return "not_recommended"

        if strong_cpu and ram >= 16:
            return "recommended"

        return "acceptable"

    # ---------------------------------------------------------
    # BUSINESS / OFFICE
    # ---------------------------------------------------------
    if purpose == "business":
        if weak_cpu and ram <= 4:
            return "not_recommended"

        if ram >= 8 and has_ssd:
            return "recommended"

        return "acceptable"

    # ---------------------------------------------------------
    # STUDENT / SCHOOL
    # ---------------------------------------------------------
    if purpose == "student":
        if weak_cpu and ram <= 4:
            return "not_recommended"

        if ram >= 8 and has_ssd:
            return "recommended"

        return "acceptable"

    return "acceptable"


def find_upgrade(best, purpose, max_budget, preferred_brand=None):
    """
    Find a stronger laptop above the customer's budget.

    If the customer requested a brand, prefer that brand first.
    Otherwise choose the cheapest suitable upgrade.
    """
    if not max_budget:
        return None

    upgrades = []

    for p in PRODUCTS:
        if p.get("stock", 0) <= 0:
            continue

        if p["price"] <= max_budget:
            continue

        if p["name"] == best["name"]:
            continue

        level = recommendation_level(p, purpose)

        if level == "recommended":
            upgrades.append(p)

    if not upgrades:
        return None

    if preferred_brand:
        same_brand = [
            p for p in upgrades
            if p.get("brand", "").lower() == preferred_brand.lower()
        ]

        if same_brand:
            same_brand.sort(key=lambda p: p["price"])
            return same_brand[0]

    upgrades.sort(key=lambda p: p["price"])
    return upgrades[0]

def handle_catalogue_question(message):
    """
    Handle simple catalogue questions without carrying over
    an old purpose such as programming or graphics.
    """

    text = message.lower().strip()

    catalogue_words = [
        "what laptops do you have",
        "what laptops do you sell",
        "what laptops are available",
        "what do you have in stock",
        "what do you have",
        "show me your laptops",
        "show me the laptops",
        "list the laptops",
        "which laptops do you have",
        "available laptops",
        "laptops do you have"
    ]

    cheapest_words = [
        "which one is cheapest",
        "what is the cheapest",
        "cheapest laptop",
        "cheapest one",
        "cheapest"
    ]

    products = [
        p for p in PRODUCTS
        if p.get("stock", 0) > 0
    ]

    if any(phrase in text for phrase in cheapest_words):
        if not products:
            return "I don't currently have any laptops in stock."

        cheapest = min(products, key=lambda p: p["price"])

        return (
            f"💰 Cheapest available laptop: {cheapest['name']}\n\n"
            f"{product_details(cheapest)}\n\n"
            "If you tell me your purpose or budget, I can also "
            "recommend the best option rather than simply the cheapest."
        )

    if any(phrase in text for phrase in catalogue_words):
        if not products:
            return "I don't currently have any laptops in stock."

        products = sorted(products, key=lambda p: p["price"])

        response = "💻 Laptops currently available at AnG Computers:\n\n"

        for product in products:
            response += (
                f"• {product['name']} — {money(product['price'])}\n"
                f"  {product.get('cpu', 'Unknown CPU')} · "
                f"{product.get('ram', 'Unknown RAM')} · "
                f"{product.get('storage', 'Unknown storage')}\n"
            )

        response += (
            "\nTell me your budget, preferred brand, or what you need "
            "the laptop for and I can recommend the best match."
        )

        return response

    return None


def recommend_products(message):
    catalogue_response = handle_catalogue_question(message)

    if catalogue_response:
        return catalogue_response, get_memory()

    memory = update_memory(message)

    min_budget = memory.get("min_budget")
    max_budget = memory.get("max_budget")
    brand = memory.get("brand")
    purpose = memory.get("purpose")
    ram = memory.get("ram")
    storage = memory.get("storage")

    candidates = [
        p for p in PRODUCTS
        if p.get("stock", 0) > 0
    ]

    # ---------------------------------------------------------
    # HARD FILTERS
    # ---------------------------------------------------------

    if brand:
        candidates = [
            p for p in candidates
            if p.get("brand", "").lower() == brand
        ]

    if max_budget is not None:
        candidates = [
            p for p in candidates
            if p["price"] <= max_budget
        ]

    if min_budget is not None and max_budget is None:
        candidates = [
            p for p in candidates
            if p["price"] >= min_budget
        ]

    if min_budget is not None and max_budget is not None:
        candidates = [
            p for p in candidates
            if min_budget <= p["price"] <= max_budget
        ]

    if not candidates:
        return [], memory

    # ---------------------------------------------------------
    # INTELLIGENT RANKING
    # Purpose and technical suitability dominate the score.
    # ---------------------------------------------------------

    scored = []

    for p in candidates:
        score = 0

        product_purpose = p.get("purpose", "").lower()
        cpu = p.get("cpu", "").lower()
        ram_value = product_ram(p)
        storage_value = product_storage(p)
        storage_text = p.get("storage", "").lower()

        # -----------------------------------------------------
        # PURPOSE MATCH
        # -----------------------------------------------------

        if purpose:
            if purpose in product_purpose:
                score += 50

            # Programming
            if purpose == "programming":
                if any(x in cpu for x in [
                    "i7", "i9", "ryzen 7", "ryzen 9"
                ]):
                    score += 35
                elif "i5" in cpu or "ryzen 5" in cpu:
                    score += 30
                elif "i3" in cpu:
                    score += 10
                elif any(x in cpu for x in [
                    "celeron", "pentium", "atom"
                ]):
                    score -= 40

                if ram_value >= 16:
                    score += 30
                elif ram_value >= 8:
                    score += 20
                elif ram_value >= 4:
                    score -= 25

                if storage_value >= 512:
                    score += 20
                elif storage_value >= 256:
                    score += 12
                elif storage_value >= 128:
                    score -= 5

                if "ssd" in storage_text:
                    score += 15

            # Design / graphics / video / editing
            elif purpose in ["design", "graphics", "video", "editing"]:
                if any(x in cpu for x in [
                    "i7", "i9", "ryzen 7", "ryzen 9"
                ]):
                    score += 35
                elif "i5" in cpu or "ryzen 5" in cpu:
                    score += 20
                elif any(x in cpu for x in [
                    "celeron", "pentium", "atom"
                ]):
                    score -= 45

                if ram_value >= 16:
                    score += 35
                elif ram_value >= 8:
                    score += 15
                else:
                    score -= 30

                if storage_value >= 512:
                    score += 15
                elif storage_value >= 256:
                    score += 8

            # Business / office
            elif purpose == "business":
                if "business" in product_purpose or "office" in product_purpose:
                    score += 25

                if ram_value >= 8:
                    score += 15
                elif ram_value >= 4:
                    score += 5

                if "ssd" in storage_text:
                    score += 15

            # Student / school
            elif purpose == "student":
                if "student" in product_purpose or "school" in product_purpose:
                    score += 25

                if ram_value >= 8:
                    score += 15
                elif ram_value >= 4:
                    score += 5

                if "ssd" in storage_text:
                    score += 12

        # -----------------------------------------------------
        # EXPLICIT RAM REQUIREMENT
        # -----------------------------------------------------

        if ram:
            if ram_value >= ram:
                score += 25
            else:
                score -= 40

        # -----------------------------------------------------
        # EXPLICIT STORAGE REQUIREMENT
        # -----------------------------------------------------

        if storage:
            if storage_value >= storage:
                score += 25
            else:
                score -= 40

        # -----------------------------------------------------
        # GENERAL TECHNICAL QUALITY
        # -----------------------------------------------------

        cpu_value = cpu_score(p)

        score += cpu_value * 5
        score += min(ram_value, 16)

        if "ssd" in storage_text:
            score += 8

        # -----------------------------------------------------
        # VALUE WITHIN THE CUSTOMER'S BUDGET
        # Prefer stronger machines, but don't blindly choose
        # the most expensive laptop.
        # -----------------------------------------------------

        if max_budget:
            price_ratio = p["price"] / max_budget

            if price_ratio >= 0.85:
                score += 10
            elif price_ratio >= 0.70:
                score += 7
            elif price_ratio >= 0.50:
                score += 3

        scored.append((score, p))

    # Highest suitability first.
    # Price is only the secondary tie-breaker.
    scored.sort(
        key=lambda x: (x[0], x[1]["price"]),
        reverse=True
    )

    return scored, memory


def recommendation_reason(product, purpose):
    """
    Explain why a laptop is a good match for the customer's purpose.
    """

    name = product.get("name", "This laptop")
    cpu = product.get("cpu", "unknown processor")
    ram = product.get("ram", "unknown RAM")
    storage = product.get("storage", "unknown storage")

    if purpose == "programming":
        return (
            f"{name} is a strong match for programming because it "
            f"has {cpu}, {ram}, and {storage}. "
            "That gives you a balanced setup for coding, development "
            "tools, multitasking, and everyday use."
        )

    if purpose == "business":
        return (
            f"{name} is a good business choice with {cpu}, {ram}, "
            f"and {storage}. It should handle office applications, "
            "browsing, documents, email, and everyday business work."
        )

    if purpose == "student":
        return (
            f"{name} is a good student option with {cpu}, {ram}, "
            f"and {storage}. It should handle school work, browsing, "
            "documents, online learning, and everyday tasks."
        )

    if purpose in ["design", "graphics", "video", "editing"]:
        return (
            f"{name} has {cpu}, {ram}, and {storage}. "
            "It can handle general creative work, although demanding "
            "professional workloads may require a stronger machine."
        )

    return (
        f"{name} offers {cpu}, {ram}, and {storage}, making it "
        "a practical option for everyday computing."
    )


def product_details(product):
    return (
        f"{product['name']} — {money(product['price'])}\n"
        f"• {product['cpu']}\n"
        f"• {product['ram']}\n"
        f"• {product['storage']}\n"
        f"• Stock: {product['stock']}"
    )


# ============================================================
# CHAT RESPONSE
# ============================================================

def reply(message):
    text = message.lower().strip()
    intent = detect_intent(message)

    # Greeting
    if intent == "greeting":
        return (
            "Hello 👋 Welcome to AnG Computers!\n\n"
            "I'm your laptop assistant. I can help you choose a laptop "
            "based on your budget, brand, RAM, storage or what you need "
            "the laptop for.\n\n"
            "For example:\n"
            "• Show me HP laptops\n"
            "• I have 1 million\n"
            "• I need a laptop for programming\n"
            "• Dell under 1m"
        )

    # Casual
    if intent == "casual":
        if "thank" in text:
            return (
                "You're welcome 😊 I'm here whenever you need help "
                "choosing a laptop from AnG Computers."
            )

        return (
            "😄 I'm good! I'm here and ready to help you find the right "
            "laptop from AnG Computers.\n\n"
            "Tell me your budget, preferred brand, or what you need "
            "the laptop for."
        )

    # Location
    if intent == "location":
        return (
            f"📍 {BUSINESS['name']} is located at:\n"
            f"{BUSINESS['location']}"
        )

    # Contact
    if intent == "contact":
        return (
            f"📞 Contact {BUSINESS['name']} on:\n"
            f"{BUSINESS['phone']}"
        )

    # Delivery
    if intent == "delivery":
        return (
            "Please contact AnG Computers on "
            f"{BUSINESS['phone']} to confirm delivery availability "
            "and the delivery fee for your location."
        )

    # Services
    if intent == "services":
        services = "\n".join(
            f"• {service}"
            for service in BUSINESS["services"]
        )

        return f"🛠️ AnG Computers offers:\n{services}"

    # Budget button
    if intent == "budget_question":
        return (
            "💰 What's your budget?\n\n"
            "You can type:\n"
            "• 500k\n"
            "• 900k\n"
            "• 1 million\n"
            "• 1.5m\n"
            "• Between 500k and 650k\n"
            "• Over 1 million"
        )

    # Programming quick button
    if intent == "programming":
        reset_memory()
        scored, memory = recommend_products("programming")

        if not scored:
            return (
                "I don't currently have a suitable programming laptop "
                "in the available catalogue."
            )

        response = "💻 Good options for programming:\n\n"

        for _, p in scored[:3]:
            response += product_details(p) + "\n\n"

        response += (
            "Tell me your budget and I'll narrow these down "
            "to the best option."
        )

        return response

    # Catalogue questions
    if intent == "catalogue":
        catalogue_response = handle_catalogue_question(message)

        if catalogue_response:
            return catalogue_response

    # Product
    if intent == "product" or intent == "brand":
        scored, memory = recommend_products(message)

        min_budget = memory.get("min_budget")
        max_budget = memory.get("max_budget")
        brand = memory.get("brand")
        purpose = memory.get("purpose")

        products = [p for _, p in scored]

        # Gaming/design honesty
        if purpose in ["gaming", "design"]:
            return (
                f"I don't currently have a dedicated {purpose} laptop "
                "in the available catalogue.\n\n"
                "I don't want to recommend something unsuitable just "
                "to make a sale. I can show you the strongest available "
                "machines instead."
            )

        # No matching brand
        if brand and not products:
            if min_budget is not None and max_budget is not None:
                return (
                    f"I don't currently have a {brand.upper()} laptop "
                    f"between {money(min_budget)} and "
                    f"{money(max_budget)}.\n\n"
                    "I can show you other brands in that range."
                )

            if max_budget is not None:
                return (
                    f"I don't currently have a {brand.upper()} laptop "
                    f"at or below {money(max_budget)}."
                )

            return (
                f"I don't currently have any {brand.upper()} laptops "
                "available in the catalogue."
            )

        # No products
        if not products:
            if min_budget is not None and max_budget is not None:
                return (
                    f"I don't currently have a laptop between "
                    f"{money(min_budget)} and {money(max_budget)}."
                )

            if max_budget is not None:
                return (
                    f"I don't currently have a laptop at or below "
                    f"{money(max_budget)}."
                )

            if min_budget is not None:
                return (
                    f"I don't currently have a laptop over "
                    f"{money(min_budget)}."
                )

            return (
                "I couldn't find a matching laptop in the current "
                "catalogue."
            )

        # --------------------------------------------------------
        # RANGE
        # --------------------------------------------------------

        if min_budget is not None and max_budget is not None:

            # Intelligent purpose-based recommendation
            if purpose:
                best = products[0]
                level = recommendation_level(best, purpose)

                if level == "not_recommended":
                    upgrade = find_upgrade(
                        best,
                        purpose,
                        max_budget,
                        brand
                    )

                    response = (
                        f"💻 I found {best['name']} within your "
                        f"{money(min_budget)}–{money(max_budget)} budget.\n\n"
                        f"{product_details(best)}\n\n"
                        f"🔴 Not recommended for {purpose}.\n"
                        "The specifications are below what I would "
                        "prefer for this type of work."
                    )

                    if upgrade:
                        extra = upgrade["price"] - max_budget

                        response += (
                            f"\n\n"
                            f"💡 Recommended upgrade: "
                            f"{upgrade['name']} — "
                            f"{money(upgrade['price'])}\n"
                            f"That's only {money(extra)} above your "
                            "budget and gives you a much stronger "
                            "machine for the job.\n\n"
                            f"{product_details(upgrade)}"
                        )

                    return response

                if level == "acceptable":
                    response = (
                        f"💻 Acceptable for {purpose}: "
                        f"{best['name']}\n\n"
                        f"{product_details(best)}\n\n"
                        "🟡 This can handle the work, but it isn't "
                        "the strongest choice available."
                    )

                    upgrade = find_upgrade(
                        best,
                        purpose,
                        max_budget,
                        brand
                    )

                    if upgrade:
                        extra = upgrade["price"] - max_budget

                        response += (
                            f"\n\n"
                            f"💡 If you can add {money(extra)}, "
                            f"I'd choose the {upgrade['name']} at "
                            f"{money(upgrade['price'])} instead."
                        )

                    return response

                if level == "recommended":
                    response = (
                        f"🟢 Recommended for {purpose}: "
                        f"{best['name']}\n\n"
                        f"{product_details(best)}\n\n"
                        "This is a good match for what you need."
                    )

                    remaining = max_budget - best["price"]

                    if remaining >= 0:
                        response += (
                            f"\n💰 You would have "
                            f"{money(remaining)} left from your budget."
                        )

                    return response

            if min_budget == max_budget:
                budget_text = money(max_budget)
            else:
                budget_text = (
                    f"{money(min_budget)}–{money(max_budget)}"
                )

            response = (
                f"💻 Here are the best available options in "
                f"{budget_text}:\n\n"
            )

            for p in products[:5]:
                response += product_details(p) + "\n\n"

            return response.rstrip()
            if min_budget == max_budget:
                budget_text = money(max_budget)
            else:
                budget_text = (
                    f"{money(min_budget)}–{money(max_budget)}"
                )

            response = (
                f"💻 Here are the best available options in "
                f"{budget_text}:\n\n"
            )

            for p in products[:5]:
                response += product_details(p) + "\n\n"

            return response.rstrip()

        # --------------------------------------------------------
        # OVER / ABOVE
        # --------------------------------------------------------

        if min_budget is not None and max_budget is None:
            response = (
                f"💻 Here are the available options from "
                f"{money(min_budget)} and above:\n\n"
            )

            for p in products[:5]:
                response += product_details(p) + "\n\n"

            return response.rstrip()

        # --------------------------------------------------------
        # NORMAL MAX BUDGET
        # --------------------------------------------------------

        if max_budget is not None:
            best = products[0]

            # Programming suitability warning
            if purpose == "programming":
                weak_cpu = any(x in best.get("cpu", "").lower()
                                for x in ["celeron", "pentium", "atom"])
                weak_ram = product_ram(best) < 8

                if weak_cpu or weak_ram:
                    stronger = [
                        p for p in PRODUCTS
                        if p.get("stock", 0) > 0
                        and p["price"] > max_budget
                        and product_ram(p) >= 8
                        and not any(
                            x in p.get("cpu", "").lower()
                            for x in ["celeron", "pentium", "atom"]
                        )
                    ]

                    response = (
                        f"💻 I found {best['name']} within your "
                        f"{money(max_budget)} budget, but I wouldn't "
                        "recommend it for programming.\n\n"
                        f"{product_details(best)}\n\n"
                        "⚠️ Its processor/RAM is limited for programming "
                        "and multitasking.\n"
                    )

                    if stronger:
                        stronger.sort(key=lambda p: p["price"])
                        upgrade = stronger[0]
                        extra = upgrade["price"] - max_budget

                        response += (
                            f"\n💡 A better choice would be "
                            f"{upgrade['name']} at {money(upgrade['price'])}. "
                            f"That is {money(extra)} above your budget, "
                            "but it gives you a much better platform "
                            "for programming.\n\n"
                            f"{product_details(upgrade)}"
                        )
                    else:
                        response += (
                            "\n💡 If you can increase your budget, "
                            "I can show you stronger i5/i7 or Ryzen "
                            "options with at least 8GB RAM and an SSD."
                        )

                    return response

            response = (
                f"🟢 My recommendation: {best['name']}\n\n"
                f"{product_details(best)}\n\n"
            )

            if purpose:
                response += (
                    f"💡 Why it fits {purpose}:\n"
                    f"{recommendation_reason(best, purpose)}\n"
                )

            remaining = max_budget - best["price"]

            if remaining >= 0:
                response += (
                    f"\n💰 You would have {money(remaining)} "
                    "left from your budget."
                )

            # Purpose-aware alternatives.
            # Don't show weak laptops as alternatives when the
            # customer has a specific technical purpose.
            if purpose:
                alternatives = [
                    p for p in products[1:6]
                    if p["name"] != best["name"]
                    and recommendation_level(p, purpose) == "recommended"
                ]
            else:
                alternatives = [
                    p for p in products[1:4]
                    if p["name"] != best["name"]
                ]

            if alternatives:
                if purpose:
                    response += "\n\n💰 Lower-cost alternatives:\n"
                else:
                    response += "\n\nOther suitable options:\n"

                for p in alternatives[:2]:
                    response += (
                        f"• {p['name']} — {money(p['price'])}\n"
                    )

            return response

        # --------------------------------------------------------
        # BRAND ONLY
        # --------------------------------------------------------

        if brand:
            response = (
                f"Here are the available {brand.upper()} laptops:\n\n"
            )

            for p in products[:5]:
                response += product_details(p) + "\n\n"

            return response.rstrip()

        # --------------------------------------------------------
        # PURPOSE ONLY
        # --------------------------------------------------------

        if purpose:
            response = (
                f"💻 Based on your need for {purpose}, "
                "these are the strongest matches:\n\n"
            )

            for p in products[:3]:
                response += product_details(p) + "\n\n"

            response += (
                "Tell me your budget and I can recommend the "
                "best one within your price range."
            )

            return response

        # Generic product request
        response = "💻 Here are some available laptops:\n\n"

        for p in products[:5]:
            response += product_details(p) + "\n\n"

        return response.rstrip()

    # Comparison
    if intent == "comparison":
        scored = []

        for p in PRODUCTS:
            if p.get("stock", 0) > 0:
                score = (
                    cpu_score(p) * 20
                    + product_ram(p)
                    + product_storage(p) // 100
                )

                scored.append((score, p))

        scored.sort(reverse=True, key=lambda x: x[0])

        response = "⚖️ Some strong available options:\n\n"

        for _, p in scored[:3]:
            response += product_details(p) + "\n\n"

        response += (
            "Tell me your budget or what you'll use the laptop for, "
            "and I'll help you choose."
        )

        return response

    return (
        "I can help you choose a laptop 😊\n\n"
        "Try telling me:\n"
        "• Your budget — e.g. 900k or 1.5m\n"
        "• Brand — e.g. HP or Dell\n"
        "• Purpose — e.g. programming or school\n"
        "• Specifications — e.g. 8GB RAM and 256GB SSD"
    )


# ============================================================
# ROUTES
# ============================================================

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()

    if not message:
        return jsonify({
            "reply": "Please type a message so I can help you."
        })

    return jsonify({
        "reply": reply(message)
    })


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
