# Filtr odległości

Ten filtr przepuszcza pakiet tylko wtedy, gdy jego zdekodowana pozycja mieści się w co najmniej jednej z zadanych stref.

Jak działa:

- można ustawić od 1 do 3 stref,
- każda strefa ma środek i promień,
- strefy działają w logice OR,
- jeśli nie zdefiniowano żadnej poprawnej strefy, filtr jest pomijany,
- jeśli pakiet nie ma dekodowalnej pozycji, filtr jest pomijany,
- dopiero pakiet z pozycją poza wszystkimi strefami zostaje odrzucony.

Kiedy używać:

- gdy chcesz ograniczyć ruch do wybranego obszaru,
- gdy chcesz zrobić lokalne reguły tylko dla określonej okolicy.

## Nawigacja

[Wróć do opisu Packet Flow](packet_routing_flow.pl.md)
