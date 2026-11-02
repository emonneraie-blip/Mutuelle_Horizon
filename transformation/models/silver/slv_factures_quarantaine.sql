-- Les factures inexploitables, avec leur raison. À corriger à la source puis à recharger.
select *
from {{ ref('int_factures_controlees') }}
where motif_rejet is not null
