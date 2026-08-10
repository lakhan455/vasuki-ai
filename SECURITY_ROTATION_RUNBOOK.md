# Vasuki AI Secret Rotation Runbook

1. Open `/security` and note the current fingerprint.
2. Create a new credential in the provider dashboard. Never paste private secrets into chat, source control, screenshots, tickets or logs.
3. Replace the corresponding environment variable in Render.
4. Redeploy Phase 6 and verify `/health/v9-phase6`.
5. Test the provider feature, then revoke the old credential.
6. In `/security`, choose the secret and enter the old fingerprint. Vasuki verifies the running fingerprint changed and records the rotation.

Changing a VAPID key pair invalidates existing browser Push subscriptions; users may need to enable notifications again.
