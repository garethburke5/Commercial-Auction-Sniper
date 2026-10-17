-- Private, narrowly projected Auth lookup for opted-in delivery only.
-- Intentionally owner-executed: the application has no auth.users privileges.
CREATE OR REPLACE VIEW auction_private.alert_recipients AS
SELECT p.user_id,u.email
FROM auction_private.alert_preferences p
JOIN auth.users u ON u.id::text=p.auth_subject
WHERE p.enabled=1 AND p.email=u.email
  AND u.email_confirmed_at IS NOT NULL AND u.is_anonymous IS NOT TRUE
  AND u.deleted_at IS NULL AND (u.banned_until IS NULL OR u.banned_until<=now());
REVOKE ALL ON auction_private.alert_recipients FROM PUBLIC,anon,authenticated,auction_api;
GRANT SELECT ON auction_private.alert_recipients TO auction_api;
