# Task: Refine Notification System (Red Dot & Persistence)

- [ ] **Backend: Per-User Read Status**
    - [/] Update `NotificationService` to use `read_by` array. <!-- I'll do this next -->
    - [ ] Update `notifications.py` endpoint to `array_union` `read_by`.
- [ ] **Frontend: Unread Logic**
    - [ ] Update `AppContext.jsx`- [x] Investigate audio playback logic in both frontend and backend <!-- id: 0 -->
- [x] Improve audio sound clarity (Aggressive 0.85 Vol) <!-- id: 6 -->
- [x] Fix music restarting on new click <!-- id: 7 -->
- [x] Stabilize pause/play logic (Strict persistence) <!-- id: 8 -->
- [x] Remove redundant /start calls in frontend <!-- id: 11 -->
- [x] Implement backend idempotency for playback requests <!-- id: 12 -->
- [/] Fix real-time broadcast distortion (16kHz + 16k buffer) <!-- id: 13 -->
- [ ] Verify fixes on Raspberry Pi setup <!-- id: 4 -->
- [/] Push changes to GitHub <!-- id: 5 -->
- [ ] **Verification**
    - [ ] Verify "Clear All" persists (already implemented `cleared_by`, check logic).
    - [ ] Verify Red Dot appears for new items and disappears on open.
