-- Une ligne par facture reçue jusqu'au lot traité, avec les 7 indicateurs de fraude.
-- L'historique sert de mémoire (F1, F5, F2) mais n'est pas contrôlé : il est déjà payé.

with params as (
    select {{ batch_date() }} as batch_date
),

-- Ordre de réception : « avant » veut dire la même chose pour F1 et F5.
factures as (
    select
        f.*,
        row_number() over (order by f.date_reception, f.id_demande) as ordre
    from {{ ref('slv_factures') }} f
    cross join params p
    where f.est_historique or f.batch_date <= p.batch_date
),

a_controler as (
    select * from factures where not est_historique
),

-- F1 : un autre équipement moins de 730 jours avant, même adhérent.
f1 as (
    select distinct a.id_demande
    from a_controler a
    join factures avant on avant.num_adherent = a.num_adherent and avant.ordre < a.ordre
    where a.date_soins - avant.date_soins between 1 and 729
),

-- F2 : seuls comptent les décomptes déjà reçus à la date du lot.
noemie_recue as (
    select distinct n.nir_hash, n.siret_opticien, n.date_soins
    from {{ ref('slv_noemie') }} n
    cross join params p
    where n.batch_date is null or n.batch_date <= p.batch_date
),

-- F5 : le même numéro de facture du même opticien, déjà présenté pour un autre adhérent.
f5 as (
    select distinct a.id_demande
    from a_controler a
    join factures avant
      on avant.siret_opticien = a.siret_opticien
     and avant.numero_facture = a.numero_facture
     and avant.num_adherent <> a.num_adherent
     and avant.ordre < a.ordre
),

regles as (
    select
        a.id_demande,
        a.batch_date,
        a.date_reception,
        a.date_soins,
        a.canal,
        a.num_adherent,
        a.nom_opticien,
        a.siret_opticien,
        a.rpps_prescripteur,
        a.classe,
        a.categorie_verres,
        a.montant_total,
        a.montant_demande_amc,
        ad.formule,
        ad.date_fin_contrat,
        coalesce(pl.plafond_eur, 800)   as plafond_eur,
        coalesce(ga.garantie_eur, 9999) as garantie_eur,

        f1.id_demande is not null as f1_renouvellement_precoce,

        -- Un décompte peut arriver 1 à 2 jours après la facture : avant ce délai, on ne conclut pas.
        case
            when a.date_reception > p.batch_date - 2 then 'EN_ATTENTE'
            when n.nir_hash is null then 'OUI'
            else 'NON'
        end as f2_statut,

        a.classe = 'B'
            and a.montant_demande_amc > least(coalesce(pl.plafond_eur, 800), coalesce(ga.garantie_eur, 9999)) + 0.01
            as f3_montant_gonfle,

        not coalesce(si.est_actif, false) as f4_opticien_fantome,
        f5.id_demande is not null as f5_facture_reutilisee,
        rp.rpps is null as f6_prescripteur_invalide,
        coalesce(a.date_soins > ad.date_fin_contrat, false) as f7_adherent_resilie

    from a_controler a
    cross join params p
    left join f1 on f1.id_demande = a.id_demande
    left join f5 on f5.id_demande = a.id_demande
    left join noemie_recue n
      on n.nir_hash = a.nir_hash and n.siret_opticien = a.siret_opticien and n.date_soins = a.date_soins
    left join {{ ref('slv_adherents') }} ad on ad.id_adherent = a.num_adherent
    left join {{ ref('slv_opticiens_sirene') }} si on si.siret = a.siret_opticien
    left join {{ ref('slv_prescripteurs_rpps') }} rp on rp.rpps = a.rpps_prescripteur
    left join {{ ref('ref_plafonds_optique') }} pl on pl.categorie_verres = a.categorie_verres
    left join {{ ref('ref_garanties_formule') }} ga on ga.formule = ad.formule
)

select
    *,
    f2_statut = 'OUI' as f2_sans_decompte_noemie
from regles
