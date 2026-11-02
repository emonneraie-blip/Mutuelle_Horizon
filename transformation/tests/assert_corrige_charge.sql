-- Le corrigé doit correspondre aux données : sinon, les tests d'acceptation ne prouveraient rien.
{{ config(tags=['acceptation']) }}

select count(*) as fraudes_du_corrige
from {{ ref('fraud_answer_key') }} k
join {{ ref('slv_factures') }} f on f.id_demande = k.id_demande
having count(*) = 0
