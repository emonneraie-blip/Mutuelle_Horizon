-- Un SIRET vérifié par ligne. On ne garde pas la réponse brute de l'API, qui contient de vrais noms.
select
    siret,
    found,
    etat_administratif,
    found and etat_administratif = 'A' as est_actif,
    _checked_at
from {{ source('bronze', 'SIRENE_ETABLISSEMENTS') }}
qualify row_number() over (partition by siret order by _checked_at desc) = 1
