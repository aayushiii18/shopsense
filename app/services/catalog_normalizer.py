"""
services/catalog_normalizer.py — Dedicated Product Catalog Aggregator & Normalizer.
Stage 5 Module 5.

Responsibilities:
  1. Standardizes product categories into a clean, canonical 2-tier taxonomy (Parent Category -> Subcategory).
  2. Extracts and normalizes physical units and measurements (weight in kg, display size in inches, pack counts).
  3. Infers or cleans brand/vendor identifiers.
  4. Validates price and cost boundaries (price > 0, cost_price <= price if present).
  5. Identifies potential duplicate or near-duplicate catalog listings using token similarity.
  6. Non-destructive: preserves original source database fields while generating clean normalized projections.
"""

from typing import List, Dict, Any, Optional, Tuple
import re
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.vendor import Vendor


# Canonical Category Taxonomy Mapping: Raw -> (Normalized Subcategory, Canonical Parent)
CANONICAL_TAXONOMY_MAP = {
    "headphones": ("Audio & Headphones", "Electronics"),
    "audio": ("Audio & Headphones", "Electronics"),
    "monitors": ("Computer Displays & Monitors", "Electronics"),
    "electronics": ("Consumer Electronics", "Electronics"),
    "kitchenware": ("Cookware & Dining", "Home & Kitchen"),
    "furniture": ("Ergonomic Furniture & Cushions", "Home & Kitchen"),
    "home & kitchen": ("Home Essentials", "Home & Kitchen"),
    "coffee & tea": ("Coffee Makers & Espresso", "Home & Kitchen"),
    "apparel": ("Casual Apparel & Tees", "Fashion & Apparel"),
    "clothing": ("Casual Apparel & Tees", "Fashion & Apparel"),
    "outerwear": ("Weatherproof Outerwear & Jackets", "Fashion & Apparel"),
    "fashion": ("Fashion & Apparel", "Fashion & Apparel"),
    "fitness": ("Fitness & Resistance Gear", "Sports & Fitness"),
    "strength training": ("Weightlifting & Strength Training", "Sports & Fitness"),
    "sports & fitness": ("Sports & Fitness Equipment", "Sports & Fitness"),
    "groceries": ("Artisan Coffee & Pantry", "Food & Beverage"),
    "food & beverage": ("Artisan Coffee & Pantry", "Food & Beverage"),
}


def normalize_category(raw_cat: Optional[str], raw_parent: Optional[str] = None) -> Tuple[str, str]:
    """
    Maps arbitrary or noisy category strings to canonical (Subcategory, Parent Category).
    """
    if not raw_cat:
        if raw_parent:
            return (f"General {raw_parent.strip().title()}", raw_parent.strip().title())
        return ("General Merchandise", "Uncategorized")

    clean_key = raw_cat.strip().lower()
    if clean_key in CANONICAL_TAXONOMY_MAP:
        return CANONICAL_TAXONOMY_MAP[clean_key]

    # Partial / substring matching
    for key, (subcat, parent) in CANONICAL_TAXONOMY_MAP.items():
        if key in clean_key or clean_key in key:
            return (subcat, parent)

    # Fallback to Title Cased raw string
    clean_title = raw_cat.strip().title()
    parent_title = raw_parent.strip().title() if raw_parent else "Specialty Goods"
    return (clean_title, parent_title)


def extract_unit_and_measurement(name: str, desc: Optional[str] = None) -> Dict[str, Any]:
    """
    Extracts structured physical measurements (weight, dimension, pack count) from text.
    Normalizes:
      - Weight: grams -> kg, kg -> kg
      - Dimension: inches / " -> inches
      - Pack counts: 5-Pack, Set of 3 -> pack count integer
    """
    combined = f"{name} {desc or ''}".lower()

    # 1. Weight: e.g. 1kg, 500g, 20kg
    m_weight = re.search(r"(\d+(?:\.\d+)?)\s*(kg|kilograms?|g|grams?)\b", combined)
    if m_weight:
        val = float(m_weight.group(1))
        unit = m_weight.group(2)
        if unit.startswith("g"):
            norm_val = round(val / 1000.0, 3)
            norm_unit = "kg"
        else:
            norm_val = val
            norm_unit = "kg"
        return {
            "has_measurement": True,
            "raw_text": m_weight.group(0),
            "normalized_value": norm_val,
            "normalized_unit": norm_unit,
            "unit_type": "weight",
        }

    # 2. Dimensions / Screen size: e.g. 27-inch, 27", 15.6 inch
    m_dim = re.search(r"(\d+(?:\.\d+)?)\s*(?:-| )(?:inch|inches|\")\b|(\d+(?:\.\d+)?)\"", combined)
    if m_dim:
        val_str = m_dim.group(1) or m_dim.group(2)
        val = float(val_str)
        return {
            "has_measurement": True,
            "raw_text": m_dim.group(0),
            "normalized_value": val,
            "normalized_unit": "inches",
            "unit_type": "dimension",
        }

    # 3. Pack count / Sets: e.g. 5-pack, pack of 3, set of 4
    m_pack = re.search(r"(\d+)\s*(?:-| )(?:pack|pcs|pieces)\b|pack of (\d+)\b|set of (\d+)\b", combined)
    if m_pack:
        val_str = m_pack.group(1) or m_pack.group(2) or m_pack.group(3)
        val = int(val_str)
        return {
            "has_measurement": True,
            "raw_text": m_pack.group(0),
            "normalized_value": float(val),
            "normalized_unit": "pack",
            "unit_type": "pack_count",
        }

    return {
        "has_measurement": False,
        "raw_text": None,
        "normalized_value": None,
        "normalized_unit": None,
        "unit_type": None,
    }


def infer_brand(name: str, vendor_name: Optional[str] = None) -> str:
    """
    Standardizes brand name from product title or vendor entity.
    """
    # Well-known retail prefixes
    first_token = name.strip().split()[0] if name.strip() else "Generic"
    if first_token in {"Wireless", "Ultra", "Ceramic", "Ergonomic", "Organic", "Waterproof", "Resistance", "Adjustable", "Artisan", "Single-Origin"}:
        # Inferred signature line or vendor brand
        if vendor_name:
            # Strip legal suffixes like LLC, Inc
            clean_v = re.sub(r"\b(Inc|LLC|Corp|Co|Furnishings|Electronics|Athletics|Apparel|Haven)\b", "", vendor_name).strip()
            return clean_v or vendor_name.split()[0]
        return first_token

    return first_token


def detect_duplicates(products: List[Dict[str, Any]]) -> List[Tuple[int, int, float]]:
    """
    Identifies near-duplicate products using Jaccard token similarity over normalized names.
    Returns list of (product_id_1, product_id_2, similarity_score).
    """
    duplicates = []
    n = len(products)
    for i in range(n):
        tokens_i = set(re.findall(r"\w+", products[i]["normalized_name"].lower()))
        for j in range(i + 1, n):
            tokens_j = set(re.findall(r"\w+", products[j]["normalized_name"].lower()))
            if not tokens_i or not tokens_j:
                continue
            intersection = len(tokens_i & tokens_j)
            union = len(tokens_i | tokens_j)
            jaccard = intersection / union if union > 0 else 0.0
            if jaccard >= 0.70:
                duplicates.append((products[i]["product_id"], products[j]["product_id"], round(jaccard, 2)))
    return duplicates


def normalize_product_catalog(db: Session) -> Dict[str, Any]:
    """
    Executes non-destructive catalog normalization across all catalog products.
    """
    products = db.query(Product).all()
    if not products:
        return {
            "total_products_inspected": 0,
            "categories_normalized_count": 0,
            "units_extracted_count": 0,
            "brands_standardized_count": 0,
            "duplicate_candidates_found": 0,
            "average_attribute_quality_score": 0.0,
            "taxonomy_mapping": {},
            "products": [],
            "normalization_policy_note": "No products in database.",
        }

    vendors = {v.id: v.name for v in db.query(Vendor).all()}

    normalized_items = []
    units_extracted = 0
    categories_normalized = 0

    for p in products:
        v_name = vendors.get(p.vendor_id, f"Vendor {p.vendor_id}")
        norm_subcat, norm_parent = normalize_category(p.category, p.parent_category)
        if norm_subcat != (p.category or ""):
            categories_normalized += 1

        measurement = extract_unit_and_measurement(p.name, p.description)
        if measurement["has_measurement"]:
            units_extracted += 1

        brand = infer_brand(p.name, v_name)

        # Quality scoring (0-100)
        quality_score = 100.0
        flags = []

        # Title formatting: strip excessive spaces
        norm_name = " ".join(p.name.strip().split())

        # Price sanity check
        if p.price <= 0:
            quality_score -= 40.0
            flags.append("Invalid Non-Positive Price")

        # Cost check
        markup = None
        if p.cost_price is not None:
            if p.cost_price <= 0:
                quality_score -= 20.0
                flags.append("Invalid Cost Price <= 0")
            elif p.cost_price > p.price:
                quality_score -= 30.0
                flags.append("Cost Price Exceeds Retail Price")
            else:
                markup = round(((p.price - p.cost_price) / p.cost_price * 100.0), 2)
        else:
            flags.append("Verified Cost Data Pending (Legacy NULL)")

        if not p.description or len(p.description.strip()) < 15:
            quality_score -= 15.0
            flags.append("Brief / Missing Description")

        normalized_items.append({
            "product_id": p.id,
            "original_name": p.name,
            "normalized_name": norm_name,
            "original_category": p.category,
            "normalized_category": norm_subcat,
            "parent_category": norm_parent,
            "vendor_id": p.vendor_id,
            "inferred_brand": brand,
            "price": round(float(p.price), 2),
            "cost_price": round(float(p.cost_price), 2) if p.cost_price is not None else None,
            "markup_pct": markup,
            "measurement": measurement,
            "quality_score": max(0.0, round(quality_score, 1)),
            "flags": flags,
            "is_duplicate": False,
            "duplicate_of_id": None,
        })

    # Duplicate detection pass
    dups = detect_duplicates(normalized_items)
    for id1, id2, _ in dups:
        for item in normalized_items:
            if item["product_id"] == id2:
                item["is_duplicate"] = True
                item["duplicate_of_id"] = id1
                item["flags"].append(f"Near-Duplicate candidate of Product #{id1}")

    avg_quality = (
        round(sum(p["quality_score"] for p in normalized_items) / len(normalized_items), 1)
        if normalized_items else 0.0
    )

    taxonomy_display = {
        k: f"{v[0]} ({v[1]})" for k, v in list(CANONICAL_TAXONOMY_MAP.items())[:8]
    }

    return {
        "total_products_inspected": len(normalized_items),
        "categories_normalized_count": categories_normalized,
        "units_extracted_count": units_extracted,
        "brands_standardized_count": len(normalized_items),
        "duplicate_candidates_found": len(dups),
        "average_attribute_quality_score": avg_quality,
        "taxonomy_mapping": taxonomy_display,
        "products": normalized_items,
        "normalization_policy_note": (
            "Non-destructive catalog view. Original database records are preserved intact. "
            "Extracted measurements, normalized category hierarchies, and quality scores are generated on-the-fly "
            "for downstream analytics, TF-IDF vectorization, and search."
        ),
    }


def get_single_product_normalized(db: Session, product_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves normalized catalog view for a single product."""
    catalog = normalize_product_catalog(db)
    for p in catalog.get("products", []):
        if p["product_id"] == product_id:
            return p
    return None


# Aliases
normalize_catalog = normalize_product_catalog
normalize_single_product = get_single_product_normalized

