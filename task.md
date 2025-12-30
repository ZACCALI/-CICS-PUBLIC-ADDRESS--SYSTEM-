# Task: Refine Notification System (Red Dot & Persistence)

- [ ] **Backend: Per-User Read Status**
    - [/] Update `NotificationService` to use `read_by` array. <!-- I'll do this next -->
    - [ ] Update `notifications.py` endpoint to `array_union` `read_by`.
- [ ] **Frontend: Unread Logic**
    - [ ] Update `AppContext.jsx`- [x] Investigate audio playback logic in both frontend and backend <!-- id: 0 -->
- [x] Improve audio sound clarity (initial fix) <!-- id: 6 -->
- [x] Fix music restarting on new click (initial fix) <!-- id: 7 -->
- [x] Stabilize pause/play logic (initial fix) <!-- id: 8 -->
- [/] Aggressive volume reduction (0.85) for clarity <!-- id: 9 -->
- [/] Strengthening "Pause" persistence <!-- id: 10 -->
- [ ] Verify fixes on Raspberry Pi setup <!-- id: 4 -->
- [ ] Push changes to GitHub <!-- id: 5 -->
- [ ] **Verification**
    - [ ] Verify "Clear All" persists (already implemented `cleared_by`, check logic).
    - [ ] Verify Red Dot appears for new items and disappears on open.
