# Task: Refine Notification System (Red Dot & Persistence)

- [ ] **Backend: Per-User Read Status**
    - [/] Update `NotificationService` to use `read_by` array. <!-- I'll do this next -->
    - [ ] Update `notifications.py` endpoint to `array_union` `read_by`.
- [ ] **Frontend: Unread Logic**
    - [ ] Update `AppContext.jsx`- [x] Investigate audio playback logic in both frontend and backend <!-- id: 0 -->
- [x] Improve audio sound clarity (Aggressive 0.85 Vol) <!-- id: 6 -->
- [x] Fix music restarting on new click <!-- id: 7 -->
- [x] Fix real-time broadcast distortion (initial attempt) <!-- id: 13 -->
- [x] Implement persistent streaming pipe in AudioService <!-- id: 14 -->
- [x] Fix mediaStreamRef error in RealTime.jsx <!-- id: 15 -->
- [x] Verify fixes on Raspberry Pi setup <!-- id: 4 -->
- [x] Push changes to GitHub <!-- id: 5 -->
- [x] Fix remote backend connection (CORS & startup script) <!-- id: 16 -->
- [x] Implement Heartbeat for 100% reliable Audio Stop <!-- id: 17 -->
- [ ] **Verification**
    - [ ] Verify "Clear All" persists (already implemented `cleared_by`, check logic).
    - [ ] Verify Red Dot appears for new items and disappears on open.
