-- Complétude : le fichier NOEMIE du lot doit être arrivé. S'il manque, dbt ne construit pas gold (incident 2).
select lot_sans_noemie
from (
    select
        {{ batch_date() }} as lot_sans_noemie,
        (select count(*) from {{ ref('slv_noemie') }} where batch_date = {{ batch_date() }}) as nb_decomptes
) controle
where nb_decomptes = 0
