# Blue/Green Deployment with Nginx (Observability & Alerting)

This setup includes a lightweight Python `alert_watcher` service that tails Nginx logs to provide real-time Slack alerts for failovers and high error rates.

## File Structure

* **`docker-compose.yml`**: Defines and runs all four services: `app_blue`, `app_green`, `nginx_proxy`, and `alert_watcher`. It's responsible for orchestrating the network and the new `nginx-logs` shared volume.

* **`nginx.conf.template`**: The Nginx configuration. It defines a custom JSON log format (`json_logs`) that captures detailed upstream data and writes it to the shared log file.

* **`nginx-init.sh`**: The Nginx startup script. It deletes the default log *stream* and create a *real* `access.log` file, which is required for the Python script to be able to "tail" it.

* **`watcher.py`**: The heart of the project. A Python "sidecar" script that runs in its own container, continuously reads the `access.log` file, and maintains the state of the system (current pool, error rate) to send alerts to Slack.

* **`requirements.txt`**: Lists the single Python dependency (`requests`) needed by `watcher.py` to send HTTP POST requests to the Slack webhook.

* **`.env.example`**: A template file that lists all required environment variables, including `SLACK_WEBHOOK_URL`, `ERROR_RATE_THRESHOLD`, and other watcher settings.

* **`runbook.md`**: An operator's guide. It explains what each Slack alert means and provides clear, actionable steps for an engineer to take when a failover or error rate alert is received.

### Setup Steps

These instructions assume you are running on a remote cloud server (e.g., AWS EC2).

1.  **SSH into the Cloud Server and Clone the Repository**
    ```sh
    ssh -i ~/.ssh/[your-key-pair] username@[YOUR-IP-ADDRESS/HOSTNAME]
    git clone https://github.com/cf-cloud89/nginx-blue-green-observability.git
    cd your-repo-name
    ```

2.  **Install Git, Docker, and Docker Compose**
    You must have Docker and Docker Compose installed. On modern Linux systems, this is often installed as a Docker plugin.
    * Follow the [official Docker install instructions](https://docs.docker.com/engine/install/) for your Linux distribution.
    * Ensure you install the `docker-compose-plugin` (or `docker compose`).
    * Add your user to the `docker` group to avoid using `sudo` for every command:
        ```sh
        sudo usermod -aG docker $USER
        ```
    * **Important:** You must log out and log back in for this change to take effect.

3.  **Get a Slack Webhook:** Follow the [official Slack guide](https://api.slack.com/messaging/webhooks) to create an "Incoming Webhook" URL.

4.  **Create `.env`:** Copy `.env.example` to `.env`.

5.  **Edit `.env`:** Paste your Slack Webhook URL into `SLACK_WEBHOOK_URL="..."`.

6.  **Make Init Script Executable:**
    The `nginx-init.sh` script must have execute permissions to run inside the container.

    ```sh
    chmod +x nginx-init.sh
    ```

### How to Test

1.  **Start the System:**
    * This will start 4 containers: blue, green, nginx, and the watcher
    * Run Docker Compose in detached (`-d`) mode. (Use `sudo` if you didn't add your user to the `docker` group in no2 of the **Setup Steps**).
    ```sh
    sudo docker compose up -d
    ```

2.  **Firewall Prerequisite**
Before you can test, you must **open ports** in your cloud provider's firewall (e.g., AWS Security Group, GCP Firewall).

You need to allow inbound TCP traffic on the following ports:
* `8080` (for the Nginx proxy)
* `8081` (for the Blue app's chaos endpoint)
* `8082` (for the Green app's chaos endpoint)

3.  **Verify Nginx Logs:**
    * First, send a test request: `curl http://[YOUR_SERVER_IP]:8080/version`
    * Now, check the Nginx logs. You should see the new JSON format.
    * ```sh
        sudo docker logs nginx_proxy
        ```
    * Look for the `access_log` line at the very bottom. It will be a long JSON string. (You can also `cat` the file inside the watcher: `sudo docker exec alert_watcher cat /var/log/nginx/access.log`).

4.  **Test 1: Failover Alert**
    * **Induce Chaos:**
        ```sh
        curl -X POST http://[YOUR_SERVER_IP]:8081/chaos/start?mode=error
        ```
    * **Send a request:**
        ```sh
        curl http://[YOUR_SERVER_IP]:8080/version
        ```
    * **Check Slack:** Within seconds, you should receive a **"FAILOVER DETECTED"** alert.
    * **Test Recovery:**
        ```sh
        curl -X POST http://[YOUR_SERVER_IP]:8081/chaos/stop
        ```
    * Wait ~5 seconds (for `fail_timeout` + buffer), then send another request:
        ```sh
        curl http://[YOUR_SERVER_IP]:8080/version
        ```
    * **Check Slack:** You should receive a **"RECOVERY"** alert.

5.  **Test 2: High Error Rate Alert**
    * This alert requires filling the 200-request window.
    * **Induce Chaos (again):**
        ```sh
        curl -X POST http://[YOUR_SERVER_IP]:8081/chaos/start?mode=error
        ```
    * **Run this loop** from your terminal to quickly send > 200 requests. (This will take a few seconds):
        ```sh
        for i in {1..250}; do curl -s -o /dev/null http://[YOUR_SERVER_IP]:8080/; done
        ```
    * **Check Slack:** The watcher's log window is now full of 5xx errors. You should receive a **"High Error Rate"** alert.
    * **Clean up:**
        ```sh
        curl -X POST http://[YOUR_SERVER_IP]:8081/chaos/stop
        ```