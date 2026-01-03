from fastapi import APIRouter, Depends, HTTPException, status, Header
from firebase_admin import auth
from api.firebaseConfig import db
from api.notification_service import notification_service

auth_router = APIRouter(prefix="/auth", tags=["auth"])

from fastapi import Query
# ... imports

async def verify_token(
    authorization: str = Header(None), 
    token: str = Query(None)
):
    """
    Verifies Firebase ID token.
    Accepts 'Authorization: Bearer <token>' HEADER 
    OR '?token=<token>' QUERY PARAM (for Beacons).
    """
    id_token = None
    
    # 1. Check Header
    if authorization and authorization.startswith("Bearer "):
        id_token = authorization.split("Bearer ")[1]
    
    # 2. Check Query Param (Fallback)
    if not id_token and token:
        id_token = token
        
    if not id_token:
         raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
        )
    
    try:
        # Allow 60 seconds of clock skew
        decoded_token = auth.verify_id_token(id_token, clock_skew_seconds=60)
        return decoded_token
    except Exception as e:
        print(f"Error verifying token: {e}") 
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
        )

async def verify_admin(decoded_token: dict = Depends(verify_token)):
    """
    Verifies if the user associated with the token has admin privileges.
    Checks Firestore 'users' collection for the 'role' field.
    """
    uid = decoded_token.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user_doc = db.collection("users").document(uid).get()
    if not user_doc.exists:
        raise HTTPException(status_code=403, detail="User not found")

    user_data = user_doc.to_dict()
    if user_data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admins only")
    
    return decoded_token

@auth_router.get("/")
def auth_check():
    return {"message": "Auth module loaded"}
