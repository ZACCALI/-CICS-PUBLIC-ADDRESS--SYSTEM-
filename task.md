# Task: Refine Notification System (Red Dot & Persistence)

- [ ] **Backend: Per-User Read Status**
    - [/] Update `NotificationService` to use `read_by` array. <!-- I'll do this next -->
    - [ ] Update `notifications.py` endpoint to `array_union` `read_by`.
- [ ] **Frontend: Unread Logic**
    - [ ] Update `AppContext.jsx` to calculate `unread` based on `!read_by.includes(uid)`.
- [ ] **Verification**
    - [ ] Verify "Clear All" persists (already implemented `cleared_by`, check logic).
    - [ ] Verify Red Dot appears for new items and disappears on open.
