-- Le contrat de chaque adhérent. Aucune donnée d'identité : les règles n'en ont pas besoin.
select
    trim(id_adherent)                 as id_adherent,
    {{ clean_code('formule') }}       as formule,
    date_debut_contrat,
    date_fin_contrat,
    {{ clean_code('statut') }}        as statut,
    updated_at
from {{ source('bronze', 'ADHERENTS') }}
qualify row_number() over (partition by trim(id_adherent) order by updated_at desc) = 1
