"""Portfolio service for managing portfolios and portfolio stocks."""
from sqlmodel import Session, select
from app.database import engine
from app.models.portfolio import Portfolio, PortfolioStock
from app.services.ticker_validator import validate_ticker_list
from app.services.stock_service import get_multiple_stock_metrics
from datetime import datetime
from typing import List, Dict, Any
from uuid import UUID


def validate_portfolio_name(name: str) -> bool:
    """
    Validate portfolio name (alphanumeric and spaces only, max 128 chars).
    
    Args:
        name: Portfolio name to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not name or not name.strip():
        return False
    
    if len(name) > 128:
        return False
    
    # Allow alphanumeric and spaces only
    return all(c.isalnum() or c.isspace() for c in name)


def create_portfolio(name: str) -> Portfolio:
    """
    Create a new portfolio.
    
    Args:
        name: Portfolio name
        
    Returns:
        Created Portfolio object
        
    Raises:
        ValueError: If name is invalid
    """
    if not validate_portfolio_name(name):
        raise ValueError("Portfolio name must be alphanumeric with spaces only, max 128 characters")
    
    with Session(engine) as session:
        portfolio = Portfolio(
            portfolio_name=name.strip(),
            date_added=datetime.now(),
            date_modified=datetime.now()
        )
        session.add(portfolio)
        session.commit()
        session.refresh(portfolio)
        return portfolio


def get_all_portfolios() -> List[Portfolio]:
    """
    Get all portfolios.
    
    Returns:
        List of all Portfolio objects
    """
    with Session(engine) as session:
        statement = select(Portfolio).order_by(Portfolio.date_modified.desc())
        portfolios = session.exec(statement).all()
        return list(portfolios)


def get_portfolio(portfolio_id: UUID) -> Portfolio:
    """
    Get a portfolio by ID.
    
    Args:
        portfolio_id: Portfolio UUID
        
    Returns:
        Portfolio object
        
    Raises:
        ValueError: If portfolio not found
    """
    with Session(engine) as session:
        portfolio = session.get(Portfolio, portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio with ID {portfolio_id} not found")
        return portfolio


def update_portfolio_name(portfolio_id: UUID, new_name: str) -> Portfolio:
    """
    Update portfolio name.
    
    Args:
        portfolio_id: Portfolio UUID
        new_name: New portfolio name
        
    Returns:
        Updated Portfolio object
        
    Raises:
        ValueError: If name is invalid or portfolio not found
    """
    if not validate_portfolio_name(new_name):
        raise ValueError("Portfolio name must be alphanumeric with spaces only, max 128 characters")
    
    with Session(engine) as session:
        portfolio = session.get(Portfolio, portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio with ID {portfolio_id} not found")
        
        portfolio.portfolio_name = new_name.strip()
        portfolio.date_modified = datetime.now()
        session.add(portfolio)
        session.commit()
        session.refresh(portfolio)
        return portfolio


def delete_portfolio(portfolio_id: UUID) -> bool:
    """
    Delete a portfolio and all its stocks (cascade delete).
    
    Args:
        portfolio_id: Portfolio UUID
        
    Returns:
        True if deleted successfully
        
    Raises:
        ValueError: If portfolio not found
    """
    with Session(engine) as session:
        portfolio = session.get(Portfolio, portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio with ID {portfolio_id} not found")
        
        session.delete(portfolio)
        session.commit()
        return True


def add_stocks_to_portfolio(portfolio_id: UUID, tickers: List[str]) -> List[PortfolioStock]:
    """
    Add stocks to a portfolio. Ignores duplicates.
    
    Args:
        portfolio_id: Portfolio UUID
        tickers: List of stock ticker symbols
        
    Returns:
        List of PortfolioStock objects that were added (excluding duplicates)
        
    Raises:
        ValueError: If portfolio not found or tickers are invalid
    """
    # Validate portfolio exists
    portfolio = get_portfolio(portfolio_id)
    
    # Validate ticker formats
    valid_tickers, invalid_tickers = validate_ticker_list(tickers)
    
    if invalid_tickers:
        raise ValueError(f"Invalid ticker format(s): {', '.join(invalid_tickers)}")
    
    if not valid_tickers:
        return []
    
    with Session(engine) as session:
        added_stocks = []
        
        for ticker in valid_tickers:
            ticker = ticker.upper()
            
            # Check if stock already exists in portfolio
            statement = select(PortfolioStock).where(
                PortfolioStock.portfolio_id == portfolio_id,
                PortfolioStock.ticker == ticker
            )
            existing = session.exec(statement).first()
            
            if not existing:
                # Add new stock
                portfolio_stock = PortfolioStock(
                    portfolio_id=portfolio_id,
                    ticker=ticker,
                    date_added=datetime.now()
                )
                session.add(portfolio_stock)
                added_stocks.append(portfolio_stock)
        
        # Update portfolio's date_modified
        portfolio.date_modified = datetime.now()
        session.add(portfolio)
        
        session.commit()
        
        # Refresh added stocks
        for stock in added_stocks:
            session.refresh(stock)
        
        return added_stocks


def remove_stock_from_portfolio(portfolio_id: UUID, ticker: str) -> bool:
    """
    Remove a stock from a portfolio.
    
    Args:
        portfolio_id: Portfolio UUID
        ticker: Stock ticker symbol
        
    Returns:
        True if removed successfully
        
    Raises:
        ValueError: If portfolio or stock not found
    """
    ticker = ticker.upper()
    
    with Session(engine) as session:
        # Verify portfolio exists
        portfolio = session.get(Portfolio, portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio with ID {portfolio_id} not found")
        
        # Find and delete the stock
        statement = select(PortfolioStock).where(
            PortfolioStock.portfolio_id == portfolio_id,
            PortfolioStock.ticker == ticker
        )
        portfolio_stock = session.exec(statement).first()
        
        if not portfolio_stock:
            raise ValueError(f"Stock {ticker} not found in portfolio {portfolio_id}")
        
        session.delete(portfolio_stock)
        
        # Update portfolio's date_modified
        portfolio.date_modified = datetime.now()
        session.add(portfolio)
        
        session.commit()
        return True


def get_portfolio_stocks(portfolio_id: UUID) -> List[PortfolioStock]:
    """
    Get all stocks in a portfolio.
    
    Args:
        portfolio_id: Portfolio UUID
        
    Returns:
        List of PortfolioStock objects
        
    Raises:
        ValueError: If portfolio not found
    """
    # Verify portfolio exists
    get_portfolio(portfolio_id)
    
    with Session(engine) as session:
        statement = select(PortfolioStock).where(
            PortfolioStock.portfolio_id == portfolio_id
        ).order_by(PortfolioStock.date_added.desc())
        stocks = session.exec(statement).all()
        return list(stocks)


def get_portfolio_stocks_with_metrics(portfolio_id: UUID) -> List[Dict[str, Any]]:
    """
    Get all stocks in a portfolio with their current metrics.
    
    Args:
        portfolio_id: Portfolio UUID
        
    Returns:
        List of dictionaries containing stock metrics
    """
    stocks = get_portfolio_stocks(portfolio_id)
    
    if not stocks:
        return []
    
    # Get tickers
    tickers = [stock.ticker for stock in stocks]
    
    # Fetch metrics for all tickers
    metrics_list = get_multiple_stock_metrics(tickers)
    
    # Format numbers for display
    for metric in metrics_list:
        if 'error' not in metric:
            metric['current_price_formatted'] = f"${metric['current_price']:.2f}"
            metric['sma_50_formatted'] = f"${metric['sma_50']:.2f}"
            metric['sma_200_formatted'] = f"${metric['sma_200']:.2f}"
            metric['stddev_50d_formatted'] = f"{metric['devstep']:.1f}"
            if metric.get('dividend_yield') is not None:
                metric['dividend_yield_formatted'] = f"{metric['dividend_yield']:.2f}%"
            else:
                metric['dividend_yield_formatted'] = "N/A"
    
    return metrics_list
