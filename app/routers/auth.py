"""Authentication routes."""
import os
import logging
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
from starlette.config import Config
from starlette.requests import Request
from authlib.integrations.starlette_client import OAuth, OAuthError
from app.models.account import Account
from app.database import get_session
from sqlmodel import Session, select
from datetime import datetime
from uuid import uuid4

router = APIRouter()

# OAuth Configuration
# We can use Starlette Config or just os.environ since we load .env in main.py
# specific configuration for OAuth
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

# Setup logging
logger = logging.getLogger(__name__)

if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    logger.warning("GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not set")

oauth = OAuth()
oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

@router.get("/login")
async def login(request: Request):
    """Redirect to Google for login."""
    # Build absolute redirect URI
    redirect_uri = request.url_for('auth_google')
    
    # If running behind proxy (like Railway), ensure https
    # ALLOW 127.0.0.1 to be HTTP
    redirect_uri_str = str(redirect_uri)
    if "https" not in redirect_uri_str and "localhost" not in redirect_uri_str and "127.0.0.1" not in redirect_uri_str:
        redirect_uri = redirect_uri_str.replace("http:", "https:")
    
    logger.info(f"OIDC Login initialized. Redirect URI: {redirect_uri}")
        
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth/google")
async def auth_google(request: Request):
    """Callback for Google OAuth."""
    logger.info(f"OIDC Callback received. Params: {request.query_params}")
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as error:
        # Handle error
        logger.error(f"OIDC Auth Error: {error.description}")
        raise HTTPException(status_code=401, detail=f"Auth error: {error.description}")
        
    user_data = token.get('userinfo')
    if not user_data:
        # If userinfo is not in token, fetch it
        # usually with openid scope it's in 'id_token' claims which authorize_access_token parses
        # but let's be safe
        pass
        
    if not user_data:
         raise HTTPException(status_code=401, detail="Could not retrieve user info")

    # Sync User with DB
    # We need a session here. In FastAPI we usually use Dependency Injection, 
    # but for simple route logic we can just use the generator manually or use a context manager
    # Since we are not in a Depends context easily here without changing signature significantly for the callback
    # Let's simple create a session.
    
    from app.database import engine
    
    with Session(engine) as session:
        # Create or update account
        # In a real app, you might want to separate creation from login if registration is restricted
        # Here we auto-register Google users
        
        statement = select(Account).where(Account.email == user_data['email'])
        account = session.exec(statement).first()
        
        if not account:
            # Create new account
            account = Account(
                email=user_data['email'],
                google_sub=user_data['sub'],
                full_name=user_data.get('name'),
                picture_url=user_data.get('picture'),
                last_login_at=datetime.utcnow()
            )
            session.add(account)
            session.commit()
            session.refresh(account)
        else:
            # Update existing account
            account.full_name = user_data.get('name')
            account.picture_url = user_data.get('picture')
            account.last_login_at = datetime.utcnow()
            session.add(account)
            session.commit()
            session.refresh(account)
            
        # Store user info in session
        request.session['account_id'] = str(account.id)
        request.session['user'] = {
            'name': account.full_name or account.email,
            'email': account.email,
            'picture': account.picture_url
        }
    return RedirectResponse(url='/')


@router.get("/logout")
async def logout(request: Request):
    """Logout user."""
    request.session.clear()
    return RedirectResponse(url='/')
