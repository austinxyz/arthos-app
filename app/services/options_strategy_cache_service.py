"""Service for caching pre-computed options strategies in the database."""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
from sqlmodel import Session, select, delete
from app.database import engine
from app.models.options_cache import CachedCoveredCall, CachedRiskReversal
import logging

logger = logging.getLogger(__name__)


def prune_expired_options_cache():
    """
    Remove all cached options where expiration_date is in the past.
    Should be called at the start of each scheduler run.
    """
    today = date.today()
    try:
        with Session(engine) as session:
            # Delete expired covered calls
            cc_result = session.exec(
                delete(CachedCoveredCall).where(CachedCoveredCall.expiration_date < today)
            )
            cc_deleted = cc_result.rowcount if hasattr(cc_result, 'rowcount') else 0

            # Delete expired risk reversals
            rr_result = session.exec(
                delete(CachedRiskReversal).where(CachedRiskReversal.expiration_date < today)
            )
            rr_deleted = rr_result.rowcount if hasattr(rr_result, 'rowcount') else 0

            session.commit()

            if cc_deleted > 0 or rr_deleted > 0:
                logger.info(f"Pruned expired options cache: {cc_deleted} covered calls, {rr_deleted} risk reversals")
    except Exception as e:
        logger.error(f"Error pruning expired options cache: {e}")


def compute_and_cache_covered_calls(
    ticker: str,
    current_price: float,
    options_data_by_expiration: Optional[List[Tuple[str, Dict[float, Dict[str, Any]]]]] = None
) -> int:
    """
    Compute covered call strategies and cache them in the database.
    Uses smart upsert: UPDATE existing, INSERT new, DELETE stale entries.

    Args:
        ticker: Stock ticker symbol
        current_price: Current stock price
        options_data_by_expiration: Optional pre-fetched options data to reuse

    Returns:
        Number of strategies cached
    """
    from app.services.stock_service import get_all_options_data, calculate_covered_call_returns_v2
    from app.services.options_cache_service import calculate_atm_iv, update_stock_iv_metrics

    try:
        # Fetch options data once unless it was already supplied by caller.
        all_options_data = options_data_by_expiration
        if all_options_data is None:
            all_options_data = get_all_options_data(
                ticker,
                current_price,
                days_limit=90,
                include_leaps=False,
                force_refresh=False
            )
        if not all_options_data:
            logger.debug(f"No options data available for {ticker}")
            return 0

        # Update ATM IV metrics from the first available expiration in the fetched options set.
        # This avoids extra options API calls solely for IV refresh.
        try:
            for _, options_data in all_options_data:
                if not options_data:
                    continue
                atm_iv = calculate_atm_iv(options_data, current_price)
                if atm_iv is not None:
                    update_stock_iv_metrics(ticker, atm_iv)
                break
        except Exception as e:
            logger.warning(f"Could not update IV metrics during covered call cache refresh for {ticker}: {e}")

        # Compute strategies
        computed_strategies = calculate_covered_call_returns_v2(all_options_data, current_price)
        if not computed_strategies:
            logger.debug(f"No covered call strategies computed for {ticker}")
            return 0

        with Session(engine) as session:
            # Get existing cached entries for this ticker
            existing_rows = session.exec(
                select(CachedCoveredCall).where(CachedCoveredCall.ticker == ticker)
            ).all()
            existing = {
                (row.expiration_date, float(row.strike)): row
                for row in existing_rows
            }

            now = datetime.utcnow()
            cached_count = 0

            # Process each computed strategy
            for strategy in computed_strategies:
                try:
                    exp_date = datetime.strptime(strategy['expirationDate'], '%Y-%m-%d').date()
                    strike = float(strategy['strike'])
                    key = (exp_date, strike)

                    if key in existing:
                        # UPDATE existing row
                        row = existing[key]
                        row.call_premium = Decimal(str(strategy['callPremium']))
                        row.return_exercised = Decimal(str(strategy['returnExercised']))
                        row.return_pct_exercised = Decimal(str(strategy['returnPctExercised']))
                        row.annualized_return_exercised = Decimal(str(strategy['annualizedReturnExercised']))
                        row.return_not_exercised = Decimal(str(strategy['returnNotExercised']))
                        row.return_pct_not_exercised = Decimal(str(strategy['returnPctNotExercised']))
                        row.annualized_return_not_exercised = Decimal(str(strategy['annualizedReturnNotExercised']))
                        row.return_difference = Decimal(str(strategy['returnDifference']))
                        row.days_to_expiration = strategy['daysToExpiration']
                        row.current_price = Decimal(str(current_price))
                        row.computed_at = now
                        session.add(row)
                        existing.pop(key)  # Mark as processed
                    else:
                        # INSERT new row
                        new_row = CachedCoveredCall(
                            ticker=ticker,
                            expiration_date=exp_date,
                            strike=Decimal(str(strike)),
                            call_premium=Decimal(str(strategy['callPremium'])),
                            return_exercised=Decimal(str(strategy['returnExercised'])),
                            return_pct_exercised=Decimal(str(strategy['returnPctExercised'])),
                            annualized_return_exercised=Decimal(str(strategy['annualizedReturnExercised'])),
                            return_not_exercised=Decimal(str(strategy['returnNotExercised'])),
                            return_pct_not_exercised=Decimal(str(strategy['returnPctNotExercised'])),
                            annualized_return_not_exercised=Decimal(str(strategy['annualizedReturnNotExercised'])),
                            return_difference=Decimal(str(strategy['returnDifference'])),
                            days_to_expiration=strategy['daysToExpiration'],
                            current_price=Decimal(str(current_price)),
                            computed_at=now
                        )
                        session.add(new_row)

                    cached_count += 1
                except Exception as e:
                    logger.warning(f"Error caching covered call for {ticker}: {e}")
                    continue

            # DELETE stale entries (expirations/strikes no longer in the options chain)
            for stale_row in existing.values():
                session.delete(stale_row)

            session.commit()

            stale_count = len(existing)
            if stale_count > 0:
                logger.debug(f"Deleted {stale_count} stale covered call entries for {ticker}")

            return cached_count

    except Exception as e:
        logger.error(f"Error computing/caching covered calls for {ticker}: {e}")
        return 0


def compute_and_cache_risk_reversals(
    ticker: str,
    current_price: float,
    options_data_by_expiration: Optional[List[Tuple[str, Dict[float, Dict[str, Any]]]]] = None
) -> int:
    """
    Compute risk reversal strategies and cache them in the database.
    Uses smart upsert: UPDATE existing, INSERT new, DELETE stale entries.

    Args:
        ticker: Stock ticker symbol
        current_price: Current stock price
        options_data_by_expiration: Optional pre-fetched options data to reuse

    Returns:
        Number of strategies cached
    """
    from app.services.stock_service import calculate_risk_reversal_strategies

    try:
        # Compute strategies (reuse pre-fetched data if supplied).
        strategies_by_expiration = calculate_risk_reversal_strategies(
            ticker,
            current_price,
            options_data_by_expiration=options_data_by_expiration
        )
        if not strategies_by_expiration:
            logger.debug(f"No risk reversal strategies computed for {ticker}")
            return 0

        with Session(engine) as session:
            # Get existing cached entries for this ticker
            existing_rows = session.exec(
                select(CachedRiskReversal).where(CachedRiskReversal.ticker == ticker)
            ).all()

            # Build key for existing entries: (expiration, ratio, put_strike, call_strike, short_call_strike)
            existing = {}
            for row in existing_rows:
                short_call = float(row.short_call_strike) if row.short_call_strike else None
                key = (row.expiration_date, row.ratio, float(row.put_strike), float(row.call_strike), short_call)
                existing[key] = row

            now = datetime.utcnow()
            cached_count = 0

            # Process each computed strategy
            for expiration_str, strategies in strategies_by_expiration.items():
                try:
                    exp_date = datetime.strptime(expiration_str, '%Y-%m-%d').date()
                except ValueError:
                    continue

                for strategy in strategies:
                    try:
                        put_strike = float(strategy['put_strike'])
                        call_strike = float(strategy['call_strike'])
                        short_call_strike = float(strategy.get('sold_call_strike')) if strategy.get('sold_call_strike') else None
                        ratio = strategy['ratio']

                        key = (exp_date, ratio, put_strike, call_strike, short_call_strike)

                        if key in existing:
                            # UPDATE existing row
                            row = existing[key]
                            row.put_premium = Decimal(str(strategy['put_bid']))
                            row.call_premium = Decimal(str(strategy['call_ask']))
                            row.short_call_premium = Decimal(str(strategy.get('sold_call_bid'))) if strategy.get('sold_call_bid') else None
                            row.net_cost = Decimal(str(strategy['cost']))
                            row.cost_pct = Decimal(str(strategy['cost_pct']))
                            row.days_to_expiration = strategy['days_to_expiration']
                            row.put_risk = Decimal(str(strategy['put_risk']))
                            row.current_price = Decimal(str(current_price))
                            row.collar_type = strategy.get('collar_type')
                            row.put_breakeven = Decimal(str(strategy.get('put_breakeven', 0)))
                            row.call_breakeven = Decimal(str(strategy.get('call_breakeven', 0)))
                            row.computed_at = now
                            session.add(row)
                            existing.pop(key)  # Mark as processed
                        else:
                            # INSERT new row
                            new_row = CachedRiskReversal(
                                ticker=ticker,
                                expiration_date=exp_date,
                                ratio=ratio,
                                put_strike=Decimal(str(put_strike)),
                                call_strike=Decimal(str(call_strike)),
                                short_call_strike=Decimal(str(short_call_strike)) if short_call_strike else None,
                                put_premium=Decimal(str(strategy['put_bid'])),
                                call_premium=Decimal(str(strategy['call_ask'])),
                                short_call_premium=Decimal(str(strategy.get('sold_call_bid'))) if strategy.get('sold_call_bid') else None,
                                net_cost=Decimal(str(strategy['cost'])),
                                cost_pct=Decimal(str(strategy['cost_pct'])),
                                days_to_expiration=strategy['days_to_expiration'],
                                put_risk=Decimal(str(strategy['put_risk'])),
                                current_price=Decimal(str(current_price)),
                                collar_type=strategy.get('collar_type'),
                                put_breakeven=Decimal(str(strategy.get('put_breakeven', 0))),
                                call_breakeven=Decimal(str(strategy.get('call_breakeven', 0))),
                                computed_at=now
                            )
                            session.add(new_row)

                        cached_count += 1
                    except Exception as e:
                        logger.warning(f"Error caching risk reversal for {ticker}: {e}")
                        continue

            # DELETE stale entries
            for stale_row in existing.values():
                session.delete(stale_row)

            session.commit()

            stale_count = len(existing)
            if stale_count > 0:
                logger.debug(f"Deleted {stale_count} stale risk reversal entries for {ticker}")

            return cached_count

    except Exception as e:
        logger.error(f"Error computing/caching risk reversals for {ticker}: {e}")
        return 0


def get_cached_covered_calls(ticker: str) -> List[Dict[str, Any]]:
    """
    Retrieve cached covered call strategies from the database.
    Only returns non-expired strategies.

    Args:
        ticker: Stock ticker symbol

    Returns:
        List of covered call strategy dictionaries (same format as calculate_covered_call_returns_v2)
    """
    today = date.today()

    try:
        with Session(engine) as session:
            rows = session.exec(
                select(CachedCoveredCall)
                .where(CachedCoveredCall.ticker == ticker)
                .where(CachedCoveredCall.expiration_date >= today)
            ).all()

            if not rows:
                return []

            # Convert to the same format as calculate_covered_call_returns_v2
            strategies = []
            for row in rows:
                strategies.append({
                    'expirationDate': row.expiration_date.strftime('%Y-%m-%d'),
                    'strike': float(row.strike),
                    'callPremium': round(float(row.call_premium), 2),
                    'returnExercised': round(float(row.return_exercised), 2),
                    'returnPctExercised': round(float(row.return_pct_exercised), 2),
                    'annualizedReturnExercised': round(float(row.annualized_return_exercised), 2),
                    'returnNotExercised': round(float(row.return_not_exercised), 2),
                    'returnPctNotExercised': round(float(row.return_pct_not_exercised), 2),
                    'annualizedReturnNotExercised': round(float(row.annualized_return_not_exercised), 2),
                    'returnDifference': round(float(row.return_difference), 2),
                    'daysToExpiration': row.days_to_expiration,
                    # Recalculate derived fields
                    'stockAppreciationPct': round(((float(row.strike) - float(row.current_price)) / float(row.current_price)) * 100, 2) if float(row.current_price) > 0 else 0,
                    'callPremiumPct': round((float(row.call_premium) / float(row.current_price)) * 100, 2) if float(row.current_price) > 0 else 0,
                })

            # Sort using the same logic as calculate_covered_call_returns_v2
            strategies.sort(
                key=lambda x: (
                    x['returnDifference'],
                    -(x['annualizedReturnExercised'] + x['annualizedReturnNotExercised']) / 2
                )
            )

            return strategies

    except Exception as e:
        logger.error(f"Error retrieving cached covered calls for {ticker}: {e}")
        return []


def get_cached_risk_reversals(ticker: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Retrieve cached risk reversal strategies from the database.
    Only returns non-expired strategies.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Dict of expiration -> list of strategy dictionaries (same format as calculate_risk_reversal_strategies)
    """
    today = date.today()

    try:
        with Session(engine) as session:
            rows = session.exec(
                select(CachedRiskReversal)
                .where(CachedRiskReversal.ticker == ticker)
                .where(CachedRiskReversal.expiration_date >= today)
            ).all()

            if not rows:
                return {}

            # Group by expiration and convert to the same format as calculate_risk_reversal_strategies
            strategies_by_expiration: Dict[str, List[Dict[str, Any]]] = {}

            for row in rows:
                expiration_str = row.expiration_date.strftime('%Y-%m-%d')

                strategy = {
                    'ratio': row.ratio,
                    'put_strike': float(row.put_strike),
                    'call_strike': float(row.call_strike),
                    'put_bid': round(float(row.put_premium), 2),
                    'call_ask': round(float(row.call_premium), 2),
                    'put_breakeven': round(float(row.put_breakeven), 2) if row.put_breakeven else 0,
                    'call_breakeven': round(float(row.call_breakeven), 2) if row.call_breakeven else 0,
                    'strike_spread': round(abs(float(row.call_strike) - float(row.put_strike)), 2),
                    'cost': round(float(row.net_cost), 2),
                    'cost_pct': round(float(row.cost_pct), 2),
                    'days_to_expiration': row.days_to_expiration,
                    'put_risk': round(float(row.put_risk), 2),
                    'put_risk_formatted': f"{float(row.put_risk):,.2f}",
                    'expiration': expiration_str,
                    'put_proximity': abs(float(row.put_strike) - float(row.current_price)),
                    'call_proximity': abs(float(row.call_strike) - float(row.put_strike)),
                }

                # Add Collar-specific fields
                if row.short_call_strike:
                    strategy['sold_call_strike'] = float(row.short_call_strike)
                    strategy['sold_call_bid'] = round(float(row.short_call_premium), 2) if row.short_call_premium else 0
                    strategy['collar_type'] = row.collar_type
                    strategy['max_profit_strike'] = float(row.short_call_strike)

                if expiration_str not in strategies_by_expiration:
                    strategies_by_expiration[expiration_str] = []
                strategies_by_expiration[expiration_str].append(strategy)

            # Sort strategies within each expiration and mark highlights
            for expiration_str, strategies in strategies_by_expiration.items():
                # Sort by put proximity, call proximity, cost
                strategies.sort(key=lambda s: (s['put_proximity'], s['call_proximity'], abs(s['cost'])))

                # Find strategies closest to $0 for highlighting
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

            return strategies_by_expiration

    except Exception as e:
        logger.error(f"Error retrieving cached risk reversals for {ticker}: {e}")
        return {}


def get_current_price_from_db(ticker: str) -> Optional[float]:
    """
    Get the current stock price from the latest stock_price entry.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Current stock price or None if not found
    """
    from app.models.stock_price import StockPrice

    try:
        with Session(engine) as session:
            row = session.exec(
                select(StockPrice)
                .where(StockPrice.ticker == ticker)
                .order_by(StockPrice.price_date.desc())
            ).first()

            if row:
                return float(row.close_price)
            return None

    except Exception as e:
        logger.error(f"Error getting current price for {ticker}: {e}")
        return None


def cache_options_strategies_for_ticker(ticker: str) -> Dict[str, int]:
    """
    Compute and cache both covered call and risk reversal strategies for a ticker.
    Convenience function used by the scheduler.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Dict with 'covered_calls' and 'risk_reversals' counts
    """
    current_price = get_current_price_from_db(ticker)
    if not current_price or current_price <= 0:
        logger.warning(f"Cannot cache options strategies for {ticker}: no valid current price")
        return {'covered_calls': 0, 'risk_reversals': 0}

    from app.services.stock_service import get_all_options_data

    # Fetch options data once per ticker and reuse for IV/CC/RR calculations.
    shared_options_data = get_all_options_data(
        ticker=ticker,
        current_price=current_price,
        days_limit=90,
        include_leaps=True,
        force_refresh=False
    )

    cc_count = compute_and_cache_covered_calls(
        ticker,
        current_price,
        options_data_by_expiration=shared_options_data
    )
    rr_count = compute_and_cache_risk_reversals(
        ticker,
        current_price,
        options_data_by_expiration=shared_options_data
    )

    return {'covered_calls': cc_count, 'risk_reversals': rr_count}
