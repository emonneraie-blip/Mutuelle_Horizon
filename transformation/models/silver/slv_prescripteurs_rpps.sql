-- Les ophtalmologues connus de l'annuaire : un numéro RPPS par ligne, sans nom.
select distinct
    {{ clean_digits('rpps') }} as rpps
from {{ source('bronze', 'RPPS_PRESCRIPTEURS') }}
where {{ clean_digits('rpps') }} is not null
