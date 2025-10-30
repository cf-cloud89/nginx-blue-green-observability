# nginx blue/green alerts Runbook

This document explains what to do when you receive an alert from the Nginx Blue/Green proxy.

---

### 1. Alert: FAILOVER DETECTED
* **Message:** `FAILOVER DETECTED: Traffic has flipped from 'blue' to 'green'.`
* **What it Means:** The `blue` pool (primary) has failed its health check. Nginx has automatically and invisibly routed all traffic to the `green` pool (backup). The application is still **UP**, but it is running on its backup.
* **Your Action:**
    1.  **Investigate the primary pool.** The container has likely crashed or is unhealthy.
    2.  Check the container's logs:
        ```sh
        sudo docker logs app_blue
        ```
    3.  Look for crashes, `OutOfMemory` errors, or application-level exceptions.
    4.  Once the root cause is fixed and the `app_blue` container is stable, Nginx will automatically fail back (see next alert).

---

### 2. Alert: RECOVERY
* **Message:** `RECOVERY: Traffic has flipped from 'green' to 'blue'.`
* **What it Means:** The `blue` pool, which had previously failed, is now healthy again. Nginx has automatically detected this and routed traffic back to the primary pool.
* **Your Action:**
    1.  **Monitor.** This is a good alert. It means the system is self-healing.
    2.  You should already know *why* it failed (from the previous failover alert). This alert confirms the fix is working.

---

### 3. Alert: High Error Rate
* **Message:** `High upstream 5xx error rate detected: 15.50% over the last 200 requests...`
* **What it Means:** The application is **NOT** down, but it is failing. It's responding with 5xx (server-side) errors for many requests. This means a failover is *about* to happen, or is happening intermittently.
* **Your Action:**
    1.  **This is an application-level bug.** This is not a crash.
    2.  Check the application logs immediately for exceptions:
        ```sh
        sudo docker logs app_blue
        ```
    3.  If a bad deployment is the cause, prepare for a manual toggle. **Manually make `green` the primary pool** to stop the errors:
        * `nano .env` (Set `ACTIVE_POOL=green`)
        * `sudo docker compose up -d --force-recreate nginx_proxy`

---

### Planned Maintenance
To perform a planned manual toggle (e.g., to deploy a new version to Blue) without spamming Slack, you can enable Maintenance Mode.

1.  Edit your `.env` file and set `MAINTENANCE_MODE=true`.
2.  Restart the watcher to apply the change:
    ```sh
    sudo docker compose up -d --force-recreate alert_watcher
    ```
3.  Perform your maintenance. No alerts will be sent.
4.  **Remember to set `MAINTENANCE_MODE=false`** and restart the watcher again when you're done.