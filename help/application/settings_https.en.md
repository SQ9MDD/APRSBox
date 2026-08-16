# HTTPS

This panel switches the APRSBox web interface from HTTP to HTTPS and manages the files used by the server.

## Preparing the files

APRSBox requires a matching pair:

- a PEM server certificate stored as `aprsbox.crt`,
- a PEM private key stored as `aprsbox.key`,
- an optional CA chain stored as `aprsbox-ca-chain.crt`.

Files can be uploaded with the extensions shown in the form. APRSBox stores them under fixed names in `/opt/aprsbox/data/ssl`. The certificate and private key are checked as a pair before HTTPS can be enabled.

Local PKI generation and Root CA download are currently disabled. For now, create the certificate with an external CA or your own PKI tool and upload it in this panel.

## mDNS hostname

If the host advertises a name through mDNS, APRSBox can be available at an address such as `https://aprsbox.local`. This requires mDNS to be running on the host and supported by the client device.

The certificate must contain the name being used, for example `DNS:aprsbox.local`, in its Subject Alternative Name (SAN). A Common Name alone is not sufficient for modern browsers. Public certificate authorities generally do not issue certificates for `.local` names, so a private CA is normally used and its Root CA is installed as trusted on client devices.

## Certificates for IP addresses

When APRSBox is opened as `https://192.168.1.20`, that exact address must appear in SAN as an IP entry, for example `IP:192.168.1.20`. A `DNS:192.168.1.20` entry is not equivalent to an IP entry.

For an address assigned by DHCP, configure a reservation or a static address. If the address changes, the certificate no longer matches and must be reissued. One certificate can contain multiple DNS names and multiple IP addresses.

## Enabling HTTPS

1. Upload the certificate and matching private key. The CA chain is optional.
2. Check the green file status icons.
3. Select `Enable HTTPS`.
4. Select `Save and restart` and wait for the services to restart.

When enabled, APRSBox listens for HTTPS on port `443`. The regular HTTP server on port `8000` is disabled, while port `80` redirects requests to HTTPS with status `308`.

With a certificate issued by a private CA, the browser can display a warning until the Root CA is installed as trusted on that device.

## Removing files

The server certificate and private key cannot be removed while HTTPS is active. Disable HTTPS first and wait for the interface to return at `http://address:8000`. The CA chain can be downloaded or removed independently.
