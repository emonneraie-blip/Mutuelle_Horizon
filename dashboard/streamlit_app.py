"""Mutuelle Horizon Santé · liste du gestionnaire anti-fraude (Streamlit in Snowflake).

Déploiement : Snowsight > Projects > Streamlit > + Streamlit App, rôle TRANSFORM_ROLE, entrepôt BI_WH,
base MUTUELLE_FRAUD, schéma GOLD. Coller ce fichier. Snowflake fournit la session : aucun mot de passe ici.
Lit uniquement GOLD. Les données sont fictives et aucun vrai SIRET n'est affiché en clair.
"""
import streamlit as st
from snowflake.snowpark.context import get_active_session

MART = "MUTUELLE_FRAUD.GOLD.MART_FACTURES_A_CONTROLER"
KPI = "MUTUELLE_FRAUD.GOLD.KPI_FRAUDE_QUOTIDIEN"
REGLES = {
    "F1": "Renouvellement en moins de 2 ans",
    "F2": "Pas de décompte de la Sécurité sociale",
    "F3": "Montant au-dessus du plafond ou de la garantie",
    "F4": "Opticien inconnu ou fermé dans SIRENE",
    "F5": "Numéro de facture déjà remboursé à un autre adhérent",
    "F6": "Prescripteur absent de l'annuaire",
    "F7": "Soins après la fin du contrat",
}


@st.cache_data(ttl=60)         # 1 minute : la démo voit vite le nouveau lot, sans relancer l'entrepôt à chaque clic
def lire(sql):
    df = get_active_session().sql(sql).to_pandas()
    df.columns = [c.lower() for c in df.columns]
    return df


st.set_page_config(page_title="Contrôle anti-fraude", layout="wide")
st.title("Mutuelle Horizon Santé · factures optique à contrôler")

kpi = lire(f"SELECT * FROM {KPI} ORDER BY batch_date DESC")
if kpi.empty:
    st.warning("Aucun lot n'a encore été traité.")
    st.stop()

dernier = kpi.iloc[0]
st.caption(f"Dernier lot traité : {dernier['batch_date']} · calculé le {dernier['calcule_le']} · données fictives")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Factures du lot", f"{int(dernier['nb_factures']):,}".replace(",", " "))
c2.metric("À contrôler", int(dernier["nb_a_controler"]))
c3.metric("En attente du décompte", int(dernier["nb_en_attente"]))
c4.metric("Montant bloqué", f"{float(dernier['montant_bloque']):,.2f} €".replace(",", " "))

lots = lire(f"SELECT DISTINCT batch_date FROM {MART} ORDER BY batch_date DESC")["batch_date"].tolist()
lot = st.selectbox("Lot", lots, index=0)

liste = lire(f"""
    SELECT id_demande, date_soins, canal, nom_opticien, siret_masque, classe, categorie_verres,
           montant_demande_amc, score, regles_declenchees, montant_a_risque, f2_statut
    FROM {MART}
    WHERE decision = 'A_CONTROLER' AND batch_date = '{lot}'
    ORDER BY score DESC, montant_a_risque DESC
""")

st.subheader(f"{len(liste)} facture(s) à contrôler avant paiement")
st.dataframe(liste, use_container_width=True, hide_index=True)

if not liste.empty:
    choix = st.selectbox("Comprendre une facture", liste["id_demande"].tolist())
    facture = liste[liste["id_demande"] == choix].iloc[0]
    for code in facture["regles_declenchees"].split():
        st.write(f"**{code}** : {REGLES[code]}")

with st.expander("Les règles de fraude"):
    for code, texte in REGLES.items():
        st.write(f"**{code}** : {texte}")

st.subheader("Évolution par lot")
st.bar_chart(kpi.sort_values("batch_date").set_index("batch_date")[["nb_a_controler", "nb_en_attente"]])
