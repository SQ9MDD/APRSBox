# Application update

This panel checks the installed APRSBox version and, on supported installations, updates the application from the selected channel.

## Update channel

The channel identifies the source branch used for version checks and updates. A channel other than the stable channel can contain unfinished or incompatible changes; the warning in the panel remains visible whenever such a channel is selected.

`Save update channel` changes the source used by later checks and updates. It does not update the application by itself.

## Actions

- `Check version` compares the installed version with the selected channel and does not modify the installation.
- `Update application` fetches code from that channel, runs database initialization, and restarts `aprsbox-core` and `aprsbox-web` at the end.
- The GUI can temporarily lose connection while services restart. The progress dialog follows the background job and reconnects when possible.

## Docker installations

Inside Docker, version comparison is informational only and host-level update actions are disabled. Update APRSBox by pulling the required image and recreating the container with the deployment tool used by the installation.

Only administrators and operators can change the channel or start an update.
