# Task: Refine Notification System (Red Dot & Persistence)

- [ ] **Backend: Per-User Read Status**
    - [/] Update `NotificationService` to use `read_by` array. <!-- I'll do this next -->
    - [ ] Update `notifications.py` endpoint to `array_union` `read_by`.
- [ ] **Frontend: Unread Logic**
    - [ ] Update `AppContext.jsx`- [x] Investigate audio playback logic in both frontend and backend <!-- id: 0 -->
- [x] Fix auto-pause loop issue <!-- id: 1 -->
- [x] Fix seeking issue (clicking on timeline) <!-- id: 2 -->
- [x] Fix interruption resume logic <!-- id: 3 -->
- [/] Verify fixes on Raspberry Pi setup (simulated or logic-based) <!-- id: 4 -->
- [/] Push changes to GitHub <!-- id: 5 -->
- [ ] **Verification**
    - [ ] Verify "Clear All" persists (already implemented `cleared_by`, check logic).
    - [ ] Verify Red Dot appears for new items and disappears on open.
