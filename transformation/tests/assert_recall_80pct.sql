-- Test d'acceptation : au moins 80 % des fraudes déjà observables sont dans la liste à contrôler.
-- Une F2 reçue depuis moins de 2 jours n'est pas encore observable : elle ne compte pas.
{{ config(tags=['acceptation']) }}

with lot as (
    select max(batch_date) as batch_date from {{ ref('mart_factures_a_controler') }}
),
attendues as (
    select k.id_demande
    from {{ ref('fraud_answer_key') }} k
    cross join lot
    where k.date_reception <= lot.batch_date
      and (k.fraud_type <> 'F2_SANS_DECOMPTE_NOEMIE' or k.date_reception <= lot.batch_date - 2)
),
mesure as (
    select
        count(*) as attendues,
        sum(case when m.decision = 'A_CONTROLER' then 1 else 0 end) as trouvees
    from attendues a
    left join {{ ref('mart_factures_a_controler') }} m on m.id_demande = a.id_demande
)
select *
from mesure
where attendues > 0 and trouvees < 0.8 * attendues
