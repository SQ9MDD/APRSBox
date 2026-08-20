# HTTPS

This panel switches the APRSBox web interface from HTTP to HTTPS and manages the server certificate files.

## Required files

- PEM server certificate: `aprsbox.crt`
- matching PEM private key: `aprsbox.key`
- optional CA chain: `aprsbox-ca-chain.crt`

APRSBox stores these files in `/opt/aprsbox/data/ssl` and checks the certificate and key as a pair. Local PKI generation and Root CA download are currently disabled, so create the files with an external CA or PKI tool and upload them here.

## mDNS and IP addresses

For an mDNS address such as `https://aprsbox.local`, the certificate SAN must contain `DNS:aprsbox.local`. mDNS must also be active on the host and supported by the client.

For an address such as `https://192.168.1.20`, SAN must contain an IP entry such as `IP:192.168.1.20`. A DNS entry containing the same digits is not equivalent. Use a DHCP reservation or static address so that the certificate remains valid. One certificate can contain multiple DNS names and IP addresses.

Private CAs are normally used for `.local` names and private addresses. Install the corresponding Root CA as trusted on each client device.

## Enabling HTTPS

Upload the matching certificate and key, select `Enable HTTPS`, then select `Save and restart`. HTTPS uses port `443`, HTTP on port `8000` is disabled, and port `80` redirects to HTTPS with status `308`.

The server certificate and private key cannot be removed while HTTPS is active. Disable HTTPS first and wait for `http://address:8000`. The CA chain can be downloaded or removed independently.
