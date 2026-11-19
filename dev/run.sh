#!/bin/sh
# Run the dashboard locally with auth disabled (DEV) against the repo's modules.
R=$(cd "$(dirname "$0")/.." && pwd)
UZ_WEB_DEV=1 UZ_WEB_PORT=${PORT:-18080} UZ_MOD_DIR=$R/rootfs/usr/local/lib/uz/settings \
UZ_UI_DIR=$R/rootfs/usr/local/share/uz/settings UZ_INDEX=$R/rootfs/usr/local/share/uz/index.html \
exec python3 -I $R/rootfs/usr/local/bin/uz-web
