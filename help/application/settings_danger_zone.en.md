# Danger zone

These actions affect running services or the entire host. They are available only to administrators and operators and are disabled inside Docker.

## Restart services

Restarts `aprsbox-core` and `aprsbox-web`. Radio and web processing pause during the restart, and the browser can briefly lose connection.

## Reboot host

Reboots the operating system. All APRSBox services and remote access are interrupted. The confirmation dialog requires the exact text `REBOOT`.

## Power off host

Shuts down the operating system. Remote access is interrupted and physical or out-of-band access can be required to power the host on again. The confirmation dialog requires the exact text `POWER OFF`.

In Docker, restart or recreate the container through Docker or the deployment platform instead of using these host actions.
