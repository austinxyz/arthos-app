from starlette.middleware.sessions import SessionMiddleware
from starlette.types import ASGIApp, Scope, Receive, Send
import json
import base64
from itsdangerous import Signer

# Mock app
async def mock_app(scope, receive, send):
    pass

SECRET_KEY = "your-secret-key-here"

def sign_manual(data):
    json_data = json.dumps(data).encode("utf-8")
    base64_data = base64.b64encode(json_data)
    signer = Signer(SECRET_KEY, salt="session")
    return signer.sign(base64_data).decode("utf-8")

if __name__ == "__main__":
    data = {"account_id": "123", "user_info": {"name": "Test"}}
    signed = sign_manual(data)
    print(f"Manual Signed: {signed}")
    
    # Check if we can verify it
    signer = Signer(SECRET_KEY, salt="session")
    unsign = signer.unsign(signed)
    print(f"Unsigned: {unsign}")
