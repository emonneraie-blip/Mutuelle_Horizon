-- Les chiffres agrégés de la direction, par lot. Seule table visible par ANALYST_ROLE.
{{ config(grants={'select': ['REDGRAVE_GRADER', 'ANALYST_ROLE']}) }}

select
    batch_date,
    count(*)                                                      as nb_factures,
    sum(case when decision = 'A_CONTROLER' then 1 else 0 end)     as nb_a_controler,
    sum(case when decision = 'EN_ATTENTE' then 1 else 0 end)      as nb_en_attente,
    sum(montant_demande_amc)                                      as montant_demande,
    sum(montant_a_risque)                                         as montant_bloque,
    round(sum(montant_a_risque) / nullif(sum(montant_demande_amc), 0), 4) as part_bloquee,
    current_timestamp                                             as calcule_le
from {{ ref('mart_factures_a_controler') }}
group by batch_date
