
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from api.smart_parser import smart_parser

ai_router = APIRouter(prefix="/ai", tags=["AI"])

class SmartCommand(BaseModel):
    command: str
    zones: list[str] = []

@ai_router.post("/parse_schedule")
def parse_schedule(payload: SmartCommand):
    """
    Parses a natural language command into schedule details.
    """
    try:
        result = smart_parser.parse_command(payload.command, payload.zones)
        if "error" in result:
             raise HTTPException(status_code=500, detail=result["error"])
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
