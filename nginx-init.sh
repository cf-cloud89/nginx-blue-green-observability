#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Install gettext-utils, which provides the 'envsubst' command
apk add --no-cache gettext

echo "Starting Nginx's nginx-init script..."
echo "Active pool is: $ACTIVE_POOL"

# 1. Logic to set status variables based on ACTIVE_POOL
if [ "$ACTIVE_POOL" = "green" ]; then
    echo "Setting GREEN as primary, BLUE as backup."
    export BLUE_STATUS="backup"
    export GREEN_STATUS=""
else
    echo "Setting BLUE as primary, GREEN as backup."
    export BLUE_STATUS=""
    export GREEN_STATUS="backup"
fi

# 2. Use envsubst to substitute variables in the template
#    and create the final config file for Nginx to use.
envsubst '$PORT $BLUE_STATUS $GREEN_STATUS' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf

echo "Nginx config generated:"
cat /etc/nginx/conf.d/default.conf
echo "------------------------"

# 3. Start the Nginx server in the foreground.
#    This is the main command that keeps the container running.
echo "Starting Nginx..."
nginx -g 'daemon off;'
