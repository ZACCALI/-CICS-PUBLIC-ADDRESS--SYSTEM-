from firebase_admin import firestore
from fastapi import APIRouter, HTTPException, Depends
from api.firebaseConfig import db, firestore_server_timestamp
from api.routes.auth import verify_token
from pydantic import BaseModel
from typing import Optional, List

notifications_router = APIRouter(prefix="/notifications", tags=["notifications"])

class NotificationUpdate(BaseModel):
    read: bool

@notifications_router.put("/{id}/read")
def mark_as_read(id: str, update: NotificationUpdate, user_token: dict = Depends(verify_token)):
    try:
        ref = db.collection("notifications").document(id)
        doc = ref.get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Notification not found")
        
        uid = user_token.get('uid')
        
        # Add UID to 'read_by' array
        ref.update({
            "read_by": firestore.firestore.ArrayUnion([uid])
        })
        return {"message": "Updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@notifications_router.delete("/{id}")
def delete_notification(id: str, user_token: dict = Depends(verify_token)):
    try:
        doc_ref = db.collection("notifications").document(id)
        doc = doc_ref.get()
        if not doc.exists:
             # Already deleted or doesn't exist
             return {"message": "Notification not found or already deleted"}
             
        data = doc.to_dict()
        uid = user_token.get('uid')
        
        # 1. Personal Notification (Target User matches requester)
        if data.get('targetUser') == uid:
            doc_ref.delete()
            return {"message": "Notification deleted permanently"}
            
        # 2. Shared Notification (Target Role exists)
        elif data.get('targetRole'):
            # Soft Clear: Add UID to 'cleared_by' array
            # Firestore array_union
            doc_ref.update({
                "cleared_by": firestore.firestore.ArrayUnion([uid])
            })
            return {"message": "Notification cleared for user"}
            
        else:
            # Fallback (maybe old data?), allow delete if admin?
            # For safety, just delete if it looks personal or orphan
            doc_ref.delete()
            return {"message": "Notification deleted"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@notifications_router.delete("/")
def clear_all_notifications(user_token: dict = Depends(verify_token)):
    """Clears all notifications for the requesting user"""
    try:
        # Resolve username/uid from token
        # This requires storing 'targetUser' on notification creation
        # Implementation later
        return {"message": "Clear All Not Implemented Yet"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
