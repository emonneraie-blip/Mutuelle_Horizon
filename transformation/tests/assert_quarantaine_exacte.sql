-- Test d'acceptation : la quarantaine contient exactement les lignes attendues, avec le bon code.
-- Chaque ligne renvoyée est un écart : une ligne manquante, une ligne en trop ou un mauvais code.
{{ config(tags=['acceptation']) }}

with lot as (
    select {{ batch_date() }} as batch_date
),
attendues as (
    select k.id_demande, k.reason
    from {{ ref('quarantine_key') }} k
    cross join lot
    where k.date_reception <= lot.batch_date
),
trouvees as (
    select q.id_demande, q.motif_rejet
    from {{ ref('slv_factures_quarantaine') }} q
    cross join lot
    where q.batch_date <= lot.batch_date
)
select
    coalesce(a.id_demande, t.id_demande) as id_demande,
    a.reason as code_attendu,
    t.motif_rejet as code_trouve
from attendues a
full outer join trouvees t on t.id_demande = a.id_demande
where a.id_demande is null or t.id_demande is null or a.reason <> t.motif_rejet
