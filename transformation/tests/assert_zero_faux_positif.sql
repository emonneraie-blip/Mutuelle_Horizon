-- Test d'acceptation : aucune facture honnête dans la liste à contrôler.
{{ config(tags=['acceptation']) }}

select m.id_demande, m.regles_declenchees
from {{ ref('mart_factures_a_controler') }} m
left join {{ ref('fraud_answer_key') }} k on k.id_demande = m.id_demande
where m.decision = 'A_CONTROLER' and k.id_demande is null
