-- Si plus de 15 % des factures sont rejetées, le problème vient de la source : on arrête tout.
with volumes as (
    select
        (select count(*) from {{ ref('slv_factures_quarantaine') }}) as rejetees,
        (select count(*) from {{ ref('slv_factures') }})             as gardees
)
select *
from volumes
where rejetees > 0.15 * (rejetees + gardees)
