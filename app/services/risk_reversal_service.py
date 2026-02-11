"""Risk reversal strategy calculation service."""
from typing import Dict, Any, List
from datetime import datetime
import logging
from app.services.options_data_service import get_leaps_expirations

logger = logging.getLogger(__name__)

def calculate_risk_reversal_strategies(ticker: str, current_price: float) -> Dict[str, List[Dict[str, Any]]]:
    """
    Calculate Risk Reversal strategies for LEAPS expirations.

    Algorithm based on risk_reversal.md specs:
    - Only LEAPS expiring Jan next year or later
    - Put strike: close to current price (90% to 130% of current price)
    - Call strike: at or above put strike
    - Ratios: 1:1, 1:2, 1:3, Collar (1:1 or 1:2 with sold OTM call at least 30% higher)
    - Always use average of bid/ask prices (filter out missing quotes)

    Cost limits:
    - 1:1: ±3% of current price
    - 1:2: ±3% of current price (pivot-based search)
    - 1:3: ±5% of current price (pivot-based search)

    1:2 and 1:3 Algorithm:
    1. Find pivot strike where put/call at same strike meets cost limit
    2. Expand search ±10% from pivot strike
    """
    strategies_by_expiration = {}
    
    try:
        # Use options provider (MarketData if available, else yfinance)
        if hasattr(ProviderFactory, 'get_options_provider'):
            provider = ProviderFactory.get_options_provider()
        else:
            provider = ProviderFactory.get_default_provider()
        
        # Track if we need to fallback to yfinance due to rate limits
        use_fallback = False
            
        leaps_expirations = get_leaps_expirations(ticker)
        
        logger.info(f"Risk Reversal for {ticker}: Found {len(leaps_expirations)} LEAPS expirations: {leaps_expirations}")
        
        if not leaps_expirations:
            logger.warning(f"Risk Reversal for {ticker}: No LEAPS expirations found")
            return strategies_by_expiration
        
        logger.info(f"Risk Reversal for {ticker}: Current price=${current_price:.2f}")
        
        today = date.today()
        
        for expiration in leaps_expirations:
            try:
                try:
                    opt_chain = provider.fetch_options_chain(ticker, expiration)
                except DataNotAvailableError as e:
                    # Check if this is a rate limit error and we haven't already fallen back
                    if "rate limit" in str(e).lower() and not use_fallback:
                        logger.warning(f"MarketData rate limit hit for {ticker} {expiration}, falling back to yfinance")
                        use_fallback = True
                        # Retry with yfinance
                        from app.providers.yfinance_provider import YFinanceProvider
                        provider = YFinanceProvider()
                        try:
                            opt_chain = provider.fetch_options_chain(ticker, expiration)
                        except DataNotAvailableError:
                            logger.debug(f"Risk Reversal for {ticker} {expiration}: Options chain not available from yfinance")
                            continue
                    else:
                        logger.debug(f"Risk Reversal for {ticker} {expiration}: Options chain not available")
                        continue
                
                strategies = []
                
                if not opt_chain.puts or not opt_chain.calls:
                    logger.debug(f"Risk Reversal for {ticker} {expiration}: Missing puts or calls")
                    continue

                def get_mid_price(bid, ask) -> Optional[float]:
                    """Only use average of bid/ask. Filter out missing quotes."""
                    if bid is not None and ask is not None and bid > 0 and ask > 0:
                        return (float(bid) + float(ask)) / 2.0
                    return None

                # Build put options list (90% to 130% of current price)
                min_put_strike = current_price * 0.90
                max_put_strike = current_price * 1.30
                
                puts = []
                for p in opt_chain.puts:
                    if p.strike < min_put_strike or p.strike > max_put_strike:
                        continue
                    mid = get_mid_price(p.bid, p.ask)
                    if mid is None:
                        continue
                    puts.append({'strike': round(p.strike, 2), 'mid': mid, 'bid': p.bid, 'ask': p.ask})

                # Build call options list (within 30% of current price for now, will filter further)
                min_call_strike = current_price * 0.90
                max_call_strike = current_price * 1.50  # Allow higher for collar sold calls
                
                calls = []
                for c in opt_chain.calls:
                    if c.strike < min_call_strike or c.strike > max_call_strike:
                        continue
                    mid = get_mid_price(c.bid, c.ask)
                    if mid is None:
                        continue
                    calls.append({'strike': round(c.strike, 2), 'mid': mid, 'bid': c.bid, 'ask': c.ask})

                if not puts or not calls:
                    logger.debug(f"Risk Reversal for {ticker} {expiration}: No valid quotes after filtering")
                    continue

                exp_date = datetime.strptime(expiration, '%Y-%m-%d').date()
                days_to_exp = (exp_date - today).days
                cost_limit = current_price * 0.03

                # Sort puts by proximity to current price
                puts_sorted = sorted(puts, key=lambda p: abs(p['strike'] - current_price))

                # --- 1:1 strategies ---
                strategies_1_1 = []
                for put in puts_sorted:
                    # Calls should be at or above put strike
                    eligible_calls = [c for c in calls if c['strike'] >= put['strike']]
                    # Sort calls by proximity to put strike
                    eligible_calls_sorted = sorted(eligible_calls, key=lambda c: abs(c['strike'] - put['strike']))
                    
                    for call in eligible_calls_sorted[:10]:  # Limit combinations
                        net_cost = call['mid'] - put['mid']
                        if abs(net_cost) > cost_limit:
                            continue
                        cost_pct = (net_cost / current_price) * 100 if current_price > 0 else 0
                        put_risk = put['strike'] * 100
                        strategies_1_1.append({
                            'ratio': '1:1',
                            'put_strike': put['strike'],
                            'call_strike': call['strike'],
                            'put_bid': round(put['mid'], 2),
                            'call_ask': round(call['mid'], 2),
                            'put_breakeven': round(put['strike'] - put['mid'], 2),
                            'call_breakeven': round(call['strike'] + call['mid'], 2),
                            'strike_spread': round(abs(call['strike'] - put['strike']), 2),
                            'cost': round(net_cost, 2),
                            'cost_pct': round(cost_pct, 2),
                            'days_to_expiration': days_to_exp,
                            'put_risk': round(put_risk, 2),
                            'put_risk_formatted': f"{put_risk:,.2f}",
                            'expiration': expiration,
                            'put_proximity': abs(put['strike'] - current_price),
                            'call_proximity': abs(call['strike'] - put['strike']),
                        })

                # Sort 1:1 by: put proximity, call proximity to put, then net cost
                strategies_1_1.sort(key=lambda s: (s['put_proximity'], s['call_proximity'], abs(s['cost'])))
                strategies_1_1 = strategies_1_1[:5]

                # --- 1:2 strategies ---
                # Per spec: Find pivot strike where put premium finances 2 calls at same strike (<3% cost)
                # Then expand search ±10% from pivot
                strategies_1_2 = []
                cost_limit_1_2 = current_price * 0.03  # 3% for 1:2

                # Step 1: Find pivot strike (same strike for put and call where net cost < 3%)
                pivot_strike_1_2 = None
                for put in puts:
                    # Find call at same strike
                    matching_calls = [c for c in calls if c['strike'] == put['strike']]
                    if matching_calls:
                        call = matching_calls[0]
                        net_cost = (2 * call['mid']) - put['mid']
                        if abs(net_cost) <= cost_limit_1_2:
                            pivot_strike_1_2 = put['strike']
                            break

                # Step 2: If pivot found, search ±10% of pivot; otherwise search all puts
                if pivot_strike_1_2:
                    min_search_strike = pivot_strike_1_2 * 0.90
                    max_search_strike = pivot_strike_1_2 * 1.10
                    search_puts = [p for p in puts if min_search_strike <= p['strike'] <= max_search_strike]
                else:
                    search_puts = puts

                for put in search_puts:
                    eligible_calls = [c for c in calls if c['strike'] >= put['strike']]
                    eligible_calls_sorted = sorted(eligible_calls, key=lambda c: abs(c['strike'] - put['strike']))

                    for call in eligible_calls_sorted[:10]:
                        net_cost = (2 * call['mid']) - put['mid']
                        if abs(net_cost) > cost_limit_1_2:
                            continue
                        cost_pct = (net_cost / current_price) * 100 if current_price > 0 else 0
                        put_risk = put['strike'] * 100
                        strategies_1_2.append({
                            'ratio': '1:2',
                            'put_strike': put['strike'],
                            'call_strike': call['strike'],
                            'put_bid': round(put['mid'], 2),
                            'call_ask': round(call['mid'], 2),
                            'put_breakeven': round(put['strike'] - put['mid'], 2),
                            'call_breakeven': round(call['strike'] + (net_cost / 2), 2),
                            'strike_spread': round(abs(call['strike'] - put['strike']), 2),
                            'cost': round(net_cost, 2),
                            'cost_pct': round(cost_pct, 2),
                            'days_to_expiration': days_to_exp,
                            'put_risk': round(put_risk, 2),
                            'put_risk_formatted': f"{put_risk:,.2f}",
                            'expiration': expiration,
                            'put_proximity': abs(put['strike'] - current_price),
                            'call_proximity': abs(call['strike'] - put['strike']),
                        })

                # Sort by: same strike first, then put proximity, then cost
                strategies_1_2.sort(key=lambda s: (s['call_proximity'], s['put_proximity'], abs(s['cost'])))
                strategies_1_2 = strategies_1_2[:5]

                # --- 1:3 strategies ---
                # Per spec: Find pivot strike where put premium finances 3 calls at same strike (<5% cost)
                # Then expand search ±10% from pivot
                strategies_1_3 = []
                cost_limit_1_3 = current_price * 0.05  # 5% for 1:3

                # Step 1: Find pivot strike (same strike for put and call where net cost < 5%)
                pivot_strike_1_3 = None
                for put in puts:
                    matching_calls = [c for c in calls if c['strike'] == put['strike']]
                    if matching_calls:
                        call = matching_calls[0]
                        net_cost = (3 * call['mid']) - put['mid']
                        if abs(net_cost) <= cost_limit_1_3:
                            pivot_strike_1_3 = put['strike']
                            break

                # Step 2: If pivot found, search ±10% of pivot; otherwise search all puts
                if pivot_strike_1_3:
                    min_search_strike = pivot_strike_1_3 * 0.90
                    max_search_strike = pivot_strike_1_3 * 1.10
                    search_puts = [p for p in puts if min_search_strike <= p['strike'] <= max_search_strike]
                else:
                    search_puts = puts

                for put in search_puts:
                    eligible_calls = [c for c in calls if c['strike'] >= put['strike']]
                    eligible_calls_sorted = sorted(eligible_calls, key=lambda c: abs(c['strike'] - put['strike']))

                    for call in eligible_calls_sorted[:10]:
                        net_cost = (3 * call['mid']) - put['mid']
                        if abs(net_cost) > cost_limit_1_3:
                            continue
                        cost_pct = (net_cost / current_price) * 100 if current_price > 0 else 0
                        put_risk = put['strike'] * 100
                        strategies_1_3.append({
                            'ratio': '1:3',
                            'put_strike': put['strike'],
                            'call_strike': call['strike'],
                            'put_bid': round(put['mid'], 2),
                            'call_ask': round(call['mid'], 2),
                            'put_breakeven': round(put['strike'] - put['mid'], 2),
                            'call_breakeven': round(call['strike'] + (net_cost / 3), 2),
                            'strike_spread': round(abs(call['strike'] - put['strike']), 2),
                            'cost': round(net_cost, 2),
                            'cost_pct': round(cost_pct, 2),
                            'days_to_expiration': days_to_exp,
                            'put_risk': round(put_risk, 2),
                            'put_risk_formatted': f"{put_risk:,.2f}",
                            'expiration': expiration,
                            'put_proximity': abs(put['strike'] - current_price),
                            'call_proximity': abs(call['strike'] - put['strike']),
                        })

                # Sort by: same strike first, then put proximity, then cost
                strategies_1_3.sort(key=lambda s: (s['call_proximity'], s['put_proximity'], abs(s['cost'])))
                strategies_1_3 = strategies_1_3[:5]

                # --- Collar strategies (sell put, buy call(s), sell OTM call) ---
                # Per spec: sold call must be at least 30% higher than bought call
                strategies_collar = []
                for put in puts_sorted:
                    eligible_calls = [c for c in calls if c['strike'] >= put['strike']]
                    eligible_calls_sorted = sorted(eligible_calls, key=lambda c: abs(c['strike'] - put['strike']))

                    for call in eligible_calls_sorted[:5]:
                        # Find OTM calls to sell (strikes at least 30% higher than the bought call)
                        otm_calls = [c for c in calls if c['strike'] >= call['strike'] * 1.30]
                        otm_calls_sorted = sorted(otm_calls, key=lambda c: c['strike'])

                        for sold_call in otm_calls_sorted[:3]:
                            # 1:1 Collar: sell put, buy 1 call, sell 1 OTM call
                            net_cost_1_1 = call['mid'] - put['mid'] - sold_call['mid']
                            if abs(net_cost_1_1) <= cost_limit:
                                cost_pct = (net_cost_1_1 / current_price) * 100 if current_price > 0 else 0
                                put_risk = put['strike'] * 100
                                strategies_collar.append({
                                    'ratio': 'Collar',
                                    'put_strike': put['strike'],
                                    'call_strike': call['strike'],
                                    'sold_call_strike': sold_call['strike'],
                                    'put_bid': round(put['mid'], 2),
                                    'call_ask': round(call['mid'], 2),
                                    'sold_call_bid': round(sold_call['mid'], 2),
                                    'put_breakeven': round(put['strike'] - put['mid'], 2),
                                    'call_breakeven': round(call['strike'] + net_cost_1_1, 2),
                                    'strike_spread': round(abs(call['strike'] - put['strike']), 2),
                                    'cost': round(net_cost_1_1, 2),
                                    'cost_pct': round(cost_pct, 2),
                                    'days_to_expiration': days_to_exp,
                                    'put_risk': round(put_risk, 2),
                                    'put_risk_formatted': f"{put_risk:,.2f}",
                                    'expiration': expiration,
                                    'put_proximity': abs(put['strike'] - current_price),
                                    'call_proximity': abs(call['strike'] - put['strike']),
                                    'collar_type': '1:1',
                                    'max_profit_strike': sold_call['strike'],
                                })

                            # 1:2 Collar: sell put, buy 2 calls, sell 2 OTM calls
                            net_cost_1_2 = (2 * call['mid']) - put['mid'] - (2 * sold_call['mid'])
                            if abs(net_cost_1_2) <= cost_limit:
                                cost_pct = (net_cost_1_2 / current_price) * 100 if current_price > 0 else 0
                                put_risk = put['strike'] * 100
                                strategies_collar.append({
                                    'ratio': 'Collar',
                                    'put_strike': put['strike'],
                                    'call_strike': call['strike'],
                                    'sold_call_strike': sold_call['strike'],
                                    'put_bid': round(put['mid'], 2),
                                    'call_ask': round(call['mid'], 2),
                                    'sold_call_bid': round(sold_call['mid'], 2),
                                    'put_breakeven': round(put['strike'] - put['mid'], 2),
                                    'call_breakeven': round(call['strike'] + (net_cost_1_2 / 2), 2),
                                    'strike_spread': round(abs(call['strike'] - put['strike']), 2),
                                    'cost': round(net_cost_1_2, 2),
                                    'cost_pct': round(cost_pct, 2),
                                    'days_to_expiration': days_to_exp,
                                    'put_risk': round(put_risk, 2),
                                    'put_risk_formatted': f"{put_risk:,.2f}",
                                    'expiration': expiration,
                                    'put_proximity': abs(put['strike'] - current_price),
                                    'call_proximity': abs(call['strike'] - put['strike']),
                                    'collar_type': '1:2',
                                    'max_profit_strike': sold_call['strike'],
                                })

                strategies_collar.sort(key=lambda s: (s['put_proximity'], s['call_proximity'], abs(s['cost'])))
                strategies_collar = strategies_collar[:5]

                # Combine all strategies
                strategies.extend(strategies_1_1 + strategies_1_2 + strategies_1_3 + strategies_collar)
                
                # Find strategies closest to $0 and mark for highlighting
                if strategies:
                    closest_negative = None
                    closest_positive = None
                    closest_negative_abs = None
                    closest_positive_abs = None
                    
                    for strategy in strategies:
                        cost = strategy['cost']
                        if cost < 0:
                            abs_cost = abs(cost)
                            if closest_negative_abs is None or abs_cost < closest_negative_abs:
                                closest_negative = strategy
                                closest_negative_abs = abs_cost
                        elif cost > 0:
                            if closest_positive_abs is None or cost < closest_positive_abs:
                                closest_positive = strategy
                                closest_positive_abs = cost
                    
                    for strategy in strategies:
                        strategy['highlight'] = (
                            strategy == closest_negative or 
                            strategy == closest_positive or
                            strategy['cost'] == 0
                        )
                    
                    strategies_by_expiration[expiration] = strategies
                    
            except Exception as e:
                logger.error(f"Error processing Risk Reversal expiration {expiration} for {ticker}: {str(e)}")
                import traceback
                traceback.print_exc()
                continue
        
        logger.info(f"Risk Reversal for {ticker}: Total expirations with strategies: {len(strategies_by_expiration)}")
        if not strategies_by_expiration:
            logger.warning(
                f"Risk Reversal for {ticker}: No strategies found. Possible reasons: missing bid/ask quotes or no strikes in range."
            )
        
        return strategies_by_expiration
        
    except Exception as e:
        logger.error(f"Error calculating Risk Reversal strategies for {ticker}: {str(e)}")
        import traceback
        traceback.print_exc()
        return strategies_by_expiration

