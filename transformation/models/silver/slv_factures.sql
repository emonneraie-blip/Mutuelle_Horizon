-- Les factures exploitables : une ligne par id_demande.
select * exclude (motif_rejet)
from {{ ref('int_factures_controlees') }}
where motif_rejet is null
