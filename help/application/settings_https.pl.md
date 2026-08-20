# HTTPS

Ten panel przełącza interfejs WWW APRSBoxa z HTTP na HTTPS i zarządza plikami używanymi przez serwer.

## Przygotowanie plików

APRSBox wymaga pasującej pary:

- certyfikat serwera w formacie PEM: `aprsbox.crt`,
- klucz prywatny w formacie PEM: `aprsbox.key`,
- opcjonalny łańcuch CA: `aprsbox-ca-chain.crt`.

Pliki można przesłać z rozszerzeniami wskazanymi w formularzu. APRSBox zapisuje je pod stałymi nazwami w `/opt/aprsbox/data/ssl`. Certyfikat i klucz są sprawdzane jako para przed udostępnieniem przełącznika HTTPS.

Generator lokalnego PKI oraz pobieranie Root CA pozostają obecnie nieaktywne. Certyfikat trzeba na razie przygotować za pomocą zewnętrznego CA lub własnego narzędzia PKI, a następnie przesłać w tym panelu.

## Nazwa mDNS

Jeżeli host publikuje nazwę przez mDNS, APRSBox może być dostępny na przykład jako `https://aprsbox.local`. Działa to tylko wtedy, gdy mDNS jest uruchomione w systemie i obsługiwane przez urządzenie klienckie.

Certyfikat musi zawierać używaną nazwę, na przykład `DNS:aprsbox.local`, w rozszerzeniu Subject Alternative Name (SAN). Sama wartość Common Name nie wystarcza we współczesnych przeglądarkach. Certyfikaty publiczne zwykle nie są wystawiane dla nazw `.local`, dlatego w takiej sieci najczęściej używa się własnego CA i instaluje jego certyfikat główny jako zaufany na urządzeniach klienckich.

## Certyfikat dla adresu IP

Jeżeli APRSBox jest otwierany jako `https://192.168.1.20`, dokładny adres musi znaleźć się w SAN jako wpis typu IP, na przykład `IP:192.168.1.20`. Wpis `DNS:192.168.1.20` nie jest równoważny wpisowi IP.

Przy adresie przydzielanym przez DHCP warto skonfigurować rezerwację albo stały adres. Po zmianie adresu certyfikat przestanie pasować i trzeba będzie wystawić nowy. Jeden certyfikat może zawierać kilka nazw DNS i kilka adresów IP.

## Włączenie HTTPS

1. Prześlij certyfikat i pasujący klucz prywatny. Łańcuch CA jest opcjonalny.
2. Sprawdź zielone ikony przy plikach.
3. Zaznacz `Włącz HTTPS`.
4. Kliknij `Zapisz i uruchom ponownie` i poczekaj na restart usług.

Po włączeniu APRSBox nasłuchuje HTTPS na porcie `443`. Zwykły serwer HTTP na porcie `8000` jest wyłączony, a port `80` przekierowuje żądania do HTTPS kodem `308`.

Przy certyfikacie z własnego CA przeglądarka może pokazać ostrzeżenie, dopóki Root CA nie zostanie dodany do zaufanych certyfikatów urządzenia.

## Usuwanie plików

Certyfikatu serwera ani klucza prywatnego nie można usunąć, gdy HTTPS jest aktywny. Najpierw wyłącz HTTPS i poczekaj na powrót interfejsu pod `http://adres:8000`. Łańcuch CA można pobrać lub usunąć niezależnie.
