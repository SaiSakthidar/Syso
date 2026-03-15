from fastapi import APIRouter, Request, Depends, HTTPException
from starlette.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
import os
import logging
from backend.agent.memory_tier3 import MemoryTier3

router = APIRouter(prefix="/auth")
logger = logging.getLogger(__name__)

oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

# Global status for desktop app polling
# In a real distributed system, this would be a session-based or token-based check
_auth_cache = {
    "is_logged_in": False,
    "user_info": None
}

@router.get('/login')
async def login(request: Request):
    redirect_uri = request.url_for('auth_callback')
    return await oauth.google.authorize_redirect(request, str(redirect_uri))

@router.get('/callback', name='auth_callback')
async def auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        user = token.get('userinfo')
        if user:
            user_id = user.get('sub', 'guest')
            logger.info(f"User logged in: {user.get('name')} ({user.get('email')}) - ID: {user_id}")
            
            # Persist to MemoryTier3
            base_dir = os.getenv("DATA_PATH", "data")
            tier3 = MemoryTier3(user_id=user_id, base_dir=base_dir)
            tier3.profile["name"] = user.get("name")
            tier3.profile["email"] = user.get("email")
            tier3.profile["picture"] = user.get("picture")
            tier3.save()
            
            _auth_cache["is_logged_in"] = True
            _auth_cache["user_info"] = user
            _auth_cache["user_id"] = user_id
            
            # Success page for the user to close
            return """
            <html>
                <body style="font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh;">
                    <h1 style="color: #4CAF50;">Login Successful!</h1>
                    <p>You can now close this tab and return to the Syso app.</p>
                </body>
            </html>
            """
    except Exception as e:
        logger.error(f"Auth error: {e}")
        raise HTTPException(status_code=400, detail=f"Authentication failed: {str(e)}")

@router.get('/status')
async def get_status():
    """Polling endpoint for the desktop app to know when login is done."""
    return _auth_cache

@router.get('/logout')
async def logout():
    tier3 = MemoryTier3()
    tier3.profile["name"] = None
    tier3.save()
    
    _auth_cache["is_logged_in"] = False
    _auth_cache["user_info"] = None
    return {"status": "logged_out"}
