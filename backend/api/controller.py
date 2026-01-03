import threading
import time
import os
import uuid
from enum import IntEnum
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from firebase_admin import firestore
from firebase_admin import firestore
from api.firebaseConfig import db
from api.audio_service import audio_service 
from api.notification_service import notification_service # <--- NEW IMPORT

# --- 1. Constants & Enums ---
class Priority(IntEnum):
    IDLE = 0
    BACKGROUND = 10
    SCHEDULE = 20
    REALTIME = 30
    EMERGENCY = 100

class State(IntEnum):
    PENDING = 1
    PLAYING = 2
    INTERRUPTED = 3
    COMPLETED = 4

class TaskType:
    VOICE = 'voice'
    TEXT = 'text'
    EMERGENCY = 'emergency'
    SCHEDULE = 'schedule'
    BACKGROUND = 'background'

# --- 2. Data Structures ---
class Task:
    def __init__(self, 
                 type: str, 
                 priority: int, 
                 data: dict, 
                 id: str = None, 
                 status: State = State.PENDING, 
                 created_at: datetime = None,
                 scheduled_time: datetime = None):
        self.id = id if id else str(uuid.uuid4())
        self.type = type
        self.priority = priority
        self.data = data
        self.status = status
        self.created_at = created_at if created_at else datetime.now()
        self.scheduled_time = scheduled_time if scheduled_time else datetime.now()

    def to_dict(self):
        return {
            'id': self.id,
            'type': self.type,
            'priority': int(self.priority),
            'data': self.data,
            'status': int(self.status),
            'created_at': self.created_at.isoformat(),
            'scheduled_time': self.scheduled_time.isoformat()
        }

# --- 3. The Controller ---
class PAController:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PAController, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self._lock = threading.Lock()  # THE MUTEX
        self.current_task: Optional[Task] = None
        self.queue: List[Task] = []    # Priority Queue for Schedules
        self.emergency_mode = False
        self.emergency_owner = None # Track who started it for strict deactivation
        self._running = True
        
        # Track interruption duration to shift queue
        self.pause_start_time: Optional[datetime] = None
        
        # Track Suspended Task (for Resume)
        self.suspended_task: Optional[Task] = None

        # Background Music State
        self.background_resume_time = 0
        self.background_play_start: Optional[datetime] = None
        self.last_background_content: Optional[str] = None

        # Reset Logic on init to ensure clean state
        audio_service.cleanup_all() # <--- KILL ZOMBIE MUSIC ON STARTUP
        self._reset_state()
        
        # Cleanup State
        # Cleanup State
        self.last_cleanup = datetime.now()
        
        # Monitor Heartbeats
        self.last_heartbeats: Dict[str, datetime] = {}

        # Start Scheduler Thread
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        
        self._initialized = True
        self._initialized = True
        print("PA Controller Initialized")
        # NOTIFICATION: Device Online
        notification_service.create(
            "Device Status", 
            "PA system is online (Raspberry Pi/Service Started)", 
            type="success", 
            target_role="admin"
        )

    def _reset_state(self):
        """Resets Firestore state to Idle on startup"""
        try:
            db.collection('system').document('state').set({
                'active_task': None,
                'priority': 0,
                'mode': 'IDLE',
                'timestamp': firestore.SERVER_TIMESTAMP
            })
            self._load_pending_schedules() # <--- NEW: Load schedules on reset/startup
        except Exception as e:
            print(f"Failed to reset state: {e}")

    def _load_pending_schedules(self):
        """Resilience: Loads 'Pending' schedules from Firestore into Queue on startup"""
        print("[Controller] Loading pending schedules from database...")
        try:
            # Query all Pending schedules
            # FIX: Use keyword arguments to silence UserWarning
            docs = db.collection('schedules').where(filter=firestore.FieldFilter('status', '==', 'Pending')).stream()
            count = 0
            for doc in docs:
                data = doc.to_dict()
                try:
                    # Parse Date/Time
                    dt_str = f"{data.get('date')} {data.get('time')}"
                    scheduled_time = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
                    
                    # Create Task
                    task = Task(
                        id=doc.id,
                        type=TaskType.SCHEDULE,
                        priority=Priority.SCHEDULE,
                        data=data,
                        scheduled_time=scheduled_time
                    )
                    
                    # Add to internal queue (avoiding re-triggering logic)
                    self.queue.append(task)
                    count += 1
                except ValueError:
                    print(f"  -> Skipping invalid date format in {doc.id}")
                    continue
            
            # Sort queue
            self.queue.sort(key=lambda x: x.scheduled_time)
            print(f"[Controller] Resilience: Loaded {count} pending tasks.")
            
        except Exception as e:
            print(f"[Controller] Failed to load pending schedules: {e}")

    # --- MAIN ENTRY POINT ---
    def request_playback(self, new_task: Task) -> bool:
        with self._lock:  # Critical Section
            print(f"[Controller] Request: {new_task.type} (Pri: {new_task.priority})")

            # 1. Emergency Check (Invincible)
            if self.emergency_mode and new_task.priority < Priority.EMERGENCY:
                print(f"[Controller] Denied: Emergency Active")
                return False

            # 2. Schedule Check (Always Queue first)
            if new_task.type == TaskType.SCHEDULE:
                 # Standard Schedule submission (queued)
                 print(f"[Controller] Queued Schedule: {new_task.id}")
                 self._add_to_queue(new_task)
                 return True 

            # 3. Priority Check
            current_pri = self.current_task.priority if self.current_task else Priority.IDLE
            
            # CHECK OWNERSHIP: Allow user to interrupt THEMSELVES (e.g. Refresh page)
            is_same_user = False
            if self.current_task and self.current_task.data.get('user') == new_task.data.get('user'):
                is_same_user = True

            # Logic: Higher Priority WINS OR (Equal Priority AND Same User WINS)
            if new_task.priority > current_pri or (new_task.priority == current_pri and is_same_user):
                
                # IDEMPOTENCY CHECK: If it's the SAME background track already playing, IGNORE.
                if self.current_task and self.current_task.type == TaskType.BACKGROUND and new_task.type == TaskType.BACKGROUND:
                    if self.current_task.data.get('content') == new_task.data.get('content'):
                        # Check start_time to distinguish between "Seek" and "Redundant Play"
                        # If start_time is 0, it's usually a redundant "New Play" click.
                        if new_task.data.get('start_time') == 0:
                            print(f"[Controller] Ignoring redundant start request for: {new_task.data.get('content')}")
                            return True # Success (but do nothing)

                # FRESH START: If it's a new Background Music request, reset the resume offset
                if new_task.type == TaskType.BACKGROUND:
                    new_content = new_task.data.get('content')
                    if new_content != self.last_background_content:
                        print(f"[Controller] New Track: {new_content}. Resetting Resume Point.")
                        self.background_resume_time = 0
                        self.last_background_content = new_content
                    else:
                        print(f"[Controller] Resuming Track: {new_content} at {self.background_resume_time}s")
                    
                    self.background_play_start = None

                # PREEMPTION
                self._preempt_current_task(new_task.priority)
                
                # --- NEW: NON-BLOCKING EMERGENCY ---
                if new_task.type == TaskType.EMERGENCY:
                    # Run activation in background so API returns instantly
                    threading.Thread(target=self._start_task, args=(new_task,), daemon=True).start()
                else:
                    self._start_task(new_task)
                
                return True
            
            else:
                # Lower/Equal priority (different user) -> Busy
                print(f"[Controller] Denied: Busy (Current: {current_pri}, New: {new_task.priority})")
                return False

    def stop_session_task(self, user: str):
        """Used during logout to stop personal audio (Music, Voice, Text, Emergency)"""
        with self._lock:
            if not self.current_task:
                return
            
            # NEVER stop schedules on logout
            if self.current_task.type == TaskType.SCHEDULE:
                print(f"[Controller] Logout: Keeping Schedule {self.current_task.id} active.")
                return

            print(f"[Controller] Logout: Stopping {self.current_task.type} for session end.")
            # For logout, we use 'System' as the stop requester to allow override
            self.stop_task(None, user='System')

    def stop_task(self, task_id: str, task_type: str = None, user: str = None):
        """Called to manually stop a task (e.g., Stop Broadcast, Clear Emergency)"""
        with self._lock:
            # FIX: If emergency mode is active, we MUST allow stop even if current_task is None
            # (Because the script might have finished, but the siren is still looping)
            if not self.current_task and not self.emergency_mode:
                return

            # If requesting to stop specific task, check ID
            if task_id and self.current_task and self.current_task.id != task_id:
                print(f"[Controller] Denied Stop: ID Mismatch ({task_id} vs {self.current_task.id})")
                return

            # NEW: If requesting to stop specific TYPE, check Type (unless ID provided)
            # This prevents 'Stop Voice' (Refresh) from killing 'Background Music'
            if task_type and self.current_task:
                 if not task_id: # ID override always wins
                     # Special Case: 'voice' stop should NOT kill 'background' or 'schedule'
                     # 'any' stop (None) kills everything
                     if self.current_task.type != task_type and task_type != 'any':
                         # Allow mapped types if string differs, but here we use TaskType enum mostly.
                         # Realtime router maps string to Enum. self.current_task.type is Enum.
                         # We should compare Enums or accept string match.
                         print(f"[Controller] Denied Stop: Type Mismatch (Requested {task_type} vs Active {self.current_task.type})")
                         return

            # ADMIN OVERRIDE & ID PROTECTION
            if not task_id and self.current_task:
                 # Check if user is an Admin (allowing bypass of ID requirement)
                 is_admin = user in ['System', 'System Admin', 'Admin', 'admin']
                 
                 # Schedules are protected unless explicit ID is given?
                 # No, schedules usually only stop via ID or completion.
                 if self.current_task.type == TaskType.SCHEDULE and not is_admin:
                      print(f"[Controller] Denied Generic Stop: Cannot kill Schedule without Task ID.")
                      return

                 # Emergency PROTECTION (Normal users need ID, Admins don't)
                 if self.current_task.type == TaskType.EMERGENCY or self.emergency_mode:
                     if not is_admin:
                         # Check against persistent owner
                         owner = self.emergency_owner or (self.current_task.data.get('user') if self.current_task else None)
                         if user != owner and owner is not None:
                             print(f"[Controller] Denied Stop: Emergency requires Owner ({owner}) or Admin.")
                             return

            if self.current_task:
                print(f"[Controller] Stopping Task: {self.current_task.id}")
                
                if self.current_task.priority == Priority.EMERGENCY:
                    self.emergency_mode = False
                    self.emergency_owner = None
                
                # Stop stream if active
                if self.current_task.type == TaskType.VOICE:
                    audio_service.stop_streaming()
            else:
                # Emergency mode stopping without current_task
                print("[Controller] Stopping Emergency Mode (Voice already finished)")
                self.emergency_mode = False
                self.emergency_owner = None

            self._update_firestore_state(None, Priority.IDLE, 'IDLE')
            
            # Stop Audio
            if self.current_task and self.current_task.type == TaskType.BACKGROUND:
                # Calculate final offset before stopping
                if self.background_play_start:
                    elapsed = (datetime.now() - self.background_play_start).total_seconds()
                    self.background_resume_time += elapsed
                    self.background_play_start = None
                
                # If we are hard stopping (Manual Stop), clear the resume point
                # (Unless we want it to stay for next time? User said "resume where it stops")
                # But "Stop" button usually means stop completely.
                # However, "Interrupted" is different. 
                # Let's keep resume_time until a NEW background task is started.
            
            self.current_task = None
            audio_service.stop()
            
            # Application of Time Shift (System became IDLE)
            # Application of Time Shift (System became IDLE)
            self._apply_queue_shift()

            # NOTIFICATION: Ended (Manually Stopped)
            # Only if it was running and not just preempted logic
            # Actually stop_task means explicit stop (User action or Complete signal)
            notification_service.create(
                 "Broadcast Ended",
                 "Announcement finished or was stopped.",
                 type="info",
                 target_role="admin" # Broadcasts are public
            )

            # RESUME SUSPENDED TASK
            if self.suspended_task:
                 print(f"[Controller] [RESUME] Found Suspended Task: {self.suspended_task.type} (ID: {self.suspended_task.id})")
                 # Small delay for smooth transition
                 time.sleep(1)
                 # Force status reset just in case
                 self.suspended_task.status = State.PENDING
                 self._start_task(self.suspended_task)
                 # IMPORTANT: Do NOT clear suspended_task here if _start_task fails (it doesn't fail).
                 # We must ensure we don't lose it.
                 self.suspended_task = None
                 print(f"[Controller] [RESUME] Task Resumed. Suspended cleared.")
            else:
                 print(f"[Controller] No Suspended Task to resume.")

    def get_queue(self):
        return self.queue
        
    def remove_from_queue(self, schedule_id: str):
        with self._lock:
             self.queue = [t for t in self.queue if t.id != schedule_id]

    def get_active_emergency_user(self) -> Optional[str]:
        with self._lock:
            if self.current_task and self.current_task.priority == Priority.EMERGENCY:
                 return self.current_task.data.get('user')
            return None

    def seek_background_music(self, user: str, time_seconds: float):
        """Forces the current background music to seek to a specific time"""
        with self._lock:
            if not self.current_task or self.current_task.type != TaskType.BACKGROUND:
                print("[Controller] Seek Denied: No Background Music playing")
                return False
            
            # Update resume time and restart
            self.background_resume_time = time_seconds
            self.background_play_start = None # Reset start tracking
            
            # Re-start the same task with new offset
            task = self.current_task
            audio_service.stop()
            self._start_task(task)
            return True

    def play_realtime_chunk(self, audio_base64: str):
        """Decodes RAW PCM chunks, wraps in WAV header, and plays immediately"""
        # Ensure we are actually in a Voice Broadcast state
        if not self.current_task or self.current_task.type != TaskType.VOICE:
            print("[Controller] Denied Speak: No Voice Broadcast Active")
            return

        try:
             import base64
             import wave
             
             # Clean header if present (though frontend sends raw b64 now)
             if "base64," in audio_base64:
                 audio_base64 = audio_base64.split("base64,")[1]
            
             decoded_pcm = base64.b64decode(audio_base64)
             
             # Feed Raw PCM directly to AudioService Stream
             audio_service.feed_stream(decoded_pcm)
             
        except Exception as e:
            print(f"[Controller] Chunk Error: {e}")

    # --- INTERNAL LOGIC ---
    def _add_to_queue(self, task: Task):
        self.queue.append(task)
        # Sort by scheduled_time
        self.queue.sort(key=lambda x: x.scheduled_time)

    def _preempt_current_task(self, new_priority):
        if not self.current_task:
            return

        print(f"[Controller] Preempting: {self.current_task.type}")

        # Specific Logic per Type
        if self.current_task.type == TaskType.SCHEDULE:
            # Soft Stop: Re-queue at HEAD
            print(f"  -> Re-queueing Schedule {self.current_task.id}")
            self.current_task.status = State.INTERRUPTED
            # Push to front of queue
            # Push to front of queue
            self.queue.insert(0, self.current_task) 
            
            # NOTIFICATION: Schedule Interrupted
            notification_service.create(
                "Scheduled Announcement Interrupted",
                f"Schedule '{self.current_task.data.get('message', 'Msg')}' was interrupted by higher priority task.",
                type="warning",
                target_user=self.current_task.data.get('user'), # Notify Owner
                target_role="admin" # Notify Admin
            ) 
        
        elif self.current_task.type == TaskType.VOICE or self.current_task.type == TaskType.TEXT:
            # Hard Stop: Kill completely
            print(f"  -> Killing Realtime {self.current_task.id}")
            print(f"  -> Killing Realtime {self.current_task.id}")
            self.current_task.status = State.COMPLETED
            
            # NOTIFICATION: Realtime Interrupted
            notification_service.create(
                "Live Announcement Interrupted",
                "Your live broadcast was interrupted by a higher priority event (e.g. Emergency).",
                type="error",
                target_user=self.current_task.data.get('user'),
                target_role="admin"
            )
            
        elif self.current_task.type == TaskType.BACKGROUND:
            # FIX: If we are just switching tracks (BACKGROUND -> BACKGROUND), do NOT suspend.
            if new_priority == Priority.BACKGROUND:
                 print(f"  -> Switching Track: {self.current_task.id} replaced by new Background Task.")
                 self.current_task = None
                 # Do not set suspended_task
                 # audio_service.stop() will happen below
            else:
                 # Soft Stop: Suspend (Only if Higher Priority Interrupted)
                 print(f"  -> [SUSPEND] Suspending Background Task {self.current_task.id} for {new_priority}")
                 
                 # Save offset correctly
                 if self.background_play_start:
                     elapsed = (datetime.now() - self.background_play_start).total_seconds()
                     self.background_resume_time += elapsed
                     print(f"  -> Saved resume offset: {self.background_resume_time}s")
                     self.background_play_start = None

                 self.suspended_task = self.current_task
                 self.current_task = None
            # Do NOT mark COMPLETED. State remains valid in object.
        
        else:
             # Default Fallback
             self.current_task = None

        self.current_task = None
        
        # Stop Audio logic
        audio_service.stop()

    def _start_task(self, task: Task):
        self.current_task = task
        self.current_task.status = State.PLAYING
        
        # Start Time Shift Tracking if High Priority
        if task.priority >= Priority.REALTIME:
            if self.pause_start_time is None:
                self.pause_start_time = datetime.now()
                print(f"[Controller] Time Shift Started at {self.pause_start_time}")

        if task.priority == Priority.EMERGENCY:
            self.emergency_mode = True
            self.emergency_owner = task.data.get('user')
            # Play Siren on Pi (Start quiet)
            audio_service.play_siren(zones=['All Zones'], volume=0.002)
            
            # NOTIFICATION: Emergency Started
            notification_service.create(
                "Emergency Activated",
                "Emergency broadcast in progress. All other schedules paused.",
                type="error",
                target_role="admin" # And User too? Plan said System Level.
            )
            # Duplicate for generic users? Or frontend handles 'target_role' logic?
            # We'll just send to admin and let frontend logic display it generally if needed 
            # OR send two notifications.
            notification_service.create(
                "Emergency Activated",
                "Emergency broadcast in progress.",
                type="error",
                target_role="user"
            )

        
        mode = 'BROADCAST'
        if task.type == TaskType.EMERGENCY: mode = 'EMERGENCY'
        elif task.type == TaskType.SCHEDULE: mode = 'SCHEDULE'
        elif task.type == TaskType.BACKGROUND: mode = 'BACKGROUND'

        print(f"[Controller] Starting: {task.type} (Mode: {mode})")
        self._update_firestore_state(task, task.priority, mode)
        
        # --- AUDIO OUTPUT START ---
        if task.type == TaskType.VOICE:
             # 1. Play Intro Chime Synchronously (Non-blocking threads)
             zones = task.data.get('zones', [])
             if isinstance(zones, str):
                 zones = [z.strip() for z in zones.split(',')]
             print(f"[Controller] DEBUG: Voice Task Zones: {zones} (Type: {type(zones)})") # <--- DEBUG LOG
             print(f"[Controller] Playing Intro Chime for Voice Broadcast...")
             audio_service.play_chime_sync(zones)
             
             # Small delay to ensure chime is fully finished and hardware is ready
             time.sleep(0.5)

             # 2. Start the Streaming Pipe
             audio_service.start_streaming(zones)

        elif task.type == TaskType.SCHEDULE:
             # Check if it's Audio File or Text
             audio_data = task.data.get('audio')
             
             if audio_data:
                 print(f"[Controller] Playing Audio File Schedule...")
                 try:
                     # Remove header if present (data:audio/webm;base64,)
                     if "base64," in audio_data:
                         audio_data = audio_data.split("base64,")[1]
                     
                     import base64
                     decoded_audio = base64.b64decode(audio_data)
                     
                     # Save to temp file
                     temp_filename = f"temp_broadcast_{uuid.uuid4().hex}.wav" # Most pipes handle webm/wav
                     temp_path = os.path.join("system_sounds", temp_filename)
                     abs_temp = os.path.abspath(temp_path)
                     
                     with open(abs_temp, "wb") as f:
                         f.write(decoded_audio)
                                          # Play Intro -> Audio File
                     intro_path = os.path.join("system_sounds", "intro.mp3")
                     abs_intro = os.path.abspath(intro_path)
                     
                     audio_service.play_wav(abs_intro, abs_temp, zones=task.data.get('zones'))
                     
                     # Cleanup happens by next write or OS, but let's try to be clean 
                     # (Actually audio_service is async/threaded usually? 
                     # If _play_multizone blocks (it seems to for Linux), we can delete after.
                     # If Windows, it returns immediately. 
                     # Let's leave it for OS cleanup or future robust GC).
                     
                 except Exception as e:
                     print(f"[Controller] Failed to decode/play audio: {e}")
             
             else:
                 # Text TTS
                 msg = task.data.get('message', '')
                 if not msg: msg = "Scheduled Announcement."
                 
                 voice = task.data.get('voice', 'female') # Default to female
    
                 # UPDATED: Use chained playback (Intro -> Text) Non-Blocking
                 intro_path = os.path.join("system_sounds", "intro.mp3")
                 abs_intro = os.path.abspath(intro_path)
                 audio_service.play_announcement(abs_intro, msg, voice=voice, zones=task.data.get('zones'))
             
             # NOTIFICATION: Schedule Started
             notification_service.create(
                "Scheduled Announcement Started",
                f"Broadcast started...",
                type="success",
                target_user=task.data.get('user'),
                target_role="admin"
             )

            
        elif task.type == TaskType.TEXT:
            # FIX: Route sends 'content', not 'message'
            msg = task.data.get('content') or task.data.get('message', '')
            voice = task.data.get('voice', 'female') # Default to female
            
            if msg:
                zones = task.data.get('zones', [])
                if isinstance(zones, str):
                     zones = [z.strip() for z in zones.split(',')]
                     
                print(f"[Controller] Speaking Text: {msg} (Voice: {voice}) Zones: {zones}")
                # UPDATED: Use chained playback
                intro_path = os.path.join("system_sounds", "intro.mp3")
                abs_intro = os.path.abspath(intro_path)
                audio_service.play_announcement(abs_intro, msg, voice=voice, zones=zones)
                
                # NOTIFICATION: Text Broadcast Started
                notification_service.create(
                    "Live Text Announcement",
                    f"Now broadcasting text: {msg[:30]}...",
                    type="info",
                    target_user=task.data.get('user'),
                    target_role="admin"
                )
            else:
                print("[Controller] Error: Text task has no content/message to speak.")
                
        elif task.type == TaskType.BACKGROUND:
            # --- BACKGROUND MUSIC PLAYBACK ---
            filename = task.data.get('content')
            if filename:
                media_path = os.path.join("media", filename)
                abs_media = os.path.abspath(media_path)
                
                if os.path.exists(abs_media):
                    print(f"[Controller] Playing Background Music: {filename}")
                    
                    # Determine Start Offset
                    # 1. Check if Task Data has 'start_time' (explicit seek)
                    # 2. Otherwise use saved 'background_resume_time'
                    start_offset = task.data.get('start_time', self.background_resume_time)
                    print(f"  -> Offset: {start_offset}s")
                    
                    # Track when we actually started playing
                    self.background_play_start = datetime.now()
                    
                    # Async Playback on All Zones (or specified)
                    zones = task.data.get('zones', ['All Zones'])
                    if isinstance(zones, str): zones = [z.strip() for z in zones.split(',')]
                    audio_service.play_background_music(abs_media, zones=zones, start_time=start_offset)
                    
                    notification_service.create(
                        "Music Started",
                        f"Now playing: {filename}",
                        type="info",
                        target_user=task.data.get('user'),
                        target_role="admin"
                    )
                else:
                    print(f"[Controller] Error: Media file not found: {abs_media}")
            else:
                print("[Controller] Error: Background task missing content (filename).")

        elif task.type == TaskType.EMERGENCY:
             # UPDATED EMERGENCY SCRIPT
             script = ("Attention. This is an emergency alert. Please remain calm and follow the instructions carefully. "
                       "The situation is urgent. Stay tuned for further information.")
             
             # SYNC PLAYBACK: Blocks this thread until finished, keeping active_task in UI
             # targets ALSA Card 2 (Pi Speakers) via zones=['All Zones']
             # skip_stop=True allows siren to keep looping in background
             # UPDATED LOGIC: STOP SIREN WHILE SPEAKING
             # 1. Play Siren briefly (already started above)
             # Let it play for ~2.5 seconds (play "twice") before interrupting
             time.sleep(2.5)
             
             # 2. Stop Siren (implicitly via play_announcement, or explicitly)
             # We let play_announcement stop it (default behavior)
             
             # 3. Play Voice (Blocking)
             print("[Controller] Stopping Siren for Voice Announcement...")
             audio_service.play_announcement(None, script, voice='female', zones=['All Zones']) # skip_stop=False
             
             # 4. Resume Siren
             print("[Controller] Voice Finished. Resuming Siren...")
             audio_service.play_siren(zones=['All Zones'], volume=0.002)

             # --- AUTO-UNLOCK DEACTIVATION & VOLUME RAMP ---
             # Once the script is done, we clear current_task so frontend shows "DEACTIVATE"
             # but we keep emergency_mode=True so siren continues and logic stays locked.
             with self._lock:
                 # Only clear if it hasn't been stopped manually in the meantime
                 if self.current_task and self.current_task.id == task.id:
                     print("[Controller] Emergency Voice Finished. Ramping siren and unlocking deactivation.")
                     # Ramp siren volume to 0.8 over 5 seconds
                     audio_service.ramp_siren_volume(0.8, 5.0)
                     
                     self.current_task = None
                     self._update_firestore_state(None, Priority.EMERGENCY, 'EMERGENCY')
        # --- AUDIO OUTPUT END ---

    def _apply_queue_shift(self):
        """Shifts all queued items by the duration of the High Priority Interruption"""
        if self.pause_start_time:
            now = datetime.now()
            duration = now - self.pause_start_time
            print(f"[Controller] Applying Time Shift: +{duration}")
            
            batch = db.batch()
            updated_count = 0

            for task in self.queue:
                task.scheduled_time += duration
                
                # Update Firestore so UI reflects new time
                try:
                     ref = db.collection('schedules').document(task.id)
                     new_date = task.scheduled_time.strftime("%Y-%m-%d")
                     new_time = task.scheduled_time.strftime("%H:%M")
                     batch.update(ref, {'date': new_date, 'time': new_time})
                     updated_count += 1
                except ValueError:
                    pass # Skip if invalid ID/Doc

            # Sort again just in case (though relative order shouldn't change)
            self.queue.sort(key=lambda x: x.scheduled_time)
            
            if updated_count > 0:
                try:
                    batch.commit()
                    print(f"[Controller] Persisted shift for {updated_count} schedules")
                except Exception as e:
                    print(f"[Controller] Batch update failed: {e}")

            self.pause_start_time = None

    def _update_firestore_state(self, task, priority, mode):
        try:
            data = {
                'active_task': task.to_dict() if task else None,
                'priority': int(priority),
                'mode': mode,
                'timestamp': firestore.SERVER_TIMESTAMP
            }
            db.collection('system').document('state').set(data)
        except Exception as e:
            print(f"[Controller] DB Error: {e}")

        self.last_heartbeats: Dict[str, datetime] = {} # User -> Timestamp

    def register_heartbeat(self, user: str):
        with self._lock:
            self.last_heartbeats[user] = datetime.now()
            # print(f"[Controller] Heartbeat registered for: {user}")

    # --- SCHEDULER LOOP ---
    def _scheduler_loop(self):
        while self._running:
            time.sleep(1) # Tiick every 1s
            
            # --- HEARTBEAT CHECK ---
            if self.current_task and self.current_task.type in [TaskType.BACKGROUND, TaskType.VOICE]:
               # Only monitor Background/Voice tasks (Schedules run on their own)
               owner = self.current_task.data.get('user')
               if owner and owner != 'System':
                   last_beat = self.last_heartbeats.get(owner)
                   if last_beat:
                       seconds_since = (datetime.now() - last_beat).total_seconds()
                       if seconds_since > 15: # 15s Timeout
                           print(f"[Controller] Heartbeat Lost for {owner} ({seconds_since}s ago). Stopping session.")
                           # Force Stop from System
                           self.stop_session_task(owner)
                   # Note: If no heartbeat ever registered, we assume they are legacy/local? 
                   # Or we enforce it? Let's assume strict:
                   elif self.current_task.type == TaskType.BACKGROUND: # Only enforce for Music for now to play safe
                        # If just started, give grace period? 
                        created_ago = (datetime.now() - self.current_task.created_at).total_seconds()
                        if created_ago > 25: 
                             # STRICT KILL: If user has played music for 25s and NEVER sent a heartbeat, they are likely gone/zombie.
                             print(f"[Controller] Security: No heartbeat registered for {owner} (>25s). Killing zombie session.")
                             self.stop_session_task(owner)
            
            # --- OPTIMIZATION: PERIODIC CLEANUP (Every 24 Hours) ---
            if (datetime.now() - self.last_cleanup).total_seconds() > 86400:
                self._cleanup_old_data()
                self.last_cleanup = datetime.now()

            with self._lock:
                # 1. Check for Due Tasks
                now = datetime.now()
                candidates = [t for t in self.queue if t.scheduled_time <= now]
                
                if not candidates:
                    continue

                next_task = candidates[0]
                
                # 2. Priority Check
                # If system is busy with Higher or Equal priority, wait.
                if self.current_task and self.current_task.priority >= next_task.priority:
                    continue
                    
                # 3. Promote & Execute
                self.queue.remove(next_task)
                next_task.priority = Priority.SCHEDULE # Ensure it has correct priority
                
                print(f"[Scheduler] Promoting Schedule {next_task.id}")
                
                # Mark as Completed in DB (for the specific instance)
                try:
                    db.collection('schedules').document(next_task.id).update({'status': 'Completed'})
                    
                    # NOTIFICATION: Schedule Completed
                    notification_service.create(
                        "Scheduled Announcement Completed",
                        f"Your announcement '{next_task.data.get('message', '')[:20]}...' finished successfully.",
                        type="success",
                        target_user=next_task.data.get('user')
                    )
                except Exception as e:
                    print(f"[Scheduler] Failed to mark completed: {e}")

                # Preempt lower priority if needed
                if self.current_task:
                    self._preempt_current_task(next_task.priority)
                
                # Start
                # We need to call _start_task, but we are inside lock? 
                # _start_task assumes lock is held? No, _start_task updates internal state.
                # But request_playback calls it.
                # Here we are in scheduler loop, we should just run it.
                self._start_task(next_task)

                self._start_task(next_task)
                
                # NEW: RECURRENCE LOGIC (Daily/Weekly)
                self._handle_recurrence(next_task)

    def _handle_recurrence(self, task: Task):
        """Checks if task needs to repeat and schedules the next instance"""
        repeat = task.data.get('repeat', 'once').lower()
        if repeat == 'once':
            return
            
        print(f"[Scheduler] Processing Recurrence: {repeat}")
        
        # FIX: DRIFT PREVENTION
        # Instead of adding 24h to the 'current executing time' (which might be delayed),
        # we calculate the next date but force the Original Time.
        
        try:
            # 1. Get Original Time Metadata
            original_time_str = task.data.get('time') # e.g. "12:00"
            if not original_time_str:
                 # Fallback if missing
                 original_time_str = task.scheduled_time.strftime("%H:%M")

            # 2. Calculate Next Date
            current_date = task.scheduled_time.date()
            next_date = None
            
            if repeat == 'daily':
                next_date = current_date + timedelta(days=1)
            elif repeat == 'weekly':
                next_date = current_date + timedelta(weeks=1)

            if next_date:
                # 3. Combine Next Date + Original Time
                next_dt_str = f"{next_date.strftime('%Y-%m-%d')} {original_time_str}"
                next_time_obj = datetime.strptime(next_dt_str, "%Y-%m-%d %H:%M")
                
                # 4. Create New Task
                new_data = task.data.copy()
                new_data['date'] = next_date.strftime("%Y-%m-%d")
                new_data['time'] = original_time_str
                new_data['status'] = 'Pending'
                if 'id' in new_data: del new_data['id'] 
                
                # 5. Save & Queue
                _, new_ref = db.collection('schedules').add(new_data)
                new_id = new_ref.id
                print(f"[Scheduler] Created recurring instance: {new_id} for {new_data['date']} at {new_data['time']}")
                
                new_task = Task(
                    id=new_id,
                    type=TaskType.SCHEDULE,
                    priority=Priority.SCHEDULE,
                    data=new_data,
                    scheduled_time=next_time_obj
                )
                self._add_to_queue(new_task)
                
        except Exception as e:
            print(f"[Scheduler] Recurrence Failed: {e}")

    def _cleanup_old_data(self):
        """Optimization: Garbage Collect old data to keep DB lean"""
        print("[Controller] Running Daily Cleanup...")
        try:
             # 1. Delete Old Logs (> 7 Days)
             cutoff = datetime.now() - timedelta(days=7)
             logs = db.collection('logs').where('timestamp', '<', cutoff).limit(100).stream()
             batch = db.batch()
             count = 0
             for doc in logs:
                 batch.delete(doc.reference)
                 count += 1
             
             # 2. Delete Completed Schedules (> 7 Days)
             # Note: 'schedules' store strings for date/time usually, so verify format or query carefully.
             # Ideally we rely on status='Completed'. 
             # For simpler logic, we'll just check status for now, or skip if complex date parsing needed query-side.
             # Let's just do Logs for now to be safe from deleting future recurrents by accident.
             
             if count > 0:
                 batch.commit()
                 print(f"[Controller] Cleanup: Deleted {count} old log entries.")
             else:
                 print("[Controller] Cleanup: No old data to delete.")
                 
        except Exception as e:
            print(f"[Controller] Cleanup Failed: {e}")

# Global Instance
controller = PAController()

