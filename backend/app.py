from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes.auth import auth_router
from api.routes.realtime import real_time_announcements_router 
from api.routes.scheduled import scheduled_announcements_router

from api.routes.account import manage_account_router
from api.routes.emergency import emergency_route
from api.routes.files import router as files_router
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"Hello": "World"}


app.include_router(auth_router)
app.include_router(real_time_announcements_router)
app.include_router(scheduled_announcements_router)
app.include_router(manage_account_router)
app.include_router(emergency_route)
app.include_router(files_router)

# Import and include the AI Router for Smart Scheduler
from api.routes.ai import ai_router
app.include_router(ai_router)
app.include_router(manage_account_router)
app.include_router(emergency_route)
app.include_router(files_router, prefix="/files", tags=["Files"])
from api.routes.notifications import notifications_router
app.include_router(notifications_router)


# Mount Media Directory
if not os.path.exists("media"):
    os.makedirs("media")
app.mount("/media", StaticFiles(directory="media"), name="media")

# Graceful Shutdown
from contextlib import asynccontextmanager
from api.audio_service import audio_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up Device Heartbeat...")
    
    stop_event = threading.Event()
    
    def heartbeat():
        from api.firebaseConfig import db, firestore_server_timestamp
        while not stop_event.is_set():
            try:
                # Update 'devices/pi-main' document
                db.collection('devices').document('pi-main').set({
                    'status': 'online',
                    'last_heartbeat': firestore_server_timestamp(),
                    'type': 'backend'
                }, merge=True)
                # Sleep 30s
            except Exception as e:
                print(f"[Heartbeat] Error: {e}")
            
            # Sleep in chunks to allow fast exit
            for _ in range(30):
                if stop_event.is_set(): break
                time.sleep(1)

    t = threading.Thread(target=heartbeat, daemon=True)
    t.start()
    
    yield
    # Shutdown
    print("[LifeSpan] Shutting down services...")
    stop_event.set()
    try:
        audio_service.stop()
    except Exception as e:
        print(f"[LifeSpan] Cleanup skipped or failed: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
