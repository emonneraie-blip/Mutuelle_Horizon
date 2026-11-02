-- Décomptes de la Sécurité sociale : on aplatit le JSON, une ligne par décompte.
select
    raw['id_decompte']::varchar                     as id_decompte,
    {{ hash_nir("raw['nir']::varchar") }}           as nir_hash,
    {{ clean_digits("raw['identifiant_ps']::varchar") }} as siret_opticien,
    {{ clean_date("raw['date_soins']::varchar") }}  as date_soins,
    {{ clean_date("raw['date_liquidation']::varchar") }} as date_liquidation,
    _batch_date                                     as batch_date,
    _source_file,
    _loaded_at
from {{ source('bronze', 'NOEMIE_DECOMPTES') }}
qualify row_number() over (partition by raw['id_decompte']::varchar order by _loaded_at, _file_row) = 1
