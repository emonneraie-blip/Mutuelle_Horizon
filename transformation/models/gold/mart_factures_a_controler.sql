-- La liste du gestionnaire anti-fraude. Grain : une ligne par facture.
-- Score : nombre de règles déclenchées (0 à 7). Montant à risque : la part demandée à la mutuelle si score >= 1.
-- Exclusions : historique déjà payé, renvois techniques et lignes en quarantaine.

with calcul as (
    select
        *,
        f1_renouvellement_precoce::int + f2_sans_decompte_noemie::int + f3_montant_gonfle::int
            + f4_opticien_fantome::int + f5_facture_reutilisee::int + f6_prescripteur_invalide::int
            + f7_adherent_resilie::int as score
    from {{ ref('fct_factures_optique') }}
)

select
    id_demande,
    batch_date,
    date_reception,
    date_soins,
    canal,
    num_adherent,
    nom_opticien,
    '*********' || right(siret_opticien, 5) as siret_masque,   -- un vrai SIRET n'est jamais affiché à côté d'une alerte
    classe,
    categorie_verres,
    montant_demande_amc,
    f2_statut,
    score,
    trim(
        case when f1_renouvellement_precoce then 'F1 ' else '' end
        || case when f2_sans_decompte_noemie then 'F2 ' else '' end
        || case when f3_montant_gonfle then 'F3 ' else '' end
        || case when f4_opticien_fantome then 'F4 ' else '' end
        || case when f5_facture_reutilisee then 'F5 ' else '' end
        || case when f6_prescripteur_invalide then 'F6 ' else '' end
        || case when f7_adherent_resilie then 'F7 ' else '' end
    ) as regles_declenchees,
    case when score >= 1 then montant_demande_amc else 0 end as montant_a_risque,
    case
        when score >= 1 then 'A_CONTROLER'
        when f2_statut = 'EN_ATTENTE' then 'EN_ATTENTE'    -- aucune alerte, mais F2 n'est pas encore évaluée : on ne paie pas
        else 'OK'
    end as decision
from calcul
