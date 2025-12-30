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

from fastapi.responses import FileResponse

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(real_time_announcements_router)
app.include_router(scheduled_announcements_router)
app.include_router(manage_account_router)
app.include_router(emergency_route)
app.include_router(files_router)

# Import and include the AI Router for Smart Scheduler
from api.routes.ai import ai_router
app.include_router(ai_router)
# Removed duplicate includes

# Mount Media Directory
if not os.path.exists("media"):
    os.makedirs("media")
app.mount("/media", StaticFiles(directory="media"), name="media")


# --- FRONTEND HOSTING (SPA) ---
# Serve the React App from 'frontend-react/dist'
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend-react", "dist")

if os.path.exists(frontend_dist):
    # 1. Mount Assets (JS/CSS)
    assets_path = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

    # 2. Catch-All Route for React Router
    @app.get("/{full_path:path}")
    async def serve_react_app(full_path: str):
        # Build path to potential file
        file_path = os.path.join(frontend_dist, full_path)
        
        # If file exists (e.g. favicon.ico, manifest.json, robots.txt), serve it
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        
        # Otherwise, serve index.html (SPA Fallback)
        # This allows routes like /dashboard/schedule to work on refresh
        return FileResponse(os.path.join(frontend_dist, "index.html"))
else:
    print("[WARNING] Frontend build not found. Run 'npm run build' in frontend-react/ folder to enable local hosting.")
    @app.get("/")
    def read_root():
        return {"message": "Backend Running. Frontend not built."}


if __name__ == "__main__":
    import uvicorn
    # Host 0.0.0.0 allows access from other devices on the network
    uvicorn.run(app, host="0.0.0.0", port=8000)
