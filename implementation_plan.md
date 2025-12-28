# Implementation Plan - Refined Notification System

## Goal
Modify the notification system to support per-user "Clearing" of notifications (even shared ones) and remove the "Mark as Read" feature.

## Proposed Changes

### Backend (`backend/api/routes/notifications.py`)

#### [MODIFY] `delete_notification`
- **Logic Change**: Rename/Refactor to support "Clearing".
- **Shared Notifications**: If `targetRole` exists, append UID to `cleared_by` array.
- **Personal Notifications**: If `targetUser` exists, delete document.

#### [NEW] `mark_all_read` (Batch)
- **Endpoint**: `PUT /notifications/read-all`
- **Logic**: update `read: true` for all notifications targetting current user (or shared). 
- *Alternatively*: just use the existing `mark_as_read` in a loop (simpler for MVP).
- **Trigger**: Called when User clicks the Bell Icon.

### Frontend (`frontend-react/`)

#### [MODIFY] `src/context/AppContext.jsx`
- **Timestamp**: Ensure `notification` objects have a properly formatted `timeAgo` string (e.g. "5 mins ago") derived from Firestore timestamp.
- **Badge Logic**: 
    - Badge is visible if `notifications.some(n => !n.read)`.
    - **Action**: `markAllAsRead` is called automatically when the Notification Dropdown is opened.

#### [MODIFY] `src/components/common/Header.jsx`
- **UI**: 
    - Display the `timeAgo` in the notification item.
    - Remove "Mark as read" button.
    - Add "Unread Indicator" (Red Dot) on Bell Icon.
    - On Click (Open Dropdown) -> Call `markAllAsRead` -> Badge disappears.

## Verification Plan
1.  **Shared Test**: Create a System Notification (e.g., Device Online).
    - User A "Clears" it. It should disappear for User A.
    - User B logs in. It should STILL be visible for User B.
2.  **Personal Test**: Create a user-specific notification.
    - User "Clears" it. It should be deleted from DB.
