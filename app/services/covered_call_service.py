"""Covered call strategy calculation service."""
from typing import Dict, Any, List, Tuple
import logging

logger = logging.getLogger(__name__)

def calculate_covered_call_returns(options_data: Dict[float, Dict[str, Any]], current_price: float) -> List[Dict[str, Any]]:
    """
    Calculate covered call strategy returns for each strike price.
    
    Args:
        options_data: Dictionary mapping strike prices to put/call data
        current_price: Current stock price (used as purchase price)
        
    Returns:
        List of dictionaries containing covered call return calculations for each strike
    """
    covered_calls = []
    
    # Handle empty or None options_data
    if not options_data or not isinstance(options_data, dict):
        return covered_calls
    
    # Ensure current_price is valid
    if current_price is None or current_price <= 0:
        return covered_calls
    
    try:
        for strike in sorted(options_data.keys()):
            strike_data = options_data.get(strike)
            if not strike_data or not isinstance(strike_data, dict):
                continue
            
            # Only process strikes that have call options
            if strike_data.get('call') is None:
                continue
            
            call_data = strike_data['call']
            if not isinstance(call_data, dict):
                continue
            
            # Calculate call premium: max(Last Price, (Bid + Ask) / 2)
            last_price = call_data.get('lastPrice')
            if last_price is None or pd.isna(last_price):
                last_price = 0
            else:
                last_price = float(last_price)
            
            bid = call_data.get('bid')
            if bid is None or pd.isna(bid):
                bid = 0
            else:
                bid = float(bid)
            
            ask = call_data.get('ask')
            if ask is None or pd.isna(ask):
                ask = 0
            else:
                ask = float(ask)
            
            avg_bid_ask = (bid + ask) / 2 if (bid > 0 and ask > 0) else 0
            
            # Calculate call premium: max(Last Price, (Bid + Ask) / 2)
            if last_price > 0 and avg_bid_ask > 0:
                call_premium = max(last_price, avg_bid_ask)
            elif last_price > 0:
                call_premium = last_price
            elif avg_bid_ask > 0:
                call_premium = avg_bid_ask
            else:
                call_premium = 0
            
            if call_premium == 0:
                continue  # Skip if no valid premium
            
            # Calculate returns for exercised scenario
            # Total Return = Strike Price + Call Premium - Stock Purchase Price
            total_return_exercised = strike + call_premium - current_price
            total_return_pct_exercised = (total_return_exercised / current_price) * 100 if current_price > 0 else 0
            
            # Stock appreciation return % = (Strike Price - Stock Purchase Price) / Stock Purchase Price
            stock_appreciation_pct = ((strike - current_price) / current_price) * 100 if current_price > 0 else 0
            
            # Call premium return % = Call Premium / Stock Purchase Price
            call_premium_pct = (call_premium / current_price) * 100 if current_price > 0 else 0
            
            # Calculate returns for not exercised scenario
            # Total Return = Call Premium
            total_return_not_exercised = call_premium
            total_return_pct_not_exercised = (total_return_not_exercised / current_price) * 100 if current_price > 0 else 0
            
            covered_calls.append({
                'strike': strike,
                'callPremium': round(call_premium, 2),
                'totalReturnExercised': round(total_return_exercised, 2),
                'totalReturnPctExercised': round(total_return_pct_exercised, 2),
                'totalReturnNotExercised': round(total_return_not_exercised, 2),
                'totalReturnPctNotExercised': round(total_return_pct_not_exercised, 2),
                'stockAppreciationPct': round(stock_appreciation_pct, 2),
                'callPremiumPct': round(call_premium_pct, 2),
            })
    except Exception as e:
        # If there's an error processing options, log it and return what we have
        logger.error(f"Error processing covered call returns: {str(e)}")
        import traceback
        traceback.print_exc()
    
    return covered_calls



def calculate_covered_call_returns_v2(
    options_data_by_expiration: List[Tuple[str, Dict[float, Dict[str, Any]]]],
    current_price: float
) -> List[Dict[str, Any]]:
    """
    Enhanced covered call strategy calculator with annualized returns and improved ranking.

    This version:
    - Processes options for the next 3 months
    - Filters for premiums > 1% of stock price
    - Calculates annualized returns for both scenarios
    - Ranks by similarity of exercised vs not-exercised returns (within 2%), then by annualized return

    Args:
        options_data_by_expiration: List of tuples (expiration_date_str, options_data_dict)
        current_price: Current stock price (used as purchase price)

    Returns:
        List of dictionaries containing enhanced covered call calculations, sorted by ranking
    """
    from datetime import datetime, timedelta

    covered_calls = []
    today = datetime.now().date()
    three_months_out = today + timedelta(days=90)

    # Handle empty or None options_data
    if not options_data_by_expiration or not isinstance(options_data_by_expiration, list):
        return covered_calls

    # Ensure current_price is valid
    if current_price is None or current_price <= 0:
        return covered_calls

    # Minimum premium threshold: 1% of stock price
    min_premium_threshold = current_price * 0.01

    try:
        for expiration_str, options_data in options_data_by_expiration:
            if not expiration_str or not options_data:
                continue

            # Parse expiration date
            try:
                expiration_date = datetime.strptime(expiration_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                continue

            # Filter: only process expirations within 3 months
            if expiration_date > three_months_out:
                continue

            # Calculate days to expiration (calendar days)
            days_to_expiration = (expiration_date - today).days
            if days_to_expiration <= 0:
                continue

            # Process each strike
            for strike in sorted(options_data.keys()):
                strike_data = options_data.get(strike)
                if not strike_data or not isinstance(strike_data, dict):
                    continue

                # Only process strikes that have call options
                if strike_data.get('call') is None:
                    continue

                call_data = strike_data['call']
                if not isinstance(call_data, dict):
                    continue

                # Calculate call premium: average of bid and ask
                bid = call_data.get('bid')
                if bid is None or pd.isna(bid):
                    bid = 0
                else:
                    bid = float(bid)

                ask = call_data.get('ask')
                if ask is None or pd.isna(ask):
                    ask = 0
                else:
                    ask = float(ask)

                # Use average of bid and ask as call premium
                if bid > 0 and ask > 0:
                    call_premium = (bid + ask) / 2
                else:
                    # Fallback to last price if bid/ask not available
                    last_price = call_data.get('lastPrice')
                    if last_price is None or pd.isna(last_price) or last_price <= 0:
                        continue
                    call_premium = float(last_price)

                # Filter: Only include if premium > 1% of current stock price (strictly greater than)
                if call_premium <= min_premium_threshold:
                    continue

                # Filter: Only include if strike price >= current stock price (ATM and OTM calls only, no ITM)
                if strike < current_price:
                    continue

                # Scenario 1: Call Exercised
                # Return = (strike price + call premium - current stock price)
                return_exercised = strike + call_premium - current_price
                return_pct_exercised = (return_exercised / current_price) * 100 if current_price > 0 else 0

                # Annualized return if exercised = (return % * 365) / days to expiration
                annualized_return_exercised = (return_pct_exercised * 365) / days_to_expiration if days_to_expiration > 0 else 0

                # Scenario 2: Call Not Exercised
                # Return = call premium only
                return_not_exercised = call_premium
                return_pct_not_exercised = (return_not_exercised / current_price) * 100 if current_price > 0 else 0

                # Annualized return if not exercised = (return % * 365) / days to expiration
                annualized_return_not_exercised = (return_pct_not_exercised * 365) / days_to_expiration if days_to_expiration > 0 else 0

                # Calculate return difference for ranking (used to find scenarios where both returns are similar)
                return_difference = abs(return_pct_exercised - return_pct_not_exercised)

                # Calculate stock appreciation percentage (for visualization)
                stock_appreciation_pct = ((strike - current_price) / current_price) * 100 if current_price > 0 else 0

                # Call premium percentage (for visualization)
                call_premium_pct = (call_premium / current_price) * 100 if current_price > 0 else 0

                covered_calls.append({
                    'expirationDate': expiration_str,
                    'strike': strike,
                    'callPremium': round(call_premium, 2),
                    'returnExercised': round(return_exercised, 2),
                    'returnPctExercised': round(return_pct_exercised, 2),
                    'annualizedReturnExercised': round(annualized_return_exercised, 2),
                    'returnNotExercised': round(return_not_exercised, 2),
                    'returnPctNotExercised': round(return_pct_not_exercised, 2),
                    'annualizedReturnNotExercised': round(annualized_return_not_exercised, 2),
                    'returnDifference': round(return_difference, 2),
                    'stockAppreciationPct': round(stock_appreciation_pct, 2),
                    'callPremiumPct': round(call_premium_pct, 2),
                    'daysToExpiration': days_to_expiration,
                })

        # Ranking logic:
        # 1. Prioritize where returns are within 2% of each other (lower return_difference is better)
        # 2. Then sort by average annualized return (descending)
        covered_calls.sort(
            key=lambda x: (
                x['returnDifference'],  # First: minimize difference between exercised and not-exercised
                -(x['annualizedReturnExercised'] + x['annualizedReturnNotExercised']) / 2  # Second: maximize avg annualized return
            )
        )

    except Exception as e:
        # If there's an error processing options, log it and return what we have
        logger.error(f"Error processing enhanced covered call returns: {str(e)}")
        import traceback
        traceback.print_exc()

    return covered_calls
