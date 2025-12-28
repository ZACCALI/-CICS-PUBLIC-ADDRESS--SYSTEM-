from api.firebaseConfig import db, firestore_server_timestamp

class NotificationService:
    @staticmethod
    def create(title, message, type='info', target_user=None, target_role=None):
        """
        Creates a notification in Firestore.
        target_user: Specific username/uid
        target_role: 'admin' or 'user' (for broadcast alerts)
        """
        try:
            data = {
                "title": title,
                "message": message,
                "type": type, # info, success, warning, error
                "targetUser": target_user,
                "targetRole": target_role,
                "read_by": [],
                "cleared_by": [],
                "timestamp": firestore_server_timestamp()
            }
            # Add to 'notifications' collection
            db.collection("notifications").add(data)
            print(f"[Notification] Sent: {title} - {message}")
        except Exception as e:
            print(f"[Notification] Failed: {e}")

notification_service = NotificationService()
