# Schedule Announcement System - Backend Logic Analysis

This document outlines the complete lifecycle, logic, and architecture behind the Schedule Announcement System in the backend.

## 1. Core Architecture

The scheduling system is built on a **Priority Queue Controller** pattern.
- **Queue**: A time-sorted list of tasks waiting to be executed.
- **Controller (`PAController`)**: A singleton class that manages the queue, handles interruptions, and controls audio playback.
- **Scheduler Loop**: A background thread that checks every second for tasks that are due.

## 2. The Logic Flow

### A. Creation & Queueing
When a user creates a schedule (e.g., "Lunch Break" at 12:00 PM):
1.  **Validation**: Backend checks integrity (date/time format).
2.  **Conflict Check**: Queries Firestore. If a "Pending" schedule already exists for that exact Date & Time, it rejects the request (Time Slot Busy).
3.  **Persistence**: Saves the schedule to Firestore (`schedules` collection) with `status: 'Pending'`.
4.  **InMemory Queue**: The schedule is immediately loaded into the Controller's RAM queue and sorted by time.

### B. Execution (The "Heartbeat")
The `_scheduler_loop` runs every 1 second:
1.  **Check**: Is the first item in the queue due? (`scheduled_time <= now`)
2.  **Busy Check**: Is the system currently playing something of **Higher Priority**?
    - If **Yes**: Wait. (The schedule effectively gets delayed/shifted).
    - If **No**: Proceed.
3.  **Promote**: 
    - Remove from Queue.
    - Set Firestore status to `Completed`.
    - **Play Audio**.
4.  **Recurrence**: Trigger the "Auto-Increment" logic for Daily/Weekly tasks.

---

## 3. Scenarios & Behavior

### Scenario 1: "Once"
*   **User sets**: Today at 2:00 PM.
*   **Logic**:
    1.  At 2:00 PM, system wakes up.
    2.  Plays announcement.
    3.  Marks document as `Completed`.
    4.  **End**. No new tasks checks created.

### Scenario 2: "Daily" (Auto-Increment)
*   **User sets**: Daily at 8:00 AM.
*   **Logic**:
    1.  **Day 1 @ 8:00 AM**: System plays the announcement.
    2.  **Recurrence Trigger**: The system detects `repeat: 'daily'`.
    3.  **Calculation**:
        - It takes the **Original Time** (8:00 AM).
        - It takes **Current Date + 1 Day**.
    4.  **New Creation**: It creates a **BRAND NEW** schedule entry in Firestore for **Tomorrow @ 8:00 AM**.
    5.  **Queue**: This new task is added to the waiting queue.
    6.  **Result**: You now have a record of the *completed* task for today, and a *pending* task for tomorrow.

### Scenario 3: "Weekly"
*   **User sets**: Mondays at 9:00 AM.
*   **Logic**: 
    - Identical to Daily, but adds **7 Days** to the date.
    - Creates a new entry for Next Monday @ 9:00 AM.

---

## 4. Conflict & Interruption Handling

### Scenario A: Interruption "While Playing"
*   **Situation**: A Schedule is currently playing audio. An **Emergency** or **Live Mic Announcement** starts.
*   **Logic**:
    1.  **Preemption**: The Controller detects a higher priority request (Emergency > Realtime > Schedule).
    2.  **Soft Stop**: The Schedule is stopped immediately.
    3.  **Re-Queue**: The Schedule is set to `status: 'INTERRUPTED'` and placed back at the **front** of the queue.
    4.  **Result**: As soon as the Emergency/Mic ends, the Schedule will immediately try to play again.

### Scenario B: Interruption "Before Playing" (Time Shift)
*   **Situation**: A Schedule is set for 10:00 AM. At 9:59 AM, the Principal starts a 5-minute speech (ends 10:04 AM).
*   **Logic**:
    1.  **Busy Wait**: At 10:00 AM, the Scheduler sees the system is busy. It waits.
    2.  **Time Shift**: The Controller tracks how long the system was busy (5 minutes).
    3.  **Adjustment**: When the speech ends at 10:04 AM:
        - The Controller **ADDs 5 minutes** to the scheduled time of *everything* in the queue.
        - The 10:00 AM schedule effectively becomes a 10:05 AM schedule.
        - It updates Firestore with the new time (persisting the delay).
    4.  **Play**: The schedule plays at 10:05 AM.

### Critical: Does it return to the "Original Time"?
**YES.**
Even if today's "Daily 8:00 AM" announcement was delayed to 8:15 AM due to an emergency:
1.  The system identifies the task was *originally* for 8:00 AM (stored in metadata).
2.  When calculating the Next Occurrence (`_handle_recurrence`):
    - It ignores the actual played time (8:15 AM).
    - It uses the **Original Time (8:00 AM)**.
3.  **Result**: Tomorrow's schedule is created for **8:00 AM**, not 8:15 AM. The drift corrects itself automatically.

---

## 5. Technical Summary Table

| Feature | Implementation Logic |
| :--- | :--- |
| **Storage** | Firestore (`schedules` collection). |
| **Execution** | Python `threading` + Priority Queue (InMemory). |
| **Conflict** | `409 Conflict` if specific Time checks match a 'Pending' doc. |
| **Recurrence** | "Cloning" logic. Executes Task A -> Creates Task B (for tomorrow). |
| **Interruption** | `Preemption` (Pause & Re-queue) + `Time Shift` (Delay future tasks). |
| **Drift** | **Self-Correcting**. Uses stored `time` string ("08:00") rather than execution timestamp. |
