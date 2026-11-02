-- Règle métier : aucune facture avec un montant négatif ne doit atteindre silver.
select id_demande, montant_total, montant_demande_amc
from {{ ref('slv_factures') }}
where montant_total < 0 or montant_demande_amc < 0
