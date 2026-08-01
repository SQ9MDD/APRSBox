# Strefa niebezpieczna

Te akcje wpływają na działające usługi albo cały host. Są dostępne tylko dla administratora i operatora oraz wyłączone wewnątrz Dockera.

## Restart usług

Restartuje `aprsbox-core` i `aprsbox-web`. Obsługa radia i WWW zatrzyma się na czas restartu, a przeglądarka może chwilowo stracić połączenie.

## Restart hosta

Restartuje system operacyjny. Wszystkie usługi APRSBox i dostęp zdalny zostaną przerwane. Okno potwierdzenia wymaga dokładnego tekstu `REBOOT`.

## Wyłączenie hosta

Wyłącza system operacyjny. Dostęp zdalny zostanie przerwany, a ponowne uruchomienie może wymagać dostępu fizycznego albo konsoli out-of-band. Okno potwierdzenia wymaga dokładnego tekstu `POWER OFF`.

W Dockerze należy zrestartować albo odtworzyć kontener przez Docker lub platformę wdrożeniową zamiast używać tych akcji hosta.
