"""
Add hard matching cases to synthetic data
These represent real-world scenarios that challenge the matching algorithm
"""

import logging
import random

import pandas as pd

from config import (
    DEFAULT_N_HARD_CASES,
    HARD_CASE_SCENARIO_A_THRESHOLD,
    HARD_CASE_SCENARIO_B_THRESHOLD,
    SHOPIFY_CSV,
    SHOPIFY_HARD_CSV,
    STRIPE_CSV,
    STRIPE_HARD_CSV,
    GROUND_TRUTH_CSV,
    GROUND_TRUTH_HARD_CSV,
)

logger = logging.getLogger(__name__)

def add_hard_cases(
    shopify_df: pd.DataFrame,
    stripe_df: pd.DataFrame,
    ground_truth_df: pd.DataFrame,
    n_hard_cases: int = DEFAULT_N_HARD_CASES,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Add intentionally difficult matching cases to test algorithm limits

    Hard Case Types:
    1. Email domain changed + moved cities + new phone (Scenario A)
    2. Name changed (marriage) + email changed
    3. Only name matches, everything else different
    """
    hard_cases_shopify = []
    hard_cases_stripe = []
    hard_cases_ground_truth = []

    for i in range(n_hard_cases):
        true_id = f"CUST_HARD_{i:04d}"

        first_name = random.choice([
            'John', 'Sarah', 'Michael', 'Emma', 'David', 'Lisa',
            'James', 'Jennifer', 'Robert', 'Patricia', 'William', 'Linda',
            'Charles', 'Barbara', 'Daniel', 'Susan', 'Matthew', 'Jessica',
        ])
        last_name = random.choice([
            'Smith', 'Johnson', 'Williams', 'Brown', 'Jones',
            'Garcia', 'Miller', 'Davis', 'Wilson', 'Moore',
            'Taylor', 'Anderson', 'Thomas', 'Jackson', 'White',
        ])

        # SCENARIO A: Everything changed except name (Digital Nomad)
        if i < n_hard_cases * HARD_CASE_SCENARIO_A_THRESHOLD:
            shopify_record = {
                'source_platform': 'shopify',
                'source_customer_id': f'SHOPIFY_HARD_{random.randint(1000, 9999)}',
                'true_customer_id': true_id,
                'name': f'{first_name} {last_name}',
                'email': f'{first_name.lower()}.{last_name.lower()}@gmail.com',
                'phone': f'+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}',
                'address': f'{random.randint(100, 999)} Oak Street, Boston, MA',
                'zipcode': '02101',
                'order_count': random.randint(1, 10),
                'total_spent': round(random.uniform(100, 1000), 2)
            }
            
            stripe_record = {
                'source_platform': 'stripe',
                'source_customer_id': f'STRIPE_HARD_{random.randint(1000, 9999)}',
                'true_customer_id': true_id,
                'name': f'{first_name} {last_name}',  # Same name
                'email': f'{first_name.lower()}.{last_name.lower()}@yahoo.com',  # Different domain
                'phone': f'+1-415-{random.randint(100, 999)}-{random.randint(1000, 9999)}',  # Different phone
                'address': f'{random.randint(100, 999)} Market Street, San Francisco, CA',  # Moved
                'zipcode': '94102',  # Different zipcode
                'subscription_active': random.choice([True, False]),
                'lifetime_value': round(random.uniform(200, 2000), 2)
            }
        
        # SCENARIO B: Name changed (marriage) + email changed
        elif i < n_hard_cases * HARD_CASE_SCENARIO_B_THRESHOLD:
            old_last_name = last_name
            new_last_name = random.choice(['Martinez', 'Garcia', 'Rodriguez', 'Lee', 'Chen'])
            
            shopify_record = {
                'source_platform': 'shopify',
                'source_customer_id': f'SHOPIFY_HARD_{random.randint(1000, 9999)}',
                'true_customer_id': true_id,
                'name': f'{first_name} {old_last_name}',
                'email': f'{first_name.lower()}.{old_last_name.lower()}@gmail.com',
                'phone': f'+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}',
                'address': f'{random.randint(100, 999)} Pine Avenue, Seattle, WA',
                'zipcode': '98101',
                'order_count': random.randint(1, 10),
                'total_spent': round(random.uniform(100, 1000), 2)
            }
            
            stripe_record = {
                'source_platform': 'stripe',
                'source_customer_id': f'STRIPE_HARD_{random.randint(1000, 9999)}',
                'true_customer_id': true_id,
                'name': f'{first_name} {new_last_name}',  # Changed last name
                'email': f'{first_name.lower()}.{new_last_name.lower()}@gmail.com',  # New email
                'phone': shopify_record['phone'],  # Same phone
                'address': shopify_record['address'],  # Same address
                'zipcode': shopify_record['zipcode'],  # Same zipcode
                'subscription_active': random.choice([True, False]),
                'lifetime_value': round(random.uniform(200, 2000), 2)
            }
        
        # SCENARIO C: Only name matches (hardest case)
        else:  # 15% are Scenario C
            shopify_record = {
                'source_platform': 'shopify',
                'source_customer_id': f'SHOPIFY_HARD_{random.randint(1000, 9999)}',
                'true_customer_id': true_id,
                'name': f'{first_name} {last_name}',
                'email': f'{first_name.lower()}{random.randint(1, 99)}@gmail.com',
                'phone': f'+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}',
                'address': f'{random.randint(100, 999)} Elm Street, Portland, OR',
                'zipcode': '97201',
                'order_count': random.randint(1, 10),
                'total_spent': round(random.uniform(100, 1000), 2)
            }
            
            stripe_record = {
                'source_platform': 'stripe',
                'source_customer_id': f'STRIPE_HARD_{random.randint(1000, 9999)}',
                'true_customer_id': true_id,
                'name': f'{first_name} {last_name}',  # Only this matches
                'email': f'{first_name.lower()}{random.randint(1, 99)}@outlook.com',
                'phone': f'+1-206-{random.randint(100, 999)}-{random.randint(1000, 9999)}',
                'address': f'{random.randint(100, 999)} Broadway, New York, NY',
                'zipcode': '10001',
                'subscription_active': random.choice([True, False]),
                'lifetime_value': round(random.uniform(200, 2000), 2)
            }
        
        # Add to lists
        hard_cases_shopify.append(shopify_record)
        hard_cases_stripe.append(stripe_record)
        
        # Ground truth
        hard_cases_ground_truth.append({
            'true_customer_id': true_id,
            'canonical_name': shopify_record['name'],
            'canonical_email': shopify_record['email'],
            'canonical_phone': shopify_record['phone'],
            'canonical_address': shopify_record['address'],
            'canonical_zipcode': shopify_record['zipcode']
        })
    
    # Append to existing dataframes
    shopify_hard_df = pd.DataFrame(hard_cases_shopify)
    stripe_hard_df = pd.DataFrame(hard_cases_stripe)
    ground_truth_hard_df = pd.DataFrame(hard_cases_ground_truth)
    
    # Combine with existing data
    new_shopify = pd.concat([shopify_df, shopify_hard_df], ignore_index=True)
    new_stripe = pd.concat([stripe_df, stripe_hard_df], ignore_index=True)
    new_ground_truth = pd.concat([ground_truth_df, ground_truth_hard_df], ignore_index=True)
    
    new_shopify.to_csv(SHOPIFY_HARD_CSV, index=False)
    new_stripe.to_csv(STRIPE_HARD_CSV, index=False)
    new_ground_truth.to_csv(GROUND_TRUTH_HARD_CSV, index=False)

    n_a = int(n_hard_cases * HARD_CASE_SCENARIO_A_THRESHOLD)
    n_b = int(n_hard_cases * (HARD_CASE_SCENARIO_B_THRESHOLD - HARD_CASE_SCENARIO_A_THRESHOLD))
    n_c = n_hard_cases - n_a - n_b
    logger.info("Added %d hard cases:", n_hard_cases)
    logger.info("  Scenario A (everything changed except name):    %d", n_a)
    logger.info("  Scenario B (name + email changed, same phone):  %d", n_b)
    logger.info("  Scenario C (only name matches):                 %d", n_c)
    logger.info("New totals -> Shopify: %d  Stripe: %d  Ground truth: %d",
                len(new_shopify), len(new_stripe), len(new_ground_truth))

    return new_shopify, new_stripe, new_ground_truth


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    shopify_df = pd.read_csv(SHOPIFY_CSV)
    stripe_df = pd.read_csv(STRIPE_CSV)
    ground_truth_df = pd.read_csv(GROUND_TRUTH_CSV)

    logger.info("Original data -> Shopify: %d  Stripe: %d  Ground truth: %d",
                len(shopify_df), len(stripe_df), len(ground_truth_df))

    add_hard_cases(shopify_df, stripe_df, ground_truth_df)

    logger.info("Hard cases added. New files: %s, %s, %s",
                SHOPIFY_HARD_CSV, STRIPE_HARD_CSV, GROUND_TRUTH_HARD_CSV)
