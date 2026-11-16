-- Verificare pe baza de date reala (data\efactura.db), cu orice program care citeste SQLite.
-- Nu schimba nimic.

-- 1. Facturi emise de un client catre alt client din lista: este salvata si copia cumparatorului?
--    copia_cumparatorului = 0 la un cumparator pentru care ati descarcat acele zile inseamna ca
--    ANAF foloseste acelasi id pentru amandoua, iar programul a pastrat doar una.
SELECT s.cui AS vanzator, s.customer_cui AS cumparator, s.invoice_number AS factura,
       s.invoice_issue_date AS data, s.id AS id_la_vanzator,
       (SELECT COUNT(*) FROM messages r
         WHERE r.cui = s.customer_cui AND r.id_solicitare = s.id_solicitare
           AND r.message_type LIKE 'FACTURA PRIMITA%') AS copia_cumparatorului
FROM messages s
WHERE s.message_type LIKE 'FACTURA TRIMISA%'
  AND s.customer_cui IN (SELECT cui FROM clients)
ORDER BY s.invoice_issue_date DESC;

-- 2. Aceeasi incarcare (id_solicitare) salvata de mai multe ori: sub id-uri diferite sau nu?
SELECT id_solicitare, COUNT(*) AS mesaje, COUNT(DISTINCT id) AS id_uri_diferite,
       GROUP_CONCAT(cui || ' ' || message_type, ' | ') AS unde
FROM messages
WHERE id_solicitare IS NOT NULL AND message_type LIKE 'FACTURA%'
GROUP BY id_solicitare HAVING COUNT(*) > 1;
