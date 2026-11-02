-- Toutes les factures, typées et dédoublonnées, avec la raison du rejet s'il y en a une.
-- slv_factures garde les bonnes lignes, slv_factures_quarantaine les autres : rien n'est perdu.
{{ config(materialized='view') }}

with typees as (
    select
        trim(id_demande)                          as id_demande,
        {{ clean_code('canal') }}                 as canal,
        {{ clean_date('date_reception') }}        as date_reception,
        {{ clean_text('numero_facture') }}        as numero_facture,
        {{ clean_digits('siret_opticien') }}      as siret_opticien,
        {{ clean_text('nom_opticien') }}          as nom_opticien,
        {{ clean_digits('rpps_prescripteur') }}   as rpps_prescripteur,
        {{ clean_text('num_adherent') }}          as num_adherent,
        {{ hash_nir('nir_beneficiaire') }}        as nir_hash,
        {{ clean_date('date_soins') }}            as date_soins,
        {{ clean_code('classe') }}                as classe,
        {{ clean_code('categorie_verres') }}      as categorie_verres,
        {{ clean_amount('montant_total') }}       as montant_total,
        {{ clean_amount('montant_demande_amc') }} as montant_demande_amc,
        _batch_date                               as batch_date,
        _batch_date is null                       as est_historique,
        _source_file,
        _loaded_at
    from {{ source('bronze', 'FACTURES_OPTIQUE') }}
    -- Même id_demande deux fois = renvoi technique, pas une fraude. On garde le premier reçu.
    qualify row_number() over (partition by trim(id_demande) order by _loaded_at, _file_row) = 1
)

select
    *,
    case
        when id_demande is null then 'identifiant manquant'
        when date_soins is null then 'date de soins illisible ou impossible'
        when date_reception is null then 'date de réception illisible'
        when date_soins > date_reception then 'date de soins après la réception'
        when montant_demande_amc is null then 'montant demandé illisible'
        when montant_demande_amc < 0 or montant_total < 0 then 'montant négatif'
        when num_adherent is null then 'adhérent manquant'
        when length(siret_opticien) <> 14 then 'SIRET invalide'
        when classe not in ('A', 'B') then 'classe inconnue'
        when categorie_verres not in ('SIMPLE', 'MIXTE', 'COMPLEXE', 'TRES_COMPLEXE') then 'catégorie inconnue'
    end as motif_rejet
from typees
