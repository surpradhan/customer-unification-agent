import logging
import random
import re

import pandas as pd
from faker import Faker

from config import (
    DEFAULT_CROSS_PLATFORM_RATE,
    DEFAULT_N_CUSTOMERS,
    VARIATION_PROBABILITIES,
)

logger = logging.getLogger(__name__)

random.seed(42)
fake = Faker()
Faker.seed(42)

def generate_base_customers(n: int = 500) -> list[dict]:
    customers = []
    for i in range(n):
        full_name = fake.name()
        email = fake.email()
        customers.append({
            'true_customer_id': f'CUST_{i:04d}',
            'canonical_name': full_name,
            'canonical_email': email,
            'canonical_phone': fake.phone_number(),
            'canonical_address': fake.address().replace('\n', ', '),
            'canonical_zipcode': fake.zipcode()
        })
    return customers

def vary_name(name: str) -> str:
    variations = [
        lambda n: n,  # Keep as is
        lambda n: ' '.join([p[0] + '.' if i == 0 else p for i, p in enumerate(n.split())]),  # J. Smith
        lambda n: ''.join(n.split()),  # JohnSmith (no space)
        lambda n: ' '.join([p[0] for p in n.split()[:-1]] + [n.split()[-1]]),  # J Smith
        lambda n: n.split()[0][0] + ' ' + n.split()[-1] if len(n.split()) > 1 else n,  # J Smith
        lambda n: n.split()[-1] + ' ' + n.split()[0] if len(n.split()) > 1 else n,  # Smith John
        lambda n: ' '.join([p for i, p in enumerate(n.split()) if i < len(n.split())-1 or i == 0] + [n.split()[-1][0]] if len(n.split()) > 1 else n),  # John S
    ]
    return random.choice(variations)(name)

def vary_email(email: str) -> str:
    local, domain = email.split('@')

    variations = [
        lambda e: e,  # Keep as is
        lambda e: local.replace('.', '') + '@' + domain,  # Remove dots from local part only
        lambda e: local.split('.')[0] + '@' + domain if '.' in local else e,  # Just first segment
        lambda e: local + '+shopify@' + domain,  # Gmail alias
        lambda e: local + '@' + random.choice(['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com']),  # Different provider
    ]
    return random.choice(variations)(email)

def vary_phone(phone: str) -> str:
    # Extract just digits
    digits = re.sub(r'\D', '', phone)
    
    if len(digits) < 10:
        digits = '555' + digits[-7:]
    
    variations = [
        lambda p: p,  # Keep as is
        lambda p: digits,  # Just digits
        lambda p: f"{digits[:3]}-{digits[3:6]}-{digits[6:10]}",  # Formatted
        lambda p: f"({digits[:3]}) {digits[3:6]}-{digits[6:10]}",  # Formatted with parens
        lambda p: digits[:-1] + str((int(digits[-1]) + 1) % 10),  # Typo in last digit
        lambda p: f"+1-{digits[:3]}-{digits[3:6]}-{digits[6:10]}",  # With country code
    ]
    return random.choice(variations)(phone)

def vary_address(address: str) -> str:
    variations = [
        lambda a: a,  # Keep as is
        lambda a: a.replace('Street', 'St').replace('Avenue', 'Ave').replace('Road', 'Rd'),  # Abbreviations
        lambda a: a.replace('St', 'Street').replace('Ave', 'Avenue'),  # Expand abbreviations
        lambda a: a.replace('Apartment', 'Apt').replace('Suite', 'Ste'),  # Abbreviate unit
        lambda a: a + ', Apt ' + str(random.randint(1, 20)) if 'Apt' not in a else a,  # Add apartment
        lambda a: a[:-1] + chr(ord(a[-1]) + 1) if a[-1].isalpha() else a,  # Typo in last char
    ]
    return random.choice(variations)(address)

def apply_variations(customer: dict, platform: str, variation_intensity: str = "medium") -> dict:
    """Apply realistic variations based on platform"""
    record = {
        'source_platform': platform,
        'source_customer_id': f"{platform.upper()}_{random.randint(1000, 9999)}",
        'true_customer_id': customer['true_customer_id']  # Keep for validation
    }
    
    prob = VARIATION_PROBABILITIES[variation_intensity]
    
    # Name - almost always varies
    record['name'] = vary_name(customer['canonical_name']) if random.random() < prob else customer['canonical_name']
    
    # Email - sometimes varies
    record['email'] = vary_email(customer['canonical_email']) if random.random() < (prob * 0.5) else customer['canonical_email']
    
    # Phone - often varies in formatting
    record['phone'] = vary_phone(customer['canonical_phone']) if random.random() < prob else customer['canonical_phone']
    
    # Address - sometimes varies
    record['address'] = vary_address(customer['canonical_address']) if random.random() < (prob * 0.6) else customer['canonical_address']
    
    record['zipcode'] = customer['canonical_zipcode']
    
    # Add platform-specific fields
    if platform == 'shopify':
        record['order_count'] = random.randint(1, 15)
        record['total_spent'] = round(random.uniform(50, 2000), 2)
    else:  # stripe
        record['subscription_active'] = random.choice([True, False])
        record['lifetime_value'] = round(random.uniform(100, 5000), 2)
    
    return record

def generate_synthetic_dataset(
    n_customers: int = 500, cross_platform_rate: float = 0.7
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    """
    Generate complete synthetic dataset
    
    Args:
        n_customers: Total number of unique customers
        cross_platform_rate: % of customers appearing on both platforms
    """
    # Generate base customers
    base_customers = generate_base_customers(n_customers)
    
    # Determine which customers appear on which platforms
    n_cross_platform = int(n_customers * cross_platform_rate)
    cross_platform_customers = base_customers[:n_cross_platform]
    shopify_only = base_customers[n_cross_platform:n_cross_platform + (n_customers - n_cross_platform) // 2]
    stripe_only = base_customers[n_cross_platform + (n_customers - n_cross_platform) // 2:]
    
    # Generate Shopify records
    shopify_records = []
    for customer in cross_platform_customers + shopify_only:
        shopify_records.append(apply_variations(customer, 'shopify', 'medium'))
    
    # Generate Stripe records
    stripe_records = []
    for customer in cross_platform_customers + stripe_only:
        stripe_records.append(apply_variations(customer, 'stripe', 'medium'))
    
    # Create DataFrames
    df_shopify = pd.DataFrame(shopify_records)
    df_stripe = pd.DataFrame(stripe_records)
    
    # Shuffle
    df_shopify = df_shopify.sample(frac=1).reset_index(drop=True)
    df_stripe = df_stripe.sample(frac=1).reset_index(drop=True)
    
    return df_shopify, df_stripe, base_customers

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from config import SHOPIFY_CSV, STRIPE_CSV, GROUND_TRUTH_CSV

    df_shopify, df_stripe, ground_truth = generate_synthetic_dataset(
        n_customers=DEFAULT_N_CUSTOMERS,
        cross_platform_rate=DEFAULT_CROSS_PLATFORM_RATE,
    )

    df_shopify.to_csv(SHOPIFY_CSV, index=False)
    df_stripe.to_csv(STRIPE_CSV, index=False)
    pd.DataFrame(ground_truth).to_csv(GROUND_TRUTH_CSV, index=False)

    logger.info("Generated datasets:")
    logger.info("  Shopify:      %d records", len(df_shopify))
    logger.info("  Stripe:       %d records", len(df_stripe))
    logger.info("  Ground truth: %d unique customers", len(ground_truth))
    logger.info(
        "Expected matches: ~%d", len(df_shopify) + len(df_stripe) - len(ground_truth)
    )
