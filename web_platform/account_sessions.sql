-- Private read-only projection for validating already signature-checked JWTs.
-- Intentionally owner-executed, with no direct application access to Auth.
-- Contains no email, password, refresh token or user-editable metadata.
CREATE OR REPLACE VIEW auction_private.active_account_sessions AS
SELECT s.id AS session_id,s.user_id AS auth_subject
FROM auth.sessions s JOIN auth.users u ON u.id=s.user_id
WHERE (s.not_after IS NULL OR s.not_after>now())
  AND u.email_confirmed_at IS NOT NULL AND u.is_anonymous IS NOT TRUE
  AND u.deleted_at IS NULL AND (u.banned_until IS NULL OR u.banned_until<=now());
REVOKE ALL ON auction_private.active_account_sessions FROM PUBLIC,anon,authenticated,auction_api;
GRANT SELECT ON auction_private.active_account_sessions TO auction_api;
