from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional, List
from pydantic import BaseModel
from api.firebaseConfig import db, firestore_server_timestamp
from api.controller import controller, Task, TaskType, Priority
from api.routes.auth import verify_token

real_time_announcements_router = APIRouter(
    prefix="/realtime",
    tags=["Real Time Announcements"]
)

class BroadcastRequest(BaseModel):
    user: str
    zones: List[str]
    type: str = "voice" # 'voice' or 'text'
    content: Optional[str] = None # Text content or encoded metadata
    voice: Optional[str] = None # 'female' or 'male'
    session_token: Optional[str] = None # NEW: Session Tracking

class BroadcastAction(BaseModel):
    user: str
    type: str # 'voice' or 'text'
    action: str # 'START', 'STOP', 'MESSAGE'
    details: str
    timestamp: Optional[str] = None

class SeekRequest(BaseModel):
    user: str
    time: float

class HeartbeatRequest(BaseModel):
    session_token: Optional[str] = None

@real_time_announcements_router.post("/heartbeat")
def heartbeat(user: str, req: HeartbeatRequest = None, user_token: dict = Depends(verify_token)):
    """
    Called periodically by frontend to confirm 'User Presence'.
    If missing for >15s, controller auto-stops active session music.
    """
    token = req.session_token if req else None
    controller.register_heartbeat(user, token)
    return {"status": "alive"}

@real_time_announcements_router.post("/start")
def start_broadcast(req: BroadcastRequest, user_token: dict = Depends(verify_token)):
    """
    Request to start a Live Broadcast (Voice or Text) or Background Audio.
    Verified by PA Controller.
    """
    # Determine Priority and Type
    if req.type == 'background':
        task_type = TaskType.BACKGROUND
        priority = Priority.BACKGROUND
    elif req.type == 'voice':
        task_type = TaskType.VOICE
        priority = Priority.REALTIME
    else:
        task_type = TaskType.TEXT
        priority = Priority.REALTIME

    task = Task(
        type=task_type,
        priority=priority,
        data={
             "user": req.user,
            "zones": req.zones,
            "content": req.content,
            "voice": req.voice,
            "session_token": req.session_token # NEW: Session Tracking
        }
    )
    
    success = controller.request_playback(task)
    if not success:
        raise HTTPException(status_code=409, detail="System Busy or Higher Priority Active")
    
    return {"message": "Broadcast Started", "task_id": task.id}

class SpeakRequest(BaseModel):
    user: str
    audio_data: str # Base64 encoded

@real_time_announcements_router.post("/speak")
def speak_chunk(req: SpeakRequest, user_token: dict = Depends(verify_token)):
    """
    Receive and play a chunk of audio for the active broadcast.
    """
    try:
        controller.play_realtime_chunk(req.audio_data)
        return {"message": "Chunk processed"}
    except Exception as e:
        print(f"Speak error: {e}")
        # Return 200 to keep frontend streaming, but log error
        return {"message": "Chunk failed", "error": str(e)}

@real_time_announcements_router.post("/stop")
def stop_broadcast(user: str, type: str = "voice", task_id: Optional[str] = None, user_token: dict = Depends(verify_token)): 
    """
    Request to stop the current broadcast.
    Type can be 'voice', 'text', 'background'
    """
    # Type logic is actually handled loosely by controller or ignored if User matches.
    # We pass None to let controller decide based on User ownership if ID is missing.
    target_type = None
    if type == 'background':
        target_type = TaskType.BACKGROUND
    elif type == 'text':
        target_type = TaskType.TEXT
    elif type == 'voice':
        target_type = TaskType.VOICE
    
    controller.stop_task(task_id, task_type=target_type, user=user)
    return {"message": "Broadcast Stopped"}

@real_time_announcements_router.post("/stop-session")
def stop_session_audio(user: str, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """
    Stops current audio if it's NOT a schedule. Called on logout/tab close.
    Accepts token via Header OR Query Param (for sendBeacon).
    """
    # 1. Resolve Token
    actual_token = None
    if authorization and "Bearer " in authorization:
        actual_token = authorization.split("Bearer ")[1]
    elif token:
        actual_token = token
    
    if not actual_token:
         raise HTTPException(status_code=401, detail="Missing Token")

    # 2. Verify
    try:
        from firebase_admin import auth
        auth.verify_id_token(actual_token, clock_skew_seconds=60)
    except Exception as e:
        print(f"Token verification failed: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid Token: {e}")

    controller.stop_session_task(user)
    return {"message": "Session Audio Stopped"}

class CompleteRequest(BaseModel):
    task_id: str

@real_time_announcements_router.post("/complete")
def complete_task(req: CompleteRequest, user_token: dict = Depends(verify_token)):
    """
    Signal that a task (e.g. Schedule playback) has finished.
    """
    controller.stop_task(req.task_id, user="System")
    return {"message": "Task Completed"}

@real_time_announcements_router.post("/seek")
def seek_music(req: SeekRequest, user_token: dict = Depends(verify_token)):
    """
    Requested by frontend to skip/seek in background music.
    """
    success = controller.seek_background_music(req.user, req.time)
    if not success:
        raise HTTPException(status_code=404, detail="No background music active to seek")
    return {"message": "Seek successful"}

@real_time_announcements_router.post("/log")
def log_broadcast(action: BroadcastAction, user_token: dict = Depends(verify_token)):
    # Log history only
    try:
        log_entry = action.dict()
        log_entry["timestamp"] = firestore_server_timestamp()
        update_time, doc_ref = db.collection("logs").add(log_entry)
        return {"message": "Logged successfully", "id": doc_ref.id}
    except Exception as e:
        print(f"Logging failed: {e}")
        return {"message": "Logged (fallback)", "id": None}

@real_time_announcements_router.get("/logs")
def get_logs():
    try:
        from firebase_admin import firestore
        docs = db.collection("logs").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(50).stream()
        logs = []
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            if "timestamp" in data and data["timestamp"]:
                ts = data["timestamp"]
                if hasattr(ts, 'isoformat'):
                    data["timestamp"] = ts.isoformat()
                else:
                    data["timestamp"] = str(ts)
            logs.append(data)
        return logs
    except Exception as e:
        print(f"Fetch logs failed: {e}")
        return []

class LogUpdate(BaseModel):
    action: str = None
    details: str = None

@real_time_announcements_router.put("/log/{log_id}")
def update_log(log_id: str, update: LogUpdate, user_token: dict = Depends(verify_token)):
    try:
        doc_ref = db.collection("logs").document(log_id)
        if not doc_ref.get().exists:
            raise HTTPException(status_code=404, detail="Log not found")
        fields_to_update = {k: v for k, v in update.dict().items() if v is not None}
        if fields_to_update:
            doc_ref.update(fields_to_update)
        return {"message": "Log updated successfully"}
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))
         
@real_time_announcements_router.delete("/log/{log_id}")
def delete_log(log_id: str, user_token: dict = Depends(verify_token)):
    try:
        db.collection("logs").document(log_id).delete()
        return {"message": "Log deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
