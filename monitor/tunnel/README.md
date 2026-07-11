# Tunnel (server machine)

Public HTTPS for the dashboard is configured on a **server or edge machine**, not on the bot PC.

The bot PC runs Sentinel on port **8787**. Point your tunnel or reverse proxy at `http://<bot-pc-ip>:8787`.

See [README.md](../README.md) for architecture and first-time install.
